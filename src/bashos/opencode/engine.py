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
from collections.abc import Callable
from pathlib import Path

from ..config import KernelConfig
from ..registry import CommandSpec, find_root, load_registry
from . import auth, project, server
from .client import OpencodeClient, OpencodeError, PromptResult

STATE_DIR = ".bashos"
ENGINE_LOG = "opencode.log"

_REJECTION = (
    "Denied by bashOS policy — this terminal is non-interactive and cannot "
    "approve. Work within your allowed tools and report what you found."
)


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

    async def stop(self) -> None:
        if self._handle is None:
            return
        handle, self._handle = self._handle, None
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

    async def complete(self, prompt: str, *, system: str | None = None) -> str:
        """One answer, no tools — the syscall the stateless loops run on."""
        result = await self._run(
            prompt, agent=project.SEALED_AGENT, system=system, on_event=None
        )
        if result.failed:
            raise OpencodeError(f"engine completion failed: {result.error}")
        if not result.text:
            raise OpencodeError(
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
    ) -> PromptResult:
        """A full reason ↔ act loop under policy, streaming tool calls."""
        return await self._run(prompt, agent=agent, system=system, on_event=on_event)

    async def _run(
        self,
        prompt: str,
        *,
        agent: str,
        system: str | None,
        on_event: Callable[[str], None] | None,
    ) -> PromptResult:
        client = self.client
        session_id = await client.create_session(title=f"bashos:{agent}", agent=agent)
        # The watcher always runs, even with nothing to display: it is what
        # refuses approval prompts. A rule that resolves to "ask" would
        # otherwise block a headless run until the request timed out.
        live = asyncio.Event()
        watcher = asyncio.create_task(self._watch(session_id, on_event, live))
        try:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(live.wait(), timeout=5)
            return await client.prompt(
                session_id,
                prompt,
                agent=agent,
                system=system,
                model=project.qualify_model(self.config.model),
            )
        except OpencodeError as exc:
            await client.abort(session_id)
            raise OpencodeError(f"{exc}{self._failure_hint()}") from exc
        except BaseException:
            await client.abort(session_id)
            raise
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
            await client.delete_session(session_id)

    async def _watch(
        self,
        session_id: str,
        on_event: Callable[[str], None] | None,
        live: asyncio.Event,
    ) -> None:
        """Report tool calls, and refuse anything that stops to ask.

        bashOS is non-interactive by construction: the policy in policy.py is
        the answer, so an approval request is a request the policy did not
        already allow — and the honest reply is no.
        """
        from .client import read_tool_part

        seen: set[str] = set()
        try:
            async for event in self.client.events():
                live.set()  # the stream is open; the prompt may start
                kind = event.get("type")
                props = event.get("properties") or {}
                if props.get("sessionID") not in (session_id, None):
                    continue  # another session on the same engine

                if kind == "permission.asked":
                    await self.client.reject_permission(session_id, str(props.get("id")))
                    self._note(on_event, f"denied by policy: {props.get('permission')}")
                elif kind == "permission.v2.asked":
                    await self.client.reject_permission_v2(
                        str(props.get("id")), _REJECTION
                    )
                    self._note(on_event, f"denied by policy: {props.get('action')}")
                elif kind == "message.part.updated":
                    part = props.get("part") or {}
                    if part.get("type") != "tool":
                        continue
                    call = read_tool_part(part)
                    if not call.call_id or call.call_id in seen or call.status in ("pending", ""):
                        continue
                    seen.add(call.call_id)
                    self._note(on_event, call.describe())
        except asyncio.CancelledError:
            raise
        except Exception:
            live.set()  # a broken event stream must never wedge the prompt
            return

    @staticmethod
    def _note(on_event: Callable[[str], None] | None, text: str) -> None:
        if on_event is not None:
            on_event(text)

    def _failure_hint(self) -> str:
        """Point a raw engine error at the two things that actually explain it.

        The most common cause by far is a credential the engine could not use,
        which it reports as an opaque 500 — so name the credential path first
        and the log second.
        """
        hint = f"\n  auth: {self.auth_status}\n  check: bashos doctor"
        log = self._handle.log_path if self._handle else None
        return f"{hint}\n  engine log: {log}" if log else hint


_ENGINE: OpencodeEngine | None = None


async def get_engine(config: KernelConfig, **kwargs: object) -> OpencodeEngine:
    """Process-wide engine, started once and reused across REPL lines."""
    global _ENGINE
    if _ENGINE is None or not _ENGINE.started:
        _ENGINE = await OpencodeEngine(config, **kwargs).start()  # type: ignore[arg-type]
    return _ENGINE


async def shutdown_engine() -> None:
    global _ENGINE
    if _ENGINE is not None:
        await _ENGINE.stop()
        _ENGINE = None
