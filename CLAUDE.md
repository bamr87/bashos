# bashOS

Terminal-first AI runtime: Claude slash commands routed through a LangGraph
kernel on Claude Code OAuth. Design doc: docs/HARNESS.md.

## Layout

- `.claude/commands/*.md` — userland. Each file is BOTH a Claude Code slash
  command and a bashOS command; `bashos:` frontmatter declares its loop
  (`prompt` | `refine` | `react`). Keep them in sync with nothing — they are
  the single source of truth.
- `src/bashos/kernel/` — LangGraph state machine (parse → classify/dispatch →
  loop → respond). State lives in `kernel/state.py`; `trace` is append-only.
- `src/bashos/loops/` — orchestration loops. A loop is a node factory
  `(registry, llm, config) -> async node`. Register new ones in
  `kernel/graph.py:_LOOP_NODES`.
- `src/bashos/runtime/` — backend resolution + the Claude Agent SDK adapter
  (`ClaudeCodeChatModel`). Default backend is Claude Code OAuth; API key is
  fallback. Default model: claude-opus-5.
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
- The react loop's tool policy is deny-by-default: read tools + `Bash(<probe>:*)`
  allowlist in `loops/react.py`. Don't add write/network tools.
- Shell code style everywhere (bin/, generated prompts): `set -Eeuo pipefail`,
  quoted expansions, shellcheck-clean.

## Commands

```bash
.venv/bin/pytest -q                  # offline tests (fake model)
.venv/bin/bashos run -n "/sh ..."    # dry-run: no auth needed
.venv/bin/bashos doctor              # auth/backend diagnosis
```
