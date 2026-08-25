"""The two bashOS themes — cyan-led, matching the banner."""

from __future__ import annotations

from textual.theme import Theme

BASHOS_DARK = Theme(
    name="bashos-dark",
    primary="#00b7c3",
    secondary="#4ec9b0",
    accent="#c586c0",
    foreground="#d4d8de",
    background="#101418",
    surface="#151a20",
    panel="#1d242e",
    success="#4ec9b0",
    warning="#d7ba7d",
    error="#f14c4c",
    dark=True,
)

BASHOS_LIGHT = Theme(
    name="bashos-light",
    primary="#008a94",
    secondary="#1f7a68",
    accent="#8f4d8a",
    foreground="#20262c",
    background="#f4f6f8",
    surface="#ffffff",
    panel="#e8ecf0",
    success="#1f7a68",
    warning="#8a6d1f",
    error="#c23434",
    dark=False,
)
