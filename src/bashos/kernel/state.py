"""Kernel state — the record that flows through every orchestration loop."""

from __future__ import annotations

import operator
from typing import Annotated, NotRequired, TypedDict


class KernelState(TypedDict):
    input: str
    command: NotRequired[str]
    args: NotRequired[str]
    route: NotRequired[str]  # "slash" | "classified" | "fallback" | "error"
    output: NotRequired[str]
    error: NotRequired[str]
    # append-only harness log; every node contributes, reducer merges
    trace: Annotated[list[str], operator.add]
