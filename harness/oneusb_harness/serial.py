"""Serial console as test oracle: wait for a regex in the log QEMU writes."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path


class SerialTimeout(AssertionError):
    pass


def wait_for(log: Path, pattern: str | re.Pattern, timeout: float, *, start: int = 0,
             alive: Callable[[], bool] | None = None, poll: float = 0.5) -> tuple[re.Match, int]:
    """Wait until `pattern` matches the log (from byte offset `start`).

    Returns (match, end_offset) so callers can chain waits without re-matching.
    Fails early if `alive()` turns false (VM exited) and the pattern still isn't there.
    """
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern
    deadline = time.monotonic() + timeout
    while True:
        text = read_text(log)[start:]
        m = rx.search(text)
        if m:
            return m, start + m.end()
        if alive is not None and not alive():
            raise SerialTimeout(f"VM exited before {rx.pattern!r} appeared; tail:\n{tail(log)}")
        if time.monotonic() > deadline:
            raise SerialTimeout(f"{rx.pattern!r} not seen within {timeout:.0f}s; tail:\n{tail(log)}")
        time.sleep(poll)


def read_text(log: Path) -> str:
    try:
        return log.read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def tail(log: Path, lines: int = 40) -> str:
    return "\n".join(read_text(log).splitlines()[-lines:])
