"""The AI Console — the REPL, reborn as a desktop window.

Every feature of the old line REPL lives here: slash commands and plain
english through the kernel, follow-up routing, bounded conversation memory
(ConsoleSession), `exec` confirm-then-run, `!` shell escapes, and the
builtins — now as UI actions. On top of that: live route hints on every
keystroke (model-free), streamed answer text, a tool-activity feed, and a
Stop that aborts the engine run.

Each window owns its ConsoleSession, its own kernel, and (on the engine
backend) its own model handles carrying this window's event sink.
"""

from __future__ import annotations

import asyncio

from rich.panel import Panel
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, RichLog, Static

from ... import events as engine_events
from ...kernel import guess_command, looks_like_followup, parse_line
from ...shell.render import is_literal_output
from ...shell.session import ConsoleSession
from ..history import InputHistory
from ..messages import EngineEventMsg, OpenAppRequest, TurnFinished, TurnStarted
from ..modals import ExecModal
from ..services import DesktopServices
from ..wm import Window

BUILTINS = ("help", "list", "doctor", "engine", "clear", "exec", "exit", "quit")


class PromptInput(Input):
    BINDINGS = [
        Binding("up", "history_prev", show=False),
        Binding("down", "history_next", show=False),
        Binding("escape", "stop_turn", show=False),
    ]

    def __init__(self, console: ConsoleApp, **kwargs) -> None:
        super().__init__(**kwargs)
        self.console = console

    def action_history_prev(self) -> None:
        if (line := self.console.history.previous(self.value)) is not None:
            self.value = line
            self.cursor_position = len(line)

    def action_history_next(self) -> None:
        if (line := self.console.history.next()) is not None:
            self.value = line
            self.cursor_position = len(line)

    def action_stop_turn(self) -> None:
        self.console.stop_turn()


class ConsoleApp(Vertical):
    """One conversation window against the kernel."""

    def __init__(self, services: DesktopServices) -> None:
        super().__init__(classes="console")
        self.services = services
        self.session = ConsoleSession()
        self.history = InputHistory(services.history_path)
        self._turn_worker = None
        self._turn_running = False
        self._stream_target: Markdown | None = None
        self._stream_buffer = ""
        self._stream_dirty = False
        self._tool_state: dict[str, str] = {}
        self._prefill = ""
        llm, classify_llm = services.models_for_window(self._sink)
        self.kernel = services.build_kernel(
            llm=llm, classify_llm=classify_llm, on_engine_event=self._sink
        )

    def _sink(self, event: engine_events.EngineEvent) -> None:
        """Engine → UI bridge: called from the watch task, must not block."""
        self.post_message(EngineEventMsg(event))

    # ---------------------------------------------------------------- layout

    def compose(self):
        yield VerticalScroll(classes="transcript")
        feed = RichLog(classes="tool-feed", markup=False, wrap=True, max_lines=200)
        feed.display = False
        yield feed
        with Horizontal(classes="prompt-bar"):
            yield Static("▸", classes="prompt-glyph")
            yield PromptInput(
                self,
                placeholder="/command, plain english, !shell — F2 for apps",
                classes="prompt-input",
            )
            stop = Static("■ stop (esc)", classes="stop-btn")
            stop.display = False
            yield stop
        yield Static("", classes="route-hint", markup=False)

    def on_mount(self) -> None:
        # streamed text coalesces on this timer, not per delta
        self.set_interval(0.05, self._flush_stream)
        prompt = self.query_one(PromptInput)
        if self._prefill:
            prompt.value = self._prefill
            prompt.cursor_position = len(self._prefill)
        prompt.focus()

    def set_prefill(self, text: str) -> None:
        """Callable before mount (the launcher pre-types a command)."""
        self._prefill = text
        if self.is_mounted:
            prompt = self.query_one(PromptInput)
            prompt.value = text
            prompt.cursor_position = len(text)

    # ----------------------------------------------------------------- input

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        self.history.append(line)
        await self.handle_line(line)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.query_one(".route-hint", Static).update(self.hint_for(event.value.strip()))

    def hint_for(self, text: str) -> str:
        """Zero-cost routing preview — pure functions, no model calls."""
        if not text or text.startswith("!") or text in BUILTINS:
            return ""
        command, _ = parse_line(text)
        registry = self.services.registry
        if command is not None:
            if spec := registry.get(command):
                return f"→ /{command} · {spec.loop} loop"
            return f"unknown command /{command}"
        if self.session.turns and looks_like_followup(text):
            return f"↩ follow-up → /{self.session.turns[-1].command}"
        if guessed := guess_command(text, registry):
            return f"→ /{guessed} (heuristic)"
        return "→ classify"

    async def handle_line(self, line: str) -> None:
        if line in ("exit", "quit"):
            self._close_window()
            return
        if line == "clear":
            await self.query_one(".transcript", VerticalScroll).remove_children()
            feed = self.query_one(".tool-feed", RichLog)
            feed.clear()
            feed.display = False
            return
        if line in ("help", "list"):
            self.post_message(OpenAppRequest("launcher"))
            return
        if line == "doctor":
            self.post_message(OpenAppRequest("doctor"))
            return
        if line == "engine":
            self.post_message(OpenAppRequest("engine"))
            return
        if line == "exec":
            self._exec_last()
            return
        if line.startswith("!"):
            await self.app.shell_runner.run_captured(line[1:].strip())  # type: ignore[attr-defined]
            return
        if self._turn_running:
            self._notice("a turn is already running — esc stops it")
            return
        self._start_turn(line)

    # ----------------------------------------------------------------- turns

    def _start_turn(self, line: str) -> None:
        self._append(Static(f"you ▸ {line}", classes="user-line", markup=False))
        payload = self.session.payload_for(line)
        self._turn_running = True
        self._set_running_ui(True)
        self.post_message(TurnStarted(self.id or "", line))
        self._turn_worker = self.run_worker(
            self._run_turn(line, payload),
            group=f"turn-{self.id}",
            exclusive=True,
            exit_on_error=False,
        )

    async def _run_turn(self, line: str, payload: dict) -> None:
        try:
            result = await self.kernel.ainvoke(payload)
        except asyncio.CancelledError:
            # worker cancelled → CancelledError reached the engine layer,
            # which aborted the run; report the outcome without awaiting
            self._end_stream(final=None)
            self._notice("stopped.")
            self._turn_running = False
            self.call_later(self._set_running_ui, False)
            raise
        except Exception as exc:
            self._end_stream(final=None)
            self._append_error(str(exc))
            return
        finally:
            if self._turn_running:
                self._turn_running = False
                self.call_later(self._set_running_ui, False)

        output = result.get("output", "")
        if result.get("route") == "error":
            self._end_stream(final=None)
            self._append_error(output or "unknown kernel error")
        else:
            self.session.record(line, result.get("command"), output)
            self._render_output(output)
        self.post_message(TurnFinished(self.id or "", line, dict(result)))

    def stop_turn(self) -> None:
        if self._turn_running and self._turn_worker is not None:
            self._turn_worker.cancel()

    def _render_output(self, output: str) -> None:
        if is_literal_output(output):
            self._end_stream(final=None)
            self._append(Static(output, classes="literal-output", markup=False))
        elif self._stream_target is not None:
            # the final text is authoritative — replace the streamed buffer
            self._end_stream(final=output)
        else:
            self._append(Markdown(output, classes="answer"))

    # ------------------------------------------------------------- streaming

    def on_engine_event_msg(self, message: EngineEventMsg) -> None:
        # no message.stop(): the app also watches these for the taskbar
        event = message.event
        if isinstance(event, engine_events.TextDelta):
            if self._turn_running:
                self._stream_text(event.text)
        elif isinstance(event, engine_events.ToolEvent):
            self._tool_line(event)
        elif isinstance(event, engine_events.PermissionEvent):
            if event.decision == "auto-rejected":
                self._feed(f"✗ denied by policy: {event.action}")

    def _stream_text(self, fragment: str) -> None:
        if self._stream_target is None:
            self._stream_target = Markdown("", classes="answer -streaming")
            self._append(self._stream_target)
        self._stream_buffer += fragment
        self._stream_dirty = True

    def _flush_stream(self) -> None:
        if self._stream_dirty and self._stream_target is not None:
            self._stream_dirty = False
            self._stream_target.update(self._stream_buffer)
            self._scroll_end()

    def _end_stream(self, *, final: str | None) -> None:
        target, self._stream_target = self._stream_target, None
        self._stream_buffer = ""
        self._stream_dirty = False
        if target is not None:
            target.remove_class("-streaming")
            if final is not None:
                target.update(final)
            else:
                target.remove()

    def _tool_line(self, event: engine_events.ToolEvent) -> None:
        if event.status in ("pending", ""):
            return
        state = self._tool_state.get(event.call_id)
        if event.status == "running" and state is None:
            self._tool_state[event.call_id] = "running"
            self._feed(f"⚙ {event.description}")
        elif event.status in ("completed", "error") and state != "done":
            self._tool_state[event.call_id] = "done"
            mark = "✓" if event.status == "completed" else "✗"
            duration = (
                f" ({event.duration_ms / 1000:.1f}s)" if event.duration_ms else ""
            )
            self._feed(f"{mark} {event.description}{duration}")

    def _feed(self, text: str) -> None:
        feed = self.query_one(".tool-feed", RichLog)
        feed.display = True
        feed.write(text)

    # ------------------------------------------------------------------ exec

    def _exec_last(self) -> None:
        command = self.session.runnable_from_last()
        if not command:
            self._append_error("nothing to exec — no bash fence in the last answer")
            return

        def _decide(choice: str | None) -> None:
            if choice == "captured":
                self.app.call_later(self.app.shell_runner.run_captured, command)  # type: ignore[attr-defined]
            elif choice == "attached":
                code = self.app.shell_runner.run_attached(command)  # type: ignore[attr-defined]
                self._notice(f"exit {code}" if code else "done")

        self.app.push_screen(ExecModal(command), _decide)

    # --------------------------------------------------------------- helpers

    def _append(self, widget) -> None:
        self.query_one(".transcript", VerticalScroll).mount(widget)
        self._scroll_end()

    def _scroll_end(self) -> None:
        self.query_one(".transcript", VerticalScroll).scroll_end(animate=False)

    def _append_error(self, text: str) -> None:
        self._append(Static(
            Panel(text, border_style="red", title="error", title_align="left"),
            classes="error-panel",
        ))

    def _notice(self, text: str) -> None:
        self._append(Static(text, classes="notice", markup=False))

    def _set_running_ui(self, running: bool) -> None:
        self.query_one(".stop-btn", Static).display = running
        self.set_class(running, "-busy")

    def _close_window(self) -> None:
        node = self.parent
        while node is not None and not isinstance(node, Window):
            node = node.parent
        if node is not None:
            node.post_message(Window.CloseRequested(node))
