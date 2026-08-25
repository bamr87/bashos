"""Typed engine events — the structured channel between the engine and a UI.

The engine's watch loop emits these to an `EventSink`; a desktop renders them
richly (spinners on running tools, streamed text, denial notices) while the
one-shot CLI keeps its historical one-line output through `to_legacy`.

Contract notes:

- Sinks are synchronous and must never block: they are called from the
  engine's watch task while a prompt is in flight. Post to your UI loop and
  return.
- `TextDelta.text` carries only the NEW fragment of a text part, in stream
  order. The final `PromptResult.text` is authoritative and replaces any
  streamed buffer, so a missed or reordered delta is self-healing. The engine
  does not throttle deltas — a UI coalesces on its own refresh timer.
- This module stays import-light (stdlib only) so every layer can use it
  without cycles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EngineEvent:
    """Base: everything that happens is attributed to one engine session."""

    session_id: str


@dataclass(frozen=True)
class ToolEvent(EngineEvent):
    """One observed state of one tool invocation (a call appears once per
    status transition — pending, running, completed/error)."""

    tool: str
    call_id: str
    status: str  # "pending" | "running" | "completed" | "error" | ""
    title: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    description: str = ""  # the bounded one-liner, e.g. "bash(uname -a)"
    duration_ms: int | None = None  # filled on completed/error


@dataclass(frozen=True)
class TextDelta(EngineEvent):
    """A new fragment of assistant text on one message part."""

    part_id: str
    text: str


@dataclass(frozen=True)
class PermissionEvent(EngineEvent):
    request_id: str
    action: str
    protocol: str  # "v1" | "v2"
    decision: str  # "auto-rejected" | "pending" | "approved" | "rejected" | "timed-out"


@dataclass(frozen=True)
class LifecycleEvent(EngineEvent):
    phase: str  # "session.created" | "prompt.started" | "prompt.finished" |
    # "session.deleted" | "stream.lost" | "stream.reconnected"


@dataclass(frozen=True)
class ErrorEvent(EngineEvent):
    kind: str
    message: str


EventSink = Callable[[EngineEvent], None]


def describe(event: EngineEvent) -> str | None:
    """The legacy one-line rendering, or None for events the CLI never showed."""
    if isinstance(event, ToolEvent):
        return event.description or event.tool
    if isinstance(event, PermissionEvent) and event.decision == "auto-rejected":
        return f"denied by policy: {event.action}"
    return None


def to_legacy(on_event: Callable[[str], None]) -> EventSink:
    """Adapt today's one-line string callback onto a typed sink.

    This closure is where the historical output contract lives: exactly one
    line per tool call (deduped by call_id, pending and blank statuses
    dropped) plus one line per auto-refused permission — and nothing else.
    `bashos run -v` output must stay byte-identical through this adapter.
    """
    seen: set[str] = set()

    def sink(event: EngineEvent) -> None:
        if isinstance(event, ToolEvent):
            if not event.call_id or event.call_id in seen or event.status in ("pending", ""):
                return
            seen.add(event.call_id)
        line = describe(event)
        if line is not None:
            on_event(line)

    return sink
