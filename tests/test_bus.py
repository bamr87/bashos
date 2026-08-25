"""The event bus, engine sessions, and text-delta streaming — all offline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from bashos import events as events_mod
from bashos.config import KernelConfig
from bashos.opencode import engine as engine_mod
from bashos.opencode.bus import EngineEventBus
from bashos.opencode.client import OpencodeClient
from bashos.opencode.server import EngineHandle


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


def _text_event(session, part_id, text, *, synthetic=False):
    part: dict = {"type": "text", "id": part_id, "text": text}
    if synthetic:
        part["synthetic"] = True
    return {"type": "message.part.updated", "properties": {"sessionID": session, "part": part}}


class _BusClient:
    """A client whose global event stream is fed by hand."""

    def __init__(self):
        self.feed: asyncio.Queue = asyncio.Queue()
        self.rejected: list[tuple[str, str]] = []
        self.rejected_v2: list[str] = []
        self.streams_opened = 0

    async def events(self):
        self.streams_opened += 1
        while True:
            item = await self.feed.get()
            if item is None:  # end the stream (as if the server went away)
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def reject_permission(self, session_id, permission_id):
        self.rejected.append((session_id, permission_id))

    async def reject_permission_v2(self, request_id, message):
        self.rejected_v2.append(request_id)


async def _settle():
    """Let the pump and the registration watchers run their queues dry."""
    for _ in range(10):
        await asyncio.sleep(0.005)


# ------------------------------------------------------------------------ bus


async def test_bus_routes_events_only_to_their_session():
    client = _BusClient()
    bus = EngineEventBus(client)
    seen1: list = []
    seen2: list = []
    async with bus.run("s1", seen1.append, asyncio.Event()):
        async with bus.run("s2", seen2.append, asyncio.Event()):
            client.feed.put_nowait(_tool_event("s1", "c1", "bash", "uname"))
            client.feed.put_nowait(_tool_event("s2", "c2", "read", "x"))
            await _settle()
    await bus.close()

    tools1 = [e.call_id for e in seen1 if isinstance(e, events_mod.ToolEvent)]
    tools2 = [e.call_id for e in seen2 if isinstance(e, events_mod.ToolEvent)]
    assert tools1 == ["c1"]
    assert tools2 == ["c2"]
    assert client.streams_opened == 1, "N sessions must share ONE subscription"


async def test_bus_handles_sessionless_permission_exactly_once():
    client = _BusClient()
    bus = EngineEventBus(client)
    async with bus.run("s1", None, asyncio.Event()):
        async with bus.run("s2", None, asyncio.Event()):
            client.feed.put_nowait(
                {"type": "permission.v2.asked", "properties": {"id": "p9", "action": "edit"}}
            )
            await _settle()
    await bus.close()
    assert client.rejected_v2 == ["p9"], "one refusal, not one per subscriber"


async def test_bus_stream_loss_releases_all_waiters_and_reconnects():
    client = _BusClient()
    bus = EngineEventBus(client)
    live1, live2 = asyncio.Event(), asyncio.Event()
    phases: list = []
    async with bus.run("s1", phases.append, live1):
        async with bus.run("s2", None, live2):
            client.feed.put_nowait(RuntimeError("stream died"))
            await asyncio.wait_for(live1.wait(), timeout=1)
            await asyncio.wait_for(live2.wait(), timeout=1)
            # the pump retries: a second subscription proves reconnection
            client.feed.put_nowait(_tool_event("s1", "c1", "bash", "uname"))
            for _ in range(200):
                await asyncio.sleep(0.01)
                if any(isinstance(e, events_mod.ToolEvent) for e in phases):
                    break
    await bus.close()

    assert client.streams_opened >= 2
    lifecycle = [e.phase for e in phases if isinstance(e, events_mod.LifecycleEvent)]
    assert "stream.lost" in lifecycle
    assert "stream.reconnected" in lifecycle


async def test_late_registration_on_a_live_stream_is_immediately_live():
    client = _BusClient()
    bus = EngineEventBus(client)
    first = asyncio.Event()
    async with bus.run("s1", None, first):
        client.feed.put_nowait({"type": "server.connected", "properties": {}})
        await asyncio.wait_for(first.wait(), timeout=1)
        late = asyncio.Event()
        async with bus.run("s2", None, late):
            assert late.is_set(), "a connected bus must not make new sessions wait 5s"
    await bus.close()


# ------------------------------------------------------------- engine session


def _http_engine(handler) -> engine_mod.OpencodeEngine:
    """A real engine over a MockTransport client, its event stream fed by hand."""
    client = OpencodeClient("http://engine.test")
    client._http = httpx.AsyncClient(
        base_url="http://engine.test", transport=httpx.MockTransport(handler)
    )
    feed: asyncio.Queue = asyncio.Queue()

    async def fake_events():
        yield {"type": "server.connected", "properties": {}}
        while True:
            yield await feed.get()

    client.events = fake_events  # type: ignore[method-assign]
    engine = engine_mod.OpencodeEngine(KernelConfig(), root=Path("."), registry={})
    engine._handle = EngineHandle(url="http://engine.test", client=client)
    return engine


def _session_handler(counts: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/session":
            counts["created"] += 1
            return httpx.Response(200, json={"id": f"ses_{counts['created']}"})
        if request.method == "POST" and request.url.path.endswith("/message"):
            counts["prompted"] += 1
            return httpx.Response(
                200, json={"info": {}, "parts": [{"type": "text", "text": "ok"}]}
            )
        if request.method == "DELETE":
            counts["deleted"] += 1
            return httpx.Response(200, json={})
        if request.method == "POST" and request.url.path.endswith("/abort"):
            counts["aborted"] = counts.get("aborted", 0) + 1
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    return handler


async def test_session_reuse_sends_many_prompts_on_one_session():
    counts = {"created": 0, "prompted": 0, "deleted": 0}
    engine = _http_engine(_session_handler(counts))
    session = await engine.open_session("bashos", title="bashos:desktop:console-1")
    first = await session.prompt("one")
    second = await session.prompt("two")
    await session.close()
    await engine.bus.close()

    assert first.text == "ok" and second.text == "ok"
    assert counts == {"created": 1, "prompted": 2, "deleted": 1}
    assert engine._sessions == set()


async def test_engine_stop_sweeps_sessions_a_window_never_closed():
    counts = {"created": 0, "prompted": 0, "deleted": 0}
    engine = _http_engine(_session_handler(counts))
    await engine.open_session("bashos")  # deliberately never closed
    await engine.stop()
    assert counts["deleted"] == 1
    assert engine._sessions == set()


async def test_one_shot_run_still_creates_and_deletes_per_call():
    counts = {"created": 0, "prompted": 0, "deleted": 0}
    engine = _http_engine(_session_handler(counts))
    result = await engine.act("probe the disk")
    await engine.bus.close()
    assert result.text == "ok"
    assert counts == {"created": 1, "prompted": 1, "deleted": 1}


# ----------------------------------------------------------------- text deltas


async def _typed_watch(evts: list[dict], session="ses_1"):
    async def stream():
        for event in evts:
            yield event

    typed: list = []
    await engine_mod.watch_events(stream(), session, typed.append, asyncio.Event(), None)
    return typed


async def test_watch_emits_text_deltas_in_order_and_skips_synthetic():
    typed = await _typed_watch(
        [
            _text_event("ses_1", "p1", "Lin"),
            _text_event("ses_1", "p1", "Linux is"),
            _text_event("ses_1", "p2", "Second part"),
            _text_event("ses_1", "p0", "internal", synthetic=True),
        ]
    )
    deltas = [(d.part_id, d.text) for d in typed if isinstance(d, events_mod.TextDelta)]
    assert deltas == [("p1", "Lin"), ("p1", "ux is"), ("p2", "Second part")]


async def test_delta_counter_resets_when_a_part_shrinks():
    typed = await _typed_watch(
        [
            _text_event("ses_1", "p1", "Linux is"),
            _text_event("ses_1", "p1", "Li"),  # mid-stream edit shrank the part
            _text_event("ses_1", "p1", "Linus"),
        ]
    )
    deltas = [d.text for d in typed if isinstance(d, events_mod.TextDelta)]
    assert deltas == ["Linux is", "Li", "nus"]


def test_legacy_adapter_renders_no_text_deltas():
    lines: list[str] = []
    sink = events_mod.to_legacy(lines.append)
    sink(events_mod.TextDelta(session_id="s", part_id="p1", text="streaming..."))
    assert lines == []


# ------------------------------------------------------------- sink threading


def test_models_for_attaches_sink_to_main_llm_only():
    from bashos.runtime.llm import models_for

    def sink(event):  # pragma: no cover - never called here
        pass

    config = KernelConfig(backend="opencode", classify_model="claude-haiku-4-5")
    llm, classifier = models_for(config, event_sink=sink)
    assert llm.event_sink is sink
    assert classifier is not None
    assert classifier.event_sink is None
