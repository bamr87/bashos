"""Health monitor — the deterministic bin/os-health floor, rendered natively.

The floor prints machine-parseable `[ OK ]/[WARN]/[CRIT] name detail` lines
with a worst-verdict exit code; nothing rendered them until now. The
"Ask /health" button hands investigation to the react command, keeping the
split the FORGE design established: deterministic floor, model for causes.
"""

from __future__ import annotations

import asyncio
import re

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static

from ...registry import find_root
from ..messages import OpenAppRequest
from ..services import DesktopServices

VERDICT_RE = re.compile(r"^\[\s*(OK|WARN|CRIT)\s*\]\s+(\S+)\s*(.*)$")
_STYLE = {"OK": "green", "WARN": "yellow", "CRIT": "red bold"}


class HealthApp(Vertical):
    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="health")
        self.services = services

    def compose(self):
        yield Static("running bin/os-health…", classes="health-header", markup=False)
        table = DataTable(classes="health-table", cursor_type="row", zebra_stripes=True)
        table.add_columns("verdict", "check", "detail")
        yield table
        with Horizontal(classes="button-row"):
            yield Button("refresh", id="health-refresh")
            yield Button("ask /health", id="health-ask", variant="primary")

    def on_mount(self) -> None:
        self.refresh_floor()

    def refresh_floor(self) -> None:
        self.run_worker(self._refresh(), group="health", exclusive=True, exit_on_error=False)

    async def _read_floor(self) -> tuple[int, str]:
        """Run the floor; monkeypatched in tests."""
        script = find_root() / "bin" / "os-health"
        proc = await asyncio.create_subprocess_exec(
            str(script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        return proc.returncode or 0, out.decode(errors="replace")

    async def _refresh(self) -> None:
        header = self.query_one(".health-header", Static)
        table = self.query_one(DataTable)
        try:
            code, output = await self._read_floor()
        except OSError as exc:
            header.update(f"could not run bin/os-health: {exc}")
            return
        table.clear()
        worst = "OK"
        for line in output.splitlines():
            match = VERDICT_RE.match(line.strip())
            if match is None:
                continue  # tolerate banners and free text between verdicts
            verdict, name, detail = match.groups()
            if verdict == "CRIT" or (verdict == "WARN" and worst == "OK"):
                worst = verdict
            table.add_row(Text(f"[{verdict}]", style=_STYLE[verdict]), name, detail)
        header.update(
            Text.assemble(
                "floor verdict: ",
                (worst, _STYLE[worst]),
                f"  (exit {code})",
            )
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "health-refresh":
            self.refresh_floor()
        elif event.button.id == "health-ask":
            self.post_message(OpenAppRequest("console", "/health "))
