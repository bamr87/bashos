"""Confirm-then-run the first bash fence from a kernel answer."""

from __future__ import annotations

import asyncio
import sys

from rich.panel import Panel
from rich.prompt import Confirm

from ..loops.common import first_fence
from . import render


def runnable_from(output: str) -> str | None:
    return first_fence(output)


async def run_command(command: str) -> int:
    """Spawn the command in the user's shell and return its exit code.

    No console I/O of its own — the confirming surface (CLI prompt or a
    desktop modal) owns the presentation around it.
    """
    proc = await asyncio.create_subprocess_shell(command)
    return await proc.wait()


async def confirm_and_run(command: str, *, yes: bool = False) -> int:
    render.console.print(Panel(command, title="exec", border_style="yellow", title_align="left"))
    if not yes:
        if not sys.stdin.isatty():
            render.print_error("--exec needs a TTY or --yes")
            return 1
        if not Confirm.ask("run this command?", default=False):
            return 0
    return await run_command(command)
