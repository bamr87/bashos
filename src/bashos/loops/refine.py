"""The refine loop: generate → verify → repair, bounded.

A LangGraph cycle where the critic is a real external verifier, not the model
grading itself:

    draft ──▶ verify(shellcheck) ──▶ finalize
                 │        ▲
                 ▼        │
               repair ────┘   (at most config.refine_max_iters passes)

If shellcheck isn't installed, verification is skipped and the output is
labeled unverified.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from typing import NotRequired

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from ..config import KernelConfig
from ..kernel.context import context_block, system_prompt
from ..kernel.state import KernelState
from ..registry import CommandSpec
from .common import dry_run_report, usage_or_none

_CODE_FENCE = re.compile(r"```(?:bash|sh|shell)?\s*\n(.*?)```", re.DOTALL)


class RefineState(KernelState):
    draft: NotRequired[str]
    critique: NotRequired[str]
    lint_status: NotRequired[str]  # "clean" | "issues" | "unavailable"
    iterations: NotRequired[int]


def extract_script(text: str) -> str:
    match = _CODE_FENCE.search(text)
    return (match.group(1) if match else text).strip()


def find_shellcheck() -> str | None:
    return shutil.which("shellcheck")


async def run_shellcheck(script: str) -> tuple[str, str]:
    """Lint a script from stdin. Returns (status, report)."""
    exe = find_shellcheck()
    if exe is None:
        return "unavailable", ""
    proc = await asyncio.create_subprocess_exec(
        exe,
        "--shell=bash",
        "--format=gcc",
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate(script.encode())
    if proc.returncode == 0:
        return "clean", ""
    return "issues", stdout.decode().strip()


_STATUS_NOTE = {
    "clean": "verified: shellcheck clean",
    "issues": "warning: shellcheck still reports issues — review before running",
    "unavailable": "note: shellcheck not installed — script is unverified",
}


def build_refine_graph(
    registry: dict[str, CommandSpec],
    llm: BaseChatModel | None,
    config: KernelConfig,
):
    from ..runtime.llm import message_text

    async def draft(state: RefineState) -> dict:
        spec = registry[state["command"]]
        args = state.get("args", "")
        if usage := usage_or_none(spec, args):
            return {"output": usage, "trace": ["refine: missing args → usage"]}
        prompt = f"{spec.render(args)}\n\n{context_block()}"
        if config.dry_run or llm is None:
            return {"output": dry_run_report(spec, prompt), "trace": ["refine: dry-run"]}
        reply = await llm.ainvoke(
            [SystemMessage(system_prompt(spec.system)), HumanMessage(prompt)]
        )
        return {
            "draft": extract_script(message_text(reply)),
            "iterations": 0,
            "trace": ["refine: draft generated"],
        }

    async def verify(state: RefineState) -> dict:
        status, report = await run_shellcheck(state["draft"])
        return {
            "lint_status": status,
            "critique": report,
            "trace": [f"refine: shellcheck → {status}"],
        }

    async def repair(state: RefineState) -> dict:
        spec = registry[state["command"]]
        passes = state.get("iterations", 0) + 1
        reply = await llm.ainvoke(  # type: ignore[union-attr]  # unreachable when llm is None
            [
                SystemMessage(system_prompt(spec.system)),
                HumanMessage(
                    "Your bash script:\n\n```bash\n"
                    f"{state['draft']}\n```\n\nshellcheck reports:\n\n"
                    f"{state['critique']}\n\n"
                    "Fix every reported issue without changing behavior. "
                    "Return ONLY the corrected script in a single ```bash fence."
                ),
            ]
        )
        return {
            "draft": extract_script(message_text(reply)),
            "iterations": passes,
            "trace": [f"refine: repair pass {passes}"],
        }

    def finalize(state: RefineState) -> dict:
        note = _STATUS_NOTE[state.get("lint_status", "unavailable")]
        return {
            "output": f"```bash\n{state['draft']}\n```\n\n{note}",
            "trace": ["refine: finalized"],
        }

    def after_draft(state: RefineState) -> str:
        # usage / dry-run short-circuit already produced output
        return END if state.get("output") else "verify"

    def after_verify(state: RefineState) -> str:
        needs_repair = (
            state.get("lint_status") == "issues"
            and state.get("iterations", 0) < config.refine_max_iters
        )
        return "repair" if needs_repair else "finalize"

    graph = StateGraph(RefineState)
    graph.add_node("draft", draft)
    graph.add_node("verify", verify)
    graph.add_node("repair", repair)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "draft")
    graph.add_conditional_edges("draft", after_draft, ["verify", END])
    graph.add_conditional_edges("verify", after_verify, ["repair", "finalize"])
    graph.add_edge("repair", "verify")
    graph.add_edge("finalize", END)
    return graph.compile()
