"""The engine façade — the one object the kernel talks to.

`OpencodeEngine` is bashOS's handle on the reasoning engine. Starting it is
four steps, in this order:

  1. project the registry onto `opencode.jsonc`   (config is read at boot)
  2. attach to a running server, or supervise a private one
  3. install the Claude Code OAuth credential      (subscription, not API key)
  4. hand the kernel two verbs

The two verbs are the whole surface:

  complete(...)  one answer, no tools. What the prompt/refine loops and the
                 kernel's classifier run on.
  act(...)       a full reason ↔ act loop under the readonly policy, with tool
                 calls streaming to the terminal as they happen. What the react
                 loop runs on.

Everything below those verbs — the agent loop, the tool broker, session state,
the permission gate — belongs to OpenCode. bashOS supplies routing, policy, and
the terminal.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from .. import events
from ..config import KernelConfig
from ..registry import CommandSpec, find_root, load_registry
from . import auth, project, server
from .client import (
    EmptyCompletion,
    EngineHTTPError,
    OpencodeClient,
    OpencodeError,
    PromptResult,
    ProviderError,
    RunAborted,
)

STATE_DIR = ".bashos"
ENGINE_LOG = "opencode.log"

_REJECTION = (
    "Denied by bashOS policy — this terminal is non-interactive and cannot "
    "approve. Work within your allowed tools and report what you found."
)


async def watch_events(
    stream: AsyncIterator[dict[str, Any]],
    session_id: str,
    sink: events.EventSink | None,
    live: asyncio.Event,
    client: Any,
) -> None:
    """Consume one session's slice of the engine event stream.

    Emits typed events to `sink`, and refuses anything that stops to ask:
    bashOS is non-interactive by construction — the policy in policy.py is
    the answer, so an approval request is a request the policy did not
    already allow, and the honest reply is no.

    Pure over an injected stream so tests and the event bus can both drive
    it. Any stream failure sets `live` and returns: a dead stream must never
    wedge the prompt.
    """
    from .client import read_tool_part

    started: dict[str, float] = {}
    emitted: dict[str, int] = {}  # text part id → chars already forwarded
    try:
        async for event in stream:
            live.set()  # the stream is open; the prompt may start
            kind = event.get("type")
            props = event.get("properties") or {}
            if props.get("sessionID") not in (session_id, None):
                continue  # another session on the same engine

            if kind == "permission.asked":
                await client.reject_permission(session_id, str(props.get("id")))
                _emit(sink, events.PermissionEvent(
                    session_id=session_id,
                    request_id=str(props.get("id")),
                    action=str(props.get("permission")),
                    protocol="v1",
                    decision="auto-rejected",
                ))
            elif kind == "permission.v2.asked":
                await client.reject_permission_v2(str(props.get("id")), _REJECTION)
                _emit(sink, events.PermissionEvent(
                    session_id=session_id,
                    request_id=str(props.get("id")),
                    action=str(props.get("action")),
                    protocol="v2",
                    decision="auto-rejected",
                ))
            elif kind == "message.part.updated":
                part = props.get("part") or {}
                ptype = part.get("type")
                if ptype == "text" and not part.get("synthetic"):
                    # OpenCode sends cumulative text snapshots; forward only
                    # the new suffix. A shrinking part (mid-stream edit)
                    # resets the counter — the final PromptResult.text is
                    # authoritative, so the display self-heals.
                    part_id = str(part.get("id", ""))
                    text = str(part.get("text", ""))
                    sent = emitted.get(part_id, 0)
                    if len(text) < sent:
                        sent = 0
                    if len(text) > sent:
                        emitted[part_id] = len(text)
                        _emit(sink, events.TextDelta(
                            session_id=session_id, part_id=part_id, text=text[sent:]
                        ))
                    continue
                if ptype != "tool":
                    continue
                call = read_tool_part(part)
                if not call.call_id:
                    continue
                now = time.monotonic()
                first = started.setdefault(call.call_id, now)
                duration = (
                    int((now - first) * 1000)
                    if call.status in ("completed", "error")
                    else None
                )
                _emit(sink, events.ToolEvent(
                    session_id=session_id,
                    tool=call.tool,
                    call_id=call.call_id,
                    status=call.status,
                    title=call.title,
                    input=call.input,
                    description=call.describe(),
                    duration_ms=duration,
                ))
    except asyncio.CancelledError:
        raise
    except Exception:
        live.set()  # a broken event stream must never wedge the prompt
        return


def _emit(sink: events.EventSink | None, event: events.EngineEvent) -> None:
    if sink is not None:
        sink(event)


def _with_hint(exc: OpencodeError, hint: str) -> OpencodeError:
    """Rebuild the same error type with the failure hint appended."""
    message = f"{exc}{hint}"
    if isinstance(exc, EngineHTTPError):
        return type(exc)(message, exc.status)
    return type(exc)(message)


class OpencodeEngine:
    """A started, authenticated OpenCode server bashOS can dispatch to."""

    def __init__(
        self,
        config: KernelConfig,
        *,
        root: Path | None = None,
        registry: dict[str, CommandSpec] | None = None,
    ) -> None:
        self.config = config
        self.root = root or find_root()
        self._registry = registry
        self._handle: server.EngineHandle | None = None
        self._bus = None
        self._sessions: set[str] = set()  # open EngineSessions, swept on stop
        self.auth_status = "not started"
        self.sync_status = "not started"
        self.version = "unknown"

    # ------------------------------------------------------------- lifecycle

    @property
    def started(self) -> bool:
        return self._handle is not None

    @property
    def url(self) -> str:
        return self._handle.url if self._handle else ""

    @property
    def supervised(self) -> bool:
        return bool(self._handle and self._handle.supervised)

    @property
    def password(self) -> str:
        """The secret guarding a supervised engine's loopback socket."""
        auth_pair = self._handle.auth if self._handle else None
        return auth_pair[1] if auth_pair else ""

    @property
    def client(self) -> OpencodeClient:
        if self._handle is None:
            raise OpencodeError("engine not started")
        return self._handle.client

    @property
    def registry(self) -> dict[str, CommandSpec]:
        if self._registry is None:
            self._registry = load_registry(self.root)
        return self._registry

    async def start(self) -> OpencodeEngine:
        if self._handle is not None:
            return self
        self.sync_status = self._sync_config()
        if url := server.configured_url():
            self._handle = await server.attach(url, directory=str(self.root))
            self.version = await self.client.version()
            self.auth_status = await self._install_attached_credential()
        else:
            # the credential rides in on the child's environment, so it has to
            # be resolved before the process exists
            env_extra, self.auth_status = auth.engine_environment()
            self._handle = await server.spawn(
                directory=str(self.root),
                log_path=self._log_path(),
                env_extra=env_extra,
            )
            self.version = await self.client.version()
        return self

    @property
    def bus(self):
        """The single live event subscription, shared by every session."""
        from .bus import EngineEventBus

        if self._bus is None:
            self._bus = EngineEventBus(self.client)
        return self._bus

    async def stop(self) -> None:
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
        if self._bus is not None:
            await self._bus.close()
            self._bus = None
        # crash-cleanup: a window that never closed its session must not
        # leave one behind on the engine
        for session_id in list(self._sessions):
            await handle.client.delete_session(session_id)
        self._sessions.clear()
        await handle.stop()

    async def __aenter__(self) -> OpencodeEngine:
        return await self.start()

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    def _log_path(self) -> Path:
        state = self.root / STATE_DIR
        state.mkdir(parents=True, exist_ok=True)
        return state / ENGINE_LOG

    def _sync_config(self) -> str:
        """Regenerate `opencode.jsonc` before the engine reads it at boot."""
        if os.environ.get("BASHOS_OPENCODE_SYNC") == "0":
            return "skipped (BASHOS_OPENCODE_SYNC=0)"
        try:
            _, changed = project.sync(self.root, self.registry)
        except OSError as exc:
            return f"could not write {project.CONFIG_FILE}: {exc}"
        return "regenerated" if changed else "up to date"

    async def _install_attached_credential(self) -> str:
        """Best effort for an engine bashOS did not start.

        An attached server's environment is already fixed, so the Claude Code
        bearer route is closed — whoever started it owns its credentials. Only
        an API key can still be pushed in, and only when the engine has nothing.
        """
        connected: list[str] = []
        with contextlib.suppress(OpencodeError):
            connected = await self.client.connected_providers()
        if auth.PROVIDER_ID in connected:
            return "attached engine already authenticated (kept)"
        payload = auth.attached_credential()
        if payload is None:
            return (
                "attached engine has no anthropic credential — start it with "
                "`bashos opencode serve` to use your Claude Code login"
            )
        credential, source = payload
        try:
            await self.client.set_auth(auth.PROVIDER_ID, credential)
        except OpencodeError as exc:
            return f"could not install credential: {exc}"
        return f"installed {source} into the attached engine"

    # ----------------------------------------------------------------- verbs

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        on_event: events.EventSink | None = None,
    ) -> str:
        """One answer, no tools — the syscall the stateless loops run on."""
        result = await self._run(
            prompt, agent=project.SEALED_AGENT, system=system, sink=on_event
        )
        if result.failed:
            raise ProviderError(f"engine completion failed: {result.error}")
        if not result.text:
            raise EmptyCompletion(
                "engine returned an empty completion — run `bashos doctor`"
            )
        return result.text

    async def act(
        self,
        prompt: str,
        *,
        system: str | None = None,
        agent: str = project.READONLY_AGENT,
        on_event: Callable[[str], None] | None = None,
        on_engine_event: events.EventSink | None = None,
    ) -> PromptResult:
        """A full reason ↔ act loop under policy, streaming tool calls.

        `on_engine_event` receives typed events; `on_event` is the legacy
        one-line string callback (used only when no typed sink is given).
        """
        sink = on_engine_event or (events.to_legacy(on_event) if on_event else None)
        return await self._run(prompt, agent=agent, system=system, sink=sink)

    async def open_session(self, agent: str, *, title: str | None = None) -> EngineSession:
        """Create one engine session and hold it open across turns.

        This is what gives a desktop console window conversational
        continuity on the engine side. The caller owns `close()`; anything
        left open is swept by `stop()`.
        """
        session_id = await self.client.create_session(
            title=title or f"bashos:{agent}", agent=agent
        )
        self._sessions.add(session_id)
        return EngineSession(self, session_id, agent)

    async def _run(
        self,
        prompt: str,
        *,
        agent: str,
        system: str | None,
        sink: events.EventSink | None,
    ) -> PromptResult:
        """One prompt on a fresh session, deleted afterwards — the one-shot
        semantics `complete()` and `act()` have always had."""
        session = await self.open_session(agent)
        _emit(sink, events.LifecycleEvent(
            session_id=session.session_id, phase="session.created"
        ))
        try:
            return await session.prompt(prompt, system=system, sink=sink)
        finally:
            await session.close()
            _emit(sink, events.LifecycleEvent(
                session_id=session.session_id, phase="session.deleted"
            ))

    def _failure_hint(self) -> str:
        """Point a raw engine error at the two things that actually explain it.

        The most common cause by far is a credential the engine could not use,
        which it reports as an opaque 500 — so name the credential path first
        and the log second.
        """
        hint = f"\n  auth: {self.auth_status}\n  check: bashos doctor"
        log = self._handle.log_path if self._handle else None
        return f"{hint}\n  engine log: {log}" if log else hint


class EngineSession:
    """One OpenCode session held open across turns — a console window's handle.

    `prompt()` may be called any number of times; the engine accumulates the
    conversation server-side. `abort()` is the Stop affordance; `close()`
    deletes the session and must be called when the window goes away.
    """

    def __init__(self, engine: OpencodeEngine, session_id: str, agent: str) -> None:
        self.engine = engine
        self.session_id = session_id
        self.agent = agent
        self._aborted = False

    async def prompt(
        self,
        text: str,
        *,
        system: str | None = None,
        sink: events.EventSink | None = None,
    ) -> PromptResult:
        self._aborted = False
        client = self.engine.client
        live = asyncio.Event()
        # The registration always runs, even with nothing to display: its
        # watcher is what refuses approval prompts. A rule that resolves to
        # "ask" would otherwise block a headless run until it timed out.
        async with self.engine.bus.run(self.session_id, sink, live):
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(live.wait(), timeout=5)
            _emit(sink, events.LifecycleEvent(
                session_id=self.session_id, phase="prompt.started"
            ))
            try:
                result = await client.prompt(
                    self.session_id,
                    text,
                    agent=self.agent,
                    system=system,
                    model=project.qualify_model(self.engine.config.model),
                )
            except OpencodeError as exc:
                await client.abort(self.session_id)
                if self._aborted:
                    raise RunAborted("stopped by user") from exc
                raise _with_hint(exc, self.engine._failure_hint()) from exc
            except BaseException:
                await client.abort(self.session_id)
                raise
            _emit(sink, events.LifecycleEvent(
                session_id=self.session_id, phase="prompt.finished"
            ))
            return result

    async def abort(self) -> None:
        """Stop the in-flight turn; the session itself stays open."""
        self._aborted = True
        await self.engine.client.abort(self.session_id)

    async def close(self) -> None:
        await self.engine.client.delete_session(self.session_id)
        self.engine._sessions.discard(self.session_id)


_ENGINE: OpencodeEngine | None = None
_ENGINE_LOCK: asyncio.Lock | None = None
_ENGINE_LOCK_LOOP: asyncio.AbstractEventLoop | None = None


def _engine_lock() -> asyncio.Lock:
    """A lock scoped to the running loop.

    The engine singleton is process-wide, but one process may run several
    event loops over its lifetime (one per asyncio.run); concurrency only
    exists within a loop, so the lock is rebuilt when the loop changes.
    """
    global _ENGINE_LOCK, _ENGINE_LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _ENGINE_LOCK is None or _ENGINE_LOCK_LOOP is not loop:
        _ENGINE_LOCK = asyncio.Lock()
        _ENGINE_LOCK_LOOP = loop
    return _ENGINE_LOCK


async def get_engine(config: KernelConfig, **kwargs: object) -> OpencodeEngine:
    """Process-wide engine, started once and reused across turns.

    Serialized: two windows prompting at the same time must share one engine,
    not race each other into spawning two.
    """
    global _ENGINE
    async with _engine_lock():
        if _ENGINE is None or not _ENGINE.started:
            _ENGINE = await OpencodeEngine(config, **kwargs).start()  # type: ignore[arg-type]
        return _ENGINE


async def shutdown_engine() -> None:
    global _ENGINE
    async with _engine_lock():
        if _ENGINE is not None:
            engine, _ENGINE = _ENGINE, None
            await engine.stop()
