"""Shared modal screens: help, quit confirmation, and exec confirmation."""

from __future__ import annotations

from rich.panel import Panel
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


class ExecModal(ModalScreen[str | None]):
    """Confirm-then-run for a generated command.

    Dismisses with 'captured' (output into a window), 'attached' (suspend
    the desktop, give the command the real terminal), or None. Cancel holds
    the default focus — running anything requires deliberate intent, the
    same contract as the CLI's Confirm(default=False).
    """

    BINDINGS = [Binding("escape", "cancel_exec", "cancel")]

    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command

    def compose(self):
        with Vertical(id="exec-modal", classes="modal-box"):
            yield Static(
                Panel(self.command, title="exec", border_style="yellow", title_align="left")
            )
            yield Static("run this command?", id="exec-question")
            with Horizontal(classes="modal-buttons"):
                yield Button("run", variant="warning", id="exec-captured")
                yield Button("run attached", id="exec-attached")
                yield Button("cancel", variant="primary", id="exec-cancel")

    def on_mount(self) -> None:
        self.query_one("#exec-cancel", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(
            {"exec-captured": "captured", "exec-attached": "attached"}.get(
                event.button.id or ""
            )
        )

    def action_cancel_exec(self) -> None:
        self.dismiss(None)
