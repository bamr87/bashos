"""Shared modal screens: help and quit confirmation.

(The exec-confirm modal joins these in the console milestone.)
"""

from __future__ import annotations

from rich.table import Table
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

KEYS = [
    ("ctrl+p", "command palette"),
    ("f2", "launcher (apps + commands)"),
    ("f1", "this help"),
    ("ctrl+n", "new AI console window"),
    ("ctrl+o", "cycle window focus"),
    ("ctrl+b", "maximize / restore the active window"),
    ("ctrl+shift+w", "close the active window"),
    ("ctrl+t", "cycle theme"),
    ("ctrl+q", "quit the desktop"),
]


class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close_help", "close")]

    def compose(self):
        table = Table(title="bashOS desktop keys", title_justify="left", border_style="dim")
        table.add_column("key", style="bold cyan", no_wrap=True)
        table.add_column("action")
        for key, action in KEYS:
            table.add_row(key, action)
        with Vertical(id="help-modal", classes="modal-box"):
            yield Static(table)
            yield Static("every action is also in the command palette (ctrl+p)", classes="dim")

    def action_close_help(self) -> None:
        self.dismiss(None)


class QuitConfirm(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel_quit", "cancel")]

    def compose(self):
        with Vertical(id="quit-modal", classes="modal-box"):
            yield Static("quit the bashOS desktop?", id="quit-question")
            with Horizontal(classes="modal-buttons"):
                yield Button("quit", variant="error", id="quit-yes")
                yield Button("stay", variant="primary", id="quit-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "quit-yes")

    def action_cancel_quit(self) -> None:
        self.dismiss(False)
