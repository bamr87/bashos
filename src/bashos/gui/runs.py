"""Runs: what the desktop shows instead of scrollback.

A run is one line through the kernel — the same line the REPL would take —
recorded with everything the terminal prints and then throws away: the route
it took, every kernel node as it completed, every tool call the engine made,
and the answer. The GUI subscribes to a run while it is live and reads the same
record back afterwards.

In memory, this process only. bashOS keeps no history file, and a desktop
front end is not a reason to start writing one — closing the window is how you
clear it.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

MAX_RUNS = 200  # a session's worth; oldest dropped first
MAX_EVENTS = 500  # per run — a runaway engine cannot exhaust memory

# Event kinds carried to the page, in the order a run produces them:
#   status  run lifecycle           ("started" | "finished")
#   node    a kernel node completed (parse, classify, loop_*, respond)
#   trace   an appended trace line  (the kernel's own harness log)
#   tool    an engine tool call     (react loop only, live)
#   output  the answer
#   error   the run failed
#   done    terminal marker; the stream closes after it


@dataclass(frozen=True)
class RunEvent:
    kind: str
    text: str
    at: float

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "text": self.text, "at": self.at}


@dataclass
class Run:
    id: str
    input: str
    dry_run: bool
    model: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"  # running | ok | error
    command: str = ""
    route: str = ""
    loop: str = ""
    output: str = ""
    error: str = ""
    trace: list[str] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    _subscribers: list[asyncio.Queue[RunEvent | None]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------- recording

    def emit(self, kind: str, text: str) -> None:
        event = RunEvent(kind=kind, text=text, at=time.time())
        if len(self.events) < MAX_EVENTS:
            self.events.append(event)
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def finish(self, status: str) -> None:
        self.status = status
        self.finished_at = time.time()
        self.emit("status", status)
        for queue in list(self._subscribers):
            queue.put_nowait(None)  # sentinel: the stream may close
        self._subscribers.clear()

    @property
    def duration(self) -> float:
        return (self.finished_at or time.time()) - self.started_at

    # ------------------------------------------------------------ subscribing

    async def stream(self) -> AsyncIterator[tuple[str, object]]:
        """Replay what already happened, then follow the run until it ends."""
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        live = self.status == "running"
        # subscribe before snapshotting, so a concurrent emit lands in the
        # queue rather than in the gap between the two
        if live:
            self._subscribers.append(queue)
        backlog = list(self.events)
        try:
            for event in backlog:
                yield event.kind, event.as_dict()
            while live:
                event = await queue.get()
                if event is None:
                    break
                if event in backlog:
                    continue  # already replayed
                yield event.kind, event.as_dict()
            yield "done", self.summary()
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    # -------------------------------------------------------------- rendering

    def summary(self) -> dict[str, object]:
        return {
            "id": self.id,
            "input": self.input,
            "command": self.command,
            "route": self.route,
            "loop": self.loop,
            "status": self.status,
            "dry_run": self.dry_run,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": round(self.duration, 3),
            "tool_calls": sum(1 for e in self.events if e.kind == "tool"),
        }

    def detail(self) -> dict[str, object]:
        return {
            **self.summary(),
            "output": self.output,
            "error": self.error,
            "trace": self.trace,
            "events": [event.as_dict() for event in self.events],
        }


class RunStore:
    """Bounded, newest-first history of this process's runs."""

    def __init__(self, limit: int = MAX_RUNS) -> None:
        self._runs: dict[str, Run] = {}
        self._limit = limit

    def create(self, line: str, *, dry_run: bool, model: str) -> Run:
        run = Run(id=uuid.uuid4().hex[:12], input=line, dry_run=dry_run, model=model)
        self._runs[run.id] = run
        while len(self._runs) > self._limit:
            self._runs.pop(next(iter(self._runs)))
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self, limit: int = 50) -> list[dict[str, object]]:
        newest = sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)
        return [run.summary() for run in newest[:limit]]

    def stats(self) -> dict[str, object]:
        runs = list(self._runs.values())
        done = [r for r in runs if r.finished_at is not None]
        return {
            "total": len(runs),
            "ok": sum(1 for r in runs if r.status == "ok"),
            "failed": sum(1 for r in runs if r.status == "error"),
            "running": sum(1 for r in runs if r.status == "running"),
            "tool_calls": sum(r.summary()["tool_calls"] for r in runs),  # type: ignore[misc]
            "avg_duration": round(sum(r.duration for r in done) / len(done), 2) if done else 0.0,
        }
