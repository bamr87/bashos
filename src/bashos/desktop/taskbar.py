"""The taskbar: apps button, window tabs, engine indicator, model, clock."""

from __future__ import annotations

import time

from textual import events as textual_events
from textual.containers import Horizontal
from textual.widgets import Static

from .messages import OpenAppRequest
from .wm import Window


class WindowTab(Static):
    """One clickable tab per open window (the whole switcher in -compact)."""

    def __init__(self, window: Window) -> None:
        super().__init__(window.window_title, classes="window-tab", markup=False)
        self.window = window

    def on_click(self, event: textual_events.Click) -> None:
        event.stop()
        self.post_message(Window.Activated(self.window))


class AppsButton(Static):
    def __init__(self) -> None:
        super().__init__("◫ apps", id="apps-button")

    def on_click(self, event: textual_events.Click) -> None:
        event.stop()
        self.post_message(OpenAppRequest("launcher"))


class Clock(Static):
    def on_mount(self) -> None:
        self._tick()
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        self.update(time.strftime("%H:%M"))


class TaskBar(Horizontal):
    """Bottom bar; the app pushes window-set changes into it."""

    def __init__(self, *, backend: str, model: str) -> None:
        super().__init__(id="taskbar")
        self._backend = backend
        self._model = model

    def compose(self):
        yield AppsButton()
        yield Horizontal(id="taskbar-tabs")
        yield Static("", id="taskbar-spacer")
        yield Static("⏻ engine: idle", id="engine-indicator", markup=False)
        yield Static(
            f"{self._backend} · {self._model}", id="model-label", markup=False
        )
        yield Clock(id="clock")

    def update_windows(self, windows: list[Window], active: Window | None) -> None:
        tabs = self.query_one("#taskbar-tabs", Horizontal)
        tabs.remove_children()
        for window in windows:
            tab = WindowTab(window)
            tab.set_class(window is active, "-active")
            tabs.mount(tab)

    def set_engine_state(self, state: str) -> None:
        self.query_one("#engine-indicator", Static).update(f"⏻ engine: {state}")
