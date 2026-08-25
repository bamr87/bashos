"""The desktop app registry.

An app is a factory `(services) -> Widget` plus chrome metadata. The
launcher, the command palette, and the taskbar all read this one dict —
adding an app here is the whole registration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from textual.widget import Widget
from textual.widgets import Static

from ..services import DesktopServices


@dataclass(frozen=True)
class AppSpec:
    id: str
    title: str
    factory: Callable[[DesktopServices], Widget]
    singleton: bool = False  # focus the existing window instead of a second


class DoctorPanel(Static):
    """Auth + environment checks — runtime.auth.run_checks, rendered."""

    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="doctor-panel")
        self._services = services

    def on_mount(self) -> None:
        from ...runtime.auth import run_checks
        from ...shell.render import doctor_table

        self.update(doctor_table(run_checks(self._services.config)))


def _placeholder(text: str) -> Callable[[DesktopServices], Widget]:
    def factory(services: DesktopServices) -> Widget:
        return Static(text, classes="placeholder", markup=False)

    return factory


def _console(services: DesktopServices) -> Widget:
    from .console import ConsoleApp

    return ConsoleApp(services)


def _health(services: DesktopServices) -> Widget:
    from .health import HealthApp

    return HealthApp(services)


def _engine(services: DesktopServices) -> Widget:
    from .engine import EngineApp

    return EngineApp(services)


def _command(services: DesktopServices) -> Widget:
    from .command import CommandApp

    return CommandApp(services)


def _trace(services: DesktopServices) -> Widget:
    from .trace import TraceViewerApp

    return TraceViewerApp(services)


def _opencode_tui(services: DesktopServices) -> Widget:
    from .opencode_tui import OpencodeTuiApp

    return OpencodeTuiApp(services)


APPS: dict[str, AppSpec] = {
    "console": AppSpec(id="console", title="AI Console", factory=_console),
    "health": AppSpec(id="health", title="Health", factory=_health, singleton=True),
    "doctor": AppSpec(id="doctor", title="Doctor", factory=DoctorPanel, singleton=True),
    "engine": AppSpec(id="engine", title="Engine", factory=_engine, singleton=True),
    "command": AppSpec(id="command", title="Commands", factory=_command, singleton=True),
    "trace": AppSpec(id="trace", title="Trace", factory=_trace, singleton=True),
    "opencode": AppSpec(
        id="opencode", title="OpenCode TUI", factory=_opencode_tui, singleton=True
    ),
}
