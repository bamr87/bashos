<!-- kit: sdlc v0.1.0 · AGENTS.md is the CANONICAL agent instructions file (decision D4, UPS-AGENT-07/08). -->

# bashos

> How to work in bashOS: the exact commands, the layout, the hard rules and the generated files, canonical for every coding agent and contributor.

## What this repo is

bashOS is a terminal-first AI runtime: Markdown slash commands (`.claude/commands/*.md`) are routed by a LangGraph kernel (`src/bashos/kernel/`) through a loop (`src/bashos/loops/`) onto the OpenCode engine (`src/bashos/opencode/`), authenticated with the user's Claude Code OAuth. It serves people who want an AI-assisted terminal for software development and systems work, through three surfaces on one kernel: the Typer CLI (`shell/`), the Textual desktop (`desktop/`) and the loopback GUI (`gui/`). `chui/` is the optional macOS terminal environment. A change is done when `make test`, `make lint`, `node --test tests/shell.test.mjs` and `.venv/bin/bashos opencode sync` (leaving no diff) are all clean, the generated docs are current, and the docs a change affects are updated in the same PR.

Design docs: [docs/HARNESS.md](docs/HARNESS.md) (layers, loops, extension guide), [docs/OPENCODE.md](docs/OPENCODE.md) (policy, credential bridge, projection), [docs/DESKTOP.md](docs/DESKTOP.md) (the Textual desktop and the GUI), [docs/FORGE.md](docs/FORGE.md) (the dev-box monitoring pattern behind `bin/os-health`, `/health`, `/dash`). Every document is indexed in [docs/README.md](docs/README.md).

## Hard rules

1. **bashOS never implements a reasoning loop.** OpenCode owns the agent loop, tool broker, sessions and permission gate; bashOS owns userland, routing, policy and the terminal. Work that would add a tool loop to bashOS belongs in the engine layer or nowhere. Loops call the engine, never a model directly. The desktop and GUI are views: they render events, run kernel lines, and never reason or run a loop of their own.
2. **Loops never get network or write tools.** Tool policy is deny-by-default and lives only in `src/bashos/opencode/policy.py` — widening that file is the only way to widen what bashOS can touch. Never add a tool that writes, reaches the network, or spawns an agent not bound by the policy. Bash probes on the allowlist must be strictly read-only and must not be able to execute other commands. Remote work goes through fixed, code-owned probes (`remote.PROBES`); never give a loop ssh or network tools.
3. **`opencode.jsonc` is generated, committed, and credential-free.** Never hand-edit it. Change `.claude/commands/*.md` or `policy.py`, then run `.venv/bin/bashos opencode sync`; a test fails on drift. It must never contain a credential — secrets go in the engine's environment only (`opencode/auth.py`), never on disk.
4. **Anthropic model IDs are limited to** `claude-opus-5-5` (the default), `claude-sonnet-5-5` and `claude-haiku-5-5`, optionally `anthropic/`-qualified. Use no other Claude model strings.
5. **Nothing blocks on a human.** Approval requests are auto-refused and a dead event stream releases the prompt. The desktop's interactive affordances (exec confirm, Stop) never loosen this; an approval queue would be a new, explicitly named policy profile, off by default.

## Stack & commands

Python 3.11+ (LangGraph, langchain-core, httpx to the engine, Typer + Rich, Textual, PyYAML); the engine is the `opencode` binary, installed outside pip; Node runs only the GUI reducer tests; shellcheck lints the shell code.

```bash
npm i -g opencode-ai         # the engine (or: curl -fsSL https://opencode.ai/install | bash)
make install                 # .venv + editable install with the dev extras
./bin/bashos                 # the desktop (bootstraps .venv itself if make install was skipped)
./bin/bashos gui             # …or the GUI desktop, on the same kernel
make test                    # the offline suite: fake model, no auth, no engine
make lint                    # ruff check . + shellcheck
```

```bash
node --test tests/shell.test.mjs                 # GUI layout reducer tests
.venv/bin/bashos opencode sync                   # regenerate opencode.jsonc after command/policy edits
python3 tools/gen_commands_table.py --write      # regenerate the README commands table
python3 tools/docs_index.py --write              # regenerate the docs/README.md index
.venv/bin/bashos run -n "/sh ..."                # dry-run: routing + rendered prompt, no auth needed
.venv/bin/bashos doctor                          # auth/backend diagnosis (offline)
.venv/bin/bashos opencode status                 # boot the engine, report live state
.venv/bin/bashos gui --browser                   # the GUI desktop, in a browser tab
bin/bashos chui install --dry-run                # macOS terminal environment: the plan, nothing changed
```

Before opening a PR: `make test`, `make lint` and `node --test tests/shell.test.mjs` pass, and `.venv/bin/bashos opencode sync` leaves no diff.

## Layout

- `.claude/commands/*.md` — userland, the single source of truth. Each file is a Claude Code slash command, a bashOS command and (compiled) an OpenCode command; `bashos:` frontmatter declares its loop (`prompt` | `refine` | `react`) and optionally its engine `agent`.
- `src/bashos/kernel/` — the LangGraph state machine (parse → classify/dispatch → loop → respond). State lives in `kernel/state.py`; `trace` is append-only.
- `src/bashos/loops/` — the orchestration loops, registered in `kernel/graph.py:_LOOP_NODES`.
- `src/bashos/opencode/` — the core. `policy.py` is the ONLY place that widens bashOS's blast radius; `project.py` compiles the registry + policy into `opencode.jsonc`; `auth.py` bridges Claude Code OAuth into the engine process's environment (never to disk); `server.py`/`engine.py` supervise the engine and expose two verbs, `complete()` and `act()`.
- `src/bashos/runtime/` — backend resolution. Default `opencode`; the Claude Agent SDK adapter and the direct API are completion-only fallbacks that cannot run the react loop.
- `src/bashos/remote.py` — dev-box integration (`bashos remote …`): code runs fixed read-only probes over ssh, the model reasons locally over the gathered text, and the interaction mirrors onto the box's tmux console monitor. Extend `remote.PROBES`; never give loops ssh or network tools.
- `src/bashos/shell/` — the Typer CLI (`bashos run` and friends) and its Rich rendering.
- `src/bashos/desktop/` — the Textual desktop: tiling window manager, taskbar, launcher, app suite (AI console, health, doctor, engine, commands, trace, OpenCode TUI). It renders typed events (`src/bashos/events.py`) and never reasons.
- `src/bashos/gui/` — the GUI desktop (`bashos gui`). `http.py` is a ~300-line asyncio HTTP/SSE server (never add a web framework); `server.py` routes onto the kernel behind a loopback + per-process-token guard; `web/` is hand-written and unbundled — `app.js` draws, `shell.js` is a pure layout reducer tested by `tests/shell.test.mjs`. It runs kernel lines only: no shell passthrough, no policy of its own, never a loop. Window/OS-shell direction: [docs/frontend/](docs/frontend/README.md).
- `bin/` — `bashos` (the launcher: bootstraps `.venv`, dispatches `chui` before it) and `os-health` (the verdict floor `/health` and the desktop's Health app run).
- `chui/` — the optional macOS terminal environment (Oh My Zsh + p10k + Zellij + modern CLI; formerly bamr87/chui, merged with history). See **chui** below.
- `tools/` — repository scripts that do not ship: `capture_desktop.py` (the stills/GIFs in `docs/DESKTOP-TOUR.md`; not in CI, re-run when the front end changes, needs `pip install playwright pillow`), `gen_commands_table.py` and the vendored `docs_index.py`.
- `docker-compose.yml`, `docker/` — optional services: `phoenix` (:6006), `langgraph-dev` (serves the kernel graph via `langgraph.json`, :2024), `bashos` (the containerized terminal, profile `cli`). LangChain/LangGraph are in-process libraries otherwise.
- `tests/` — the offline pytest suite (`tests/desktop/` has SVG snapshots) and `shell.test.mjs`; `features/`, `verify/` — the fleet feature index and user scenarios.

## Conventions

- **Backlog of record:** GitHub Issues with the fleet labels (`.github/sdlc.yml`, issues mode). Pick up issues labelled `agent:ready`; never touch `agent:hold` or `human-review`.
- **Definition of Done:** the fleet default pull request checklist (this repo has no `.github/pull_request_template.md`), plus the gates under **Stack & commands**.
- **Decisions:** ADRs in `docs/adr/NNNN-slug.md`, indexed in `docs/adr/README.md`. Add one for anything hard to reverse.
- **Commits:** Conventional Commits (`feat fix docs style refactor test chore perf ci build`). The PR title is the squash subject.
- **Branches:** `feature/`, `fix/`, `docs/`, `refactor/`, `test/` or `chore/` off `main`.
- **Changelog:** `CHANGELOG.md` (Keep a Changelog) records notable changes.
- **Generated files — never hand-edit:** `opencode.jsonc` (`bashos opencode sync`), the `AUTO:commands` span in `README.md` (`tools/gen_commands_table.py`), the `AUTO:docs-index` span in `docs/README.md` (`tools/docs_index.py`, vendored from the hub — change it there). `tests/test_opencode.py` and `tests/test_docs.py` fail when any of them is stale.
- **New commands and loops ship with docs:** run `python3 tools/gen_commands_table.py --write` for the README commands table and, for a loop, add a section to `docs/HARNESS.md`.
- **Markdown:** one paragraph per line (no hard-wrapped prose); every document opens with one H1 and a one-sentence `>` summary.
- **Never:** push to `main` directly, commit lockfiles or secrets, suppress type errors, leave empty exception handlers, or edit generated files by hand.

## Code rules

- Everything is async; never call sync `invoke` inside the kernel — use `await llm.ainvoke(...)`. The CLI wraps one `asyncio.run`; the Textual desktop is the documented exception (Textual owns its loop).
- The desktop owns the alternate screen: kernel and engine code never print — emit typed events (`src/bashos/events.py`) and let the surface render them.
- A loop is a node factory `(registry, llm, config) -> async node`. Loops short-circuit on missing args (usage) and on `config.dry_run` (rendered prompt, no model call); tests rely on the dry-run path.
- The GUI uses no web framework, no npm and no build step.
- Shell code (`bin/`, `chui/`, generated prompts): `set -Eeuo pipefail`, quoted expansions, shellcheck-clean.

## chui

- Plain bash + zsh, no Python dependency: `bin/bashos chui …` dispatches to `chui/tui.sh` BEFORE the venv bootstrap, and the Typer `bashos chui` command forwards to the same script.
- `tui.sh` is the one dispatch table (the zsh `chui` function only re-sources prefs); `lib.sh` holds the link table, the `local.zsh` managed block (never rewrite the rest of that file) and the Zellij key mode. Install never deletes a real file.
- Tests: `chui/tests/` (stdlib + pytest, a throwaway `$HOME`, `defaults`/`osascript` shimmed). They run under macOS's stock bash 3.2 too, so keep the scripts 3.2-compatible. Docs: [chui/README.md](chui/README.md).

## Releasing

Tag `vX.Y.Z` and push the tag; CI builds the sdist/wheel, cuts a GitHub release, publishes to PyPI and pushes the GHCR image. Agents do not tag or release unless explicitly asked.

## Fleet context

Member of the bamr87 fleet, vendored in the hub as the `projects/bashos` submodule: commit and push here first; the hub bumps its pointer afterwards. The standards live in the hub: <https://github.com/bamr87/bamr87/tree/main/specs> (the Universal Project Standard); this repo's SDLC declaration is `.github/sdlc.yml`. Loops that act on this repo: `claude.yml` (the `@claude` mention handler), `conformance.yml` (the hub's fleet conformance check), `verify.yml` (the fleet verify gate over `features/` and `verify/`), and from the hub the daily fleet-pulse doctor (draft fix PRs for failing workflows) and the issue pipeline (`agent:ready` issues to draft PRs). None of them merges.

## Standard deviations

none

## Governance

Read [`docs/constitution.md`](docs/constitution.md) before changing anything: it is the highest-precedence rule set here and wins over this file when they disagree. It changes only through a numbered record in [`docs/amendments/`](docs/amendments/), ratified by the maintainer merging the PR; agents propose, never merge. Every user-facing feature has a stable id in [`features/features.yml`](features/features.yml) with `status`, location and the PRD requirement ids it serves; the PRD's "Feature catalog" block is generated from it (`python3 <bamr87/bamr87>/tools/governance_lint.py prd-sync . --write`; check with `… check .`). Never hand-edit that block or `CHANGELOG.md`.
