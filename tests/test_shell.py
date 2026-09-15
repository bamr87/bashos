"""The shell reducer's contract, run through the offline suite.

The layout reducer is JavaScript (`gui/web/shell.js`), so its unit tests are
too — `tests/shell.test.mjs`, on node's own test runner. Driving them from
pytest keeps one command for the whole suite (`pytest -q`) and keeps the
nav-intent contract from drifting: docs/frontend/SPEC-os-shell.md requires a
tested consumer for every documented intent.

Offline like the rest of the suite: no network, no engine, no browser.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SUITE = Path(__file__).parent / "shell.test.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_shell_reducer_contract():
    proc = subprocess.run(
        ["node", "--test", str(SUITE)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=SUITE.parent.parent,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_reducer_ships_with_the_page():
    """A module the page imports must be inside the served web directory."""
    from bashos.gui.server import WEB_DIR

    assert (WEB_DIR / "shell.js").is_file()
    assert 'from "/shell.js"' in (WEB_DIR / "app.js").read_text()
