"""LangChain chat-model adapter over the Claude Agent SDK.

This is the bridge that lets every LangGraph loop in bashOS run on the user's
Claude Code OAuth credentials: LangChain interface on top, the `claude` harness
underneath. No API key required — auth comes from the logged-in Claude Code CLI
or a CLAUDE_CODE_OAUTH_TOKEN minted with `claude setup-token`.

Single-completion calls only (tools off, one turn). Agentic tool use goes
through loops/react.py, which drives the harness directly.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ..config import DEFAULT_MODEL
from .llm import message_text

_INSTALL_HINT = (
    "claude-agent-sdk is not installed — reinstall bashOS (`pip install -e .`)"
)
_EMPTY_HINT = (
    "no response from the Claude Code harness — run `bashos doctor` "
    "(is the `claude` CLI installed and logged in?)"
)

# Completions must never enter a tool loop: deny the whole builtin toolset
# explicitly (an empty allowed_tools alone still leaves tools visible to the
# model, and a denied attempt burns a turn).
_NO_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebSearch", "WebFetch", "NotebookEdit", "Task", "TodoWrite",
]
_NO_TOOLS_NOTE = "You have no tools in this context — answer directly in a single message."


def _split_messages(messages: list[BaseMessage]) -> tuple[str | None, str]:
    """Flatten a LangChain message list into (system_prompt, prompt)."""
    system_parts: list[str] = []
    turns: list[tuple[str, str]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            system_parts.append(message_text(message))
        else:
            role = "Assistant" if message.type == "ai" else "User"
            turns.append((role, message_text(message)))
    system = "\n\n".join(p for p in system_parts if p) or None
    if len(turns) <= 1:
        prompt = turns[0][1] if turns else ""
    else:
        prompt = "\n\n".join(f"{role}: {text}" for role, text in turns)
    return system, prompt


class ClaudeCodeChatModel(BaseChatModel):
    """Chat completions served by the Claude Code harness (Claude Agent SDK)."""

    model: str = DEFAULT_MODEL

    @property
    def _llm_type(self) -> str:
        return "bashos-claude-code"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model}

    async def _acomplete(self, messages: list[BaseMessage]) -> str:
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                TextBlock,
                query,
            )
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(_INSTALL_HINT) from exc

        system, prompt = _split_messages(messages)
        system = f"{system}\n\n{_NO_TOOLS_NOTE}" if system else _NO_TOOLS_NOTE
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=self.model,
            disallowed_tools=_NO_TOOLS,
            max_turns=3,  # headroom for a stray denied tool attempt
        )
        parts: list[str] = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        if not parts:
            raise RuntimeError(_EMPTY_HINT)
        return "".join(parts)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        text = await self._acomplete(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop=stop, **kwargs))
        raise RuntimeError(
            "ClaudeCodeChatModel is async inside a running event loop — use `await llm.ainvoke(...)`"
        )
