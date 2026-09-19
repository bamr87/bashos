# bashOS

<<<<<<< Updated upstream
Terminal-first AI runtime: Claude slash commands routed through a LangGraph kernel onto the OpenCode engine, on Claude Code OAuth. Design doc: docs/HARNESS.md. The engine (policy, credential bridge, projection): docs/OPENCODE.md. The desktop (windowed Textual surface): docs/DESKTOP.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`): docs/FORGE.md. docs/OPENCODE.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`): docs/FORGE.md. The GUI front end (`bashos gui`): docs/DESKTOP.md.
||||||| Stash base
Terminal-first AI runtime: Claude slash commands routed through a LangGraph kernel onto the OpenCode engine, on Claude Code OAuth. Design doc: docs/HARNESS.md. The engine (policy, credential bridge, projection): docs/OPENCODE.md. The desktop (windowed Textual surface): docs/DESKTOP.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`):
docs/FORGE.md.
======= Terminal-first AI runtime: Claude slash commands routed through a LangGraph kernel onto the OpenCode engine, on Claude Code OAuth. Design doc: docs/HARNESS.md. The engine (policy, credential bridge, projection):
<<<<<<< HEAD
docs/OPENCODE.md. The desktop (windowed Textual surface): docs/DESKTOP.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`): docs/FORGE.md.
||||||| e147539
docs/OPENCODE.md. The dev-server monitoring pattern (`bin/os-health`,
`/health`, `/dash`): docs/FORGE.md.
======= docs/OPENCODE.md. The dev-server monitoring pattern (`bin/os-health`, `/health`, `/dash`): docs/FORGE.md. The GUI front end (`bashos gui`): docs/DESKTOP.md.
>>>>>>> 4e04c89164334d9daf8762caec1f7bed433d776e
>>>>>>> Stashed changes

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
Agent SDK adapter and the direct API are completion-only fallbacks that cannot run the react loop. Default model: claude-opus-5.
- `src/bashos/remote.py` — dev-box integration (`bashos remote …`): CODE runs
<<<<<<< Updated upstream
fixed read-only probes over ssh, the model reasons locally over the gathered text, and the interaction mirrors onto the box's tmux console monitor. Never give loops ssh/network tools — extend `remote.PROBES` instead.
||||||| Stash base
fixed read-only probes over ssh, the model reasons locally over the gathered text, and the interaction mirrors onto the box's tmux console monitor. Never
  give loops ssh/network tools — extend `remote.PROBES` instead.
======= fixed read-only probes over ssh, the model reasons locally over the gathered text, and the interaction mirrors onto the box's tmux console monitor. Never give loops ssh/network tools — extend `remote.PROBES` instead.
<<<<<<< HEAD
>>>>>>> Stashed changes
- `src/bashos/shell/` — Typer CLI (one-shot `bashos run` and friends) + Rich
  rendering for it.
- `src/bashos/desktop/` — the Textual desktop, the interactive surface: tiling
<<<<<<< Updated upstream
window manager, taskbar, launcher, app suite (AI console, health, doctor, engine, commands, trace, OpenCode TUI). A client of the kernel/engine — it renders typed events (`src/bashos/events.py`), it never reasons. Docs: docs/DESKTOP.md.
- `src/bashos/shell/` — Typer CLI, prompt-toolkit REPL, Rich rendering.
- `src/bashos/gui/` — the desktop (`bashos gui`, docs/DESKTOP.md). `http.py` is
a ~300-line asyncio HTTP/SSE server (no web framework — never add one); `server.py` routes onto the kernel behind a loopback + per-process-token guard; `web/` is the front end, hand-written and unbundled (no npm, no build step) — `app.js` draws, `shell.js` is a pure layout reducer (experience modes, nav intents) tested by `tests/shell.test.mjs`. The GUI is a VIEW: it runs kernel lines only — no shell passthrough, no policy of its own, and never a loop. Window/OS-shell direction: docs/frontend/.
- `tools/capture_desktop.py` — drives the GUI with a real browser and writes
the stills/GIFs in `docs/DESKTOP-TOUR.md`. Not packaged, not in CI; re-run it when the front end changes (`pip install playwright pillow`).
||||||| Stash base
window manager, taskbar, launcher, app suite (AI console, health, doctor, engine, commands, trace, OpenCode TUI). A client of the kernel/engine — it renders typed events (`src/bashos/events.py`), it never reasons. Docs:
  docs/DESKTOP.md.
======= window manager, taskbar, launcher, app suite (AI console, health, doctor, engine, commands, trace, OpenCode TUI). A client of the kernel/engine — it renders typed events (`src/bashos/events.py`), it never reasons. Docs: docs/DESKTOP.md.
||||||| e147539
- `src/bashos/shell/` — Typer CLI, prompt-toolkit REPL, Rich rendering.
=======
- `src/bashos/shell/` — Typer CLI, prompt-toolkit REPL, Rich rendering.
- `src/bashos/gui/` — the desktop (`bashos gui`, docs/DESKTOP.md). `http.py` is
a ~300-line asyncio HTTP/SSE server (no web framework — never add one); `server.py` routes onto the kernel behind a loopback + per-process-token guard; `web/` is the front end, hand-written and unbundled (no npm, no build step) — `app.js` draws, `shell.js` is a pure layout reducer (experience modes, nav intents) tested by `tests/shell.test.mjs`. The GUI is a VIEW: it runs kernel lines only — no shell passthrough, no policy of its own, and never a loop. Window/OS-shell direction: docs/frontend/.
- `tools/capture_desktop.py` — drives the GUI with a real browser and writes
the stills/GIFs in `docs/DESKTOP-TOUR.md`. Not packaged, not in CI; re-run it when the front end changes (`pip install playwright pillow`).
>>>>>>> 4e04c89164334d9daf8762caec1f7bed433d776e
>>>>>>> Stashed changes
- `docker-compose.yml` — optional services: `phoenix` (observability, :6006),
`langgraph-dev` (serves the kernel graph via `langgraph.json`, :2024), `bashos` (containerized terminal, profile `cli`). LangChain/LangGraph are in-process libraries otherwise — no daemon required.

## Conventions

- Everything async; the CLI wraps one `asyncio.run` (the desktop is the
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
<<<<<<< HEAD
.venv/bin/bashos desktop             # the desktop (bare `bashos` on a TTY too)
||||||| e147539
=======
.venv/bin/bashos gui --browser       # the desktop, in a browser tab
>>>>>>> 4e04c89164334d9daf8762caec1f7bed433d776e
.venv/bin/bashos run -n "/sh ..."    # dry-run: no auth needed
.venv/bin/bashos doctor              # auth/backend diagnosis (offline)
.venv/bin/bashos opencode sync       # regenerate opencode.jsonc
.venv/bin/bashos opencode status     # boot the engine, report live state
```
