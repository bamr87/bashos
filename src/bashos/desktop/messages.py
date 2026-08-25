"""Textual messages the desktop's widgets exchange."""

from __future__ import annotations

from typing import Any

from textual.message import Message

from .. import events as engine_events


class EngineEventMsg(Message):
    """A typed engine event crossing into the UI loop."""

    def __init__(self, event: engine_events.EngineEvent) -> None:
        super().__init__()
        self.event = event


class OpenAppRequest(Message):
    """Ask the app to open (or focus) a desktop app window."""

    def __init__(self, app_id: str, args: str = "") -> None:
        super().__init__()
        self.app_id = app_id
        self.args = args


class TurnStarted(Message):
    def __init__(self, window_id: str, line: str) -> None:
        super().__init__()
        self.window_id = window_id
        self.line = line


class TurnFinished(Message):
    def __init__(self, window_id: str, line: str, result: dict[str, Any]) -> None:
        super().__init__()
        self.window_id = window_id
        self.line = line
        self.result = result
