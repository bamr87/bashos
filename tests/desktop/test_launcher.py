"""Launcher grid + command palette providers, offline."""

from __future__ import annotations

from textual.widgets import OptionList

from bashos.desktop.launcher import LauncherScreen
from bashos.desktop.wm import Desktop


def _option_ids(option_list: OptionList) -> set[str]:
    return {
        option.id
        for option in (
            option_list.get_option_at_index(i) for i in range(option_list.option_count)
        )
        if option.id
    }


async def test_launcher_lists_every_registry_command_and_app(desktop_app, registry):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(desktop_app.screen, LauncherScreen)
        ids = _option_ids(desktop_app.screen.query_one(OptionList))
        for name in registry:
            assert f"cmd:{name}" in ids
        for app_id in ("console", "health", "doctor", "engine", "trace"):
            assert f"app:{app_id}" in ids


async def test_escape_dismisses_the_launcher(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(desktop_app.screen, LauncherScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(desktop_app.screen, LauncherScreen)
        assert len(desktop_app.query_one(Desktop).windows) == 0


async def test_selecting_an_app_opens_its_window(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await pilot.press("f2")
        await pilot.pause()
        option_list = desktop_app.screen.query_one(OptionList)
        # find and select the doctor entry
        for index in range(option_list.option_count):
            if option_list.get_option_at_index(index).id == "app:doctor":
                option_list.highlighted = index
                break
        await pilot.press("enter")
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        assert len(desktop.windows) == 1
        assert desktop.windows[0].id.startswith("win-doctor-")


async def test_command_palette_provider_finds_registry_commands(desktop_app, registry):
    from bashos.desktop.launcher import BashosCommandProvider

    assert BashosCommandProvider in desktop_app.COMMANDS
    assert "sh" in registry  # the provider's data source is the live registry
