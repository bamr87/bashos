"""Command runner — any registry command with a zero-cost preview.

The preview is `dry_run_report` over the rendered prompt: exactly what
`bashos run -n` prints, free of charge (no model, no auth). Run hands the
line to a console window.
"""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Select, Static

from ...loops.common import dry_run_report
from ...opencode.project import agent_for
from ..messages import OpenAppRequest
from ..services import DesktopServices


class CommandApp(Vertical):
    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="command-app")
        self.services = services

    def compose(self):
        options = [
            (f"/{name} — {spec.description}", name)
            for name, spec in self.services.registry.items()
        ]
        yield Select(options, prompt="pick a command", id="command-select")
        yield Static("", classes="command-meta", markup=False)
        yield Input(placeholder="arguments…", classes="command-args")
        with Horizontal(classes="button-row"):
            yield Button("preview (dry-run)", id="command-preview")
            yield Button("run in console", id="command-run", variant="primary")
        yield VerticalScroll(Static("", classes="command-preview-body", markup=False))

    def _selected(self):
        name = self.query_one("#command-select", Select).value
        if name is Select.BLANK:
            return None
        return self.services.registry.get(str(name))

    def on_select_changed(self, event: Select.Changed) -> None:
        event.stop()
        spec = self._selected()
        meta = self.query_one(".command-meta", Static)
        if spec is None:
            meta.update("")
            return
        meta.update(
            f"{spec.usage}\nloop={spec.loop} · agent={agent_for(spec)} — {spec.description}"
        )

    def preview(self) -> None:
        spec = self._selected()
        body = self.query_one(".command-preview-body", Static)
        if spec is None:
            body.update("pick a command first")
            return
        args = self.query_one(".command-args", Input).value.strip()
        if not args and spec.requires_args:
            body.update(spec.usage)
            return
        prompt = spec.render(args)
        body.update(dry_run_report(spec, prompt))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "command-preview":
            self.preview()
        elif event.button.id == "command-run":
            spec = self._selected()
            if spec is None:
                return
            args = self.query_one(".command-args", Input).value.strip()
            self.post_message(OpenAppRequest("console", f"/{spec.name} {args}".rstrip() + " "))
