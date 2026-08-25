"""Shared guards and text helpers for orchestration loops."""

from __future__ import annotations

import re

from ..registry import CommandSpec

_CODE_FENCE = re.compile(r"```(?:bash|sh|shell)?\s*\n(.*?)```", re.DOTALL)


def usage_or_none(spec: CommandSpec, args: str) -> str | None:
    """Return usage text when a command that needs arguments got none."""
    if not args and spec.requires_args:
        return spec.usage
    return None


def dry_run_report(spec: CommandSpec, prompt: str, extra: str = "") -> str:
    header = f"[dry-run] /{spec.name} → loop={spec.loop}"
    if extra:
        header += f"\n{extra}"
    return f"{header}\n\n--- rendered prompt ---\n\n{prompt}"


def first_fence(text: str) -> str | None:
    """Return the first bash/sh fence body, or None if the text has no fence."""
    match = _CODE_FENCE.search(text)
    return match.group(1).strip() if match else None


def extract_script(text: str) -> str:
    """Fence body if present, otherwise the whole text (refine draft fallback)."""
    return first_fence(text) or text.strip()
