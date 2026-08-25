"""The launcher: an app-grid modal (F2) and command-palette providers (^P).

Both read the same two sources — the userland registry (CommandSpec) and the
desktop app registry (AppSpec). Selecting a command opens a console window
for it; selecting an app opens that app's window.
"""

from __future__ import annotations

from functools import partial

from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..opencode.project import agent_for
from ..registry import CommandSpec
from .apps import APPS


class LauncherScreen(ModalScreen[str | None]):
    """Full-screen overlay listing every command and desktop app.

    Dismisses with the selection id — "cmd:<name>" or "app:<id>" — or None.
    """

    BINDINGS = [Binding("escape", "dismiss_launcher", "close")]

    def __init__(self, registry: dict[str, CommandSpec]) -> None:
        super().__init__()
        self._registry = registry

    def compose(self):
        options: list[Option] = [Option("─ apps ─", disabled=True)]
        for spec in APPS.values():
            options.append(Option(f"  {spec.title}", id=f"app:{spec.id}"))
        options.append(Option("─ commands ─", disabled=True))
        for name, spec in self._registry.items():
            label = f"  /{name} · {spec.loop} · {agent_for(spec)} — {spec.description}"
            options.append(Option(label, id=f"cmd:{name}"))
        with Vertical(id="launcher"):
            yield Static("bashOS launcher", id="launcher-title")
            yield OptionList(*options, id="launcher-list")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_dismiss_launcher(self) -> None:
        self.dismiss(None)


class BashosCommandProvider(Provider):
    """Registry commands in the command palette: '/sh — …'."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, spec in self.app.services.registry.items():  # type: ignore[attr-defined]
            text = f"/{name} — {spec.description}"
            score = matcher.match(text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(text),
                    partial(self.app.open_command, name),  # type: ignore[attr-defined]
                    help=spec.usage,
                )

    async def discover(self) -> Hits:
        for name, spec in self.app.services.registry.items():  # type: ignore[attr-defined]
            yield DiscoveryHit(
                f"/{name} — {spec.description}",
                partial(self.app.open_command, name),  # type: ignore[attr-defined]
                help=spec.usage,
            )


class DesktopAppProvider(Provider):
    """Desktop apps and window actions in the command palette."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for spec in APPS.values():
            text = f"open {spec.title}"
            score = matcher.match(text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(text),
                    partial(self.app.open_app_by_id, spec.id),  # type: ignore[attr-defined]
                )

    async def discover(self) -> Hits:
        for spec in APPS.values():
            yield DiscoveryHit(
                f"open {spec.title}",
                partial(self.app.open_app_by_id, spec.id),  # type: ignore[attr-defined]
            )
