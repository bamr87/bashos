#!/usr/bin/env python3
"""Map Cmd/Opt cursor keys in Apple Terminal to zsh emacs widgets."""

from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile

LEFT, RIGHT, UP, DOWN = "\uf702", "\uf703", "\uf700", "\uf701"
BACKSPACE, FWDDEL = "\u007f", "\uf728"

BINDINGS = {
    f"@{LEFT}": "\x01",
    f"@{RIGHT}": "\x05",
    f"@{UP}": "\x1b[1;9A",
    f"@{DOWN}": "\x1b[1;9B",
    f"~{LEFT}": "\x1bb",
    f"~{RIGHT}": "\x1bf",
    f"~{UP}": "\x1b[1;3A",
    f"~{DOWN}": "\x1b[1;3B",
    f"^{LEFT}": "\x1b[1;5D",
    f"^{RIGHT}": "\x1b[1;5C",
    f"@{BACKSPACE}": "\x15",
    f"~{BACKSPACE}": "\x1b\x7f",
    f"@{FWDDEL}": "\x0b",
    f"~{FWDDEL}": "\x1bd",
}


def _export() -> dict:
    fd, path = tempfile.mkstemp(suffix=".plist")
    os.close(fd)
    try:
        subprocess.check_call(["defaults", "export", "com.apple.Terminal", path])
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    finally:
        os.unlink(path)


def _import(data: dict) -> None:
    fd, path = tempfile.mkstemp(suffix=".plist")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            plistlib.dump(data, fh, fmt=plistlib.FMT_BINARY)
        subprocess.check_call(["defaults", "import", "com.apple.Terminal", path])
    finally:
        os.unlink(path)


def apply() -> str:
    data = _export()
    windows = data.setdefault("Window Settings", {})
    names = {
        data.get("Default Window Settings"),
        data.get("Startup Window Settings"),
    }
    names.discard(None)
    if not names:
        names = {"Clear Dark"} if "Clear Dark" in windows else set(windows)
    applied = []
    for name in sorted(names):
        prof = windows.get(name)
        if not isinstance(prof, dict):
            continue
        keys = dict(prof.get("keyMapBoundKeys") or {})
        keys.update(BINDINGS)
        prof["keyMapBoundKeys"] = keys
        prof["useOptionAsMetaKey"] = True
        applied.append(name)
    _import(data)
    return ", ".join(applied) or "(none)"


if __name__ == "__main__":
    names = apply()
    print(f"terminal keys: {names}")
    print("restart Terminal.app for Cmd/Opt arrows to take effect")
