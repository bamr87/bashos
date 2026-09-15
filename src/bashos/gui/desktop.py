"""Putting the GUI in a window.

Two ways to open the same local server, in order of preference:

  native   a real desktop window — pywebview drives the platform webview
           (WebKit on macOS, WebKit2GTK/Qt on Linux, WebView2 on Windows), so
           there is no browser chrome, no tab, and no second runtime to ship.
           `pip install "bashos[gui]"`.
  browser  the fallback: the same URL in whatever browser is default.

The window toolkit owns the main thread on macOS, so the native path runs the
asyncio server on a background loop and blocks the main thread in the toolkit.
The browser path stays a plain `asyncio.run` — the shape the rest of bashOS
uses.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import webbrowser
from collections.abc import Callable
from importlib.util import find_spec

from .server import GuiServer

TITLE = "bashOS"
WINDOW_SIZE = (1320, 880)
MIN_SIZE = (960, 620)

Announce = Callable[[GuiServer], None]


def window_available() -> bool:
    """True when a native window can be opened without a browser."""
    if find_spec("webview") is None:
        return False
    try:  # the import name is shared; confirm this is actually pywebview
        import webview

        return hasattr(webview, "create_window") and hasattr(webview, "start")
    except Exception:
        return False


def launch(
    server: GuiServer,
    *,
    window: bool = True,
    open_browser: bool = True,
    announce: Announce | None = None,
) -> None:
    """Serve the desktop until the window closes, or the terminal interrupts."""
    if window and window_available():
        _launch_window(server, announce)
    else:
        _launch_browser(server, open_browser=open_browser, announce=announce)


def _launch_browser(
    server: GuiServer, *, open_browser: bool, announce: Announce | None
) -> None:
    async def main() -> None:
        await server.start()
        if announce:
            announce(server)
        if open_browser:
            # a failure here is cosmetic — the URL is already on the terminal
            with contextlib.suppress(Exception):
                webbrowser.open(server.entry_url)
        try:
            await server.serve_forever()
        finally:
            await server.close()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())


def _launch_window(server: GuiServer, announce: Announce | None) -> None:
    import webview

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, name="bashos-gui", daemon=True)
    thread.start()
    try:
        asyncio.run_coroutine_threadsafe(server.start(), loop).result(timeout=30)
        if announce:
            announce(server)
        width, height = WINDOW_SIZE
        webview.create_window(
            TITLE,
            server.entry_url,
            width=width,
            height=height,
            min_size=MIN_SIZE,
            text_select=True,
        )
        webview.start()  # blocks on the main thread until the window closes
    finally:
        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(server.close(), loop).result(timeout=20)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        with contextlib.suppress(Exception):
            loop.close()
