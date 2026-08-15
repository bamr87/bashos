"""bashOS command line — every capability is reachable from the terminal.

    bashos                     interactive REPL (the default)
    bashos run /sh <request>   one-shot command
    bashos run <plain english> routed to the best command by the kernel
    bashos list                command table
    bashos doctor              auth + environment checks
"""

from __future__ import annotations

import asyncio

import typer
from dotenv import load_dotenv

from ..config import KernelConfig
from ..kernel import build_kernel
from ..registry import load_registry
from ..runtime.auth import run_checks
from ..runtime.llm import get_chat_model
from . import render

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="bashOS — terminal-first AI runtime on Claude Code OAuth.",
)


async def run_line(
    line: str,
    *,
    dry_run: bool = False,
    model: str | None = None,
    verbose: bool = False,
) -> int:
    config = KernelConfig.from_env(model=model, dry_run=dry_run, verbose=verbose)
    registry = load_registry()
    llm = None if dry_run else get_chat_model(config)
    kernel = build_kernel(registry, llm, config, on_event=render.print_event)

    try:
        if dry_run:
            result = await kernel.ainvoke({"input": line, "trace": []})
        else:
            with render.status():
                result = await kernel.ainvoke({"input": line, "trace": []})
    except Exception as exc:  # render a clean panel, not a traceback
        render.print_error(str(exc))
        return 1

    if verbose:
        render.print_trace(result.get("trace", []))
    if result.get("route") == "error":
        render.print_error(result.get("output", "unknown kernel error"))
        return 1
    render.print_output(result.get("output", ""))
    return 0


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        # call the implementation, not the typer-decorated command — invoking
        # that as a plain function would pass OptionInfo defaults through
        from .repl import run_repl

        asyncio.run(run_repl(model=None))


@app.command("run")
def run(
    words: list[str] = typer.Argument(..., help="input line, e.g. '/sh find files over 100MB'"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="show routing and rendered prompt; no model call"),
    model: str | None = typer.Option(None, "--model", "-m", help="model override (default: claude-opus-5)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="print the kernel trace"),
) -> None:
    """Run one line through the kernel and exit."""
    code = asyncio.run(run_line(" ".join(words), dry_run=dry_run, model=model, verbose=verbose))
    raise typer.Exit(code)


@app.command("list")
def list_commands() -> None:
    """Show the command registry."""
    render.print_command_table(load_registry())


@app.command("doctor")
def doctor() -> None:
    """Check auth and environment."""
    render.print_doctor_table(run_checks(KernelConfig.from_env()))


remote_app = typer.Typer(
    no_args_is_help=True,
    help="Drive a dev box over ssh: probe, monitor, and mirror AI interactions "
    "onto its physical display. Hosts are ~/.ssh/config aliases. (docs/FORGE.md)",
)
app.add_typer(remote_app, name="remote")


@remote_app.command("doctor")
def remote_doctor(host: str = typer.Argument(..., help="ssh alias of the box")) -> None:
    """Check the box: ssh, tmux console, monitor client, health floor."""
    from .. import remote

    checks = asyncio.run(remote.doctor(host))
    for name, ok, detail in checks:
        mark = "[ OK ]" if ok else "[FAIL]"
        typer.echo(f"{mark} {name:<17} {detail}")
    raise typer.Exit(0 if all(ok for _, ok, _ in checks) else 1)


@remote_app.command("health")
def remote_health(host: str = typer.Argument(..., help="ssh alias of the box")) -> None:
    """Run the deterministic health floor + probes on the box; print verdicts."""
    from .. import remote

    sections = asyncio.run(remote.gather(host))
    typer.echo(sections.get("health", "(no health section — floor failed to run)"))
    raise typer.Exit(0 if "[WARN]" not in sections.get("health", "") and "[CRIT]" not in sections.get("health", "") else 1)


@remote_app.command("setup")
def remote_setup(host: str = typer.Argument(..., help="ssh alias of the box")) -> None:
    """Install the monitoring kit on the box (user-level; sudo only if -n works)."""
    from .. import remote

    for action in asyncio.run(remote.setup(host)):
        typer.echo(f"  · {action}")


@remote_app.command("ask")
def remote_ask(
    host: str = typer.Argument(..., help="ssh alias of the box"),
    words: list[str] = typer.Argument(None, help="question about the box (default: health sweep)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="rendered prompt only; no model, no mirror"),
    model: str | None = typer.Option(None, "--model", "-m", help="model override"),
    no_mirror: bool = typer.Option(False, "--no-mirror", help="do not display the interaction on the box's monitor"),
) -> None:
    """Probe the box, reason over the readings with Claude, and mirror the
    interaction onto the box's physical monitor."""
    from .. import remote

    config = KernelConfig.from_env(model=model, dry_run=dry_run)
    answer = asyncio.run(
        remote.ask(host, " ".join(words or []), config, do_mirror=not no_mirror)
    )
    render.print_output(answer)


@app.command("repl")
def repl(
    model: str | None = typer.Option(None, "--model", "-m", help="model override"),
) -> None:
    """Start the interactive shell (also the default with no subcommand)."""
    from .repl import run_repl

    asyncio.run(run_repl(model=model))


def main() -> None:
    load_dotenv()
    from ..runtime.tracing import init_tracing

    init_tracing()  # no-op unless Phoenix is configured
    app()


if __name__ == "__main__":
    main()
