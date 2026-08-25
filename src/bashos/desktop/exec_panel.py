"""Shell escapes without inherited stdio.

A full-screen app owns the terminal, so subprocesses cannot write straight
to it. Two paths replace the old inherited-stdio pattern:

- run_captured: output streams into a RichLog window (the default for
  `!cmd` and confirmed `exec` runs)
- run_attached: the whole app suspends, the command gets the real
  terminal, and the desktop restores afterwards (for interactive commands)
"""

from __future__ import annotations

import asyncio
import subprocess

from textual.widgets import RichLog

from .wm import Window


class ShellRunner:
    def __init__(self, app) -> None:
        self._app = app
        self._counter = 0

    async def run_captured(self, command: str) -> None:
        """Run in the user's shell, streaming output into a new window."""
        self._counter += 1
        log = RichLog(classes="shell-output", markup=False, wrap=True, max_lines=2000)
        title = f"$ {command}" if len(command) <= 40 else f"$ {command[:37]}..."
        window = Window(log, title=title, wid=f"win-shell-{self._counter}")
        await self._app.desktop.add_window(window)
        self._app.run_worker(
            self._pump(command, log), group=f"shell-{self._counter}", exit_on_error=False
        )

    async def _pump(self, command: str, log: RichLog) -> None:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                log.write(line.decode(errors="replace").rstrip("\n"))
        finally:
            code = await proc.wait()
            log.write(f"[exit {code}]")

    def run_attached(self, command: str) -> int:
        """Suspend the desktop, give the command the real terminal, restore."""
        with self._app.suspend():
            return subprocess.run(command, shell=True).returncode
