"""Shared guards for orchestration loops."""

from __future__ import annotations

from ..registry import CommandSpec


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
