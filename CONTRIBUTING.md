# Contributing to bashOS

> How to set up, the architecture rules a pull request must keep, and how releases are cut; the full command list and hard rules are in [AGENTS.md](AGENTS.md).

## Setup

```bash
make install      # venv + editable install with dev extras
make test         # offline suite — fake model, no auth required
make lint         # ruff + shellcheck
```

Or without make: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

Auth is only needed to run commands against a real model (`claude` login, `claude setup-token`, or `ANTHROPIC_API_KEY`); tests and dry-runs never call one. `bashos doctor` diagnoses your environment.

## Architecture

Read [docs/HARNESS.md](docs/HARNESS.md) first. The short version:

- **Commands** are markdown files in `.claude/commands/` — one file is both a
Claude Code slash command and a bashOS-routable program. Adding one requires no code.
- **Loops** live in `src/bashos/loops/`; a loop is a node factory
`(registry, llm, config) -> async node`, registered in `kernel/graph.py:_LOOP_NODES`.
- Everything is async — use `await llm.ainvoke(...)`, never sync `invoke`,
  inside the kernel.
- Loops must short-circuit on missing args (usage) and `config.dry_run`; tests
  rely on the dry-run path.

## Ground rules

- `pytest -q` and `ruff check .` must pass; shell code (including generated
  prompts' style expectations) is `set -Eeuo pipefail`, quoted, shellcheck-clean.
- The react loop's tool policy is deny-by-default read-only — PRs must not add
  write or network tools to it.
- Found a vulnerability? Report it privately as described in [SECURITY.md](SECURITY.md), never in a public issue or PR.
- New commands/loops ship with docs: regenerate the README commands table
(`python3 tools/gen_commands_table.py --write`) and, for loops, add a section to docs/HARNESS.md. `opencode.jsonc` and the docs index are generated too: `bashos opencode sync`, `python3 tools/docs_index.py --write`.

## Releasing

release-please cuts releases from Conventional Commits; don't push tags by hand. Each push to `main` updates a release PR that bumps the version and `CHANGELOG.md`. Merging it tags `vX.Y.Z` and creates the GitHub release, and the same workflow run builds the sdist/wheel, attaches them to the release, publishes to PyPI (once a trusted publisher is configured) and pushes the image to GHCR. To re-publish an existing tag, dispatch `release.yml` with `tag`. [AGENTS.md § Releasing](AGENTS.md#releasing) has the details.
