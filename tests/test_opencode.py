"""Tests for the OpenCode engine layer — all offline, no server, no network.

The engine is a subprocess and an HTTP API, so what is tested here is
everything bashOS decides *before* the wire: the policy it compiles, the
credential it lifts out of Claude Code, the config it projects, and the shape
of the requests it sends (against a stub transport).
"""

from __future__ import annotations

import asyncio
import json
import re

import httpx
import pytest

from bashos import events as events_mod
from bashos.opencode import auth, policy, project
from bashos.opencode import client as client_mod
from bashos.opencode import engine as engine_mod
from bashos.opencode.client import OpencodeClient, OpencodeError, split_model
from bashos.registry import find_root, load_registry

# --------------------------------------------------------------------- policy


def test_bash_is_deny_by_default_with_the_catch_all_first():
    rules = policy.bash_rules()
    # opencode resolves "last matching rule wins", so the catch-all must lead
    assert next(iter(rules.items())) == ("*", "deny")
    assert rules["uname"] == "allow"
    assert rules["uname *"] == "allow"


def test_every_probe_gets_a_bare_and_an_argument_pattern():
    rules = policy.bash_rules()
    for probe in policy.PROBE_COMMANDS:
        assert rules[probe] == "allow"
        assert rules[f"{probe} *"] == "allow"


def test_mutating_and_outbound_tools_are_denied_and_hidden():
    permission = policy.readonly_permission()
    tools = policy.readonly_tools()
    for tool in ("edit", "write", "apply_patch", "webfetch", "websearch", "task"):
        assert permission[tool] == "deny", f"{tool} must be denied"
        assert tools[tool] is False, f"{tool} must not be offered to the model"


def test_readonly_profile_cannot_escape_the_project_or_stop_to_ask():
    permission = policy.readonly_permission()
    assert permission["external_directory"] == "deny"
    assert permission["question"] == "deny"


def test_sealed_profile_offers_no_tools_at_all():
    assert set(policy.sealed_tools().values()) == {False}
    assert set(policy.sealed_tools()) == set(policy.ALL_TOOLS)
    assert policy.sealed_permission() == {"*": "deny"}


def test_policy_atoms_render_both_actions():
    atoms = policy.readonly_policy()
    assert "read=allow" in atoms
    assert "write=deny" in atoms
    assert "bash:*=deny" in atoms


# ----------------------------------------------------------------------- auth


def test_env_token_becomes_a_bearer_credential(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test")
    credential = auth.discover()
    assert credential is not None
    assert credential.access == "sk-ant-oat01-test"
    assert credential.source == "CLAUDE_CODE_OAUTH_TOKEN"
    assert credential.refreshable is False


def test_bearer_credential_gets_an_expiry_it_can_actually_use(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-test")
    blob = auth.discover().to_opencode_auth()
    assert blob["type"] == "oauth"
    assert blob["access"] == "sk-ant-oat01-test"
    # no refresh token means the engine must not try to refresh: push expiry out
    assert blob["expires"] > auth._now_ms()


def test_cli_login_credential_is_read_from_the_credentials_file(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    path = tmp_path / ".credentials.json"
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "access-abc",
                    "refreshToken": "refresh-xyz",
                    "expiresAt": 4102444800000,
                    "subscriptionType": "max",
                }
            }
        )
    )
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", path)
    credential = auth.discover()
    assert credential.access == "access-abc"
    assert credential.refreshable is True
    assert credential.to_opencode_auth() == {
        "type": "oauth",
        "access": "access-abc",
        "refresh": "refresh-xyz",
        "expires": 4102444800000,
    }


def test_env_token_wins_over_a_cli_login(monkeypatch, tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(json.dumps({"claudeAiOauth": {"accessToken": "from-file"}}))
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", path)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "from-env")
    assert auth.discover().access == "from-env"


def test_garbage_credentials_file_is_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    path = tmp_path / ".credentials.json"
    path.write_text("not json at all")
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", path)
    monkeypatch.setattr(auth, "_from_keychain", lambda: None)
    assert auth._from_credentials_file(path) is None


# ------------------------------------------------------- the credential bridge


@pytest.fixture
def no_credentials(monkeypatch, tmp_path):
    """A machine with no Claude Code login and no API key."""
    for var in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("BASHOS_OPENCODE_AUTH", raising=False)
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", tmp_path / "absent.json")
    monkeypatch.setattr(auth, "_from_keychain", lambda: None)
    return monkeypatch


def test_claude_code_oauth_is_the_default_path(no_credentials):
    no_credentials.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tok")
    env, described = auth.engine_environment()

    assert "claude code oauth" in described
    # the token travels in the child's environment, never inside the config
    assert env[auth.BEARER_ENV] == "sk-ant-oat01-tok"
    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert "sk-ant-oat01-tok" not in env["OPENCODE_CONFIG_CONTENT"]

    options = config["provider"]["anthropic"]["options"]
    # capitalised: opencode drops a lowercase `authorization` key before sending
    assert options["headers"]["Authorization"] == f"Bearer {{env:{auth.BEARER_ENV}}}"
    assert options["headers"]["anthropic-beta"] == auth.OAUTH_BETA
    # an OAuth token must never also go out as x-api-key
    assert options["apiKey"] == ""
    # declaring env is what makes opencode register the provider at all
    assert config["provider"]["anthropic"]["env"] == [auth.BEARER_ENV]


def test_api_key_is_the_fallback_and_takes_the_native_path(no_credentials):
    no_credentials.setenv("ANTHROPIC_API_KEY", "sk-ant-api-key")
    env, described = auth.engine_environment()

    assert "ANTHROPIC_API_KEY" in described
    assert "OPENCODE_CONFIG_CONTENT" not in env, "an API key needs no header wiring"
    assert json.loads(env["OPENCODE_AUTH_CONTENT"]) == {
        "anthropic": {"type": "api", "key": "sk-ant-api-key"}
    }


def test_oauth_wins_over_an_api_key(no_credentials):
    no_credentials.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tok")
    no_credentials.setenv("ANTHROPIC_API_KEY", "sk-ant-api-key")
    env, _ = auth.engine_environment()
    assert auth.BEARER_ENV in env
    assert "OPENCODE_AUTH_CONTENT" not in env


def test_no_credential_anywhere_is_reported_not_guessed(no_credentials):
    assert auth.discover() is None
    env, described = auth.engine_environment()
    assert env == {}
    assert "no credential found" in described


def test_auth_can_be_switched_off_entirely(no_credentials):
    no_credentials.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tok")
    no_credentials.setenv("BASHOS_OPENCODE_AUTH", "never")
    env, described = auth.engine_environment()
    assert env == {}
    assert "never" in described
    assert auth.attached_credential() is None


def test_attached_engines_only_accept_an_api_key(no_credentials):
    """A running server's environment is fixed — the header route is closed."""
    no_credentials.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tok")
    assert auth.attached_credential() is None
    no_credentials.setenv("ANTHROPIC_API_KEY", "sk-ant-api-key")
    assert auth.attached_credential() == ({"type": "api", "key": "sk-ant-api-key"}, "ANTHROPIC_API_KEY")


def test_the_generated_project_config_carries_no_credentials(registry):
    """Secrets belong in the child's environment, not a committed file."""
    rendered = project.render_config(registry)
    assert "provider" not in json.loads(re.sub(r"^//.*$", "", rendered, flags=re.MULTILINE))
    for marker in ("sk-ant", "Authorization", "apiKey", auth.BEARER_ENV):
        assert marker not in rendered


# -------------------------------------------------------------------- project


@pytest.fixture
def config_body(registry):
    return project.build_config(registry)


def test_model_ids_get_qualified_with_a_provider():
    assert project.qualify_model("claude-opus-5") == "anthropic/claude-opus-5"
    assert project.qualify_model("anthropic/claude-opus-5") == "anthropic/claude-opus-5"
    assert project.qualify_model("openai/gpt-5") == "openai/gpt-5"


def test_every_registry_command_reaches_the_engine(registry, config_body):
    assert set(config_body["command"]) == set(registry)
    for name, spec in registry.items():
        assert config_body["command"][name]["template"] == spec.body


def test_react_commands_land_on_the_readonly_agent(registry, config_body):
    for name, spec in registry.items():
        expected = project.READONLY_AGENT if spec.loop == "react" else project.SEALED_AGENT
        assert config_body["command"][name]["agent"] == expected


def test_policy_binds_the_agents_not_the_whole_project(config_body):
    """Plain `opencode` in this repo must stay usable for development."""
    assert "permission" not in config_body
    assert config_body["agent"][project.READONLY_AGENT]["permission"]["bash"]["*"] == "deny"
    assert config_body["agent"][project.SEALED_AGENT]["permission"] == {"*": "deny"}


def test_generated_config_is_parseable_jsonc(registry):
    rendered = project.render_config(registry)
    assert rendered.startswith("// generated by `bashos opencode sync`")
    body = json.loads(re.sub(r"^//.*$", "", rendered, flags=re.MULTILINE))
    assert body["$schema"] == project.SCHEMA_URL
    assert set(body["agent"]) == {project.READONLY_AGENT, project.SEALED_AGENT}


def test_render_is_deterministic(registry):
    assert project.render_config(registry) == project.render_config(registry)


def test_checked_in_config_matches_the_registry():
    """`opencode.jsonc` is generated — regenerate it with `bashos opencode sync`."""
    root = find_root()
    assert project.is_in_sync(root, load_registry(root)), (
        f"{project.CONFIG_FILE} is stale — run `bashos opencode sync` and commit it"
    )


# --------------------------------------------------------------------- client


def _stub_client(handler, **kwargs) -> OpencodeClient:
    client = OpencodeClient("http://engine.test", **kwargs)
    client._http = httpx.AsyncClient(
        base_url="http://engine.test", transport=httpx.MockTransport(handler)
    )
    return client


def test_model_ids_split_into_provider_and_name():
    assert split_model("anthropic/claude-opus-5") == ("anthropic", "claude-opus-5")
    assert split_model("claude-opus-5") is None


async def test_prompt_sends_agent_system_and_qualified_model():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "info": {"modelID": "claude-opus-5"},
                "parts": [{"type": "text", "text": "the answer"}],
            },
        )

    client = _stub_client(handler, directory="/work")
    result = await client.prompt(
        "ses_1", "do it", agent="bashos", system="house rules", model="anthropic/claude-opus-5"
    )
    await client.aclose()

    assert result.text == "the answer"
    assert result.failed is False
    assert seen["body"]["parts"] == [{"type": "text", "text": "do it"}]
    assert seen["body"]["agent"] == "bashos"
    assert seen["body"]["system"] == "house rules"
    assert seen["body"]["model"] == {"providerID": "anthropic", "modelID": "claude-opus-5"}
    # the engine serves many projects — every call names ours
    assert "directory=%2Fwork" in seen["url"] or "directory=/work" in seen["url"]


async def test_prompt_collects_tool_calls_and_skips_synthetic_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {},
                "parts": [
                    {"type": "text", "text": "ignore me", "synthetic": True},
                    {
                        "type": "tool",
                        "callID": "call_1",
                        "tool": "bash",
                        "state": {"status": "completed", "input": {"command": "uname -a"}},
                    },
                    {"type": "text", "text": "Linux."},
                ],
            },
        )

    client = _stub_client(handler)
    result = await client.prompt("ses_1", "what os")
    await client.aclose()

    assert result.text == "Linux."
    assert [call.tool for call in result.tool_calls] == ["bash"]
    assert result.tool_calls[0].describe() == "bash(uname -a)"


async def test_provider_errors_surface_as_a_failed_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {
                    "error": {
                        "name": "ProviderAuthError",
                        "data": {"message": "no credential for anthropic"},
                    }
                },
                "parts": [],
            },
        )

    client = _stub_client(handler)
    result = await client.prompt("ses_1", "hello")
    await client.aclose()

    assert result.failed
    assert "no credential for anthropic" in result.error


async def test_http_errors_name_the_engine_and_the_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="engine is restarting")

    client = _stub_client(handler)
    with pytest.raises(OpencodeError, match="503"):
        await client.health()
    await client.aclose()


async def test_session_creation_requires_an_id_back():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"title": "no id here"})

    client = _stub_client(handler)
    with pytest.raises(OpencodeError, match="no id"):
        await client.create_session(title="t")
    await client.aclose()


# --------------------------------------------------------------------- engine


class _StubClient:
    """A client whose event stream is scripted, recording what got answered."""

    def __init__(self, events: list[dict]):
        self._events = events
        self.rejected: list[tuple[str, str]] = []
        self.rejected_v2: list[str] = []

    async def events(self):
        for event in self._events:
            yield event

    async def reject_permission(self, session_id, permission_id):
        self.rejected.append((session_id, permission_id))

    async def reject_permission_v2(self, request_id, message):
        self.rejected_v2.append(request_id)


def _tool_event(session, call_id, tool, command, status="running"):
    return {
        "type": "message.part.updated",
        "properties": {
            "sessionID": session,
            "part": {
                "type": "tool",
                "callID": call_id,
                "tool": tool,
                "state": {"status": status, "input": {"command": command}},
            },
        },
    }


async def _watch_with(evts: list[dict], session="ses_1"):
    """Drive the pure watch loop through the legacy string adapter — the
    string assertions below are the historical output contract."""
    stub = _StubClient(evts)
    seen: list[str] = []
    live = asyncio.Event()
    await engine_mod.watch_events(
        stub.events(), session, events_mod.to_legacy(seen.append), live, stub
    )
    return stub, seen, live


async def test_watcher_reports_each_tool_call_once():
    stub, seen, live = await _watch_with(
        [
            _tool_event("ses_1", "c1", "bash", "uname -a"),
            _tool_event("ses_1", "c1", "bash", "uname -a", status="completed"),
            _tool_event("ses_1", "c2", "read", "x"),
        ]
    )
    assert seen == ["bash(uname -a)", "read(x)"]
    assert live.is_set()


async def test_watcher_ignores_other_sessions_on_the_same_engine():
    _, seen, _ = await _watch_with([_tool_event("ses_OTHER", "c1", "bash", "rm -rf /")])
    assert seen == []


async def test_watcher_rejects_approval_requests_instead_of_hanging():
    """A rule that resolves to "ask" must be answered — nobody is watching."""
    stub, seen, _ = await _watch_with(
        [
            {
                "type": "permission.asked",
                "properties": {"sessionID": "ses_1", "id": "per_1", "permission": "bash"},
            },
            {
                "type": "permission.v2.asked",
                "properties": {"sessionID": "ses_1", "id": "per_2", "action": "edit"},
            },
        ]
    )
    assert stub.rejected == [("ses_1", "per_1")]
    assert stub.rejected_v2 == ["per_2"]
    assert seen == ["denied by policy: bash", "denied by policy: edit"]


async def test_broken_event_stream_never_wedges_the_prompt():
    class Exploding(_StubClient):
        async def events(self):
            raise RuntimeError("stream died")
            yield  # pragma: no cover - generator marker

    live = asyncio.Event()
    await engine_mod.watch_events(Exploding([]).events(), "ses_1", None, live, None)
    assert live.is_set(), "a dead stream must release the prompt, not block it"


# --------------------------------------------------------------- typed events


async def _typed_watch(evts: list[dict], session="ses_1"):
    stub = _StubClient(evts)
    typed: list = []
    live = asyncio.Event()
    await engine_mod.watch_events(stub.events(), session, typed.append, live, stub)
    return stub, typed


async def test_watch_emits_typed_tool_events_with_status_transitions():
    _, typed = await _typed_watch(
        [
            _tool_event("ses_1", "c1", "bash", "uname -a"),
            _tool_event("ses_1", "c1", "bash", "uname -a", status="completed"),
        ]
    )
    tools = [e for e in typed if isinstance(e, events_mod.ToolEvent)]
    assert [e.status for e in tools] == ["running", "completed"]
    assert tools[0].duration_ms is None
    assert tools[1].duration_ms is not None
    assert tools[1].description == "bash(uname -a)"
    assert tools[1].session_id == "ses_1"


async def test_watch_emits_a_typed_permission_event_on_auto_refusal():
    _, typed = await _typed_watch(
        [
            {
                "type": "permission.v2.asked",
                "properties": {"sessionID": "ses_1", "id": "per_9", "action": "edit"},
            }
        ]
    )
    perms = [e for e in typed if isinstance(e, events_mod.PermissionEvent)]
    assert len(perms) == 1
    assert perms[0].decision == "auto-rejected"
    assert perms[0].action == "edit"
    assert perms[0].protocol == "v2"


def test_legacy_adapter_dedupes_and_drops_pending():
    lines: list[str] = []
    sink = events_mod.to_legacy(lines.append)
    tool = dict(session_id="s", tool="bash", title="", input={}, description="bash(x)")
    sink(events_mod.ToolEvent(call_id="c1", status="pending", **tool))
    sink(events_mod.ToolEvent(call_id="c1", status="running", **tool))
    sink(events_mod.ToolEvent(call_id="c1", status="completed", **tool))
    sink(events_mod.LifecycleEvent(session_id="s", phase="prompt.finished"))
    assert lines == ["bash(x)"]


# --------------------------------------------------------------- typed errors


async def test_http_401_raises_engine_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad password")

    client = _stub_client(handler)
    with pytest.raises(client_mod.EngineAuthError) as excinfo:
        await client.health()
    await client.aclose()
    assert isinstance(excinfo.value, client_mod.EngineHTTPError)
    assert isinstance(excinfo.value, OpencodeError)
    assert excinfo.value.status == 401


async def test_transport_failure_raises_engine_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = _stub_client(handler)
    with pytest.raises(client_mod.EngineUnreachable, match="engine unreachable"):
        await client.health()
    await client.aclose()


async def test_aborted_run_is_an_outcome_not_a_failure_type():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {"error": {"name": "MessageAbortedError", "data": {"message": "aborted"}}},
                "parts": [],
            },
        )

    client = _stub_client(handler)
    result = await client.prompt("ses_1", "hello")
    await client.aclose()
    assert result.failed
    assert result.aborted
    assert client_mod.classify_result_error({"name": "MessageAbortedError"}) == "aborted"
    assert client_mod.classify_result_error({"name": "ProviderAuthError"}) == "auth"
    assert client_mod.classify_result_error({"name": "SomethingElse"}) == "provider"


def test_tool_descriptions_are_one_line_and_bounded():
    from bashos.opencode.client import read_tool_part

    call = read_tool_part(
        {
            "tool": "grep",
            "callID": "c1",
            "state": {"status": "running", "input": {"pattern": "a" * 200}},
        }
    )
    described = call.describe()
    assert "\n" not in described
    assert len(described) <= 100
    assert described.startswith("grep(")


async def test_react_renders_a_user_abort_as_stopped_not_error(registry, monkeypatch):
    from bashos.config import KernelConfig
    from bashos.loops.react import make_react_node

    class _Engine:
        async def act(self, *args, **kwargs):
            return client_mod.PromptResult(
                text="", tool_calls=[], error="aborted", error_name="MessageAbortedError"
            )

    async def fake_get_engine(config):
        return _Engine()

    monkeypatch.setattr(engine_mod, "get_engine", fake_get_engine)
    node = make_react_node(registry, KernelConfig())
    result = await node({"command": "sys", "args": "why is it slow", "trace": []})
    assert result["output"] == "stopped."
    assert result.get("route") != "error"
