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


APPS: dict[str, AppSpec] = {
    "console": AppSpec(
        id="console",
        title="AI Console",
        factory=_placeholder("AI Console — arriving in the next milestone"),
    ),
    "health": AppSpec(
        id="health",
        title="Health",
        factory=_placeholder("Health monitor — arriving in a later milestone"),
        singleton=True,
    ),
    "doctor": AppSpec(
        id="doctor",
        title="Doctor",
        factory=DoctorPanel,
        singleton=True,
    ),
    "engine": AppSpec(
        id="engine",
        title="Engine",
        factory=_placeholder("Engine inspector — arriving in a later milestone"),
        singleton=True,
    ),
    "trace": AppSpec(
        id="trace",
        title="Trace",
        factory=_placeholder("Kernel trace viewer — arriving in a later milestone"),
        singleton=True,
    ),
}
