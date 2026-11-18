"""The engine contract: does an engine still enforce policy.py, judged from what it resolved?

The fixtures are real engines' resolved bashOS agents — OpenCode 1.19.5's `GET /agent` and
OpenCode 2.0.20's `GET /api/agent`, each booted on this repo's opencode.jsonc (rules naming
paths that only exist on the capturing machine dropped) — so the contract is tested against
each engine's format, not ours. Offline: no engine, no network.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import stat
from pathlib import Path

import pytest

from bashos.opencode import contract, rules, server
from bashos.opencode.client import OpencodeError

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "opencode-1.19.5-agents.json"
FIXTURE_V2 = FIXTURES / "opencode-2.0.20-agents.json"


@pytest.fixture
def agents() -> list[dict]:
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def agents_v2() -> list[dict]:
    return json.loads(FIXTURE_V2.read_text())


def _failed(findings: list[contract.Finding]) -> set[str]:
    return {f.name for f in findings if not f.ok}


def _agent(agents: list[dict], name: str) -> dict:
    return next(a for a in agents if a["name"] == name)


def test_a_real_engine_enforces_the_policy(agents):
    findings = contract.check(agents)
    assert contract.passed(findings), [f for f in findings if not f.ok]


def test_a_reopened_escape_fails_the_contract(agents):
    _agent(agents, "bashos")["permission"].append({"permission": "bash", "pattern": "env *", "action": "allow"})
    assert _failed(contract.check(agents)) == {"readonly: bash deny-by-default"}


def test_a_denied_tool_allowed_again_fails_the_contract(agents):
    _agent(agents, "bashos")["permission"].append({"permission": "edit", "pattern": "*", "action": "allow"})
    assert "readonly: denied tools" in _failed(contract.check(agents))


def test_a_sealed_agent_with_a_tool_fails_the_contract(agents):
    _agent(agents, "bashos-sealed")["permission"].append({"permission": "bash", "pattern": "*", "action": "allow"})
    assert _failed(contract.check(agents)) == {"sealed: no tools"}


def test_a_lost_probe_fails_the_contract(agents):
    # functional, not safety: a release that stopped honouring the allowlist breaks /sys
    _agent(agents, "bashos")["permission"].append({"permission": "bash", "pattern": "uname *", "action": "deny"})
    assert _failed(contract.check(agents)) == {"readonly: probes run"}


def test_a_missing_agent_or_an_unknown_shape_is_a_failure_not_a_pass(agents):
    assert "agents" in _failed(contract.check([a for a in agents if a["name"] != "bashos-sealed"]))
    reshaped = copy.deepcopy(agents)
    for a in reshaped:
        a["permission"] = {"bash": {"*": "deny"}}  # a config-shaped block: not what /agent reports
    assert {"readonly: rules", "sealed: no tools"} <= _failed(contract.check(reshaped))


# ---------------------------------------------------------------- which engine bashOS runs


def _exe(path: Path, version: str) -> Path:
    path.write_text(f"#!/bin/sh\necho '{version}'\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_the_pinned_binary_then_the_managed_engine_then_path(tmp_path, monkeypatch):
    pinned, managed, on_path = (_exe(tmp_path / n, "1.19.5") for n in ("pinned", "managed", "opencode"))
    record = tmp_path / "record"
    record.write_text(f"{managed}\n")
    monkeypatch.setattr(server, "MANAGED_RECORD", record)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("BASHOS_OPENCODE_BIN", str(pinned))
    assert server.find_binary() == str(pinned)
    assert server.binary_source(str(pinned)) == "BASHOS_OPENCODE_BIN"
    monkeypatch.delenv("BASHOS_OPENCODE_BIN")
    assert server.find_binary() == str(managed)  # a bashOS machine: the managed copy beats PATH
    assert server.binary_source(str(managed)) == "managed by bashOS"
    record.write_text("/nonexistent/opencode\n")
    assert server.find_binary() == str(on_path)
    assert server.binary_source(str(on_path)) == "PATH"


async def test_a_major_bashos_does_not_speak_is_named_not_crashed_on(tmp_path, monkeypatch):
    monkeypatch.delenv("BASHOS_OPENCODE_BIN", raising=False)
    v3 = _exe(tmp_path / "opencode3", "opencode v3.0.0")
    with pytest.raises(OpencodeError) as caught:
        await server.spawn(directory=str(tmp_path), binary=str(v3))
    message = str(caught.value)
    assert "opencode 3.0.0" in message and "OpenCode 1 and 2" in message and "BASHOS_OPENCODE_BIN" in message


@pytest.mark.parametrize(("version", "level"), [("opencode v2.0.20", "info"), ("1.19.5", "INFO")])
async def test_the_engine_starts_with_the_log_level_its_major_accepts(tmp_path, monkeypatch, version, level):
    """OpenCode 2 rejects `--log-level INFO` and refuses to start; OpenCode 1 takes only that."""
    monkeypatch.delenv("BASHOS_OPENCODE_BIN", raising=False)
    exe = _exe(tmp_path / "opencode", version)
    seen: dict[str, tuple[str, ...]] = {}
    real_exec = asyncio.create_subprocess_exec

    async def spawn_exec(*argv, **kwargs):
        if argv[1:] == ("--version",):
            return await real_exec(*argv, **kwargs)
        seen["argv"] = argv
        raise OSError("the serve process is not needed past its argv")

    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", spawn_exec)
    with pytest.raises(OSError):
        await server.spawn(directory=str(tmp_path), binary=str(exe))
    argv = list(seen["argv"])
    assert argv[:2] == [str(exe), "serve"] and argv[argv.index("--log-level") + 1] == level
    assert argv[argv.index("--hostname") + 1] == "127.0.0.1"


def test_doctor_names_the_api_and_flags_an_unsupported_engine(tmp_path, monkeypatch):
    from bashos.runtime import auth as runtime_auth

    monkeypatch.delenv("BASHOS_OPENCODE_URL", raising=False)
    monkeypatch.setenv("BASHOS_OPENCODE_BIN", str(_exe(tmp_path / "opencode3", "opencode v3.0.0")))
    check = runtime_auth._engine_check()
    assert not check.ok and "OpenCode 1 and 2" in check.detail
    for name, version, api in (("opencode2", "opencode v2.0.20", "OpenCode 2 API"), ("opencode1", "1.19.5", "OpenCode 1 API")):
        monkeypatch.setenv("BASHOS_OPENCODE_BIN", str(_exe(tmp_path / name, version)))
        check = runtime_auth._engine_check()
        assert check.ok and api in check.detail and "BASHOS_OPENCODE_BIN" in check.detail


# ---------------------------------------------------------------- OpenCode 2


def test_a_real_opencode_2_engine_enforces_the_policy(agents_v2):
    findings = contract.check(agents_v2, major=2)
    assert contract.passed(findings), [f for f in findings if not f.ok]


def test_opencode_2_rules_are_judged_under_opencode_2_tool_names(agents_v2):
    # 2.x calls bash `shell`: judged under 1.x names, no probe would run and the gate would lie
    assert "readonly: probes run" in _failed(contract.check(agents_v2, major=1))
    assert rules.action("bash", 2) == "shell" and rules.action("task", 2) == "subagent"
    assert rules.action("bash", 1) == "bash"


def test_without_the_tool_catch_all_opencode_2_offers_code_mode(agents_v2):
    """What 2.0.20 resolved before the catch-all: its default `* allow` reached `execute`
    (JavaScript with fetch) and anything else policy.py never named."""
    readonly = _agent(agents_v2, "bashos")
    readonly["permissions"] = [r for r in readonly["permissions"]
                               if (r["action"], r["effect"]) not in (("*", "deny"), ("execute", "deny"))]
    failed = _failed(contract.check(agents_v2, major=2))
    assert {"readonly: denied tools", "readonly: tools deny-by-default"} <= failed


def test_the_tool_catch_all_resolves_before_every_allow(agents, agents_v2):
    """Last match wins: a catch-all after the allows would refuse every probe and read."""
    for found, major in ((agents, 1), (agents_v2, 2)):
        resolved = rules.from_agent(_agent(found, "bashos"))
        catch_all = resolved.index(("*", "*", "deny"))
        probe = resolved.index((rules.action("bash", major), "uname", "allow"))
        read = len(resolved) - 1 - resolved[::-1].index(("read", "*", "allow"))  # bashOS's, after the defaults
        assert catch_all < min(probe, read), major


async def test_the_engine_is_asked_in_its_own_words(agents_v2):
    """`ask_engine` puts every sample to the engine; it must allow exactly what policy.py allows."""
    resolved = {a["id"]: rules.from_agent(a) for a in agents_v2}

    class Engine:
        major = 2
        asked: list[tuple[str, str, str]] = []

        async def create_session(self, *, title, agent):
            return f"ses_{agent}"

        async def delete_session(self, session_id):
            pass

        async def evaluate_permission(self, session_id, *, agent, action, resource):
            self.asked.append((agent, action, resource))
            return rules.evaluate(resolved[agent], action, resource)

    engine = Engine()
    findings = await contract.ask_engine(engine)
    assert contract.passed(findings) and len(findings) == 2, findings
    assert ("bashos", "shell", "rm -rf /") in engine.asked  # 2.x names, not policy.py's

    resolved["bashos"].append(("shell", "curl *", "allow"))  # an engine that answers otherwise
    assert {f.name for f in await contract.ask_engine(engine) if not f.ok} == {"bashos: the engine's own answers"}


async def test_opencode_1_has_no_route_to_ask_so_the_mirror_is_the_contract():
    class Engine:
        major = 1

    assert await contract.ask_engine(Engine()) == []


async def test_the_contract_waits_for_the_project_agents(agents_v2):
    """2.0.20 answers `[]`, then its built-ins, then bashOS's agents too."""
    builtins = [{"id": "build", "name": "Build", "permissions": []}]
    answers = iter([[], builtins, builtins + agents_v2])

    class Engine:
        async def agents(self):
            return next(answers)

    found = await contract.resolved_agents(Engine(), timeout=5)
    assert {a["id"] for a in found} == {"build", "bashos", "bashos-sealed"}
