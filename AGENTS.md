# AGENTS.md — bashOS

Canonical contract for any coding agent (Claude Code, Copilot, Cursor, Codex, OpenCode) working in this repository. Details live in [CLAUDE.md](CLAUDE.md), [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/HARNESS.md](docs/HARNESS.md); if this file and those disagree, fix the drift rather than picking one.

## What this repo is

Terminal-first AI runtime: Markdown slash commands (`.claude/commands/*.md`) are routed by a LangGraph kernel (`src/bashos/kernel/`) through a loop (`src/bashos/loops/`) onto the OpenCode engine (`src/bashos/opencode/`), authenticated with the user's Claude Code OAuth. Surfaces: the Typer CLI (`shell/`), the Textual desktop (`desktop/`) and the loopback GUI (`gui/`). `chui/` is the optional macOS terminal environment (plain bash/zsh, kept bash 3.2-compatible).

## Hard rules

1. **bashOS never implements a reasoning loop.** OpenCode owns the agent loop, tool broker, sessions and permission gate; bashOS owns userland, routing, policy and the terminal. Work that would add a tool loop to bashOS belongs in the engine layer or nowhere. Loops call the engine, never a model directly. The desktop and GUI are views: they render events, run kernel lines, and never reason or run a loop of their own.
2. **Loops never get network or write tools.** Tool policy is deny-by-default and lives only in `src/bashos/opencode/policy.py` — widening that file is the only way to widen what bashOS can touch. Never add a tool that writes, reaches the network, or spawns an agent not bound by the policy. Bash probes on the allowlist must be strictly read-only and must not be able to execute other commands. Remote work goes through fixed, code-owned probes (`remote.PROBES`); never give a loop ssh or network tools.
3. **`opencode.jsonc` is generated, committed, and credential-free.** Never hand-edit it. Change `.claude/commands/*.md` or `policy.py`, then run `.venv/bin/bashos opencode sync`; a test fails on drift. It must never contain a credential — secrets go in the engine's environment only (`opencode/auth.py`), never on disk.
4. **Anthropic model IDs are limited to** `claude-opus-5-5` (the default), `claude-sonnet-5-5` and `claude-haiku-5-5`, optionally `anthropic/`-qualified. Use no other Claude model strings.
5. **Nothing blocks on a human.** Approval requests are auto-refused and a dead event stream releases the prompt. An approval queue would be a new, explicitly named policy profile, off by default.

## Conventions

- Everything is async; never call sync `invoke` inside the kernel — use `await llm.ainvoke(...)`. The CLI wraps one `asyncio.run`; the Textual desktop is the documented exception.
- Kernel and engine code never print — emit typed events (`src/bashos/events.py`) and let the surface render them.
- A loop is a node factory `(registry, llm, config) -> async node`, registered in `kernel/graph.py:_LOOP_NODES`. Loops short-circuit on missing args (usage) and on `config.dry_run`; tests rely on the dry-run path.
- The GUI uses no web framework, no npm and no build step (`gui/http.py`, hand-written `gui/web/`).
- Shell code (`bin/`, `chui/`, generated prompts): `set -Eeuo pipefail`, quoted expansions, shellcheck-clean.
- New commands and loops ship with docs: a row in the README table and, for loops, a section in docs/HARNESS.md.

## Commands

```bash
make install                         # venv + editable install with dev extras
make test                            # .venv/bin/pytest -q — offline: fake model, no auth, no engine
make lint                            # ruff check . + shellcheck
node --test tests/shell.test.mjs     # GUI layout reducer tests
.venv/bin/bashos opencode sync       # regenerate opencode.jsonc after command/policy edits
.venv/bin/bashos run -n "/sh ..."    # dry-run: no auth needed
```

Before opening a PR, `pytest -q`, `ruff check .`, shellcheck and `bashos opencode sync` (leaving no diff) must all be clean.

## Releasing

Tag `vX.Y.Z` and push the tag; CI builds the sdist/wheel, cuts a GitHub release, publishes to PyPI and pushes the GHCR image. Agents do not tag or release unless explicitly asked.
