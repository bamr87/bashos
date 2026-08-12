"""The prompt loop: render the command spec, make one model call, answer."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..config import KernelConfig
from ..kernel.context import context_block, system_prompt
from ..kernel.state import KernelState
from ..registry import CommandSpec
from .common import dry_run_report, usage_or_none


def make_prompt_node(
    registry: dict[str, CommandSpec],
    llm: BaseChatModel | None,
    config: KernelConfig,
):
    async def loop_prompt(state: KernelState) -> dict:
        spec = registry[state["command"]]
        args = state.get("args", "")
        if usage := usage_or_none(spec, args):
            return {"output": usage, "trace": ["prompt: missing args → usage"]}

        prompt = f"{spec.render(args)}\n\n{context_block()}"
        if config.dry_run or llm is None:
            return {"output": dry_run_report(spec, prompt), "trace": ["prompt: dry-run"]}

        from ..runtime.llm import message_text

        reply = await llm.ainvoke(
            [SystemMessage(system_prompt(spec.system)), HumanMessage(prompt)]
        )
        return {
            "output": message_text(reply).strip(),
            "trace": [f"prompt: 1 model call ({llm._llm_type})"],
        }

    return loop_prompt
