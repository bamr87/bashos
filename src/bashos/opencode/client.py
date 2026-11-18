"""Async HTTP client for the OpenCode server API.

OpenCode is a client/server system: the TUI, the SDKs, and now bashOS are all
clients of the same locally-running server, which owns sessions, the reasoning
loop, the tool broker, and the permission gate. This module is bashOS's client —
a thin, typed-enough wrapper over the endpoints the kernel actually uses.

It speaks two engine majors (bamr87/bashos#71). `major` picks a route table
(`PATHS`); OpenCode 2's answers are translated into OpenCode 1's shapes in
`v2.py`, so every caller above this module sees one dialect. A supervised
engine's major comes from its `--version`; an attached one is probed
(`detect`).

Everything is async; the terminal drives one event loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import v2

# Prompts run a full agent loop — minutes, not seconds. The read timeout has to
# outlast the model, so only connect/write get short bounds.
PROMPT_TIMEOUT = httpx.Timeout(connect=10.0, read=1800.0, write=60.0, pool=10.0)
CONTROL_TIMEOUT = httpx.Timeout(15.0)

# One route table per engine major. OpenCode 1 serves its API at the root; OpenCode 2 serves
# it under /api (the root is its web UI, which answers any unknown path with HTML).
PATHS: dict[int, dict[str, str]] = {
    1: {
        "health": "/global/health",
        "providers": "/provider",
        "auth": "/auth/{provider}",
        "agents": "/agent",
        "config": "/config",
        "sessions": "/session",
        "session": "/session/{session}",
        "abort": "/session/{session}/abort",
        "prompt": "/session/{session}/message",
        "permission": "/session/{session}/permissions/{request}",
        "events": "/event",
    },
    2: {
        "health": "/api/info",
        "providers": "/api/provider",
        "auth": "/api/credential",
        "agents": "/api/agent",
        "config": "/api/config",
        "sessions": "/api/session",
        "session": "/api/session/{session}",
        "abort": "/api/session/{session}/interrupt",
        "prompt": "/api/session/{session}/prompt",
        "permission": "/api/session/{session}/permission/{request}/reply",
        "events": "/api/event",
        # OpenCode 2 only: a prompt is admitted, then run; its answer is read off the timeline
        "wait": "/api/experimental/session/{session}/wait",
        "messages": "/api/session/{session}/message",
        "agent": "/api/session/{session}/agent",
        "model": "/api/session/{session}/model",
        "instructions": "/api/experimental/session/{session}/instructions/entries/{key}",
        "evaluate": "/api/session/{session}/permission",
    },
}

# The session instruction entry that carries a per-call system prompt on OpenCode 2, which has
# no `system` field on a prompt.
SYSTEM_ENTRY = "bashos.system"
# OpenCode 2 boots a project's services on the first request that names it, and answers that
# request with an empty agent list; every engine has built-in agents, so empty means "booting".
AGENT_BOOT_ATTEMPTS = 25


class OpencodeError(RuntimeError):
    """The engine refused a request or returned an unusable response.

    Subclasses give a UI something to branch on; every existing
    `except OpencodeError` keeps catching all of them.
    """


class EngineUnreachable(OpencodeError):
    """No server answered — not installed, not started, or died."""


class EngineHTTPError(OpencodeError):
    """The server answered with an HTTP error status."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class EngineAuthError(EngineHTTPError):
    """The server rejected our credentials for its own socket (401/403)."""


class ProviderError(OpencodeError):
    """The engine ran but the model provider failed the request."""


class RunAborted(OpencodeError):
    """The user stopped the run — an outcome, not a failure."""


class EmptyCompletion(OpencodeError):
    """The engine finished without producing any text."""


def classify_result_error(error: dict[str, Any] | None) -> str:
    """'aborted' | 'auth' | 'provider' — from the engine's error `name`."""
    name = str((error or {}).get("name", ""))
    if name == "MessageAbortedError":
        return "aborted"
    if name in ("ProviderAuthError", "AuthError"):
        return "auth"
    return "provider"


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
    error_name: str = ""  # the engine's error class, e.g. "MessageAbortedError"

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def aborted(self) -> bool:
        """A user Stop is an outcome, not a failure — render 'stopped', not red."""
        return self.error_name == "MessageAbortedError"


class OpencodeClient:
    """Client for one OpenCode server instance."""

    def __init__(
        self,
        base_url: str,
        *,
        directory: str | None = None,
        auth: tuple[str, str] | None = None,
        major: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.major = major
        self._directory = directory
        self._auth = auth
        # OpenCode 2 keeps the agent, model and system prompt on the session, not the prompt:
        # remember what each session was given so a turn only re-sends what changed
        self._session_agent: dict[str, str] = {}
        self._session_model: dict[str, str] = {}
        self._session_system: dict[str, str] = {}
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
    def v2(self) -> bool:
        return self.major >= 2

    def _path(self, name: str, **parts: str) -> str:
        return PATHS[2 if self.v2 else 1][name].format(**parts)

    @property
    def _params(self) -> dict[str, str]:
        # OpenCode 1 scopes every call to a project with `directory`; OpenCode 2 scopes only the
        # routes that declare a location (`_location`), and its server's cwd is the default
        if self.v2:
            return {}
        return {"directory": self._directory} if self._directory else {}

    @property
    def _location(self) -> dict[str, str]:
        return {"location[directory]": self._directory} if self.v2 and self._directory else {}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        params = {**self._params, **(kwargs.pop("params", None) or {})}
        try:
            response = await self._http.request(method, path, params=params, **kwargs)
        except httpx.HTTPError as exc:
            raise EngineUnreachable(f"engine unreachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            message = f"engine {method} {path} → {response.status_code}: {response.text[:400]}"
            if response.status_code in (401, 403):
                raise EngineAuthError(message, response.status_code)
            raise EngineHTTPError(message, response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise OpencodeError(f"engine {method} {path}: non-JSON response") from exc

    # ---------------------------------------------------------------- health

    async def detect(self) -> int:
        """Which API an engine bashOS did not start speaks, probed from its routes.

        OpenCode 1 answers `/global/health` with JSON. On OpenCode 2 that path is
        the web UI, which answers with HTML, and `/api/info` answers instead.
        """
        self.major = 1
        try:
            await self.health()
            return self.major
        except (EngineUnreachable, EngineAuthError):
            raise
        except OpencodeError:
            pass
        self.major = 2
        await self.health()
        return self.major

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", self._path("health")) or {}

    async def version(self) -> str:
        return str((await self.health()).get("version", "unknown"))

    # ------------------------------------------------------------------ auth

    async def connected_providers(self) -> list[str]:
        payload = await self._request("GET", self._path("providers"), params=self._location)
        if self.v2:
            return [str(p.get("id")) for p in v2.unwrap(payload) or [] if p.get("activation") == "enabled"]
        return [str(p) for p in (payload or {}).get("connected", [])]

    async def set_auth(self, provider_id: str, credential: dict[str, object]) -> None:
        if not self.v2:
            await self._request("PUT", self._path("auth", provider=provider_id), json=credential)
            return
        if credential.get("type") != "api":
            raise OpencodeError("an OpenCode 2 engine takes only an API key over its API")
        value = {"type": "key", "key": credential.get("key")}
        await self._request("POST", self._path("auth"), json={"integrationID": provider_id, "value": value})

    # -------------------------------------------------------------- registry

    async def agents(self) -> list[dict[str, Any]]:
        if not self.v2:
            return await self._request("GET", self._path("agents")) or []
        for attempt in range(AGENT_BOOT_ATTEMPTS):
            agents = v2.unwrap(await self._request("GET", self._path("agents"), params=self._location))
            if agents or attempt == AGENT_BOOT_ATTEMPTS - 1:
                return list(agents or [])
            await asyncio.sleep(0.2)
        return []  # pragma: no cover - the loop always returns

    async def config(self) -> Any:
        return await self._request("GET", self._path("config"), params=self._location) or {}

    # -------------------------------------------------------------- sessions

    async def list_sessions(self) -> list[dict[str, Any]]:
        params = {"directory": self._directory} if self.v2 and self._directory else {}
        return v2.unwrap(await self._request("GET", self._path("sessions"), params=params)) or []

    async def create_session(self, *, title: str, agent: str | None = None) -> str:
        body: dict[str, Any] = {"title": title}
        if agent:
            body["agent"] = agent
        if self.v2 and self._directory:
            body["location"] = {"directory": self._directory}
        session = v2.unwrap(await self._request("POST", self._path("sessions"), json=body))
        session_id = (session or {}).get("id")
        if not session_id:
            raise OpencodeError("engine created a session with no id")
        if agent:
            self._session_agent[str(session_id)] = agent
        return str(session_id)

    async def delete_session(self, session_id: str) -> None:
        for cache in (self._session_agent, self._session_model, self._session_system):
            cache.pop(session_id, None)
        try:
            await self._request("DELETE", self._path("session", session=session_id))
        except OpencodeError:
            pass  # cleanup is best-effort; a stale session is not a failure

    async def abort(self, session_id: str) -> None:
        try:
            await self._request("POST", self._path("abort", session=session_id))
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
        """Send one message and wait for the assistant to finish.

        `tools` narrows tool visibility on OpenCode 1 only; OpenCode 2 has no per-prompt
        tool map, so there the agent's resolved permissions are the whole policy.
        """
        if self.v2:
            payload = await self._prompt_v2(session_id, text, agent=agent, system=system, model=model)
            return _read_message(payload)
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
            "POST", self._path("prompt", session=session_id), json=body, timeout=PROMPT_TIMEOUT
        )
        return _read_message(payload or {})

    async def _prompt_v2(
        self, session_id: str, text: str, *, agent: str | None, system: str | None, model: str | None
    ) -> dict[str, Any]:
        """OpenCode 2 admits a prompt and runs it in the background: send what the session lacks,
        admit the text, wait for the session to go idle, then read the turn off its timeline."""
        if agent and self._session_agent.get(session_id) != agent:
            await self.set_session_agent(session_id, agent)
        if model and split_model(model) and self._session_model.get(session_id) != model:
            await self.set_session_model(session_id, model)
        if (system or "") != self._session_system.get(session_id, ""):
            await self.set_session_system(session_id, system)

        admitted = v2.unwrap(await self._request(
            "POST", self._v2_path("prompt", session=session_id), json={"text": text}
        ))
        message_id = str((admitted or {}).get("id", ""))
        if not message_id:
            raise OpencodeError("engine admitted a prompt with no message id")
        deadline = time.monotonic() + (PROMPT_TIMEOUT.read or 1800.0)
        while True:
            await self.wait_idle(session_id)
            payload = v2.message_payload(await self.timeline(session_id, message_id), message_id)
            if payload is not None:
                return payload
            if time.monotonic() > deadline:
                raise OpencodeError(f"engine never finished the turn for {message_id}")
            # admitted but not yet started when `wait` answered: the loop is about to run
            await asyncio.sleep(0.2)

    # OpenCode 2 keeps a session's agent, model and system prompt on the session, not on each
    # prompt. These are the routes `_prompt_v2` drives; `bashos opencode verify` drives them too
    # (contract.session_routes), so a release that moved one fails there, not on the next turn.

    def _v2_path(self, name: str, **parts: str) -> str:
        if not self.v2:
            raise OpencodeError(f"OpenCode {self.major} has no `{name}` session route")
        return self._path(name, **parts)

    async def set_session_agent(self, session_id: str, agent: str) -> None:
        """Run the session's next turn as `agent`."""
        await self._request("POST", self._v2_path("agent", session=session_id), json={"agent": agent})
        self._session_agent[session_id] = agent

    async def set_session_model(self, session_id: str, model: str) -> None:
        """Run the session's next turn on `model` (`provider/model`)."""
        parsed = split_model(model)
        if parsed is None:
            raise OpencodeError(f"not a provider/model reference: {model!r}")
        ref = {"providerID": parsed[0], "id": parsed[1]}
        await self._request("POST", self._v2_path("model", session=session_id), json={"model": ref})
        self._session_model[session_id] = model

    async def set_session_system(self, session_id: str, system: str | None) -> None:
        """Put the session's system prompt in its `bashos.system` instruction entry, or, with
        no system prompt, delete that entry."""
        entry = self._v2_path("instructions", session=session_id, key=SYSTEM_ENTRY)
        if system:
            await self._request("PUT", entry, json={"value": system})
            self._session_system[session_id] = system
        else:
            await self._request("DELETE", entry)
            self._session_system.pop(session_id, None)

    async def wait_idle(self, session_id: str) -> None:
        """Block until the session has no turn running (at once, on an idle session)."""
        await self._request("POST", self._v2_path("wait", session=session_id), timeout=PROMPT_TIMEOUT)

    async def probe_prompt(self, session_id: str) -> None:
        """Prove the prompt route is still served, without running a turn.

        A body with no text must be refused as invalid (400); a route the engine no longer
        serves answers 404. An engine that admits it anyway is interrupted and reported.
        """
        try:
            await self._request("POST", self._v2_path("prompt", session=session_id), json={})
        except EngineHTTPError as exc:
            if exc.status == 400:
                return
            raise
        await self.abort(session_id)
        raise OpencodeError("the engine admitted a prompt with no text")

    async def timeline(self, session_id: str, message_id: str = "", *, max_pages: int = 50) -> list[dict[str, Any]]:
        """The session's messages back to `message_id` (all of them, without one), oldest first."""
        newest_first: list[dict[str, Any]] = []
        params: dict[str, str] = {"order": "desc", "limit": "100"}
        for _ in range(max_pages):
            page = await self._request("GET", self._v2_path("messages", session=session_id), params=params) or {}
            items = list(page.get("data") or [])
            newest_first.extend(items)
            cursor = (page.get("cursor") or {}).get("next")
            if not items or not cursor or any(m.get("id") == message_id for m in items):
                break
            params = {"cursor": str(cursor), "limit": "100"}  # a cursor carries its own order
        return list(reversed(newest_first))

    # ----------------------------------------------------------- permissions

    async def reject_permission(self, session_id: str, permission_id: str, message: str = "") -> None:
        """Refuse a session's approval request (OpenCode 1's v1 protocol, or OpenCode 2's)."""
        body: dict[str, Any] = {"response": "reject"}
        if self.v2:
            body = {"decision": "reject", "message": message or None}
        with contextlib.suppress(OpencodeError):
            await self._request(
                "POST", self._path("permission", session=session_id, request=permission_id), json=body
            )

    async def reject_permission_v2(self, request_id: str, message: str) -> None:
        """Refuse an approval request (OpenCode 1's sessionless v2 permission protocol).

        OpenCode 2 has no sessionless request: its `permission.asked` names a session and is
        refused through `reject_permission`.
        """
        with contextlib.suppress(OpencodeError):
            await self._request(
                "POST",
                f"/permission/{request_id}/reply",
                json={"reply": "reject", "message": message},
            )

    async def evaluate_permission(self, session_id: str, *, agent: str, action: str, resource: str) -> str:
        """Ask an OpenCode 2 engine how it would answer `action` on `resource` for `agent`:
        "allow", "deny" or "ask". The engine contract's own-words check (contract.py)."""
        if not self.v2:
            raise OpencodeError("only OpenCode 2 evaluates a permission on request")
        body = {"action": action, "resources": [resource], "agent": agent}
        answer = v2.unwrap(await self._request("POST", self._path("evaluate", session=session_id), json=body))
        return str((answer or {}).get("effect", ""))

    # ---------------------------------------------------------------- events

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """The global server-sent event stream, decoded to dicts (OpenCode 1 shapes).

        The global stream rather than the per-session one: it opens with a
        `server.connected` frame, which is the only reliable signal that the
        subscription is live — so a caller can start watching before it
        prompts and miss nothing.
        """
        normalize = v2.EventNormalizer() if self.v2 else None
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
            trust_env=False,
            auth=self._auth,
        ) as http:
            async with http.stream("GET", self._path("events"), params=self._params) as response:
                if response.status_code >= 400:
                    return
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    if normalize is not None:
                        event = normalize(event)
                    if event is not None:
                        yield event


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
        error_name=str(error.get("name", "")) if isinstance(error, dict) else "",
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
