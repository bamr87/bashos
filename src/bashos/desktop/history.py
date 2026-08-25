"""File-backed input history for the console's prompt.

Reads and appends prompt_toolkit's FileHistory format ('#' comment lines,
'+'-prefixed entry lines) so ~/.bashos_history carries over from the old
REPL intact.
"""

from __future__ import annotations

import time
from pathlib import Path


class InputHistory:
    def __init__(self, path: Path, limit: int = 1000) -> None:
        self.path = path
        self.entries: list[str] = self._load()[-limit:]
        self._cursor: int | None = None
        self._draft = ""

    def _load(self) -> list[str]:
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        entries: list[str] = []
        current: list[str] | None = None
        for line in text.splitlines():
            if line.startswith("+"):
                current = current or []
                current.append(line[1:])
            else:
                if current:
                    entries.append("\n".join(current))
                current = None
        if current:
            entries.append("\n".join(current))
        return entries

    def append(self, line: str) -> None:
        self._cursor = None
        if not line or (self.entries and self.entries[-1] == line):
            return
        self.entries.append(line)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n# {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                for part in line.split("\n"):
                    handle.write(f"+{part}\n")
        except OSError:
            pass  # history is a convenience, never a failure

    def previous(self, current: str) -> str | None:
        """Step back; the first step stashes the in-progress draft."""
        if not self.entries:
            return None
        if self._cursor is None:
            self._draft = current
            self._cursor = len(self.entries) - 1
        elif self._cursor > 0:
            self._cursor -= 1
        return self.entries[self._cursor]

    def next(self) -> str | None:
        """Step forward; walking past the end restores the stashed draft."""
        if self._cursor is None:
            return None
        self._cursor += 1
        if self._cursor >= len(self.entries):
            self._cursor = None
            return self._draft
        return self.entries[self._cursor]
