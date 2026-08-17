"""bashOS command line — every capability is reachable from the terminal.

    bashos                     interactive REPL (the default)
    bashos run /sh <request>   one-shot command
    bashos run <plain english> routed to the best command by the kernel
    bashos list                command table
    bashos doctor              auth + environment checks
    bashos opencode …          the engine: sync · status · auth · serve
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
    help="bashOS — terminal-first AI runtime on the OpenCode engine, "
    "authenticated with Claude Code OAuth.",
)


async def run_line(
    line: str,
    *,
    dry_run: bool = False,
    model: str | None = None,
    verbose: bool = False,
) -> int:
    from ..opencode.engine import shutdown_engine

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
    finally:
        # a one-shot run owns any engine it started — never leave one behind
        await shutdown_engine()

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


engine_app = typer.Typer(
    no_args_is_help=True,
    help="The OpenCode engine bashOS runs on: project the registry onto it, "
    "wire Claude Code OAuth into it, inspect it, or serve it. (docs/OPENCODE.md)",
)
app.add_typer(engine_app, name="opencode")


@engine_app.command("sync")
def engine_sync() -> None:
    """Compile .claude/commands/*.md and the tool policy into opencode.jsonc."""
    from ..opencode import project
    from ..registry import find_root

    root = find_root()
    path, changed = project.sync(root, load_registry(root))
    verb = "wrote" if changed else "already up to date:"
    typer.echo(f"{verb} {path}")


@engine_app.command("auth")
def engine_auth() -> None:
    """Show which credential the engine will run on, and where it came from."""
    from ..opencode import auth as engine_auth_mod

    env, description = engine_auth_mod.engine_environment()
    typer.echo(description)
    if not env:
        raise typer.Exit(1)
    # names only — the values are secrets and belong in the child process alone
    typer.echo(f"passed to the engine as: {', '.join(sorted(env))}")
    if credential := engine_auth_mod.discover():
        typer.echo(f"source: {credential.source}")
        typer.echo(f"refreshable: {credential.refreshable}")


@engine_app.command("status")
def engine_status() -> None:
    """Boot the engine and report what it is actually running."""
    from ..opencode.engine import OpencodeEngine

    async def go() -> list[tuple[str, str]]:
        engine = OpencodeEngine(KernelConfig.from_env())
        try:
            await engine.start()
            agents = [a.get("name", "?") for a in await engine.client.agents()]
            providers = await engine.client.connected_providers()
            return [
                ("url", f"{engine.url} ({'supervised' if engine.supervised else 'attached'})"),
                ("version", engine.version),
                ("auth", engine.auth_status),
                ("providers", ", ".join(providers) or "none connected"),
                ("config", engine.sync_status),
                ("agents", ", ".join(sorted(agents))),
            ]
        finally:
            await engine.stop()

    try:
        render.print_engine_status(asyncio.run(go()))
    except Exception as exc:
        render.print_error(str(exc))
        raise typer.Exit(1) from exc


@engine_app.command("serve")
def engine_serve() -> None:
    """Run an engine in the foreground; other bashOS processes can attach.

    Prints the export line to put in another terminal.
    """
    from ..opencode.engine import OpencodeEngine

    async def go() -> None:
        engine = OpencodeEngine(KernelConfig.from_env())
        await engine.start()
        typer.echo(f"engine listening on {engine.url}")
        typer.echo(f"auth: {engine.auth_status}")
        typer.echo("\nattach another terminal with:")
        typer.echo(f"  export BASHOS_OPENCODE_URL={engine.url}")
        if engine.password:
            # the socket brokers shell access, so it is password-guarded; an
            # attaching process needs the secret this run generated
            typer.echo(f"  export BASHOS_OPENCODE_PASSWORD={engine.password}")
        typer.echo("\nctrl-c to stop")
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await engine.stop()

    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        typer.echo("\nengine stopped")


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
