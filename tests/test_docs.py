"""Generated documentation stays in step with its sources (fleet UPS-DOC-03/05).

The README commands table is rendered from `.claude/commands/*.md` frontmatter and
the docs index from each document's summary line; both are regenerated here and
compared, offline, so a new command or document cannot land with stale docs.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readme_commands_table_matches_the_registry():
    assert _tool("gen_commands_table").is_current(ROOT), (
        "README.md commands table is stale — run `python3 tools/gen_commands_table.py --write`"
    )


def test_every_command_has_a_row(registry):
    span = _tool("gen_commands_table").render(registry)
    for name in registry:
        assert f"| `/{name}` |" in span


def test_docs_index_is_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "docs_index.py"), "--check", "--root", str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
