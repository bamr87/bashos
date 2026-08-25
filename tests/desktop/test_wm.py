"""Window-manager behavior: responsive tiling, maximize, focus, taskbar."""

from __future__ import annotations

from bashos.desktop.taskbar import TaskBar, WindowTab
from bashos.desktop.wm import Desktop


def _visible(desktop: Desktop):
    return [w for w in desktop.windows if not w.has_class("-hidden")]


async def test_app_boots_headless_with_desktop_and_taskbar(desktop_app):
    async with desktop_app.run_test(size=(120, 40)):
        assert desktop_app.query_one(Desktop) is not None
        assert desktop_app.query_one(TaskBar) is not None
        assert desktop_app.theme == "bashos-dark"


async def test_80x24_shows_a_single_window_with_tabs(desktop_app):
    async with desktop_app.run_test(size=(80, 24)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        assert len(desktop.windows) == 2
        assert len(_visible(desktop)) == 1, "compact width tiles one window at a time"
        assert len(desktop_app.query(WindowTab).nodes) == 2, "both reachable from tabs"


async def test_160x48_tiles_two_windows(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        assert len(_visible(desktop)) == 2


async def test_maximize_hides_siblings_and_restores(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)

        desktop.toggle_maximize()
        await pilot.pause()
        assert desktop.maximized is desktop.active
        assert len(_visible(desktop)) == 1
        assert desktop.active.has_class("-maximized")

        desktop.toggle_maximize()
        await pilot.pause()
        assert desktop.maximized is None
        assert len(_visible(desktop)) == 2


async def test_cycle_moves_focus_between_windows(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        second = desktop.active
        desktop_app.action_cycle_window()
        await pilot.pause()
        assert desktop.active is not second


async def test_close_window_updates_the_taskbar(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await pilot.pause()
        assert len(desktop_app.query(WindowTab).nodes) == 2

        await desktop_app.action_close_window()
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        assert len(desktop.windows) == 1
        assert len(desktop_app.query(WindowTab).nodes) == 1
        assert desktop.active is not None


async def test_singleton_app_focuses_the_existing_window(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await desktop_app.open_app_by_id("doctor")
        await desktop_app.open_app_by_id("trace")
        await desktop_app.open_app_by_id("doctor")  # singleton: no second window
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        assert len(desktop.windows) == 2
        assert desktop.active.id.startswith("win-doctor-")
