# Contributing to bashOS

## Setup

```bash
make install      # venv + editable install with dev extras
make test         # offline suite — fake model, no auth required
make lint         # ruff + shellcheck
```

Or without make: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

Auth is only needed to run commands against a real model (`claude` login,
`claude setup-token`, or `ANTHROPIC_API_KEY`); tests and dry-runs never call
one. `bashos doctor` diagnoses your environment.

## Architecture

Read [docs/HARNESS.md](docs/HARNESS.md) first. The short version:

- **Commands** are markdown files in `.claude/commands/` — one file is both a
  Claude Code slash command and a bashOS-routable program. Adding one requires
  no code.
- **Loops** live in `src/bashos/loops/`; a loop is a node factory
  `(registry, llm, config) -> async node`, registered in
  `kernel/graph.py:_LOOP_NODES`.
- Everything is async — use `await llm.ainvoke(...)`, never sync `invoke`,
  inside the kernel.
- Loops must short-circuit on missing args (usage) and `config.dry_run`; tests
  rely on the dry-run path.

## Ground rules

- `pytest -q` and `ruff check .` must pass; shell code (including generated
  prompts' style expectations) is `set -Eeuo pipefail`, quoted, shellcheck-clean.
- The react loop's tool policy is deny-by-default read-only — PRs must not add
  write or network tools to it.
- New commands/loops ship with docs: a row in the README table and, for loops,
  a section in docs/HARNESS.md.

## Releasing

Tag `vX.Y.Z` and push the tag — CI builds sdist/wheel, cuts a GitHub release,
publishes to PyPI (once a trusted publisher is configured), and pushes the
image to GHCR.
