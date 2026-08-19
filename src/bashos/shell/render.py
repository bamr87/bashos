"""Terminal rendering — rich is the display driver."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..config import KernelConfig
from ..registry import CommandSpec
from ..runtime.auth import Check

console = Console()

BANNER = r"""
 _             _    ___  ____
| |__  __ _ __| |_ / _ \/ ___|
| '_ \/ _` (_-< ' \ (_) \___ \
|_.__/\__,_/__/_||_\___/|____/
"""


def print_banner(config: KernelConfig, backend: str) -> None:
    console.print(BANNER, style="bold cyan", highlight=False)
    console.print(
        f"terminal-first AI runtime · backend={backend} · model={config.model}",
        style="dim",
    )
    console.print(
        "type /<command>, plain english, !<shell>, or help · ctrl-d to exit\n",
        style="dim",
    )


def print_output(text: str) -> None:
    if text.startswith(("[dry-run]", "usage:")):
        # kernel reports are literal text, not markdown
        console.print(text, markup=False, highlight=False)
    else:
        console.print(Markdown(text))


def print_error(text: str) -> None:
    console.print(Panel(text, border_style="red", title="error", title_align="left"))


def print_event(text: str) -> None:
    console.print(f"  · {text}", style="dim")


def print_trace(trace: list[str]) -> None:
    if not trace:
        return
    console.print("\n[dim]kernel trace:[/dim]")
    for line in trace:
        console.print(f"  [dim]· {line}[/dim]")


def print_command_table(registry: dict[str, CommandSpec]) -> None:
    table = Table(title="bashOS commands", title_justify="left", border_style="dim")
    from ..opencode.project import agent_for

    table.add_column("command", style="bold cyan", no_wrap=True)
    table.add_column("loop", style="magenta", no_wrap=True)
    table.add_column("agent", style="dim magenta", no_wrap=True)
    table.add_column("args", style="dim", no_wrap=True, max_width=28)
    table.add_column("description")
    for spec in registry.values():
        table.add_row(
            f"/{spec.name}", spec.loop, agent_for(spec), spec.argument_hint, spec.description
        )
    console.print(table)
    console.print(
        "[dim]builtins: help · list · doctor · clear · exit · !<cmd> runs your real shell[/dim]"
    )


def print_doctor_table(checks: list[Check]) -> None:
    table = Table(title="bashos doctor", title_justify="left", border_style="dim")
    table.add_column("", no_wrap=True)
    table.add_column("check", style="bold", no_wrap=True)
    table.add_column("detail")
    for check in checks:
        mark = "[green]✓[/green]" if check.ok else "[yellow]✗[/yellow]"
        table.add_row(mark, check.label, check.detail)
    console.print(table)


def print_engine_status(rows: list[tuple[str, str]]) -> None:
    table = Table(title="bashos engine", title_justify="left", border_style="dim")
    table.add_column("", style="bold", no_wrap=True)
    table.add_column("detail")
    for label, detail in rows:
        table.add_row(label, detail)
    console.print(table)


def status(message: str = "thinking"):
    return console.status(f"[dim]{message}[/dim]", spinner="dots")
