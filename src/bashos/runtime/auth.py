"""Auth and environment diagnostics behind `bashos doctor`."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

from ..config import BACKEND_API, BACKEND_CLAUDE_CODE, KernelConfig
from .llm import has_api_key, has_claude_code, resolve_backend


@dataclass(frozen=True)
class Check:
    label: str
    ok: bool
    detail: str


def _claude_version() -> str:
    try:
        proc = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10
        )
        return proc.stdout.strip() or proc.stderr.strip() or "installed"
    except Exception:
        return "installed (version check failed)"


def run_checks(config: KernelConfig) -> list[Check]:
    checks: list[Check] = []

    claude_bin = shutil.which("claude")
    checks.append(
        Check(
            "claude CLI",
            claude_bin is not None,
            _claude_version() if claude_bin else "not found — install Claude Code, or use the api backend",
        )
    )
    checks.append(
        Check(
            "CLAUDE_CODE_OAUTH_TOKEN",
            bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
            "set" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") else "not set (optional — CLI login also works)",
        )
    )
    checks.append(
        Check(
            "ANTHROPIC_API_KEY",
            has_api_key(),
            "set" if has_api_key() else "not set (optional — fallback backend)",
        )
    )

    backend = resolve_backend(config)
    usable = (backend == BACKEND_CLAUDE_CODE and has_claude_code()) or (
        backend == BACKEND_API and has_api_key()
    )
    checks.append(Check("backend", usable, f"{backend} → {config.model}"))
    checks.append(
        Check(
            "shellcheck",
            shutil.which("shellcheck") is not None,
            "found (verifier for the refine loop)"
            if shutil.which("shellcheck")
            else "not found — /script output will be unverified (brew install shellcheck)",
        )
    )
    checks.append(Check("python", True, sys.version.split()[0]))
    return checks
