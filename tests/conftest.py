"""Shared fixtures: a deterministic fake chat model and the real registry."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bashos.registry import find_root, load_registry


class FakeChat(BaseChatModel):
    """Returns queued replies in order; repeats the last one when exhausted."""

    replies: list[str]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _next(self) -> ChatResult:
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=reply))])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._next()

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._next()


@pytest.fixture
def registry():
    return load_registry(find_root(Path(__file__).parent))
