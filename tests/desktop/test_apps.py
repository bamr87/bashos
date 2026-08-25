"""The app suite: health, engine inspector, command runner, trace, opencode."""

from __future__ import annotations

from textual.widgets import DataTable, Input, OptionList, Select, Static

from bashos.desktop.apps.command import CommandApp
from bashos.desktop.apps.engine import EngineApp
from bashos.desktop.apps.health import HealthApp
from bashos.desktop.apps.opencode_tui import tui_argv
from bashos.desktop.apps.trace import TraceViewerApp
from bashos.opencode.policy import describe_policy

CANNED_FLOOR = """\
os-health · mac.local · 2026-08-24
[ OK ] load        1.2 on 8 cores
[WARN] memory      82% used
[CRIT] disk        97% of / used
this line is not a verdict at all
[ OK ] docker      not installed (skipped)
"""


async def _open(app, pilot, app_id):
    await app.open_app_by_id(app_id)
    await pilot.pause()


async def test_health_parses_verdict_lines_and_tolerates_noise(desktop_app, monkeypatch):
    async def fake_floor(self):
        return 2, CANNED_FLOOR

    monkeypatch.setattr(HealthApp, "_read_floor", fake_floor)
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "health")
        await desktop_app.workers.wait_for_complete()
        await pilot.pause()
        health = desktop_app.query_one(HealthApp)
        table = health.query_one(DataTable)
        assert table.row_count == 4, "four verdict lines, banner and noise ignored"
        header = str(health.query_one(".health-header", Static).render())
        assert "CRIT" in header and "exit 2" in header


async def test_health_ask_button_opens_a_prefilled_console(desktop_app, monkeypatch):
    async def fake_floor(self):
        return 0, "[ OK ] load 1.0\n"

    monkeypatch.setattr(HealthApp, "_read_floor", fake_floor)
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await _open(desktop_app, pilot, "health")
        await desktop_app.workers.wait_for_complete()
        health = desktop_app.query_one(HealthApp)
        health.query_one("#health-ask").press()
        await pilot.pause()
        await pilot.pause()
        from bashos.desktop.apps.console import ConsoleApp, PromptInput

        console = desktop_app.query_one(ConsoleApp)
        assert console.query_one(PromptInput).value.startswith("/health")


async def test_engine_app_policy_view_matches_describe_policy(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "engine")
        engine = desktop_app.query_one(EngineApp)
        policy_text = str(engine.query_one(".policy-view", Static).render())
        assert policy_text == describe_policy()
        assert "bash:*=deny" in policy_text


async def test_engine_app_does_not_boot_the_engine_on_open(desktop_app, monkeypatch):
    booted = {"count": 0}

    async def fake_status():
        booted["count"] += 1
        return []

    desktop_app.services.engine_status = fake_status  # type: ignore[method-assign]
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "engine")
        await pilot.pause()
        assert booted["count"] == 0, "opening the window must not spawn a process"


async def test_command_app_preview_uses_dry_run_report_without_a_model(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "command")
        command = desktop_app.query_one(CommandApp)
        command.query_one("#command-select", Select).value = "sh"
        await pilot.pause()
        command.query_one(".command-args", Input).value = "find big files"
        command.preview()
        await pilot.pause()
        body = str(command.query_one(".command-preview-body", Static).render())
        assert body.startswith("[dry-run] /sh → loop=prompt")
        assert "find big files" in body


async def test_command_app_empty_args_shows_usage(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "command")
        command = desktop_app.query_one(CommandApp)
        command.query_one("#command-select", Select).value = "sh"
        await pilot.pause()
        command.preview()
        await pilot.pause()
        body = str(command.query_one(".command-preview-body", Static).render())
        assert body.startswith("usage: /sh")


async def test_trace_viewer_lists_finished_turns(desktop_app):
    async with desktop_app.run_test(size=(160, 48)) as pilot:
        await _open(desktop_app, pilot, "trace")
        await _open(desktop_app, pilot, "console")
        from bashos.desktop.apps.console import ConsoleApp

        console = desktop_app.query_one(ConsoleApp)
        await console.handle_line("/sh find big files")
        await desktop_app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()
        viewer = desktop_app.query_one(TraceViewerApp)
        assert viewer.query_one("#trace-list", OptionList).option_count == 1
        note = str(viewer.query_one(".trace-note", Static).render())
        assert "1 turn(s)" in note


async def test_opencode_tui_argv_is_the_plain_binary():
    assert tui_argv() == ["opencode"]


async def test_opencode_window_never_spawns_on_open(desktop_app, monkeypatch):
    import bashos.desktop.apps.opencode_tui as tui_mod

    calls = {"run": 0}
    monkeypatch.setattr(
        tui_mod.subprocess, "run", lambda *a, **k: calls.__setitem__("run", calls["run"] + 1)
    )
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        await _open(desktop_app, pilot, "opencode")
        await pilot.pause()
        assert calls["run"] == 0
