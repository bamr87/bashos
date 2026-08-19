"""Async HTTP client for the OpenCode server API.

OpenCode is a client/server system: the TUI, the SDKs, and now bashOS are all
clients of the same locally-running server, which owns sessions, the reasoning
loop, the tool broker, and the permission gate. This module is bashOS's client —
a thin, typed-enough wrapper over the endpoints the kernel actually uses.

Everything is async; the terminal drives one event loop.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

# Prompts run a full agent loop — minutes, not seconds. The read timeout has to
# outlast the model, so only connect/write get short bounds.
PROMPT_TIMEOUT = httpx.Timeout(connect=10.0, read=1800.0, write=60.0, pool=10.0)
CONTROL_TIMEOUT = httpx.Timeout(15.0)


class OpencodeError(RuntimeError):
    """The engine refused a request or returned an unusable response."""


@dataclass
class ToolCall:
    """One tool invocation observed on a session."""

    tool: str
    call_id: str
    status: str
    title: str = ""
    input: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        detail = self.title or _first_str(
            self.input, ("command", "filePath", "path", "pattern", "query")
        )
        detail = " ".join(str(detail).split())
        if len(detail) > 88:
            detail = detail[:85] + "..."
        return f"{self.tool}({detail})" if detail else self.tool


def _first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if value := data.get(key):
            return str(value)
    return ""


@dataclass
class PromptResult:
    """The assistant message a prompt produced."""

    text: str
    tool_calls: list[ToolCall]
    error: str | None = None
    model: str = ""

    @property
    def failed(self) -> bool:
        return self.error is not None


class OpencodeClient:
    """Client for one OpenCode server instance."""

    def __init__(
        self,
        base_url: str,
        *,
        directory: str | None = None,
        auth: tuple[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._directory = directory
        self._auth = auth
        # the server is on loopback; a proxy in the environment must not eat it
        self._http = httpx.AsyncClient(
            base_url=self.base_url, timeout=CONTROL_TIMEOUT, trust_env=False, auth=auth
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> OpencodeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    @property
    def _params(self) -> dict[str, str]:
        return {"directory": self._directory} if self._directory else {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        params = {**self._params, **(kwargs.pop("params", None) or {})}
        try:
            response = await self._http.request(method, path, params=params, **kwargs)
        except httpx.HTTPError as exc:
            raise OpencodeError(f"engine unreachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise OpencodeError(
                f"engine {method} {path} → {response.status_code}: {response.text[:400]}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise OpencodeError(f"engine {method} {path}: non-JSON response") from exc

    # ---------------------------------------------------------------- health

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/global/health")

    async def version(self) -> str:
        return str((await self.health()).get("version", "unknown"))

    # ------------------------------------------------------------------ auth

    async def connected_providers(self) -> list[str]:
        payload = await self._request("GET", "/provider")
        return [str(p) for p in (payload or {}).get("connected", [])]

    async def set_auth(self, provider_id: str, credential: dict[str, object]) -> None:
        await self._request("PUT", f"/auth/{provider_id}", json=credential)

    # -------------------------------------------------------------- registry

    async def agents(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/agent") or []

    async def config(self) -> dict[str, Any]:
        return await self._request("GET", "/config") or {}

    # -------------------------------------------------------------- sessions

    async def create_session(self, *, title: str, agent: str | None = None) -> str:
        body: dict[str, Any] = {"title": title}
        if agent:
            body["agent"] = agent
        session = await self._request("POST", "/session", json=body)
        session_id = (session or {}).get("id")
        if not session_id:
            raise OpencodeError("engine created a session with no id")
        return str(session_id)

    async def delete_session(self, session_id: str) -> None:
        try:
            await self._request("DELETE", f"/session/{session_id}")
        except OpencodeError:
            pass  # cleanup is best-effort; a stale session is not a failure

    async def abort(self, session_id: str) -> None:
        try:
            await self._request("POST", f"/session/{session_id}/abort")
        except OpencodeError:
            pass

    async def prompt(
        self,
        session_id: str,
        text: str,
        *,
        agent: str | None = None,
        system: str | None = None,
        model: str | None = None,
        tools: dict[str, bool] | None = None,
    ) -> PromptResult:
        """Send one message and wait for the assistant to finish."""
        body: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if agent:
            body["agent"] = agent
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools
        if model and (parsed := split_model(model)):
            body["model"] = {"providerID": parsed[0], "modelID": parsed[1]}
        payload = await self._request(
            "POST", f"/session/{session_id}/message", json=body, timeout=PROMPT_TIMEOUT
        )
        return _read_message(payload or {})

    # ----------------------------------------------------------- permissions

    async def reject_permission(self, session_id: str, permission_id: str) -> None:
        """Refuse an approval request (v1 permission protocol)."""
        with contextlib.suppress(OpencodeError):
            await self._request(
                "POST",
                f"/session/{session_id}/permissions/{permission_id}",
                json={"response": "reject"},
            )

    async def reject_permission_v2(self, request_id: str, message: str) -> None:
        """Refuse an approval request (v2 permission protocol)."""
        with contextlib.suppress(OpencodeError):
            await self._request(
                "POST",
                f"/permission/{request_id}/reply",
                json={"reply": "reject", "message": message},
            )

    # ---------------------------------------------------------------- events

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """The global server-sent event stream, decoded to dicts.

        The global stream rather than the per-session one: it opens with a
        `server.connected` frame, which is the only reliable signal that the
        subscription is live — so a caller can start watching before it
        prompts and miss nothing.
        """
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
            trust_env=False,
            auth=self._auth,
        ) as http:
            async with http.stream("GET", "/event", params=self._params) as response:
                if response.status_code >= 400:
                    return
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        yield json.loads(raw)
                    except ValueError:
                        continue


def split_model(model: str) -> tuple[str, str] | None:
    """"provider/model" → (provider, model). A bare id has no provider."""
    provider, _, name = model.partition("/")
    return (provider, name) if name else None


def _read_message(payload: dict[str, Any]) -> PromptResult:
    info = payload.get("info") or {}
    texts: list[str] = []
    calls: list[ToolCall] = []
    for part in payload.get("parts") or []:
        kind = part.get("type")
        if kind == "text" and not part.get("synthetic"):
            texts.append(str(part.get("text", "")))
        elif kind == "tool":
            calls.append(read_tool_part(part))
    error = info.get("error")
    return PromptResult(
        text="\n".join(t for t in texts if t.strip()).strip(),
        tool_calls=calls,
        error=_error_text(error) if error else None,
        model=str(info.get("modelID", "")),
    )


def read_tool_part(part: dict[str, Any]) -> ToolCall:
    state = part.get("state") or {}
    return ToolCall(
        tool=str(part.get("tool", "tool")),
        call_id=str(part.get("callID", "")),
        status=str(state.get("status", "")),
        title=str(state.get("title") or ""),
        input=state.get("input") or {},
    )


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        data = error.get("data") or {}
        message = data.get("message") or error.get("message") or error.get("name")
        return str(message or json.dumps(error)[:300])
    return str(error)
