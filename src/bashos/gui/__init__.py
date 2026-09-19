"""The bashOS desktop — a GUI front end over the same kernel the terminal runs.

The terminal stays the core access point; this is a second face on it, not a
second runtime. Every scene is a view of something that already exists: the
registry (`.claude/commands/*.md`), the kernel's own trace, the engine's tool
policy, `bashos doctor`. Runs go through `build_kernel` untouched.

    bashos gui              native window if `bashos[gui]` is installed, else browser
    bashos gui --browser    skip the window
    bashos gui --no-open    just serve; print the URL

Layout: `http.py` (transport), `server.py` (routes), `runs.py` (history),
`desktop.py` (window), `web/` (the front end — no build step, no bundler).
"""

from __future__ import annotations

from .desktop import launch, window_available
from .server import GuiServer

__all__ = ["GuiServer", "launch", "window_available"]
