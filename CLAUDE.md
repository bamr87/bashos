# bashOS

Terminal-first AI runtime: Claude slash commands routed through a LangGraph
kernel onto the OpenCode engine, on Claude Code OAuth. Design doc:
docs/HARNESS.md. The engine (policy, credential bridge, projection):
docs/OPENCODE.md. The dev-server monitoring pattern (`bin/os-health`,
`/health`, `/dash`): docs/FORGE.md.

**The core rule: bashOS never implements a reasoning loop.** OpenCode owns the
agent loop, tool broker, sessions, and permission gate; bashOS owns userland,
routing, policy, and the terminal. Work that would add a tool loop to bashOS
belongs in the engine layer or nowhere.

## Layout

- `.claude/commands/*.md` — userland. Each file is a Claude Code slash command,
  a bashOS command, AND (compiled) an OpenCode command; `bashos:` frontmatter
  declares its loop (`prompt` | `refine` | `react`) and optionally its engine
  `agent`. They are the single source of truth.
- `src/bashos/kernel/` — LangGraph state machine (parse → classify/dispatch →
  loop → respond). State lives in `kernel/state.py`; `trace` is append-only.
- `src/bashos/loops/` — orchestration loops. A loop is a node factory
  `(registry, llm, config) -> async node`. Register new ones in
  `kernel/graph.py:_LOOP_NODES`. Loops call the engine, never a model directly.
- `src/bashos/opencode/` — the core. `policy.py` is the ONLY place that widens
  bashOS's blast radius; `project.py` compiles the registry + policy into the
  generated, committed `opencode.jsonc`; `auth.py` bridges Claude Code OAuth
  into the engine process's environment (never to disk); `server.py`/`engine.py`
  supervise it and expose two verbs, `complete()` and `act()`.
- `src/bashos/runtime/` — backend resolution. Default is `opencode`; the Claude
  Agent SDK adapter and the direct API are completion-only fallbacks that
  cannot run the react loop. Default model: claude-opus-5.
- `src/bashos/remote.py` — dev-box integration (`bashos remote …`): CODE runs
  fixed read-only probes over ssh, the model reasons locally over the gathered
  text, and the interaction mirrors onto the box's tmux console monitor. Never
  give loops ssh/network tools — extend `remote.PROBES` instead.
- `src/bashos/shell/` — Typer CLI, prompt-toolkit REPL, Rich rendering.
- `docker-compose.yml` — optional services: `phoenix` (observability, :6006),
  `langgraph-dev` (serves the kernel graph via `langgraph.json`, :2024),
  `bashos` (containerized terminal, profile `cli`). LangChain/LangGraph are
  in-process libraries otherwise — no daemon required.

## Conventions

- Everything async; the CLI wraps one `asyncio.run`. Never call sync `invoke`
  inside the kernel — use `await llm.ainvoke`.
- Loops must short-circuit on missing args (usage) and `config.dry_run`
  (rendered prompt, no model call) — tests rely on the dry-run path.
- Tool policy is deny-by-default and lives in `opencode/policy.py`. Widening it
  is the only way to widen what bashOS can touch: never add a tool that writes,
  reaches the network, or spawns an unbound agent.
- `opencode.jsonc` is GENERATED and committed. Edit `.claude/commands/*.md` or
  `policy.py`, then `bashos opencode sync`; a test fails on drift. It must
  never contain a credential — secrets go in the engine's environment only.
- Anything that could block on a human must not: approval requests are
  auto-refused, and a dead event stream releases the prompt.
- Shell code style everywhere (bin/, generated prompts): `set -Eeuo pipefail`,
  quoted expansions, shellcheck-clean.

## Commands

```bash
.venv/bin/pytest -q                  # offline tests (fake model, no engine)
.venv/bin/bashos run -n "/sh ..."    # dry-run: no auth needed
.venv/bin/bashos doctor              # auth/backend diagnosis (offline)
.venv/bin/bashos opencode sync       # regenerate opencode.jsonc
.venv/bin/bashos opencode status     # boot the engine, report live state
```
