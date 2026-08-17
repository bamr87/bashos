"""Backend resolution: hand every loop a LangChain chat model.

Three backends, one interface:

  opencode     (default)  the OpenCode engine — a local `opencode serve` that
                          owns the agent loop, the tool broker, and the
                          permission gate. Authenticated with the user's Claude
                          Code OAuth login. No API key, billed to the
                          subscription.
  claude-code             Claude Agent SDK → the `claude` harness directly.
                          The fallback when the engine is not installed;
                          completions only, no bashOS tool policy.
  api                     langchain-anthropic ChatAnthropic → ANTHROPIC_API_KEY
                          (or ANTHROPIC_AUTH_TOKEN) → direct API billing.

Preference order: the engine wins when reachable, then a Claude Code login,
then an API key. Override with BASHOS_BACKEND=opencode|claude-code|api.

Only the `opencode` backend carries the full bashOS story — policy-gated tool
use, sessions, audit. The other two are completion-only escape hatches; the
react loop requires the engine.
"""

from __future__ import annotations

import os
import shutil

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from ..config import BACKEND_API, BACKEND_CLAUDE_CODE, BACKEND_OPENCODE, KernelConfig


def message_text(message: BaseMessage) -> str:
    """Extract plain text from a LangChain message, whatever its content shape."""
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def flatten_messages(messages: list[BaseMessage]) -> tuple[str | None, str]:
    """Flatten a LangChain message list into (system_prompt, prompt).

    Both single-completion backends take a system string and one prompt string
    rather than a message array, so the conversation is folded into labelled
    turns. Single-turn calls — which is what every bashOS loop makes — come out
    as the bare user text.
    """
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


def has_opencode() -> bool:
    from ..opencode import server

    return bool(server.configured_url()) or server.find_binary() is not None


def has_claude_code() -> bool:
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) or shutil.which("claude") is not None


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def resolve_backend(config: KernelConfig) -> str:
    if config.backend:
        return config.backend
    if has_opencode():
        return BACKEND_OPENCODE
    if has_claude_code():
        return BACKEND_CLAUDE_CODE
    if has_api_key():
        return BACKEND_API
    # nothing detected: default to the engine so the failure message points at
    # the primary setup path (install opencode) rather than API keys
    return BACKEND_OPENCODE


def get_chat_model(config: KernelConfig) -> BaseChatModel:
    backend = resolve_backend(config)
    if backend == BACKEND_API:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.model,
            max_tokens=config.max_output_tokens,
            default_request_timeout=300.0,
        )
    if backend == BACKEND_CLAUDE_CODE:
        from .claude_code import ClaudeCodeChatModel

        return ClaudeCodeChatModel(model=config.model)
    from ..opencode.model import OpencodeChatModel

    return OpencodeChatModel(kernel_config=config)
