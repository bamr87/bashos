"""The bashOS interactive shell.

Slash commands route through the kernel, plain english is classified to the
best command, follow-ups reuse the last command, `exec` confirm-runs the last
bash fence, and `!` passes a line straight to the real shell.
"""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from ..config import KernelConfig
from ..kernel import build_kernel
from ..registry import load_registry
from ..runtime.auth import run_checks
from ..runtime.llm import models_for, resolve_backend
from . import execute, render
from .session import ConsoleSession

BUILTINS = ("help", "list", "doctor", "engine", "clear", "exec", "exit", "quit")
HISTORY_FILE = Path.home() / ".bashos_history"


async def _passthrough(command: str) -> None:
    code = await execute.run_command(command)
    if code:
        render.console.print(f"exit {code}", style="dim red")


async def _engine_rows(config: KernelConfig) -> list[tuple[str, str]]:
    """Live engine state for the `engine` builtin — boots it if it is not up."""
    from ..opencode.engine import get_engine
    from ..opencode.status import engine_rows

    return await engine_rows(await get_engine(config))


async def run_repl(model: str | None = None) -> None:
    config = KernelConfig.from_env(model=model)
    registry = load_registry()
    backend = resolve_backend(config)
    render.print_banner(config, backend)

    llm, classify_llm = models_for(config)
    try:
        await _session(config, registry, llm, classify_llm)
    finally:
        from ..opencode.engine import shutdown_engine

        await shutdown_engine()
    render.console.print("logout", style="dim")


async def _session(config: KernelConfig, registry: dict, llm, classify_llm) -> None:
    kernel = build_kernel(
        registry, llm, config, on_event=render.print_event, classify_llm=classify_llm
    )
    completer = WordCompleter(
        [f"/{name}" for name in registry] + list(BUILTINS),
        ignore_case=True,
        WORD=True,  # treat "/sh" as one word — without this, "/" breaks completion
    )
    session: PromptSession = PromptSession(history=FileHistory(str(HISTORY_FILE)))
    conversation = ConsoleSession()

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
        if line == "exec":
            command = conversation.runnable_from_last()
            if not command:
                render.print_error("nothing to exec — no bash fence in the last answer")
                continue
            code = await execute.confirm_and_run(command)
            if code:
                render.console.print(f"exit {code}", style="dim red")
            continue
        if line.startswith("!"):
            await _passthrough(line[1:].strip())
            continue

        payload = conversation.payload_for(line)

        try:
            with render.status():
                result = await kernel.ainvoke(payload)
        except Exception as exc:  # the REPL must survive any single failure
            render.print_error(str(exc))
            continue

        if result.get("route") == "error":
            render.print_error(result.get("output", "unknown kernel error"))
            continue

        output = result.get("output", "")
        conversation.record(line, result.get("command"), output)
        render.print_output(output)
