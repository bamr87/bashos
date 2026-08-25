"""Engine inspector — status rows, the live policy, and the event wire.

Status loads on demand (loading it boots the engine, exactly like the old
`engine` builtin did — a deliberate act, not a side effect of opening the
window). The policy pane is pure text from policy.describe_policy(); the
event log shows every typed engine event the desktop sees.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, RichLog, Static, TabbedContent, TabPane

from ... import events as engine_events
from ...opencode.policy import describe_policy
from ..services import DesktopServices


class EngineApp(Vertical):
    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="engine-app")
        self.services = services

    def compose(self):
        with TabbedContent():
            with TabPane("status", id="engine-status-tab"):
                yield Static(
                    "not loaded — loading boots the engine",
                    classes="engine-note",
                    markup=False,
                )
                table = DataTable(classes="engine-table", cursor_type="row")
                table.add_columns("", "detail")
                yield table
                with Horizontal(classes="button-row"):
                    yield Button("load status", id="engine-load", variant="primary")
                    yield Button("restart engine", id="engine-restart")
            with TabPane("policy", id="engine-policy-tab"):
                yield Static(describe_policy(), classes="policy-view", markup=False)
            with TabPane("events", id="engine-events-tab"):
                yield RichLog(classes="event-log", markup=False, wrap=True, max_lines=500)

    def feed_event(self, event: engine_events.EngineEvent) -> None:
        """The app forwards every typed engine event here — the live wire."""
        log = self.query_one(".event-log", RichLog)
        log.write(f"{type(event).__name__}: {event}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "engine-load":
            self.run_worker(self._load(), group="engine", exclusive=True, exit_on_error=False)
        elif event.button.id == "engine-restart":
            self.run_worker(self._restart(), group="engine", exclusive=True, exit_on_error=False)

    async def _load(self) -> None:
        note = self.query_one(".engine-note", Static)
        note.update("starting…")
        try:
            rows = await self.services.engine_status()
        except Exception as exc:
            note.update(f"engine unavailable: {exc}")
            return
        table = self.query_one(DataTable)
        table.clear()
        for label, detail in rows:
            table.add_row(label, detail)
        note.update("live")

    async def _restart(self) -> None:
        await self.services.shutdown()
        await self._load()
