"""The react loop: reason ↔ act on the real machine, read-only.

This loop hands the task to the Claude Code harness (Claude Agent SDK) — the
same agent runtime the user's subscription already powers — under an explicit
tool policy:

  * Read / Glob / Grep for file inspection under the current directory
  * Bash restricted to an allowlist of diagnostic probes (uname, df, ps, ...)
  * Write/Edit and network tools disallowed outright

Anything outside the policy is denied by the harness and the model adapts.
Every tool action is surfaced to the terminal via `on_event` as it happens.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from ..config import KernelConfig
from ..kernel.context import context_block, system_prompt
from ..kernel.state import KernelState
from ..registry import CommandSpec
from .common import dry_run_report, usage_or_none

READ_TOOLS = ["Read", "Glob", "Grep"]

# Read-only diagnostic probes the agent may run via Bash. Deny-by-default:
# anything not matching these patterns is refused by the harness.
PROBE_COMMANDS = [
    "uname", "uptime", "df", "du", "ps", "top", "vm_stat", "free",
    "sw_vers", "sysctl", "ls", "which", "whoami", "id", "date",
    "netstat", "head", "wc", "file", "stat", "env", "git status", "git log",
    # the deterministic health floor (docs/FORGE.md) — read-only by contract
    "bin/os-health", "./bin/os-health",
    # read-only tmux verbs, so /health can inspect a dashboard session;
    # deliberately narrow — never bare "tmux" (that would allow kill-server)
    "tmux list-", "tmux capture-pane", "tmux has-session", "tmux display-message",
]

DISALLOWED_TOOLS = ["Write", "Edit", "NotebookEdit", "WebSearch", "WebFetch"]


def readonly_policy() -> list[str]:
    return [*READ_TOOLS, *(f"Bash({command}:*)" for command in PROBE_COMMANDS)]


def describe_tool(name: str, tool_input: dict) -> str:
    detail = (
        tool_input.get("command")
        or tool_input.get("file_path")
        or tool_input.get("pattern")
        or ""
    )
    detail = str(detail).replace("\n", " ")
    if len(detail) > 88:
        detail = detail[:85] + "..."
    return f"{name}({detail})" if detail else name


def make_react_node(
    registry: dict[str, CommandSpec],
    config: KernelConfig,
    on_event: Callable[[str], None] | None = None,
):
    async def loop_react(state: KernelState) -> dict:
        spec = registry[state["command"]]
        args = state.get("args", "")
        if usage := usage_or_none(spec, args):
            return {"output": usage, "trace": ["react: missing args → usage"]}

        task = f"{spec.render(args)}\n\n{context_block()}"
        if config.dry_run:
            policy = "allowed tools: " + ", ".join(readonly_policy())
            return {
                "output": dry_run_report(spec, task, extra=policy),
                "trace": ["react: dry-run"],
            }

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                ToolUseBlock,
                query,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "claude-agent-sdk is not installed — reinstall bashOS (`pip install -e .`)"
            ) from exc

        options = ClaudeAgentOptions(
            system_prompt=system_prompt(spec.system),
            model=config.model,
            allowed_tools=readonly_policy(),
            disallowed_tools=DISALLOWED_TOOLS,
            max_turns=config.react_max_turns,
            cwd=os.getcwd(),
        )

        last_text = ""
        final_result: str | None = None
        steps = 0
        async for message in query(prompt=task, options=options):
            if isinstance(message, AssistantMessage):
                texts: list[str] = []
                for block in message.content:
                    if isinstance(block, TextBlock):
                        texts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        steps += 1
                        if on_event:
                            on_event(describe_tool(block.name, block.input))
                if joined := "".join(texts).strip():
                    last_text = joined
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    return {
                        "error": f"react: agent loop failed: {message.result or 'unknown error'}",
                        "route": "error",
                        "trace": [f"react: error after {steps} tool call(s)"],
                    }
                final_result = message.result

        return {
            "output": (final_result or last_text).strip(),
            "trace": [f"react: {steps} tool call(s) via the Claude Code harness"],
        }

    return loop_react
