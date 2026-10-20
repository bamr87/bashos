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

## Claude Code notes

Moved verbatim from the former `CLAUDE.md` on 2026-10-20 (decision D4: one canonical agent file). Fold these into the sections above when you next touch them.


Terminal-first AI runtime: Claude slash commands routed through a LangGraph kernel onto the OpenCode engine, on Claude Code OAuth. Design doc: docs/HARNESS.md. The engine (policy, credential bridge, projection): docs/OPENCODE.md. The desktop (windowed Textual surface): docs/DESKTOP.md. The GUI front end (`bashos gui`): docs/DESKTOP.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`): docs/FORGE.md.

**The core rule: bashOS never implements a reasoning loop.** OpenCode owns the agent loop, tool broker, sessions, and permission gate; bashOS owns userland, routing, policy, and the terminal. Work that would add a tool loop to bashOS belongs in the engine layer or nowhere.

## Layout

- `.claude/commands/*.md` — userland. Each file is a Claude Code slash command,
  a bashOS command, AND (compiled) an OpenCode command; `bashos:` frontmatter
  declares its loop (`prompt` | `refine` | `react`) and optionally its engine
  `agent`. They are the single source of truth.
- `src/bashos/kernel/` — LangGraph state machine (parse → classify/dispatch →
  loop → respond). State lives in `kernel/state.py`; `trace` is append-only.
- `src/bashos/loops/` — orchestration loops. A loop is a node factory
`(registry, llm, config) -> async node`. Register new ones in `kernel/graph.py:_LOOP_NODES`. Loops call the engine, never a model directly.
- `src/bashos/opencode/` — the core. `policy.py` is the ONLY place that widens
bashOS's blast radius; `project.py` compiles the registry + policy into the generated, committed `opencode.jsonc`; `auth.py` bridges Claude Code OAuth into the engine process's environment (never to disk); `server.py`/`engine.py` supervise it and expose two verbs, `complete()` and `act()`.
- `src/bashos/runtime/` — backend resolution. Default is `opencode`; the Claude
Agent SDK adapter and the direct API are completion-only fallbacks that cannot run the react loop. Default model: claude-opus-5-5.
- `src/bashos/remote.py` — dev-box integration (`bashos remote …`): CODE runs
fixed read-only probes over ssh, the model reasons locally over the gathered text, and the interaction mirrors onto the box's tmux console monitor. Never give loops ssh/network tools — extend `remote.PROBES` instead.
- `src/bashos/shell/` — Typer CLI (one-shot `bashos run` and friends) + Rich
  rendering for it.
- `src/bashos/desktop/` — the Textual desktop, the interactive surface: tiling
window manager, taskbar, launcher, app suite (AI console, health, doctor, engine, commands, trace, OpenCode TUI). A client of the kernel/engine — it renders typed events (`src/bashos/events.py`), it never reasons. Docs: docs/DESKTOP.md.
- `src/bashos/gui/` — the GUI desktop (`bashos gui`, docs/DESKTOP.md).
`http.py` is a ~300-line asyncio HTTP/SSE server (no web framework — never add one); `server.py` routes onto the kernel behind a loopback + per-process-token guard; `web/` is the front end, hand-written and unbundled (no npm, no build step) — `app.js` draws, `shell.js` is a pure layout reducer (experience modes, nav intents) tested by `tests/shell.test.mjs`. The GUI is a VIEW: it runs kernel lines only — no shell passthrough, no policy of its own, and never a loop. Window/OS-shell direction: docs/frontend/.
- `tools/capture_desktop.py` — drives the GUI with a real browser and writes
the stills/GIFs in `docs/DESKTOP-TOUR.md`. Not packaged, not in CI; re-run it when the front end changes (`pip install playwright pillow`).
- `chui/` — the optional macOS terminal environment (Oh My Zsh + p10k + Zellij + modern CLI;
formerly bamr87/chui, merged with history). Plain bash + zsh, no Python dependency: `bin/bashos chui …` dispatches to `chui/tui.sh` BEFORE the venv bootstrap, and the Typer `bashos chui` command forwards to the same script. `tui.sh` is the one dispatch table (the zsh `chui` function only re-sources prefs); `lib.sh` holds the link table, the `local.zsh` managed block (never rewrite the rest of that file), and the Zellij key mode. Install never deletes a real file. Tests: `chui/tests/` (stdlib + pytest, a throwaway `$HOME`, `defaults`/`osascript` shimmed); they run under macOS's stock bash 3.2 too, so keep the scripts 3.2-compatible. Docs: chui/README.md.
- `docker-compose.yml` — optional services: `phoenix` (observability, :6006),
`langgraph-dev` (serves the kernel graph via `langgraph.json`, :2024), `bashos` (containerized terminal, profile `cli`). LangChain/LangGraph are in-process libraries otherwise — no daemon required.

## Conventions

- Everything async; the CLI wraps one `asyncio.run` (the Textual desktop is the
documented exception — Textual owns its loop). Never call sync `invoke` inside the kernel — use `await llm.ainvoke`.
- The desktop owns the alternate screen: kernel/engine code must never print —
  emit typed events (`events.py`) and let the surface render them.
- Loops must short-circuit on missing args (usage) and `config.dry_run`
  (rendered prompt, no model call) — tests rely on the dry-run path.
- Tool policy is deny-by-default and lives in `opencode/policy.py`. Widening it
is the only way to widen what bashOS can touch: never add a tool that writes, reaches the network, or spawns an unbound agent.
- `opencode.jsonc` is GENERATED and committed. Edit `.claude/commands/*.md` or
`policy.py`, then `bashos opencode sync`; a test fails on drift. It must never contain a credential — secrets go in the engine's environment only.
- Anything that could block on a human must not: approval requests are
auto-refused, and a dead event stream releases the prompt. The desktop's interactive affordances (exec confirm, Stop) never loosen this — an approval queue would be a new, explicitly named policy profile, off by default.
- Shell code style everywhere (bin/, generated prompts): `set -Eeuo pipefail`,
  quoted expansions, shellcheck-clean.

## Commands

```bash
.venv/bin/pytest -q                  # offline tests (fake model, no engine)
.venv/bin/bashos desktop             # the Textual desktop (bare `bashos` on a TTY too)
.venv/bin/bashos gui --browser       # the GUI desktop, in a browser tab
.venv/bin/bashos run -n "/sh ..."    # dry-run: no auth needed
.venv/bin/bashos doctor              # auth/backend diagnosis (offline)
.venv/bin/bashos opencode sync       # regenerate opencode.jsonc
.venv/bin/bashos opencode status     # boot the engine, report live state
bin/bashos chui install --dry-run    # macOS terminal environment: the plan, nothing changed
```
