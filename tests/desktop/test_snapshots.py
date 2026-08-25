"""Visual regression net — exactly three snapshots, kept deliberately small
because SVG baselines churn with Textual point releases.

Update after an intentional visual change:  pytest --snapshot-update
"""

from __future__ import annotations

import pytest

from bashos.desktop.apps.health import HealthApp


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    import bashos.desktop.taskbar as taskbar_mod

    monkeypatch.setattr(taskbar_mod.time, "strftime", lambda fmt: "12:00")


def test_empty_desktop_compact(snap_compare, desktop_app):
    assert snap_compare(desktop_app, terminal_size=(80, 24))


def test_two_apps_tiled_wide(snap_compare, desktop_app, monkeypatch):
    async def fake_floor(self):
        return 0, "[ OK ] load        1.2 on 8 cores\n[ OK ] disk        41% of / used\n"

    monkeypatch.setattr(HealthApp, "_read_floor", fake_floor)

    async def open_apps(pilot):
        await pilot.app.open_app_by_id("console")
        await pilot.app.open_app_by_id("health")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    assert snap_compare(desktop_app, terminal_size=(160, 48), run_before=open_apps)


def test_launcher_grid_open(snap_compare, desktop_app):
    async def open_launcher(pilot):
        await pilot.press("f2")
        await pilot.pause()

    assert snap_compare(desktop_app, terminal_size=(120, 40), run_before=open_launcher)
