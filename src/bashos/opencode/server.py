"""Engine lifecycle: attach to, or supervise, an OpenCode server.

bashOS does not reimplement a reasoning loop — it runs one. That loop lives in
an `opencode serve` process, and this module is the supervisor: it either
attaches to a server the user already has (`BASHOS_OPENCODE_URL`, or
`opencode serve` in another terminal) or starts a private one bound to
loopback, waits for it to answer `/global/health`, and shuts it down on exit.

A supervised server gets a free port picked at start time and a random
per-process password, so several bashOS sessions run side by side without a
port fight and the loopback socket — which brokers shell access — is not open
to every other process on the box. Its real address is read back from its own
startup line rather than assumed.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import secrets
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

from .client import OpencodeClient, OpencodeError

DEFAULT_BINARY = "opencode"
LISTEN_RE = re.compile(r"(https?://[^\s]+)")
STARTUP_TIMEOUT = 60.0

# opencode's server reads these; the username has a default we must match
SERVER_USER = "opencode"

INSTALL_HINT = (
    "opencode is not installed — bashOS runs on the OpenCode engine.\n"
    "  install: npm i -g opencode-ai   (or: curl -fsSL https://opencode.ai/install | bash)\n"
    "  then:    bashos doctor"
)


@dataclass
class EngineHandle:
    """A reachable engine, and whether this process is responsible for it."""

    url: str
    client: OpencodeClient
    process: asyncio.subprocess.Process | None = None
    log_path: Path | None = None
    auth: tuple[str, str] | None = None  # basic-auth pair guarding the socket

    @property
    def supervised(self) -> bool:
        return self.process is not None

    async def stop(self) -> None:
        await self.client.aclose()
        if self.process is None or self.process.returncode is not None:
            return
        self.process.terminate()
        with contextlib.suppress(TimeoutError, ProcessLookupError):
            await asyncio.wait_for(self.process.wait(), timeout=10)
        if self.process.returncode is None:  # pragma: no cover - stubborn child
            with contextlib.suppress(ProcessLookupError):
                self.process.kill()


def find_binary(name: str = DEFAULT_BINARY) -> str | None:
    return shutil.which(name)


def configured_url() -> str | None:
    """An engine URL the user pinned, if any."""
    url = os.environ.get("BASHOS_OPENCODE_URL", "").strip()
    return url.rstrip("/") or None


def _configured_auth() -> tuple[str, str] | None:
    """Credentials for attaching to someone else's secured engine."""
    if password := os.environ.get("BASHOS_OPENCODE_PASSWORD", "").strip():
        user = os.environ.get("OPENCODE_SERVER_USERNAME", SERVER_USER)
        return (user, password)
    return None


def _free_port() -> int:
    """Ask the OS for an unused loopback port and hand it to the server."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def attach(url: str, *, directory: str | None = None) -> EngineHandle:
    """Attach to an already-running engine, failing if it does not answer."""
    handle_auth = _configured_auth()
    client = OpencodeClient(url, directory=directory, auth=handle_auth)
    try:
        await client.health()
    except OpencodeError:
        await client.aclose()
        raise
    return EngineHandle(url=url, client=client, auth=handle_auth)


async def spawn(
    *,
    directory: str,
    binary: str = DEFAULT_BINARY,
    log_path: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> EngineHandle:
    """Start a private engine on a free loopback port, password-protected.

    `env_extra` carries the credential wiring (see auth.py). It goes into the
    child's environment and nowhere else, so nothing secret is written to disk
    and the engine's credentials die with the process.
    """
    executable = find_binary(binary)
    if executable is None:
        raise OpencodeError(INSTALL_HINT)

    auth = (SERVER_USER, secrets.token_urlsafe(32))
    env = {
        **os.environ,
        **(env_extra or {}),
        "OPENCODE_SERVER_USERNAME": auth[0],
        "OPENCODE_SERVER_PASSWORD": auth[1],
    }

    log_file = open(log_path, "ab") if log_path else asyncio.subprocess.DEVNULL
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            "serve",
            "--port",
            str(_free_port()),
            "--hostname",
            "127.0.0.1",
            # without this the engine logs into its own state dir, where a
            # failing run is nobody's first place to look
            "--print-logs",
            "--log-level",
            "INFO",
            cwd=directory,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=log_file,
        )
    finally:
        if log_path:
            log_file.close()  # type: ignore[union-attr]

    try:
        url = await asyncio.wait_for(_read_listen_url(process), timeout=STARTUP_TIMEOUT)
    except (TimeoutError, OpencodeError) as exc:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        detail = f" (engine log: {log_path})" if log_path else ""
        raise OpencodeError(f"opencode server did not start{detail}: {exc}") from exc

    client = OpencodeClient(url, directory=directory, auth=auth)
    await _wait_healthy(client)
    return EngineHandle(
        url=url, client=client, process=process, log_path=log_path, auth=auth
    )


async def _read_listen_url(process: asyncio.subprocess.Process) -> str:
    """Read the server's own startup line to learn the port it landed on."""
    assert process.stdout is not None
    while True:
        raw = await process.stdout.readline()
        if not raw:
            raise OpencodeError("server exited before reporting an address")
        if match := LISTEN_RE.search(raw.decode(errors="replace")):
            return match.group(1).rstrip("/")


async def _wait_healthy(client: OpencodeClient, *, attempts: int = 30) -> None:
    for attempt in range(attempts):
        try:
            await client.health()
            return
        except OpencodeError:
            if attempt == attempts - 1:
                await client.aclose()
                raise
            await asyncio.sleep(0.2)
