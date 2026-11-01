"""The engine contract: does an engine still enforce policy.py, judged from what it resolved?

The fixture is a real OpenCode 1.19.5 engine's `GET /agent` for the bashOS agents (paths that
only exist on the capturing machine dropped), so the contract is tested against the engine's
format, not ours. Offline: no engine, no network.
"""

from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path

import pytest

from bashos.opencode import contract, server
from bashos.opencode.client import OpencodeError

FIXTURE = Path(__file__).parent / "fixtures" / "opencode-1.19.5-agents.json"


@pytest.fixture
def agents() -> list[dict]:
    return json.loads(FIXTURE.read_text())


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


async def test_an_opencode_2_engine_is_named_not_crashed_on(tmp_path):
    v2 = _exe(tmp_path / "opencode2", "opencode v2.0.20")
    with pytest.raises(OpencodeError) as caught:
        await server.spawn(directory=str(tmp_path), binary=str(v2))
    message = str(caught.value)
    assert "opencode 2.0.20" in message and "bamr87/bashos#71" in message and "BASHOS_OPENCODE_BIN" in message


def test_doctor_flags_an_unsupported_engine(tmp_path, monkeypatch):
    from bashos.runtime import auth as runtime_auth

    monkeypatch.delenv("BASHOS_OPENCODE_URL", raising=False)
    monkeypatch.setenv("BASHOS_OPENCODE_BIN", str(_exe(tmp_path / "opencode", "opencode v2.0.20")))
    check = runtime_auth._engine_check()
    assert not check.ok and "#71" in check.detail
    monkeypatch.setenv("BASHOS_OPENCODE_BIN", str(_exe(tmp_path / "opencode1", "1.19.5")))
    check = runtime_auth._engine_check()
    assert check.ok and "1.19.5" in check.detail and "BASHOS_OPENCODE_BIN" in check.detail
