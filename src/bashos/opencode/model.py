"""LangChain chat-model adapter over the OpenCode engine.

The kernel's graph, its classifier, and the stateless loops are written against
one interface — `BaseChatModel`. This adapter puts the engine behind that
interface, so making OpenCode the core changed what runs underneath without
changing a single loop's shape.

Completions are sealed: the `bashos-sealed` agent has every tool switched off,
so a "one call, one answer" loop cannot silently become an agent run. Agentic
work goes through `engine.act()` instead, where the tool loop is the feature.

The engine boots lazily on the first call, which keeps `get_chat_model()`
synchronous and keeps `bashos --help` from starting a server.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from ..config import KernelConfig
from ..runtime.llm import flatten_messages


class OpencodeChatModel(BaseChatModel):
    """Chat completions served by the OpenCode engine on Claude Code OAuth."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kernel_config: KernelConfig

    @property
    def _llm_type(self) -> str:
        return "bashos-opencode"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.kernel_config.model, "engine": "opencode"}

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        from .engine import get_engine

        system, prompt = flatten_messages(list(messages))
        engine = await get_engine(self.kernel_config)
        text = await engine.complete(prompt, system=system)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop=stop, **kwargs))
        raise RuntimeError(
            "OpencodeChatModel is async inside a running event loop — use `await llm.ainvoke(...)`"
        )
