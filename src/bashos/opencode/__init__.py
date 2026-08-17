"""The OpenCode engine — the reasoning core bashOS is built on.

bashOS's own reference architecture is explicit that the agent kernel should
not contain a reasoning loop: *"Claude Code, Codex CLI, Gemini CLI, OpenCode —
any of them can run on bashOS as the reasoning engine, the way any POSIX
program runs on Linux."* This package is that separation, made real. OpenCode —
open source, client/server, provider-agnostic — supplies the agent loop, the
tool broker, session state, and the permission gate. bashOS supplies the
userland registry, the routing kernel, the policy, the terminal, and the audit
trace.

    registry.py   .claude/commands/*.md      what the system can do
    kernel/       parse → classify → loop    which program runs
    opencode/     ── policy.py               what it is allowed to touch
                  ── project.py              the registry, compiled for the engine
                  ── auth.py                 Claude Code OAuth → engine credential
                  ── server.py               engine lifecycle
                  ── client.py               engine API
                  ── engine.py               complete() / act()
                  ── model.py                the LangChain face of complete()

Auth is subscription-native by default: the user's Claude Code login is lifted
into the engine, so every session — reasoning, tools, titles — bills the
subscription and no API key is required.
"""

from .client import OpencodeClient, OpencodeError, PromptResult, ToolCall
from .engine import OpencodeEngine, get_engine, shutdown_engine
from .model import OpencodeChatModel

__all__ = [
    "OpencodeChatModel",
    "OpencodeClient",
    "OpencodeEngine",
    "OpencodeError",
    "PromptResult",
    "ToolCall",
    "get_engine",
    "shutdown_engine",
]
