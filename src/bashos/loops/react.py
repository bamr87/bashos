"""The react loop: reason ↔ act on the real machine, read-only.

This loop no longer drives a model directly — it hands the task to the OpenCode
engine, which owns the agent loop and the tool broker, and binds it to the
`bashos` agent whose permission ruleset lives in `opencode/policy.py`:

  * read / glob / grep / list for inspection under the project root
  * bash deny-by-default, with an allowlist of diagnostic probes
  * edit / write / apply_patch / webfetch / websearch / task denied outright

The gate is the engine's, not a prompt's: a denied command never executes.
Every tool call streams to the terminal through `on_event` as it happens.

The probe allowlist is re-exported here because it is this loop's contract,
even though the engine is what enforces it.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import KernelConfig
from ..kernel.context import context_block, system_prompt
from ..kernel.state import KernelState
from ..opencode import policy, project
from ..opencode.policy import PROBE_COMMANDS, readonly_policy
from ..registry import CommandSpec
from .common import dry_run_report, usage_or_none

__all__ = ["PROBE_COMMANDS", "make_react_node", "readonly_policy"]


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
        agent = spec.agent or project.LOOP_AGENTS["react"]
        if config.dry_run:
            report = f"engine agent: {agent}\n{policy.describe_policy()}"
            return {
                "output": dry_run_report(spec, task, extra=report),
                "trace": ["react: dry-run"],
            }

        from ..opencode.engine import get_engine

        engine = await get_engine(config)
        result = await engine.act(
            task,
            system=system_prompt(spec.system),
            agent=agent,
            on_event=on_event,
        )
        steps = len(result.tool_calls)
        if result.failed:
            return {
                "error": f"react: engine run failed: {result.error}",
                "route": "error",
                "trace": [f"react: error after {steps} tool call(s)"],
            }
        return {
            "output": result.text.strip(),
            "trace": [f"react: {steps} tool call(s) via the opencode engine ({agent})"],
        }

    return loop_react
