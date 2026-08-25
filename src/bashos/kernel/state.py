"""Kernel state — the record that flows through every orchestration loop."""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict


class KernelState(TypedDict):
    input: str
    command: NotRequired[str]
    args: NotRequired[str]
    route: NotRequired[str]  # "slash" | "classified" | "fallback" | "followup" | "error"
    output: NotRequired[str]
    error: NotRequired[str]
    # REPL session: previous turn, so follow-ups can reuse a command
    last_command: NotRequired[str]
    last_input: NotRequired[str]
    history: NotRequired[str]
    # append-only harness log; every node contributes, reducer merges
    trace: Annotated[list[str], operator.add]
