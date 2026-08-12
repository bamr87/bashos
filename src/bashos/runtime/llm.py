"""Backend resolution: hand every loop a LangChain chat model.

Two backends, one interface:

  claude-code  (default)  Claude Agent SDK → the `claude` harness → the user's
                          Claude Code OAuth login or CLAUDE_CODE_OAUTH_TOKEN.
                          No API key, billed to the subscription.
  api                     langchain-anthropic ChatAnthropic → ANTHROPIC_API_KEY
                          (or ANTHROPIC_AUTH_TOKEN) → direct API billing.

Preference order: an available Claude Code wins; API key is the fallback.
Override with BASHOS_BACKEND=claude-code|api.
"""

from __future__ import annotations

import os
import shutil

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from ..config import BACKEND_API, BACKEND_CLAUDE_CODE, KernelConfig


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


def has_claude_code() -> bool:
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")) or shutil.which("claude") is not None


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def resolve_backend(config: KernelConfig) -> str:
    if config.backend:
        return config.backend
    if has_claude_code():
        return BACKEND_CLAUDE_CODE
    if has_api_key():
        return BACKEND_API
    # nothing detected: default to claude-code so the failure message points at
    # the primary setup path (`claude` login) rather than API keys
    return BACKEND_CLAUDE_CODE


def get_chat_model(config: KernelConfig) -> BaseChatModel:
    backend = resolve_backend(config)
    if backend == BACKEND_API:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=config.model,
            max_tokens=config.max_output_tokens,
            default_request_timeout=300.0,
        )
    from .claude_code import ClaudeCodeChatModel

    return ClaudeCodeChatModel(model=config.model)
