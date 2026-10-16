#!/usr/bin/env python3
"""Merge CHUI terminal keybindings into VS Code User/keybindings.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER = "chui-terminal"

CHUI_KEYS = {
    ("cmd+left", "terminalFocus"),
    ("cmd+right", "terminalFocus"),
    ("alt+left", "terminalFocus"),
    ("alt+right", "terminalFocus"),
    ("cmd+up", "terminalFocus"),
    ("cmd+down", "terminalFocus"),
    ("alt+up", "terminalFocus"),
    ("alt+down", "terminalFocus"),
    ("ctrl+left", "terminalFocus"),
    ("ctrl+right", "terminalFocus"),
    ("cmd+backspace", "terminalFocus"),
    ("alt+backspace", "terminalFocus"),
    ("cmd+delete", "terminalFocus"),
    ("alt+delete", "terminalFocus"),
}


def _user_file() -> Path | None:
    home = Path.home()
    for app in ("Code", "Cursor", "Code - Insiders"):
        path = home / "Library/Application Support" / app / "User/keybindings.json"
        if path.parent.is_dir():
            return path
    return None


def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit(f"unexpected keybindings format: {path}")
    return data


def merge(dest: Path, chui_bindings: list[dict]) -> int:
    existing = _load_json(dest)
    kept = []
    for item in existing:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        pair = (item.get("key"), item.get("when"))
        if pair in CHUI_KEYS and item.get("command") == "workbench.action.terminal.sendSequence":
            continue
        kept.append(item)
    kept.extend(chui_bindings)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(kept, indent=4) + "\n", encoding="utf-8")
    return len(chui_bindings)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    src = root / "config/vscode/keybindings.json"
    dest = _user_file()
    if dest is None:
        print("vscode keys: skipped (no Code User dir)")
        sys.exit(0)
    bindings = json.loads(src.read_text(encoding="utf-8"))
    n = merge(dest, bindings)
    print(f"vscode keys: merged {n} into {dest}")
