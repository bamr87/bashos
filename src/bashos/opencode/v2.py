"""OpenCode 2's wire shapes, translated into the OpenCode 1 shapes the rest of bashOS reads.

OpenCode 2 (bamr87/bashos#71) serves its API under `/api`, wraps most answers in
`{"data": …}`, admits a prompt and runs it in the background instead of answering
the POST, and streams a different set of events. Rather than teach the kernel,
the event bus and the watchers two dialects, the client translates OpenCode 2
into OpenCode 1's shapes at the edge, here, and everything above it is unchanged:

  message_payload()   a finished OpenCode 2 turn → OpenCode 1's `{"info", "parts"}`
  EventNormalizer     OpenCode 2 SSE frames → OpenCode 1 `{"type", "properties"}` events

Every shape below was read off a live OpenCode 2.0.20 engine
(tests/fixtures/opencode-2.0.20-*.json), not from documentation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# OpenCode 2's error `type` → the OpenCode 1 error `name` that client.classify_result_error reads.
ERROR_NAMES = {
    "provider.auth": "ProviderAuthError",
    "auth": "AuthError",
    "aborted": "MessageAbortedError",
    "interrupted": "MessageAbortedError",
}


def unwrap(payload: Any) -> Any:
    """OpenCode 2 wraps an answer in `{"data": …}` (plus `location`/`cursor` beside it)."""
    if isinstance(payload, Mapping) and "data" in payload:
        return payload["data"]
    return payload


def tool_part(call_id: str, name: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """An OpenCode 1 tool part, which `client.read_tool_part` reads."""
    metadata = state.get("metadata") or {}
    return {
        "type": "tool",
        "tool": name or "tool",
        "callID": call_id,
        "state": {
            "status": str(state.get("status", "")),
            "input": state.get("input") or {},
            "title": str(metadata.get("title") or "") if isinstance(metadata, Mapping) else "",
        },
    }


def _error(error: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(error.get("type", ""))
    return {"name": ERROR_NAMES.get(kind, kind or "UnknownError"), "data": {"message": str(error.get("message", ""))}}


def message_payload(messages: list[Mapping[str, Any]], user_message_id: str) -> dict[str, Any] | None:
    """The turn that answered `user_message_id`, as OpenCode 1's prompt response.

    `messages` is the session timeline, oldest first (`GET /api/session/{id}/message`). A turn
    runs from our user message to the `idle` marker after it; until that marker exists the turn
    is still running and this returns None. Text comes from the turn's last assistant message
    (the answer, as OpenCode 1 returned it); tool calls come from every step of the turn.
    """
    start = next((i for i, m in enumerate(messages) if m.get("id") == user_message_id), None)
    if start is None:
        return None
    turn: list[Mapping[str, Any]] = []
    idle: Mapping[str, Any] | None = None
    for message in messages[start + 1:]:
        if message.get("type") == "idle":
            idle = message
            break
        turn.append(message)
    if idle is None:
        return None

    assistants = [m for m in turn if m.get("type") == "assistant"]
    parts: list[dict[str, Any]] = []
    for message in assistants:
        for item in message.get("content") or []:
            if item.get("type") == "tool":
                parts.append(tool_part(str(item.get("id", "")), str(item.get("name", "")), item.get("state") or {}))
    last = assistants[-1] if assistants else {}
    for item in last.get("content") or []:
        if item.get("type") == "text":
            parts.append({"type": "text", "text": str(item.get("text", ""))})

    info: dict[str, Any] = {"modelID": str((last.get("model") or {}).get("id", ""))}
    if isinstance(last.get("error"), Mapping):
        info["error"] = _error(last["error"])
    if idle.get("outcome") == "interrupted":
        info["error"] = {"name": "MessageAbortedError", "data": {"message": "interrupted"}}
    elif idle.get("outcome") == "failed" and "error" not in info:
        info["error"] = {"name": "UnknownError", "data": {"message": "the engine reported a failed turn"}}
    return {"info": info, "parts": parts}


class EventNormalizer:
    """OpenCode 2 SSE frames → the OpenCode 1 events `engine.watch_events` and the bus read.

    Stateful per stream: OpenCode 2 streams text as deltas and names a tool only when its
    input starts, while OpenCode 1 sent cumulative text snapshots and whole tool parts.
    Frames with no OpenCode 1 equivalent pass through under their own type, carrying their
    `data` as `properties`, so routing by sessionID still works and watchers ignore them.
    """

    def __init__(self) -> None:
        self._text: dict[str, str] = {}
        self._tools: dict[str, str] = {}  # call id → tool name
        self._inputs: dict[str, Any] = {}  # call id → its input, which later frames omit

    def __call__(self, frame: Mapping[str, Any]) -> dict[str, Any] | None:
        kind = str(frame.get("type", ""))
        data = frame.get("data")
        data = data if isinstance(data, Mapping) else {}
        session_id = data.get("sessionID")
        if not kind:
            return None
        if kind == "permission.asked":
            # session-scoped, like OpenCode 1's: the watcher refuses it through the session
            return {"type": "permission.asked", "properties": {
                "id": data.get("id"),
                "sessionID": session_id,
                "permission": data.get("action"),
                "patterns": list(data.get("resources") or []),
            }}
        if kind in ("session.text.delta", "session.text.ended"):
            part_id = f"{data.get('assistantMessageID', '')}:{data.get('ordinal', 0)}"
            if kind == "session.text.delta":
                text = self._text.get(part_id, "") + str(data.get("delta", ""))
            else:
                text = str(data.get("text", self._text.get(part_id, "")))
            self._text[part_id] = text
            return self._part(session_id, {"type": "text", "id": part_id, "text": text})
        if kind.startswith("session.tool."):
            return self._tool(kind, session_id, data)
        return {"type": kind, "properties": dict(data)}

    def _tool(self, kind: str, session_id: Any, data: Mapping[str, Any]) -> dict[str, Any] | None:
        call_id = str(data.get("id", ""))
        if kind == "session.tool.input.started":
            self._tools[call_id] = str(data.get("name", ""))
            state: dict[str, Any] = {"status": "pending"}
        elif kind == "session.tool.called":
            self._inputs[call_id] = data.get("input") or {}
            state = {"status": "running"}
        elif kind == "session.tool.success":
            state = {"status": "completed", "metadata": data.get("metadata") or {}}
        elif kind == "session.tool.failed":
            state = {"status": "error"}
        else:
            return {"type": kind, "properties": dict(data)}
        state["input"] = self._inputs.get(call_id, {})
        return self._part(session_id, tool_part(call_id, self._tools.get(call_id, ""), state))

    @staticmethod
    def _part(session_id: Any, part: dict[str, Any]) -> dict[str, Any]:
        return {"type": "message.part.updated", "properties": {"sessionID": session_id, "part": part}}
