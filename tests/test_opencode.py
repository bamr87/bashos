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
from bashos.opencode import auth, policy, project, rules
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
    bash = policy.bash_rules()
    for probe in policy.PROBE_COMMANDS:
        assert bash[probe] == "allow"
        assert bash[f"{probe} *"] == "allow"


# Programs whose job is to run another program. One of them on the allowlist turns
# "read-only probes" into "any command" (hard rule 2): `env curl …` once got through.
COMMAND_RUNNERS = {
    "env", "xargs", "sh", "bash", "zsh", "dash", "exec", "eval", "nohup", "timeout", "nice",
    "ionice", "sudo", "doas", "su", "watch", "time", "strace", "ltrace", "find", "awk", "sed",
    "perl", "python", "python3", "node", "ruby", "ssh", "script", "setsid", "stdbuf", "chroot",
    "nsenter", "unshare", "flock", "parallel", "busybox", "make", "npx", "uvx",
}


def test_no_probe_can_run_another_program():
    for probe in policy.PROBE_COMMANDS:
        assert probe.split()[0].rsplit("/", 1)[-1] not in COMMAND_RUNNERS, probe


def _bash(command: str) -> str:
    return rules.evaluate(rules.from_config({"bash": policy.bash_rules()}), "bash", command)


@pytest.mark.parametrize("command", [
    "env", "env curl https://example.com", "rm -rf /", "curl https://example.com", "sh -c id",
    "tmux display-message -p '#(curl https://example.com)'", "tmux capture-pane -p -T '#(id)'",
    "git log --output=/tmp/out", "git log -1 --output /tmp/out", "git -c core.pager=id log",
])
def test_ways_out_of_the_allowlist_are_denied(command):
    assert _bash(command) == "deny"


@pytest.mark.parametrize("command", [
    "uname", "uname -a", "git log -3 --oneline", "git status --short", "ps aux",
    "tmux display-message -p '#{session_name}'", "tmux has-session -t console", "bin/os-health",
])
def test_the_probes_still_run(command):
    assert _bash(command) == "allow"


def test_rules_mirror_opencodes_wildcard():
    assert rules.wildcard("ls", "ls *") and rules.wildcard("ls -la", "ls *")
    assert not rules.wildcard("lsblk", "ls *")
    assert rules.wildcard("a/b c", "*") and rules.wildcard("x.y", "x?y") and not rules.wildcard("x.y", "x.z")
    assert rules.wildcard("tmux list-x #(id)", "tmux *#(*")
    # last match wins; nothing matching falls back to the default
    ordered = [("bash", "*", "deny"), ("bash", "ls *", "allow")]
    assert rules.evaluate(ordered, "bash", "ls") == "allow"
    assert rules.evaluate(ordered, "bash", "rm") == "deny"
    assert rules.evaluate(ordered, "edit", "x") == "ask"


def test_mutating_and_outbound_tools_are_denied_and_hidden():
    permission = policy.readonly_permission()
    tools = policy.readonly_tools()
    for tool in ("edit", "write", "apply_patch", "webfetch", "websearch", "execute", "task"):
        assert permission[tool] == "deny", f"{tool} must be denied"
        assert tools[tool] is False, f"{tool} must not be offered to the model"


def test_a_tool_the_policy_never_named_is_refused_first():
    """Engines add tools (OpenCode 2's `execute` can fetch): the catch-all must resolve before
    every allow, and engines place the `tools` map's keys first, so it leads both blocks."""
    assert next(iter(policy.readonly_tools().items())) == ("*", False)
    assert next(iter(policy.readonly_permission().items())) == ("*", "deny")
    assert policy.readonly_policy()[0] == "*=deny"
    assert rules.evaluate(rules.from_config(policy.readonly_permission()), "execute", "x") == "deny"


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
    assert project.qualify_model("claude-opus-5-5") == "anthropic/claude-opus-5-5"
    assert project.qualify_model("anthropic/claude-opus-5-5") == "anthropic/claude-opus-5-5"
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
    assert split_model("anthropic/claude-opus-5-5") == ("anthropic", "claude-opus-5-5")
    assert split_model("claude-opus-5-5") is None


async def test_prompt_sends_agent_system_and_qualified_model():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "info": {"modelID": "claude-opus-5-5"},
                "parts": [{"type": "text", "text": "the answer"}],
            },
        )

    client = _stub_client(handler, directory="/work")
    result = await client.prompt(
        "ses_1", "do it", agent="bashos", system="house rules", model="anthropic/claude-opus-5-5"
    )
    await client.aclose()

    assert result.text == "the answer"
    assert result.failed is False
    assert seen["body"]["parts"] == [{"type": "text", "text": "do it"}]
    assert seen["body"]["agent"] == "bashos"
    assert seen["body"]["system"] == "house rules"
    assert seen["body"]["model"] == {"providerID": "anthropic", "modelID": "claude-opus-5-5"}
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

    async def reject_permission(self, session_id, permission_id, message=""):
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


# ------------------------------------------------------------ OpenCode 2 (#71)

FIXTURES = find_root() / "tests" / "fixtures"
SPA = "<!doctype html><html><body><div id='root'></div></body></html>"


def _timeline() -> list[dict]:
    """A real 2.0.20 turn (tests/fixtures/opencode-2.0.20-messages.json), oldest first."""
    return json.loads((FIXTURES / "opencode-2.0.20-messages.json").read_text())


class _V2Engine:
    """Just enough of OpenCode 2's /api — and, like the real one, the web UI everywhere else."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.timeline = _timeline()
        self.user_id = next(m["id"] for m in self.timeline if m["type"] == "user")
        self.agents = json.loads((FIXTURES / "opencode-2.0.20-agents.json").read_text())

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        self.calls.append((method, path, body))
        if not path.startswith("/api/"):
            return httpx.Response(200, text=SPA, headers={"content-type": "text/html"})
        if (method, path) == ("POST", "/api/session/ses_1/prompt") and "text" not in (body or {}):
            # what 2.0.20 answers a prompt with no text (measured), before admitting anything
            return httpx.Response(400, json={"_tag": "InvalidRequestError", "kind": "Payload",
                                             "message": 'Missing key\n  at ["text"]'})
        routes = {
            ("GET", "/api/info"): lambda: {"version": "2.0.20", "pid": 1, "urls": [], "paths": {"tmp": "/tmp"}},
            ("GET", "/api/agent"): lambda: {"location": {"directory": "/work"}, "data": self.agents},
            ("POST", "/api/session"): lambda: {"data": {"id": "ses_1", "agent": (body or {}).get("agent")}},
            ("POST", "/api/session/ses_1/prompt"): lambda: {"data": {"id": self.user_id, "type": "user"}},
            ("GET", "/api/session/ses_1/message"): lambda: {"data": self.timeline[::-1], "cursor": {}},
        }
        if (method, path) in routes:
            return httpx.Response(200, json=routes[(method, path)]())
        if method in ("POST", "PUT", "DELETE") and path.startswith("/api/"):
            return httpx.Response(204)
        return httpx.Response(404, json={"_tag": "NotFound"})


async def test_an_engine_that_serves_only_api_routes_is_driven_end_to_end():
    """OpenCode 2 moved every route under /api; the old paths answer with its web UI's HTML."""
    engine = _V2Engine()
    client = _stub_client(engine, directory="/work", major=2)

    assert (await client.health())["version"] == "2.0.20"
    assert {a["id"] for a in await client.agents()} == {"bashos", "bashos-sealed"}
    session = await client.create_session(title="t", agent="bashos")
    result = await client.prompt(session, "inspect this machine", agent="bashos",
                                 model="anthropic/claude-opus-5-5", system="house rules")
    await client.reject_permission(session, "per_1", "Denied by bashOS policy")
    await client.aclose()

    assert session == "ses_1"
    assert result.failed is False and result.text == "hello from the mock"
    assert [(c.tool, c.status) for c in result.tool_calls] == [
        ("shell", "completed"), ("shell", "error"), ("read", "completed")]
    assert result.tool_calls[0].describe() == "shell(uname -a)"
    sent = {(m, p): b for m, p, b in engine.calls}
    assert sent[("POST", "/api/session")]["location"] == {"directory": "/work"}
    assert sent[("POST", "/api/session/ses_1/prompt")] == {"text": "inspect this machine"}
    # OpenCode 2 keeps the model and the system prompt on the session, not on the prompt
    assert sent[("POST", "/api/session/ses_1/model")] == {"model": {"providerID": "anthropic", "id": "claude-opus-5-5"}}
    assert sent[("PUT", "/api/experimental/session/ses_1/instructions/entries/bashos.system")] == {"value": "house rules"}
    assert ("POST", "/api/session/ses_1/agent") not in sent  # created with that agent already
    assert sent[("POST", "/api/session/ses_1/permission/per_1/reply")] == {
        "decision": "reject", "message": "Denied by bashOS policy"}
    assert all(p.startswith("/api/") for _, p, _ in engine.calls)


async def test_an_opencode_1_client_cannot_drive_an_opencode_2_engine():
    """What main did against 2.x: /global/health is the web UI, so health() gets HTML."""
    client = _stub_client(_V2Engine())
    with pytest.raises(OpencodeError, match="non-JSON"):
        await client.health()
    await client.aclose()


async def test_an_attached_engine_s_major_is_probed_from_its_routes():
    v2_client = _stub_client(_V2Engine())
    assert await v2_client.detect() == 2 and v2_client.major == 2
    assert await v2_client.version() == "2.0.20"
    await v2_client.aclose()

    v1_client = _stub_client(lambda r: httpx.Response(200, json={"healthy": True, "version": "1.19.5"}))
    assert await v1_client.detect() == 1
    await v1_client.aclose()

    locked = _stub_client(lambda r: httpx.Response(401, text="bad password"))
    with pytest.raises(client_mod.EngineAuthError):
        await locked.detect()  # a wrong password is not a reason to guess another major
    await locked.aclose()


async def test_a_session_is_told_only_what_changed():
    engine = _V2Engine()
    client = _stub_client(engine, major=2)
    session = await client.create_session(title="t", agent="bashos")
    for _ in range(2):
        await client.prompt(session, "again", agent="bashos", model="anthropic/claude-opus-5-5", system="rules")
    await client.prompt(session, "plain", agent="bashos-sealed", model="anthropic/claude-opus-5-5")
    await client.aclose()
    sent = [(m, p) for m, p, _ in engine.calls]
    assert sent.count(("POST", "/api/session/ses_1/model")) == 1
    assert sent.count(("PUT", "/api/experimental/session/ses_1/instructions/entries/bashos.system")) == 1
    # a prompt without a system prompt removes the one an earlier prompt left on the session
    assert sent.count(("DELETE", "/api/experimental/session/ses_1/instructions/entries/bashos.system")) == 1
    assert sent.count(("POST", "/api/session/ses_1/agent")) == 1


async def test_a_turn_that_has_not_reached_idle_is_waited_for():
    engine = _V2Engine()
    finished = engine.timeline
    engine.timeline = [m for m in finished if m["type"] != "idle"]  # admitted, still running
    client = _stub_client(engine, major=2)

    async def finish_later():
        await asyncio.sleep(0.3)
        engine.timeline = finished

    task = asyncio.create_task(finish_later())
    result = await client.prompt("ses_1", "inspect")
    await task
    await client.aclose()
    assert result.text == "hello from the mock"
    assert len([c for c in engine.calls if c[1].endswith("/wait")]) >= 2


def test_an_opencode_2_turn_reads_like_an_opencode_1_message():
    from bashos.opencode import v2

    timeline = _timeline()
    user = next(m["id"] for m in timeline if m["type"] == "user")
    payload = v2.message_payload(timeline, user)
    assert payload is not None and payload["info"]["modelID"] == "m"
    assert v2.message_payload([m for m in timeline if m["type"] != "idle"], user) is None  # still running

    failed = [{"id": "u", "type": "user"},
              {"id": "a", "type": "assistant", "model": {"id": "claude-opus-5-5"}, "content": [],
               "error": {"type": "provider.auth", "message": "no credential"}},
              {"id": "i", "type": "idle", "outcome": "failed"}]
    result = client_mod._read_message(v2.message_payload(failed, "u"))
    assert result.failed and result.error == "no credential"
    assert client_mod.classify_result_error({"name": result.error_name}) == "auth"
    stopped = [{"id": "u", "type": "user"}, {"id": "i", "type": "idle", "outcome": "interrupted"}]
    assert client_mod._read_message(v2.message_payload(stopped, "u")).aborted


async def test_opencode_2_events_drive_the_same_watcher():
    """A real 2.0.20 event stream, normalized, gives the typed events OpenCode 1's did."""
    from bashos.opencode import v2

    frames = json.loads((FIXTURES / "opencode-2.0.20-events.json").read_text())
    session = next(f["data"]["sessionID"] for f in frames if f["type"] == "session.created")
    normalize = v2.EventNormalizer()
    # the turn, then an approval request as 2.0.20 sends one for a rule that resolves to "ask"
    frames.append({"type": "permission.asked", "data": {
        "id": "per_1", "sessionID": session, "action": "external_directory", "resources": ["/etc/hosts"]}})
    events = [e for e in (normalize(f) for f in frames) if e is not None]

    stub, typed = await _typed_watch(events, session=session)
    tools = [e for e in typed if isinstance(e, events_mod.ToolEvent)]
    assert [(e.tool, e.status) for e in tools if e.status in ("completed", "error")] == [
        ("shell", "completed"), ("shell", "error"), ("read", "completed")]
    assert tools[-1].description == "read(opencode.jsonc)"
    text = "".join(e.text for e in typed if isinstance(e, events_mod.TextDelta))
    assert text == "hello from the mock"
    perms = [e for e in typed if isinstance(e, events_mod.PermissionEvent)]
    assert stub.rejected == [(session, "per_1")] and perms[0].action == "external_directory"


async def test_providers_and_an_attached_api_key_on_opencode_2():
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == "/api/provider":
            return httpx.Response(200, json={"data": [
                {"id": "anthropic", "activation": "enabled"}, {"id": "other", "activation": "disabled"}]})
        return httpx.Response(200, json={"data": {"id": "cred_1"}})

    client = _stub_client(handler, major=2)
    assert await client.connected_providers() == ["anthropic"]
    await client.set_auth("anthropic", {"type": "api", "key": "sk-ant-api-key"})
    with pytest.raises(OpencodeError, match="API key"):
        await client.set_auth("anthropic", {"type": "oauth", "access": "x"})
    await client.aclose()
    assert seen[-1] == ("POST", "/api/credential", {
        "integrationID": "anthropic", "value": {"type": "key", "key": "sk-ant-api-key"}})


def test_the_oauth_bridge_never_sends_the_token_as_an_api_key_on_opencode_2(no_credentials):
    """2.0.20 sends a provider's declared `env` as x-api-key, so 2.x gets the header alone."""
    no_credentials.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat01-tok")
    env, _ = auth.engine_environment(2)
    provider = json.loads(env["OPENCODE_CONFIG_CONTENT"])["provider"]["anthropic"]
    assert "env" not in provider
    assert provider["options"]["headers"]["Authorization"] == f"Bearer {{env:{auth.BEARER_ENV}}}"
    assert provider["options"]["apiKey"] == ""
    assert env[auth.BEARER_ENV] == "sk-ant-oat01-tok" and "sk-ant-oat01-tok" not in env["OPENCODE_CONFIG_CONTENT"]


def test_an_api_key_reaches_opencode_2_through_its_own_variable(no_credentials):
    """2.0.20 ignores OPENCODE_AUTH_CONTENT; the provider reads the key from bashOS's variable."""
    no_credentials.setenv("ANTHROPIC_API_KEY", "sk-ant-api-key")
    env, described = auth.engine_environment(2)
    assert "ANTHROPIC_API_KEY" in described and "OPENCODE_AUTH_CONTENT" not in env
    assert env[auth.API_KEY_ENV] == "sk-ant-api-key"
    config = env["OPENCODE_CONFIG_CONTENT"]
    assert "sk-ant-api-key" not in config
    assert json.loads(config)["provider"]["anthropic"]["options"]["apiKey"] == f"{{env:{auth.API_KEY_ENV}}}"


# ------------------------------------------------- the session routes verify drives (#71)

ENTRY = "/api/experimental/session/ses_1/instructions/entries/bashos.system"


def _one_frame_events():
    async def events():
        yield {"type": "server.connected", "properties": {}}
    return events


async def test_verify_drives_the_session_routes_a_turn_uses_without_running_one():
    """Two of them sit under 2.x's /api/experimental. The policy checks alone would pass a
    release that moved them, and every turn would then fail."""
    from bashos.opencode import contract

    engine = _V2Engine()
    client = _stub_client(engine, major=2)
    client.events = _one_frame_events()
    findings = await contract.session_routes(client, "anthropic/claude-opus-5-5")
    await client.aclose()

    assert [f.name for f in findings] == [contract.ROUTES_FINDING] and contract.passed(findings), findings
    sent = [(m, p) for m, p, _ in engine.calls]
    for route in (("POST", "/api/session/ses_1/agent"), ("POST", "/api/session/ses_1/model"),
                  ("PUT", ENTRY), ("DELETE", ENTRY), ("POST", "/api/experimental/session/ses_1/wait"),
                  ("GET", "/api/session/ses_1/message"), ("DELETE", "/api/session/ses_1")):
        assert route in sent, route
    # the prompt route is proven with a body it must refuse: no turn is admitted
    assert [b for _, p, b in engine.calls if p.endswith("/prompt")] == [{}]


async def test_a_release_that_moved_a_session_route_fails_verify():
    from bashos.opencode import contract

    engine = _V2Engine()

    def moved(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wait") or "/instructions/" in request.url.path:
            return httpx.Response(404)  # what 2.0.20 answers on a path it does not serve
        return engine(request)

    client = _stub_client(moved, major=2)
    client.events = _one_frame_events()
    [finding] = await contract.session_routes(client, "anthropic/claude-opus-5-5")
    await client.aclose()
    assert not finding.ok
    for name in ("system prompt put (", "system prompt delete (", "wait ("):
        assert name in finding.detail, finding.detail
    assert "agent (" not in finding.detail and "events (" not in finding.detail
    assert ("DELETE", "/api/session/ses_1") in [(m, p) for m, p, _ in engine.calls]  # no session left behind


async def test_a_silent_event_stream_or_an_admitted_empty_prompt_fails_verify(monkeypatch):
    from bashos.opencode import contract

    monkeypatch.setattr(contract, "ROUTE_TIMEOUT", 0.2)
    engine = _V2Engine()

    def admits_anything(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/prompt"):
            return httpx.Response(200, json={"data": {"id": "msg_1", "type": "user"}})
        return engine(request)

    async def silent():
        await asyncio.sleep(5)
        yield {}

    client = _stub_client(admits_anything, major=2)
    client.events = silent
    [finding] = await contract.session_routes(client, "anthropic/claude-opus-5-5")
    await client.aclose()
    assert not finding.ok
    assert "events (timed out)" in finding.detail
    assert "prompt (the engine admitted a prompt with no text)" in finding.detail
    assert ("POST", "/api/session/ses_1/interrupt") in [(m, p) for m, p, _ in engine.calls]


async def test_opencode_1_takes_all_of_it_on_the_prompt_so_there_are_no_session_routes():
    from bashos.opencode import contract

    class Engine:
        major = 1

    assert await contract.session_routes(Engine(), "anthropic/claude-opus-5-5") == []
    client = _stub_client(lambda r: httpx.Response(404))
    with pytest.raises(OpencodeError, match="no `wait` session route"):
        await client.wait_idle("ses_1")
    await client.aclose()

