"""Model runtime: backend resolution, message flattening, and auth checks.

The default backend is the OpenCode engine (`bashos.opencode`); the Claude
Agent SDK adapter and the direct API client are fallbacks.
"""

from .llm import flatten_messages, get_chat_model, message_text, resolve_backend

__all__ = ["flatten_messages", "get_chat_model", "message_text", "resolve_backend"]
