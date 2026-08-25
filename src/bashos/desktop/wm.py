"""The hybrid-tiling window manager.

Tiled panes are the base: a responsive grid that degrades to one visible
window (with taskbar tabs) in a compact terminal, tiles up to MAX_TILES in a
wide one, and supports maximize/restore. Windows are plain Textual widgets;
the desktop never owns their content.
"""

from __future__ import annotations

from textual import events as textual_events
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

MAX_TILES = 4
COMPACT_BELOW = 110  # columns: under this, one window at a time


class Window(Vertical):
    """A titled, closable, maximizable tile in the desktop grid."""

    class CloseRequested(Message):
        def __init__(self, window: Window) -> None:
            super().__init__()
            self.window = window

    class MaximizeRequested(Message):
        def __init__(self, window: Window) -> None:
            super().__init__()
            self.window = window

    class Activated(Message):
        def __init__(self, window: Window) -> None:
            super().__init__()
            self.window = window

    def __init__(self, body: Widget, *, title: str, wid: str) -> None:
        super().__init__(id=wid, classes="window")
        self._body = body
        self.window_title = title

    def compose(self):
        with Horizontal(classes="titlebar"):
            yield Static(self.window_title, classes="titlebar-label", markup=False)
            yield Static("□", classes="titlebar-btn maximize-btn")
            yield Static("✕", classes="titlebar-btn close-btn")
        yield Container(self._body, classes="window-body")

    def on_click(self, event: textual_events.Click) -> None:
        widget = event.widget
        if widget is not None and widget.has_class("close-btn"):
            self.post_message(self.CloseRequested(self))
        elif widget is not None and widget.has_class("maximize-btn"):
            self.post_message(self.MaximizeRequested(self))
        else:
            self.post_message(self.Activated(self))


class Desktop(Container):
    """The tile area: tracks activation order, visibility, and maximize."""

    class Changed(Message):
        """Window set or activation changed — the taskbar re-renders on this."""

    def __init__(self) -> None:
        super().__init__(id="desktop")
        self._order: list[Window] = []  # activation order, most recent last
        self._maximized: Window | None = None
        self.active: Window | None = None

    @property
    def windows(self) -> list[Window]:
        return list(self._order)

    async def add_window(self, window: Window) -> None:
        await self.mount(window)
        self._order.append(window)
        self.activate(window)

    def activate(self, window: Window) -> None:
        if window in self._order:
            self._order.remove(window)
            self._order.append(window)
        self.active = window
        self._relayout()
        self.post_message(self.Changed())

    async def close_window(self, window: Window) -> None:
        if self._maximized is window:
            self._maximized = None
        if window in self._order:
            self._order.remove(window)
        if self.active is window:
            self.active = self._order[-1] if self._order else None
        await window.remove()
        self._relayout()
        self.post_message(self.Changed())

    def cycle(self) -> None:
        """Bring the least-recently-active window to the front."""
        if len(self._order) > 1:
            self.activate(self._order[0])

    def toggle_maximize(self, window: Window | None = None) -> None:
        target = window or self.active
        if target is None:
            return
        self._maximized = None if self._maximized is target else target
        if self._maximized is not None:
            self.activate(self._maximized)  # relayouts and notifies
        else:
            self._relayout()
            self.post_message(self.Changed())

    @property
    def maximized(self) -> Window | None:
        return self._maximized

    # ------------------------------------------------------------- messages

    async def on_window_close_requested(self, message: Window.CloseRequested) -> None:
        await self.close_window(message.window)

    def on_window_maximize_requested(self, message: Window.MaximizeRequested) -> None:
        self.toggle_maximize(message.window)

    def on_window_activated(self, message: Window.Activated) -> None:
        if message.window is not self.active:
            self.activate(message.window)

    def on_resize(self, event: textual_events.Resize) -> None:
        self._relayout()

    # --------------------------------------------------------------- layout

    def _relayout(self) -> None:
        windows = self._order
        width = self.size.width or 0
        compact = 0 < width < COMPACT_BELOW
        maximized = self._maximized if self._maximized in windows else None

        if maximized is not None:
            visible = [maximized]
        elif compact:
            visible = [self.active] if self.active is not None else windows[-1:]
        else:
            visible = windows[-MAX_TILES:]  # the most recently active tiles

        for window in windows:
            window.set_class(window not in visible, "-hidden")
            window.set_class(window is maximized, "-maximized")
            window.set_class(window is self.active, "-active")

        columns = 1 if (maximized or compact or len(visible) <= 1) else 2
        self.styles.grid_size_columns = columns
        self.styles.grid_size_rows = max(1, (len(visible) + columns - 1) // columns)
