"""The bashOS desktop — a windowed terminal environment on Textual.

This package is the L6 interface surface: a hybrid-tiling window manager,
a taskbar, a launcher, and an app suite (AI console, health, doctor, engine
inspector, …), all rendered in the terminal. It is a pure *client* of the
kernel and the engine: it builds payloads, renders results and typed engine
events, and never reasons or executes anything itself.
"""

from __future__ import annotations


def run_desktop(model: str | None = None) -> None:
    """Launch the desktop. Textual owns the event loop (no asyncio.run)."""
    from .app import BashOSApp

    BashOSApp(model=model).run()
