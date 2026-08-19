"""The bashOS interactive shell.

Slash commands route through the kernel, plain english is classified to the
best command, and `!` passes a line straight to the real shell — the terminal
stays the one interface for everything.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from ..config import KernelConfig
from ..kernel import build_kernel
from ..registry import load_registry
from ..runtime.auth import run_checks
from ..runtime.llm import get_chat_model, resolve_backend
from . import render

BUILTINS = ("help", "list", "doctor", "engine", "clear", "exit", "quit")
HISTORY_FILE = Path.home() / ".bashos_history"


async def _passthrough(command: str) -> None:
    proc = await asyncio.create_subprocess_shell(command)
    code = await proc.wait()
    if code:
        render.console.print(f"exit {code}", style="dim red")


async def _engine_rows(config: KernelConfig) -> list[tuple[str, str]]:
    """Live engine state for the `engine` builtin — boots it if it is not up."""
    from ..opencode.engine import get_engine

    engine = await get_engine(config)
    agents = [a.get("name", "?") for a in await engine.client.agents()]
    return [
        ("url", f"{engine.url} ({'supervised' if engine.supervised else 'attached'})"),
        ("version", engine.version),
        ("auth", engine.auth_status),
        ("providers", ", ".join(await engine.client.connected_providers()) or "none"),
        ("config", engine.sync_status),
        ("agents", ", ".join(sorted(agents))),
    ]


async def run_repl(model: str | None = None) -> None:
    config = KernelConfig.from_env(model=model)
    registry = load_registry()
    backend = resolve_backend(config)
    render.print_banner(config, backend)

    llm = get_chat_model(config)
    try:
        await _session(config, registry, llm)
    finally:
        # the REPL may have supervised an engine process — take it down with us
        from ..opencode.engine import shutdown_engine

        await shutdown_engine()
    render.console.print("logout", style="dim")


async def _session(config: KernelConfig, registry: dict, llm) -> None:
    kernel = build_kernel(registry, llm, config, on_event=render.print_event)
    completer = WordCompleter(
        [f"/{name}" for name in registry] + list(BUILTINS),
        ignore_case=True,
        WORD=True,  # treat "/sh" as one word — without this, "/" breaks completion
    )
    session: PromptSession = PromptSession(history=FileHistory(str(HISTORY_FILE)))

    while True:
        try:
            with patch_stdout():
                line = await session.prompt_async("bashos ▸ ", completer=completer)
        except KeyboardInterrupt:
            continue  # ctrl-c clears the line, like a shell
        except EOFError:
            break  # ctrl-d exits

        line = line.strip()
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "engine":
            render.print_engine_status(await _engine_rows(config))
            continue
        if line == "clear":
            render.console.clear()
            continue
        if line in ("help", "list"):
            render.print_command_table(registry)
            continue
        if line == "doctor":
            render.print_doctor_table(run_checks(config))
            continue
        if line.startswith("!"):
            await _passthrough(line[1:].strip())
            continue

        try:
            with render.status():
                result = await kernel.ainvoke({"input": line, "trace": []})
        except Exception as exc:  # the REPL must survive any single failure
            render.print_error(str(exc))
            continue

        if result.get("route") == "error":
            render.print_error(result.get("output", "unknown kernel error"))
        else:
            render.print_output(result.get("output", ""))
