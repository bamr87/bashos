"""The desktop back end: a read-mostly window onto the running kernel.

Every scene in the front end is one of these routes. The contract is narrow on
purpose — the GUI is a *view* of bashOS, not a second way into the machine:

  * it runs kernel lines, exactly what `bashos run` runs, and nothing else.
    There is no `!` passthrough here: in the terminal that escape hatch is the
    user's own shell by their own keystroke, but a local HTTP server that
    executes arbitrary commands is a different object with a different blast
    radius. The react loop still reaches the machine — through the engine's
    policy gate (opencode/policy.py), same as always.
  * it never returns a credential. `doctor` reports where a credential came
    from, which is what the terminal already prints; values stay in the engine
    process's environment.
  * it adds no reasoning loop. Runs go through `build_kernel` untouched, and
    the streaming is LangGraph's own node updates.

The socket is loopback, guarded by a per-process token, and refuses requests
whose Host or Origin is not its own — the same posture the engine's socket
takes in opencode/server.py, for the same reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Any

from ..config import KernelConfig
from ..registry import CommandSpec, find_root, load_registry
from .http import (
    HttpError,
    HttpServer,
    Request,
    Response,
    Router,
    Stream,
    json_response,
)
from .runs import Run, RunStore

WEB_DIR = Path(__file__).parent / "web"
TOKEN_HEADER = "x-bashos-token"
TOKEN_QUERY = "k"  # EventSource cannot set headers; SSE carries it in the URL

# Kernel state keys the update stream merges back into a final result.
_MERGE_KEYS = ("command", "args", "route", "output", "error")

_NODE_LABELS = {
    "parse": "parse",
    "classify": "classify",
    "loop_prompt": "prompt loop",
    "loop_refine": "refine loop",
    "loop_react": "react loop",
    "respond": "respond",
}


class GuiServer:
    """Serves the bashOS desktop on a loopback socket."""

    def __init__(
        self,
        config: KernelConfig,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        root: Path | None = None,
        token: str | None = None,
    ) -> None:
        self.config = config
        self.root = root or find_root()
        self.token = token or secrets.token_urlsafe(24)
        self.runs = RunStore()
        self.started_at = time.time()
        self._registry: dict[str, CommandSpec] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._http = HttpServer(
            self._build_router(), host=host, port=port, before=self._guard
        )

    # ------------------------------------------------------------- lifecycle

    @property
    def url(self) -> str:
        return self._http.url

    @property
    def entry_url(self) -> str:
        """The URL to open: carries the token the page needs for its API calls."""
        return f"{self.url}/?{TOKEN_QUERY}={self.token}"

    @property
    def registry(self) -> dict[str, CommandSpec]:
        if self._registry is None:
            self._registry = load_registry(self.root)
        return self._registry

    def reload_registry(self) -> dict[str, CommandSpec]:
        """Userland is a directory of markdown — re-read it on demand."""
        self._registry = load_registry(self.root)
        return self._registry

    async def start(self) -> GuiServer:
        await self._http.start()
        return self

    async def serve_forever(self) -> None:
        await self._http.serve_forever()

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
        await self._http.close()
        from ..opencode.engine import shutdown_engine

        await shutdown_engine()  # the window owned any engine it started

    # ----------------------------------------------------------------- guard

    def _guard(self, request: Request) -> None:
        """Loopback is not a security boundary on its own — check every caller.

        Host pins the request to the socket we opened (a DNS-rebound name
        resolving to 127.0.0.1 fails here), Origin refuses anything a different
        page initiated, and the token refuses every other process on the box.
        """
        host = request.header("host").lower()
        expected = {
            f"{self._http.host}:{self._http.port}",
            f"localhost:{self._http.port}",
            f"127.0.0.1:{self._http.port}",
        }
        if host and host not in expected:
            raise HttpError(403, "host not allowed")
        origin = request.header("origin")
        if origin and origin.lower() not in {f"http://{name}" for name in expected}:
            raise HttpError(403, "origin not allowed")
        if request.path.startswith("/api/"):
            supplied = request.header(TOKEN_HEADER) or request.query.get(TOKEN_QUERY, "")
            if not secrets.compare_digest(supplied, self.token):
                raise HttpError(401, "bad or missing token — open the URL bashOS printed")

    # ---------------------------------------------------------------- routes

    def _build_router(self) -> Router:
        router = Router()
        router.add("GET", "/", self._page)
        router.add("GET", "/{asset}", self._asset)
        router.add("GET", "/api/state", self._state)
        router.add("GET", "/api/commands", self._commands)
        router.add("GET", "/api/doctor", self._doctor)
        router.add("GET", "/api/policy", self._policy)
        router.add("GET", "/api/runs", self._list_runs)
        router.add("POST", "/api/runs", self._create_run)
        router.add("GET", "/api/runs/{run_id}", self._get_run)
        router.add("GET", "/api/runs/{run_id}/events", self._run_events)
        router.add("POST", "/api/engine/status", self._engine_status)
        return router

    async def _page(self, request: Request) -> Response:
        return _static("index.html")

    async def _asset(self, request: Request) -> Response:
        return _static(request.params["asset"])

    async def _state(self, request: Request) -> Response:
        from ..runtime.llm import resolve_backend

        registry = self.reload_registry()
        return json_response(
            {
                "version": _version(),
                "root": str(self.root),
                "backend": resolve_backend(self.config),
                "model": self.config.model,
                "config": {
                    "max_output_tokens": self.config.max_output_tokens,
                    "react_max_turns": self.config.react_max_turns,
                    "refine_max_iters": self.config.refine_max_iters,
                },
                "host": _host(),
                "commands": [_command_row(spec) for spec in registry.values()],
                "loops": _loop_counts(registry),
                "runs": self.runs.stats(),
                "uptime": round(time.time() - self.started_at, 1),
            }
        )

    async def _commands(self, request: Request) -> Response:
        registry = self.reload_registry()
        return json_response(
            [{**_command_row(spec), "body": spec.body} for spec in registry.values()]
        )

    async def _doctor(self, request: Request) -> Response:
        from ..runtime.auth import run_checks

        checks = await asyncio.to_thread(run_checks, self.config)
        return json_response(
            [{"label": c.label, "ok": c.ok, "detail": c.detail} for c in checks]
        )

    async def _policy(self, request: Request) -> Response:
        from ..opencode import policy, project

        config_path = self.root / project.CONFIG_FILE
        rules = [
            {"key": key, "action": action}
            for key, action in (atom.rsplit("=", 1) for atom in policy.readonly_policy())
        ]
        return json_response(
            {
                "rules": rules,
                "probes": list(policy.PROBE_COMMANDS),
                "agents": {
                    "readonly": project.READONLY_AGENT,
                    "sealed": project.SEALED_AGENT,
                    "loops": project.LOOP_AGENTS,
                },
                "config_file": project.CONFIG_FILE,
                "in_sync": project.is_in_sync(self.root, self.registry),
                "config_text": _read_text(config_path, limit=200_000),
            }
        )

    async def _list_runs(self, request: Request) -> Response:
        limit = _int_param(request.query.get("limit"), default=50, maximum=200)
        return json_response(self.runs.list(limit))

    async def _get_run(self, request: Request) -> Response:
        run = self.runs.get(request.params["run_id"])
        if run is None:
            raise HttpError(404, "no such run")
        return json_response(run.detail())

    async def _create_run(self, request: Request) -> Response:
        payload = request.json()
        if not isinstance(payload, dict):
            raise HttpError(400, "expected a JSON object")
        line = str(payload.get("input", "")).strip()
        if not line:
            raise HttpError(400, "input is required")
        if len(line) > 8000:
            raise HttpError(413, "input too long")
        if line.startswith("!"):
            raise HttpError(
                403,
                "the desktop does not run shell passthrough — use your terminal for `!`",
            )
        dry_run = bool(payload.get("dry_run", self.config.dry_run))
        model = str(payload.get("model") or self.config.model)
        run = self.runs.create(line, dry_run=dry_run, model=model)
        task = asyncio.create_task(self._execute(run))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return json_response(run.summary(), status=200)

    async def _run_events(self, request: Request) -> Stream:
        run = self.runs.get(request.params["run_id"])
        if run is None:
            raise HttpError(404, "no such run")
        return Stream(run.stream)

    async def _engine_status(self, request: Request) -> Response:
        """Boot the engine (or attach) and report what it is actually running."""
        from ..opencode.engine import get_engine

        try:
            engine = await get_engine(self.config)
            agents = [a.get("name", "?") for a in await engine.client.agents()]
            providers = await engine.client.connected_providers()
        except Exception as exc:
            return json_response({"ok": False, "error": str(exc)})
        return json_response(
            {
                "ok": True,
                "rows": [
                    ["url", f"{engine.url} ({'supervised' if engine.supervised else 'attached'})"],
                    ["version", engine.version],
                    ["auth", engine.auth_status],
                    ["providers", ", ".join(providers) or "none connected"],
                    ["config", engine.sync_status],
                    ["agents", ", ".join(sorted(agents))],
                ],
            }
        )

    # -------------------------------------------------------------- the run

    async def _execute(self, run: Run) -> None:
        """One kernel line, streamed. No loop lives here — LangGraph's does."""
        from ..kernel import build_kernel
        from ..runtime.llm import get_chat_model

        run.emit("status", "started")
        config = self.config.model_copy(update={"dry_run": run.dry_run, "model": run.model})
        registry = self.reload_registry()
        state: dict[str, Any] = {}
        try:
            llm = None if run.dry_run else get_chat_model(config)
            kernel = build_kernel(
                registry, llm, config, on_event=lambda text: run.emit("tool", text)
            )
            stream = kernel.astream({"input": run.input, "trace": []}, stream_mode="updates")
            async for update in stream:
                for node, delta in update.items():
                    if not isinstance(delta, dict):
                        continue
                    _merge(state, delta)
                    run.emit("node", _NODE_LABELS.get(node, node))
                    for line in delta.get("trace") or []:
                        run.trace.append(str(line))
                        run.emit("trace", str(line))
                    if spec := registry.get(str(state.get("command", ""))):
                        run.command, run.loop = spec.name, spec.loop
                    run.route = str(state.get("route", run.route))
        except asyncio.CancelledError:
            run.error = "cancelled"
            run.emit("error", run.error)
            run.finish("error")
            raise
        except Exception as exc:
            run.error = str(exc) or exc.__class__.__name__
            run.emit("error", run.error)
            run.finish("error")
            return

        if state.get("route") == "error":
            run.error = str(state.get("output") or state.get("error") or "kernel error")
            run.emit("error", run.error)
            run.finish("error")
            return
        run.output = str(state.get("output", ""))
        run.emit("output", run.output)
        run.finish("ok")


# --------------------------------------------------------------------- helpers


def _merge(state: dict[str, Any], delta: object) -> None:
    if not isinstance(delta, dict):
        return
    for key in _MERGE_KEYS:
        if key in delta and delta[key] is not None:
            state[key] = delta[key]


def _command_row(spec: CommandSpec) -> dict[str, object]:
    from ..opencode.project import agent_for

    return {
        "name": spec.name,
        "description": spec.description,
        "argument_hint": spec.argument_hint,
        "loop": spec.loop,
        "agent": agent_for(spec),
        "requires_args": spec.requires_args,
        "path": str(spec.path),
    }


def _loop_counts(registry: dict[str, CommandSpec]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for spec in registry.values():
        counts[spec.loop] = counts.get(spec.loop, 0) + 1
    return counts


def _host() -> dict[str, str]:
    """The same machine facts the kernel already appends to every prompt."""
    import os
    import platform
    import sys

    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "shell": os.path.basename(os.environ.get("SHELL", "sh")),
        "python": sys.version.split()[0],
    }


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("bashos")
    except PackageNotFoundError:
        return "dev"


def _int_param(raw: str | None, *, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(raw or default), maximum))
    except ValueError:
        return default


def _read_text(path: Path, *, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[:limit]


def _static(name: str) -> Response:
    """Serve one file from web/ — flat directory, nothing above it, ever."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise HttpError(404, f"no such asset: {name}")
    path = (WEB_DIR / name).resolve()
    if path.parent != WEB_DIR.resolve() or not path.is_file():
        raise HttpError(404, f"no such asset: {name}")
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise HttpError(404, str(exc)) from exc
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if content_type.startswith(("text/", "application/javascript")):
        content_type = f"{content_type}; charset=utf-8"
    return Response(body, content_type=content_type)
