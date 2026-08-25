"""BashOSApp — the desktop shell.

Owns the window manager, the taskbar, the launcher, themes, and the
app-scoped engine lifecycle (started lazily by the first live turn, stopped
exactly once on unmount). Everything else lives in the apps.
"""

from __future__ import annotations

import itertools

from textual.app import App, ComposeResult
from textual.binding import Binding

from .apps import APPS
from .launcher import BashosCommandProvider, DesktopAppProvider, LauncherScreen
from .messages import OpenAppRequest
from .modals import HelpModal, QuitConfirm
from .services import DesktopServices
from .taskbar import TaskBar
from .theme import BASHOS_DARK, BASHOS_LIGHT
from .wm import Desktop, Window


class BashOSApp(App[None]):
    TITLE = "bashOS"
    CSS_PATH = "desktop.tcss"
    HORIZONTAL_BREAKPOINTS = [(0, "-compact"), (110, "-standard"), (150, "-wide")]
    COMMANDS = App.COMMANDS | {BashosCommandProvider, DesktopAppProvider}
    BINDINGS = [
        Binding("f2", "launcher", "apps"),
        Binding("f1", "help", "help"),
        Binding("ctrl+n", "new_console", "console"),
        Binding("ctrl+o", "cycle_window", "next window"),
        Binding("ctrl+b", "toggle_maximize", "maximize"),
        Binding("ctrl+shift+w", "close_window", "close window"),
        Binding("ctrl+t", "cycle_theme", "theme"),
        Binding("ctrl+q", "quit_desktop", "quit", priority=True),
    ]

    def __init__(
        self,
        *,
        services: DesktopServices | None = None,
        model: str | None = None,
    ) -> None:
        self.services = services or DesktopServices.from_env(model=model)
        self._window_ids = itertools.count(1)
        super().__init__()

    # ---------------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        yield Desktop()
        yield TaskBar(
            backend=self.services.backend or "dry-run",
            model=self.services.config.model,
        )

    def on_mount(self) -> None:
        self.register_theme(BASHOS_DARK)
        self.register_theme(BASHOS_LIGHT)
        self.theme = "bashos-dark"

    async def on_unmount(self) -> None:
        # the desktop owns ONE engine for its whole lifetime — this is the
        # single place it is stopped (one-shot `bashos run` keeps its own)
        await self.services.shutdown()

    @property
    def desktop(self) -> Desktop:
        return self.query_one(Desktop)

    @property
    def taskbar(self) -> TaskBar:
        return self.query_one(TaskBar)

    def on_desktop_changed(self, message: Desktop.Changed) -> None:
        self.taskbar.update_windows(self.desktop.windows, self.desktop.active)

    # ------------------------------------------------------------------ apps

    async def open_app_by_id(self, app_id: str, args: str = "") -> None:
        spec = APPS.get(app_id)
        if spec is None:
            return
        if spec.singleton:
            for window in self.desktop.windows:
                if window.id and window.id.startswith(f"win-{app_id}-"):
                    self.desktop.activate(window)
                    return
        wid = f"win-{app_id}-{next(self._window_ids)}"
        window = Window(spec.factory(self.services), title=spec.title, wid=wid)
        await self.desktop.add_window(window)

    async def open_command(self, name: str) -> None:
        """Open a console window pre-aimed at /name (placeholder until the
        console app lands)."""
        await self.open_app_by_id("console", args=f"/{name} ")

    async def on_open_app_request(self, message: OpenAppRequest) -> None:
        if message.app_id == "launcher":
            self.action_launcher()
            return
        await self.open_app_by_id(message.app_id, message.args)

    # --------------------------------------------------------------- actions

    def action_launcher(self) -> None:
        def _launch(selection: str | None) -> None:
            if not selection:
                return
            kind, _, name = selection.partition(":")
            if kind == "app":
                self.call_later(self.open_app_by_id, name)
            elif kind == "cmd":
                self.call_later(self.open_command, name)

        self.push_screen(LauncherScreen(self.services.registry), _launch)

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    async def action_new_console(self) -> None:
        await self.open_app_by_id("console")

    def action_cycle_window(self) -> None:
        self.desktop.cycle()

    def action_toggle_maximize(self) -> None:
        self.desktop.toggle_maximize()

    async def action_close_window(self) -> None:
        if self.desktop.active is not None:
            await self.desktop.close_window(self.desktop.active)

    def action_cycle_theme(self) -> None:
        self.theme = "bashos-light" if self.theme == "bashos-dark" else "bashos-dark"

    def action_quit_desktop(self) -> None:
        def _decide(quit_: bool | None) -> None:
            if quit_:
                self.exit()

        self.push_screen(QuitConfirm(), _decide)
