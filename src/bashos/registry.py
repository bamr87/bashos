"""Command registry — the userland of bashOS.

Commands are markdown files in .claude/commands/: the exact files Claude Code
loads as project slash commands. bashOS reads the same files and routes each
one through a kernel orchestration loop declared in its frontmatter:

    ---
    description: one-line summary          # used by Claude Code and bashOS
    argument-hint: <what to pass>
    bashos:
      loop: prompt | refine | react        # which orchestration loop runs it
      requires-args: true                  # optional, default true
      system: extra system prompt          # optional
      agent: bashos | bashos-sealed        # optional, defaults from the loop
    ---
    prompt body with $ARGUMENTS placeholder

One file, three runtimes: type /sh inside Claude Code, run `bashos run /sh ...`
in any terminal, or type /sh in the OpenCode TUI — `bashos opencode sync`
compiles this same registry into the engine's project config, and `agent:`
picks which tool policy (opencode/policy.py) the command runs under.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

COMMANDS_DIR = Path(".claude") / "commands"
VALID_LOOPS = ("prompt", "refine", "react")

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    body: str
    path: Path
    argument_hint: str = ""
    loop: str = "prompt"
    system: str | None = None
    requires_args: bool = True
    agent: str | None = None  # engine agent override; None = derived from loop

    def render(self, args: str) -> str:
        return self.body.replace("$ARGUMENTS", args)

    @property
    def usage(self) -> str:
        hint = self.argument_hint or "<args>"
        return f"usage: /{self.name} {hint}\n{self.description}"


def parse_command_file(path: Path) -> CommandSpec:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    if match := _FRONTMATTER.match(text):
        meta = yaml.safe_load(match.group(1)) or {}
        body = text[match.end() :]
    bashos_meta = meta.get("bashos") or {}
    loop = str(bashos_meta.get("loop", "prompt"))
    if loop not in VALID_LOOPS:
        raise ValueError(f"{path}: unknown loop {loop!r}; expected one of {VALID_LOOPS}")
    return CommandSpec(
        name=path.stem.lower(),
        description=str(meta.get("description", "")).strip(),
        argument_hint=str(meta.get("argument-hint", "")).strip(),
        loop=loop,
        system=bashos_meta.get("system"),
        agent=bashos_meta.get("agent"),
        requires_args=bool(bashos_meta.get("requires-args", True)),
        body=body.strip(),
        path=path,
    )


def find_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default cwd) to the nearest bashOS root."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / COMMANDS_DIR).is_dir():
            return candidate
    packaged = Path(__file__).resolve().parents[2]
    if (packaged / COMMANDS_DIR).is_dir():
        return packaged
    raise FileNotFoundError(
        "no bashOS command directory found (.claude/commands) — run from a bashOS checkout"
    )


def load_registry(root: Path | None = None) -> dict[str, CommandSpec]:
    root = root or find_root()
    specs: dict[str, CommandSpec] = {}
    for path in sorted((root / COMMANDS_DIR).glob("*.md")):
        spec = parse_command_file(path)
        specs[spec.name] = spec
    return specs
