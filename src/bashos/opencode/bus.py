"""One SSE subscription, fanned out per session — the engine's event spine.

The engine's global `/event` stream carries every session's traffic. Opening
one HTTP subscription per prompt (the pre-desktop behavior) meant N windows
held N streams and every sessionID-less event reached all of them. The bus
owns exactly one subscription for the engine's lifetime and routes:

- events with a sessionID           → that session's registration only
- server.connected / any frame      → marks the stream live for every waiter
- permission.v2.asked, no sessionID → auto-refused ONCE, at bus level
- permission.asked (v1), no sessionID → handed to one registration
  (a v1 rejection answers through a session, so a watcher must own it)
- anything else without a sessionID → dropped

Each registration feeds its slice of the stream through the same pure
`engine.watch_events` loop that tests drive directly, so per-session
semantics (tool dedupe, permission refusal, text deltas) live in one place.

A dead stream must never wedge a prompt: on stream loss every waiter is
released and `stream.lost` is emitted; the pump reconnects with capped
backoff and `stream.reconnected` follows on the next healthy frame.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from .. import events


class _Registration:
    """One session's live subscription: a queue and a watcher consuming it."""

    def __init__(
        self,
        session_id: str,
        sink: events.EventSink | None,
        live: asyncio.Event,
        client: Any,
    ) -> None:
        from .engine import watch_events

        self.session_id = session_id
        self.sink = sink
        self.live = live
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.task = asyncio.create_task(
            watch_events(self._drain(), session_id, sink, live, client)
        )

    async def _drain(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        self.queue.put_nowait(None)
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


class EngineEventBus:
    """The single live `/event` subscription, with per-session fan-out."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._regs: dict[str, _Registration] = {}
        self._pump_task: asyncio.Task | None = None
        self._connected = asyncio.Event()
        self._closed = False

    @contextlib.asynccontextmanager
    async def run(
        self,
        session_id: str,
        sink: events.EventSink | None,
        live: asyncio.Event,
    ):
        """Subscribe one session for the duration of the block."""
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.create_task(self._pump())
        reg = _Registration(session_id, sink, live, self._client)
        self._regs[session_id] = reg
        if self._connected.is_set():
            live.set()  # the stream was already open before this session joined
        try:
            yield reg
        finally:
            self._regs.pop(session_id, None)
            await reg.close()

    async def close(self) -> None:
        self._closed = True
        if self._pump_task is not None:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
            self._pump_task = None
        for reg in list(self._regs.values()):
            await reg.close()
        self._regs.clear()

    async def _pump(self) -> None:
        backoff = 0.5
        lost = False
        while not self._closed:
            try:
                async for event in self._client.events():
                    backoff = 0.5
                    if lost:
                        lost = False
                        self._broadcast_phase("stream.reconnected")
                    self._connected.set()
                    for reg in list(self._regs.values()):
                        reg.live.set()
                    await self._route(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            if self._closed:
                return
            # the stream ended or died: release every waiter, then retry —
            # a dead stream must never wedge a prompt
            self._connected.clear()
            if not lost:
                lost = True
                self._broadcast_phase("stream.lost")
            for reg in list(self._regs.values()):
                reg.live.set()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)

    async def _route(self, event: dict[str, Any]) -> None:
        props = event.get("properties") or {}
        session_id = props.get("sessionID")
        if session_id is not None:
            if reg := self._regs.get(str(session_id)):
                reg.queue.put_nowait(event)
            return
        # sessionID-less traffic is decided exactly once, here — never once
        # per subscriber
        kind = event.get("type")
        if kind == "permission.v2.asked":
            from .engine import _REJECTION

            request_id = str(props.get("id"))
            await self._client.reject_permission_v2(request_id, _REJECTION)
            for reg in list(self._regs.values()):
                if reg.sink is not None:
                    reg.sink(events.PermissionEvent(
                        session_id=reg.session_id,
                        request_id=request_id,
                        action=str(props.get("action")),
                        protocol="v2",
                        decision="auto-rejected",
                    ))
        elif kind == "permission.asked" and self._regs:
            next(iter(self._regs.values())).queue.put_nowait(event)

    def _broadcast_phase(self, phase: str) -> None:
        for reg in list(self._regs.values()):
            if reg.sink is not None:
                reg.sink(events.LifecycleEvent(session_id=reg.session_id, phase=phase))
