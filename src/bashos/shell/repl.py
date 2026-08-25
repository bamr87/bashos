"""The bashOS interactive shell.

Slash commands route through the kernel, plain english is classified to the
best command, follow-ups reuse the last command, `exec` confirm-runs the last
bash fence, and `!` passes a line straight to the real shell.
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
from ..runtime.llm import models_for, resolve_backend
from . import execute, render

BUILTINS = ("help", "list", "doctor", "engine", "clear", "exec", "exit", "quit")
HISTORY_FILE = Path.home() / ".bashos_history"
_HISTORY_TURNS = 3
_EXCERPT = 280


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat[: _EXCERPT - 3] + "..." if len(flat) > _EXCERPT else flat


def _format_history(turns: list[tuple[str, str, str]]) -> str:
    chunks = []
    for user, command, output in turns[-_HISTORY_TURNS:]:
        chunks.append(f"in: {user}\nvia: /{command}\nout: {_excerpt(output)}")
    return "\n---\n".join(chunks)


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
    turns: list[tuple[str, str, str]] = []
    last_output = ""

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
            command = execute.runnable_from(last_output)
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

        payload: dict = {"input": line, "trace": []}
        if turns:
            last_user, last_command, _ = turns[-1]
            payload["history"] = _format_history(turns)
            payload["last_command"] = last_command
            payload["last_input"] = last_user

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
        last_output = output
        if command := result.get("command"):
            turns.append((line, command, output))
        render.print_output(output)
