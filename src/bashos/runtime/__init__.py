"""Model runtime: backend resolution, the Claude Code OAuth adapter, and auth checks."""

from .llm import get_chat_model, message_text, resolve_backend

__all__ = ["get_chat_model", "message_text", "resolve_backend"]
