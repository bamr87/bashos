"""The OpenCode TUI window — suspend/attach, honestly.

No maintained Textual terminal-emulator widget exists (textual-terminal is
pyte-based and stale; pyte lacks the truecolor/DECSET handling OpenCode's
bubbletea TUI needs), so embedding a live pty is deferred. The shipping
path: suspend the desktop, hand the real terminal to `opencode`, restore on
exit. v1 runs it as an independent process in the project root — safe, but
session-disjoint from the supervised engine, which the card says out loud.
"""

from __future__ import annotations

import subprocess

from textual.containers import Vertical
from textual.widgets import Button, Static

from ...opencode import server as engine_server
from ...registry import find_root
from ..services import DesktopServices


def tui_argv() -> list[str]:
    return ["opencode"]


class OpencodeTuiApp(Vertical):
    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="opencode-tui")
        self.services = services

    def compose(self):
        installed = engine_server.find_binary() is not None
        note = (
            "Opens the real OpenCode TUI full-screen (the desktop suspends and\n"
            "restores when you exit). It runs as its own process in this project\n"
            "— sessions there are separate from bashOS console turns."
            if installed
            else engine_server.INSTALL_HINT
        )
        yield Static(note, classes="opencode-note", markup=False)
        yield Button(
            "open OpenCode TUI",
            id="opencode-open",
            variant="primary",
            disabled=not installed,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "opencode-open":
            self.launch()

    def launch(self) -> None:
        with self.app.suspend():
            subprocess.run(tui_argv(), cwd=str(find_root()))
