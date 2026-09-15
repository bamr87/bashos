"""Desktop front end — offline: real server, real kernel, no model, no engine.

Every run here goes through the dry-run path, so the whole stack is exercised
(HTTP → routes → kernel → SSE) without auth, a network, or an engine process.
"""

from __future__ import annotations

import json

import httpx
import pytest

from bashos.config import KernelConfig
from bashos.gui.http import Router
from bashos.gui.server import GuiServer
from bashos.registry import find_root


@pytest.fixture
async def gui():
    server = GuiServer(KernelConfig(dry_run=True), port=0, root=find_root())
    await server.start()
    try:
        yield server
    finally:
        await server.close()


@pytest.fixture
async def client(gui):
    async with httpx.AsyncClient(
        base_url=gui.url, headers={"x-bashos-token": gui.token}, timeout=30
    ) as http:
        yield http


# ----------------------------------------------------------------- routing


def test_router_matches_params_and_methods():
    router = Router()
    router.add("GET", "/api/runs/{run_id}", lambda request: None)
    handler, params = router.match("GET", "/api/runs/abc123")
    assert handler is not None
    assert params == {"run_id": "abc123"}


def test_router_reports_wrong_method_separately():
    from bashos.gui.http import HttpError

    router = Router()
    router.add("POST", "/api/runs", lambda request: None)
    with pytest.raises(HttpError) as missing:
        router.match("GET", "/api/nope")
    assert missing.value.status == 404
    with pytest.raises(HttpError) as method:
        router.match("GET", "/api/runs")
    assert method.value.status == 405


# -------------------------------------------------------------------- guard


async def test_api_requires_the_token(gui):
    async with httpx.AsyncClient(base_url=gui.url) as http:
        assert (await http.get("/api/state")).status_code == 401
        wrong = await http.get("/api/state", headers={"x-bashos-token": "nope"})
        assert wrong.status_code == 401


async def test_foreign_host_and_origin_are_refused(gui, client):
    rebound = await client.get("/api/state", headers={"host": "bashos.example.com"})
    assert rebound.status_code == 403
    cross = await client.get("/api/state", headers={"origin": "https://evil.example"})
    assert cross.status_code == 403


async def test_page_is_served_without_the_token(gui):
    async with httpx.AsyncClient(base_url=gui.url) as http:
        page = await http.get("/")
        assert page.status_code == 200
        assert "bashOS" in page.text
        assert gui.token not in page.text  # the page is not where the secret lives
        assert "default-src 'self'" in page.headers["content-security-policy"]


async def test_static_assets_cannot_escape_the_web_directory(client):
    assert (await client.get("/app.css")).status_code == 200
    assert (await client.get("/app.js")).status_code == 200
    assert (await client.get("/..%2fserver.py")).status_code == 404
    assert (await client.get("/nope.txt")).status_code == 404


# ------------------------------------------------------------------- state


async def test_state_describes_the_runtime(client):
    state = (await client.get("/api/state")).json()
    assert state["model"]
    assert state["backend"] in ("opencode", "claude-code", "api")
    assert {"sh", "script", "sys"} <= {c["name"] for c in state["commands"]}
    assert state["loops"]["prompt"] >= 1
    assert state["host"]["system"]


async def test_commands_carry_their_prompt_spec(client):
    commands = (await client.get("/api/commands")).json()
    sh = next(command for command in commands if command["name"] == "sh")
    assert sh["loop"] == "prompt"
    assert "$ARGUMENTS" in sh["body"] or sh["body"]
    assert sh["agent"]


async def test_policy_exposes_the_deny_by_default_rules(client):
    policy = (await client.get("/api/policy")).json()
    rules = {rule["key"]: rule["action"] for rule in policy["rules"]}
    assert rules["bash:*"] == "deny"
    assert rules["write"] == "deny"
    assert rules["webfetch"] == "deny"
    assert rules["read"] == "allow"
    assert "uname" in policy["probes"]
    assert policy["config_file"] == "opencode.jsonc"


async def test_doctor_runs_offline(client):
    checks = (await client.get("/api/doctor")).json()
    assert {check["label"] for check in checks} >= {"engine", "backend", "python"}


# --------------------------------------------------------------------- runs


async def read_events(client, run_id, token):
    events = []
    async with client.stream("GET", f"/api/runs/{run_id}/events?k={token}") as response:
        assert response.status_code == 200
        kind = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                kind = line[7:].strip()
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
                if kind == "done":
                    break
    return events


async def test_a_dry_run_streams_trace_then_output(gui, client):
    created = (await client.post("/api/runs", json={"input": "/sh find big files"})).json()
    events = await read_events(client, created["id"], gui.token)
    kinds = [kind for kind, _ in events]
    assert "node" in kinds and "trace" in kinds and "output" in kinds
    assert kinds[-1] == "done"

    output = next(payload["text"] for kind, payload in events if kind == "output")
    assert "[dry-run]" in output
    assert "find big files" in output

    summary = events[-1][1]
    assert summary["status"] == "ok"
    assert summary["command"] == "sh"
    assert summary["loop"] == "prompt"


async def test_a_finished_run_replays_from_history(gui, client):
    created = (await client.post("/api/runs", json={"input": "/regex match an email"})).json()
    await read_events(client, created["id"], gui.token)

    detail = (await client.get(f"/api/runs/{created['id']}")).json()
    assert detail["status"] == "ok"
    assert detail["trace"]
    assert detail["output"].startswith("[dry-run]")

    replay = await read_events(client, created["id"], gui.token)
    assert [kind for kind, _ in replay][-1] == "done"

    listed = (await client.get("/api/runs")).json()
    assert listed[0]["id"] == created["id"]


async def test_an_unknown_command_is_reported_as_an_error(gui, client):
    created = (await client.post("/api/runs", json={"input": "/shh list files"})).json()
    events = await read_events(client, created["id"], gui.token)
    assert events[-1][1]["status"] == "error"
    error = next(payload["text"] for kind, payload in events if kind == "error")
    assert "command not found" in error


async def test_shell_passthrough_is_refused(client):
    refused = await client.post("/api/runs", json={"input": "!rm -rf /"})
    assert refused.status_code == 403
    assert "passthrough" in refused.json()["error"]


async def test_empty_and_oversized_input_are_rejected(client):
    assert (await client.post("/api/runs", json={"input": "   "})).status_code == 400
    assert (await client.post("/api/runs", json={"input": "x" * 9000})).status_code == 413


async def test_missing_run_is_a_404(client):
    assert (await client.get("/api/runs/deadbeef")).status_code == 404
    assert (await client.get("/api/runs/deadbeef/events")).status_code == 404
