"""Auth and environment diagnostics behind `bashos doctor`.

Offline by design: every check here is a file, a binary, or an environment
variable, so `doctor` answers instantly and works with no network and no
running engine. For live engine state — is it up, which providers are
connected, which agents loaded — use `bashos opencode status`, which boots it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from ..config import BACKEND_API, BACKEND_CLAUDE_CODE, BACKEND_OPENCODE, KernelConfig
from .llm import has_api_key, has_claude_code, has_opencode, resolve_backend


@dataclass(frozen=True)
class Check:
    label: str
    ok: bool
    detail: str


def _version_of(binary: str, *args: str) -> str:
    try:
        proc = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=10
        )
        return proc.stdout.strip() or proc.stderr.strip() or "installed"
    except Exception:
        return "installed (version check failed)"


def _engine_check() -> Check:
    from ..opencode import server

    if url := server.configured_url():
        return Check("engine", True, f"pinned to {url} (BASHOS_OPENCODE_URL)")
    if binary := server.find_binary():
        return Check("engine", True, f"opencode {_version_of(binary, '--version')}")
    return Check("engine", False, "opencode not found — npm i -g opencode-ai")


def _credential_check() -> Check:
    from ..opencode import auth

    if credential := auth.discover():
        note = "refreshable" if credential.refreshable else "bearer, no refresh"
        stale = " — EXPIRED, re-login" if credential.expired and credential.refreshable else ""
        return Check("claude code oauth", True, f"{credential.source} ({note}){stale}")
    return Check(
        "claude code oauth",
        False,
        "not found — log in with `claude` or run `claude setup-token`",
    )


def _config_check(config: KernelConfig) -> Check:
    from ..opencode import project
    from ..registry import find_root, load_registry

    try:
        root = find_root()
        fresh = project.is_in_sync(root, load_registry(root))
    except (FileNotFoundError, OSError, ValueError) as exc:
        return Check("engine config", False, f"could not read the registry: {exc}")
    where = project.CONFIG_FILE
    return Check(
        "engine config",
        True,
        f"{where} up to date" if fresh else f"{where} stale — regenerated on next run",
    )


def _backend_check(config: KernelConfig) -> Check:
    backend = resolve_backend(config)
    usable = {
        BACKEND_OPENCODE: has_opencode,
        BACKEND_CLAUDE_CODE: has_claude_code,
        BACKEND_API: has_api_key,
    }.get(backend, lambda: False)()
    return Check("backend", usable, f"{backend} → {config.model}")


def run_checks(config: KernelConfig) -> list[Check]:
    claude_bin = shutil.which("claude")
    shellcheck = shutil.which("shellcheck")
    return [
        _engine_check(),
        _credential_check(),
        _config_check(config),
        Check(
            "claude CLI",
            claude_bin is not None,
            _version_of("claude", "--version")
            if claude_bin
            else "not found (optional — fallback backend and slash commands)",
        ),
        Check(
            "ANTHROPIC_API_KEY",
            has_api_key(),
            "set" if has_api_key() else "not set (optional — fallback backend)",
        ),
        _backend_check(config),
        Check(
            "shellcheck",
            shellcheck is not None,
            "found (verifier for the refine loop)"
            if shellcheck
            else "not found — /script output will be unverified (brew install shellcheck)",
        ),
        Check("python", True, sys.version.split()[0]),
    ]
