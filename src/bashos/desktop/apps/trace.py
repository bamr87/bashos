"""Kernel trace viewer — every routing decision, one turn at a time.

`trace` is the kernel's append-only audit log (`bashos run -v` prints it in
the CLI). Every finished console turn lands here app-wide.
"""

from __future__ import annotations

from textual.containers import Vertical, VerticalScroll
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..messages import TurnFinished
from ..services import DesktopServices


class TraceViewerApp(Vertical):
    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="trace-app")
        self.services = services
        self._turns: list[TurnFinished] = []

    def compose(self):
        yield Static("no turns yet — run something in a console", classes="trace-note")
        yield OptionList(id="trace-list")
        yield VerticalScroll(Static("", classes="trace-detail", markup=False))

    def add_turn(self, message: TurnFinished) -> None:
        self._turns.append(message)
        command = message.result.get("command")
        route = message.result.get("route", "?")
        label = f"{message.line}  →  /{command} ({route})" if command else message.line
        self.query_one("#trace-list", OptionList).add_option(
            Option(label, id=str(len(self._turns) - 1))
        )
        self.query_one(".trace-note", Static).update(f"{len(self._turns)} turn(s)")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        message = self._turns[int(event.option.id or 0)]
        trace = message.result.get("trace") or []
        self.query_one(".trace-detail", Static).update(
            "\n".join(f"· {line}" for line in trace) or "(empty trace)"
        )
