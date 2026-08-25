"""Per-surface conversation state — the memory contract every UI shares.

A surface (REPL, desktop console window, script) keeps one `ConsoleSession`
per conversation. `payload_for` builds exactly the kernel payload the REPL
has always sent — `history` / `last_command` / `last_input` appear only once
a turn has been recorded — and `record` appends a turn only when the kernel
actually routed a command, which is what keeps follow-up routing honest.

The model never sees more than HISTORY_TURNS turns of EXCERPT-char excerpts;
what a UI *displays* is its own business and may be the full transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..loops.common import first_fence

HISTORY_TURNS = 3
EXCERPT = 280


@dataclass(frozen=True)
class Turn:
    user: str
    command: str
    output: str


def excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat[: EXCERPT - 3] + "..." if len(flat) > EXCERPT else flat


def format_history(turns: list[Turn]) -> str:
    chunks = []
    for turn in turns[-HISTORY_TURNS:]:
        chunks.append(f"in: {turn.user}\nvia: /{turn.command}\nout: {excerpt(turn.output)}")
    return "\n---\n".join(chunks)


@dataclass
class ConsoleSession:
    """One conversation's turns, last output, and kernel-payload assembly."""

    turns: list[Turn] = field(default_factory=list)
    last_output: str = ""

    def payload_for(self, line: str) -> dict:
        payload: dict = {"input": line, "trace": []}
        if self.turns:
            last = self.turns[-1]
            payload["history"] = format_history(self.turns)
            payload["last_command"] = last.command
            payload["last_input"] = last.user
        return payload

    def record(self, line: str, command: str | None, output: str) -> None:
        self.last_output = output
        if command:
            self.turns.append(Turn(line, command, output))

    def runnable_from_last(self) -> str | None:
        """The first bash fence of the last answer — the `exec` affordance."""
        return first_fence(self.last_output)
