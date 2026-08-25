"""AI Console behavior — REPL parity, offline (dry-run + FakeChat)."""

from __future__ import annotations

import asyncio

from bashos.config import KernelConfig
from bashos.desktop.app import BashOSApp
from bashos.desktop.apps.console import ConsoleApp, PromptInput
from bashos.desktop.modals import ExecModal
from bashos.desktop.wm import Desktop


async def _console(app: BashOSApp, pilot) -> ConsoleApp:
    await app.open_app_by_id("console")
    await pilot.pause()
    return app.query_one(ConsoleApp)


async def _wait_turns(app: BashOSApp) -> None:
    from textual.worker import WorkerCancelled

    try:
        await app.workers.wait_for_complete()
    except WorkerCancelled:
        pass  # a deliberately stopped turn is a valid outcome


async def test_slash_dry_run_turn_renders_literal_output(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await pilot.press(*"/sh list files")
        await pilot.press("enter")
        await _wait_turns(desktop_app)
        await pilot.pause()
        literals = console.query(".literal-output").nodes
        assert literals, "a dry-run report must render on the literal path"
        assert "[dry-run] /sh" in str(literals[0].render())


async def test_missing_args_shows_usage_literal(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("/sh")
        await _wait_turns(desktop_app)
        await pilot.pause()
        literals = console.query(".literal-output").nodes
        assert literals and str(literals[0].render()).startswith("usage: /sh")


async def test_unknown_command_renders_error_panel(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("/nope whatever")
        await _wait_turns(desktop_app)
        await pilot.pause()
        assert console.query(".error-panel").nodes, "route=error must render red"


async def test_route_hints_are_model_free(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        assert console.hint_for("/sh find files") == "→ /sh · prompt loop"
        assert console.hint_for("/nope x") == "unknown command /nope"
        assert "cron" in console.hint_for("run a job every day at 9am cron")
        assert console.hint_for("!git status") == ""


async def test_followup_hint_after_recorded_turn(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("/sh find big files")
        await _wait_turns(desktop_app)
        assert console.session.turns, "dry-run turns still record (command routed)"
        assert console.hint_for("now exclude .venv") == "↩ follow-up → /sh"


async def test_history_payload_matches_repl_shape(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("/sh find big files")
        await _wait_turns(desktop_app)
        payload = console.session.payload_for("now exclude .venv")
        assert payload["last_command"] == "sh"
        assert payload["last_input"] == "/sh find big files"
        assert "via: /sh" in payload["history"]
        assert payload["trace"] == []


async def test_clear_builtin_empties_transcript(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("/sh list")
        await _wait_turns(desktop_app)
        await pilot.pause()
        assert console.query(".transcript > *").nodes
        await console.handle_line("clear")
        await pilot.pause()
        assert not console.query(".transcript > *").nodes


async def test_stop_cancels_a_running_turn_without_crashing(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)

        class _SlowKernel:
            async def ainvoke(self, payload):
                await asyncio.sleep(3600)

        console.kernel = _SlowKernel()
        await console.handle_line("/sh anything")
        await pilot.pause()
        assert console._turn_running
        console.stop_turn()
        await _wait_turns(desktop_app)
        await pilot.pause()
        notices = [str(n.render()) for n in console.query(".notice").nodes]
        assert "stopped." in notices
        assert not console._turn_running


async def test_fakechat_turn_calls_the_model_exactly_once(registry, tmp_path):
    from bashos.desktop.services import DesktopServices
    from tests.conftest import FakeChat

    llm = FakeChat(replies=["```bash\nls -la\n```"])
    services = DesktopServices(
        config=KernelConfig(),
        registry=registry,
        llm=llm,
        classify_llm=llm,
        history_path=tmp_path / "history",
    )
    app = BashOSApp(services=services)
    async with app.run_test(size=(120, 40)) as pilot:
        console = await _console(app, pilot)
        await console.handle_line("/sh list everything")
        await _wait_turns(app)
        await pilot.pause()
        assert llm.calls == 1
        assert console.query(".answer").nodes, "markdown answer rendered"
        assert console.session.last_output.startswith("```bash")


async def test_exec_with_no_fence_shows_error(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("exec")
        await pilot.pause()
        panels = console.query(".error-panel").nodes
        assert panels, "exec with nothing runnable must say so"


async def test_exec_modal_shows_fence_and_escape_cancels(registry, tmp_path):
    from bashos.desktop.services import DesktopServices
    from tests.conftest import FakeChat

    llm = FakeChat(replies=["run this:\n```bash\necho hello\n```"])
    services = DesktopServices(
        config=KernelConfig(),
        registry=registry,
        llm=llm,
        classify_llm=llm,
        history_path=tmp_path / "history",
    )
    app = BashOSApp(services=services)
    async with app.run_test(size=(120, 40)) as pilot:
        console = await _console(app, pilot)
        await console.handle_line("/sh say hello")
        await _wait_turns(app)
        await console.handle_line("exec")
        await pilot.pause()
        assert isinstance(app.screen, ExecModal)
        assert app.screen.command == "echo hello"
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ExecModal)


async def test_bang_passthrough_streams_into_an_output_window(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("!printf 'a\\nb'")
        await _wait_turns(desktop_app)
        await pilot.pause()
        desktop = desktop_app.query_one(Desktop)
        shell_windows = [w for w in desktop.windows if (w.id or "").startswith("win-shell-")]
        assert len(shell_windows) == 1
        log_lines = [str(line) for line in shell_windows[0].query_one("RichLog").lines]
        assert any("[exit 0]" in line for line in log_lines)


async def test_builtin_doctor_opens_the_doctor_window(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("doctor")
        await pilot.pause()
        await pilot.pause()  # OpenAppRequest bubbles to the app, then mounts
        desktop = desktop_app.query_one(Desktop)
        assert any((w.id or "").startswith("win-doctor-") for w in desktop.windows)


async def test_exit_builtin_closes_the_console_window(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        await console.handle_line("exit")
        await pilot.pause()
        assert len(desktop_app.query_one(Desktop).windows) == 0


async def test_quit_shuts_the_engine_down_exactly_once(desktop_app):
    calls = {"shutdown": 0}

    async def fake_shutdown():
        calls["shutdown"] += 1

    desktop_app.services.shutdown = fake_shutdown  # type: ignore[method-assign]
    async with desktop_app.run_test(size=(120, 40)):
        pass  # exiting run_test unmounts the app
    assert calls["shutdown"] == 1


async def test_prompt_history_navigates_previous_lines(desktop_app):
    async with desktop_app.run_test(size=(120, 40)) as pilot:
        console = await _console(desktop_app, pilot)
        prompt = console.query_one(PromptInput)
        prompt.focus()
        await pilot.press(*"/sh one")
        await pilot.press("enter")
        await _wait_turns(desktop_app)
        await pilot.press(*"/sh two")
        await pilot.press("enter")
        await _wait_turns(desktop_app)
        await pilot.press("up")
        assert prompt.value == "/sh two"
        await pilot.press("up")
        assert prompt.value == "/sh one"
        await pilot.press("down")
        assert prompt.value == "/sh two"
