# bashOS

[![CI](https://github.com/bamr87/bashos/actions/workflows/ci.yml/badge.svg)](https://github.com/bamr87/bashos/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A terminal-first AI runtime.** Claude slash commands routed through a
LangGraph kernel onto the **OpenCode engine**, running on your Claude Code
OAuth — for all things software development and information systems.

```
 _             _    ___  ____
| |__  __ _ __| |_ / _ \/ ___|
| '_ \/ _` (_-< ' \ (_) \___ \
|_.__/\__,_/__/_||_\___/|____/
```

The terminal is the core access point: one REPL (and one-shot CLI) reaches
every capability. Commands are markdown specs in `.claude/commands/` — the
exact files Claude Code loads as project slash commands — and the bashOS kernel
routes those same files through AI orchestration loops. One spec, three
runtimes: Claude Code, the bashOS kernel, and the OpenCode TUI.

bashOS does not implement a reasoning loop. It runs one:
[OpenCode](https://opencode.ai) — open source, client/server,
provider-agnostic — supplies the agent loop, the tool broker, sessions, and the
permission gate. bashOS supplies the userland, the routing kernel, the policy,
and the terminal. That is the whole bet of the
[reference architecture](bashOS-architecture.md): reasoning engines churn, the
resource-management layer shouldn't.

## Quickstart

```bash
npm i -g opencode-ai         # the engine (or: curl -fsSL https://opencode.ai/install | bash)
./bin/bashos                 # first run bootstraps .venv, then drops into the REPL
```

```text
bashos ▸ /sh find files over 100MB modified this week
bashos ▸ /script rotate logs in /var/log, keep 7 days     # drafted, shellcheck-verified, repaired
bashos ▸ /sys why is this machine slow                    # read-only agent probes the real machine
bashos ▸ count unique IPs in access.log                   # no slash → kernel classifies → /pipe
bashos ▸ !git status                                      # raw passthrough to your real shell
```

One-shot, from any terminal or script:

```bash
bashos run /explain "rsync -avz --delete src/ host:/dst"
bashos run -n /script backup my dotfiles     # -n dry-run: routing + rendered prompt, no model call
bashos run -v /sh list open ports            # -v prints the kernel trace
bashos list                                  # command table
bashos doctor                                # auth + environment checks
bashos opencode status                       # boot the engine and report what it runs
```

## Auth — Claude Code OAuth, wired into the engine

bashOS needs **no API key**. It finds your Claude Code credential and hands it
to the engine at start:

1. `CLAUDE_CODE_OAUTH_TOKEN` — explicit override, and what CI uses
2. `~/.claude/.credentials.json` — your Linux/Windows `claude` login
3. macOS Keychain — service `Claude Code-credentials`

`ANTHROPIC_API_KEY` is the fallback. The credential travels in the engine
process's environment, so **no secret is written to disk** and bashOS never
touches your own `opencode auth login` credentials.

Backends, in preference order:

| backend | how it authenticates | setup |
|---|---|---|
| `opencode` *(default)* | local `opencode serve`, given your Claude Code OAuth | `npm i -g opencode-ai`, then `claude` → log in |
| `claude-code` *(fallback)* | Claude Agent SDK → your Claude Code login | install Claude Code — completions only, no `react` |
| `api` *(fallback)* | direct Anthropic API billing | `ANTHROPIC_API_KEY=...` — completions only |

Force one with `BASHOS_BACKEND=opencode|claude-code|api`; pick a model with
`BASHOS_MODEL` or `-m` (default `claude-opus-5`). `bashos doctor` shows what
was detected, `bashos opencode auth` shows which credential wins and from
where. Copy `.env.example` to `.env` for persistent settings. Details, and why
the token rides as a bearer header, are in [docs/OPENCODE.md](docs/OPENCODE.md).

## Commands

| command    | loop     | what it does |
|------------|----------|--------------|
| `/sh`      | prompt   | natural language → a safe, correct shell command |
| `/explain` | prompt   | explain any command, pipeline, error, or config like a man page |
| `/script`  | *refine* | production-grade bash script — drafted, **shellcheck-verified**, auto-repaired |
| `/debug`   | *react*  | diagnose a failure by **inspecting this machine** (read-only) |
| `/sys`     | *react*  | system health / questions, answered from **live read-only probes** |
| `/pipe`    | prompt   | design text/data pipelines (grep · sed · awk · sort · jq) |
| `/regex`   | prompt   | craft + explain + test regular expressions |
| `/cron`    | prompt   | build or explain cron expressions and schedules |
| `/port`    | prompt   | translate between bash ↔ POSIX sh ↔ zsh ↔ PowerShell ↔ Python |
| `/audit`   | prompt   | security-review a shell script, findings ranked by severity |

Every one of these also works as a plain slash command inside Claude Code when
you open this repo, and — after `bashos opencode sync` — inside the OpenCode
TUI. Same file, no duplication.

## Architecture

```
 terminal (REPL / CLI · typer + rich + prompt-toolkit)
    │
    ▼
 kernel — LangGraph state machine
    input ─▶ parse ─┬─▶ dispatch ──▶ prompt  (one model call)            ┐
                    │       ▲   └──▶ refine  (draft→shellcheck→repair)   ├─▶ respond
                    │       │   └──▶ react   (agent loop, read-only)     ┘
                    └─▶ classify  (bare english → best command)
    │
    ▼
 opencode/ — policy · registry projection · Claude Code OAuth bridge
    │
    ▼
 engine — supervised `opencode serve`: agent loop · tool broker · sessions ·
          permission gate   (fallbacks: Claude Agent SDK ▸ ANTHROPIC_API_KEY)
    │
    ▼
 userland — .claude/commands/*.md  →  compiled to opencode.jsonc
```

The engine — why it is a separate process, how the credential reaches it, and
what the policy actually enforces — is in [docs/OPENCODE.md](docs/OPENCODE.md).
The full harness design (layer contracts, loop semantics, extension guide) is
in [docs/HARNESS.md](docs/HARNESS.md). The long-range vision (an image-based
Linux appliance with the agent kernel as a first-class OS service) is the
[bashOS reference architecture](bashOS-architecture.md); HARNESS.md maps this
runtime onto its layers.

## Extending

Add a command by dropping one markdown file into `.claude/commands/`:

```markdown
---
description: what it does
argument-hint: <what to pass>
bashos:
  loop: prompt        # or refine | react
  agent: bashos       # optional — which engine tool policy it runs under
---
Prompt body with $ARGUMENTS.
```

No registration, no code — it appears in `bashos list` and in Claude Code
immediately, and reaches the engine on its next start.

## Safety model

- `/sh` and friends **generate** commands; they never execute them.
- The react loop (`/sys`, `/debug`, `/health`) runs under a **deny-by-default
  policy the engine enforces**, not a prompt: file reads plus an allowlist of
  diagnostic probes; write, edit, network, subagent and outside-the-project
  tools are denied *and hidden*; every tool action streams to your terminal
  live. See it before anything runs with `bashos run -n /sys`.
- Approval prompts are **refused, not awaited** — the terminal is
  non-interactive, so a rule that resolves to "ask" is a no.
- The engine's loopback socket drives a tool loop, so bashOS guards it with a
  random per-process password rather than leaving it open to every process on
  the box.
- Credentials live in the engine process's environment — never written to disk,
  never merged into your own `opencode` credential store.
- `/script` output is verified by shellcheck when installed, and labeled
  unverified when not.
- Only `!` lines execute anything by your intent — and that's your own shell.

## Services (Docker)

LangChain and LangGraph run **in-process as libraries** — the terminal needs no
services. The optional compose stack adds infrastructure *around* the terminal:

```bash
docker compose up -d           # phoenix + langgraph-dev
docker compose run bashos      # the terminal itself, containerized
```

| service        | port | what it is |
|----------------|------|------------|
| `phoenix`      | 6006 | [Arize Phoenix](https://github.com/Arize-ai/phoenix) — every kernel loop traced (UI + OTLP HTTP; gRPC on 4317) |
| `langgraph-dev`| 2024 | LangGraph API server exposing the **same kernel graph** over HTTP (`langgraph.json` → `kernel`; LangGraph Studio-compatible) |
| `bashos`       | —    | the terminal, containerized (`profiles: [cli]` — started explicitly) |

Container auth: interactive `claude` login isn't possible in a container, so
set `CLAUDE_CODE_OAUTH_TOKEN` (mint with `claude setup-token`) or
`ANTHROPIC_API_KEY` in `.env`. The image ships the engine and the Claude Code
CLI. Already running a Phoenix elsewhere? Remap host
ports via `BASHOS_PHOENIX_*_PORT`, or point `PHOENIX_COLLECTOR_ENDPOINT` at it
— full guide in [docs/SERVICES.md](docs/SERVICES.md).

Local tracing without containers: `pip install -e ".[trace]"`, run Phoenix
anywhere, and set `PHOENIX_COLLECTOR_ENDPOINT`. On the engine backend the model
call happens inside the `opencode` process, so spans cover the kernel and loop
structure; use the `api` backend for token-level LLM telemetry.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q            # offline: fake model, no engine, no auth needed
.venv/bin/bashos opencode sync # regenerate opencode.jsonc after editing a command
```

`opencode.jsonc` is generated and committed — a test fails if it drifts from
the registry.

## Roadmap

- Session memory: reuse engine sessions across REPL lines instead of one per call
- An `--exec` confirm-then-run mode for `/sh`
- Streaming token output in the REPL
- More loops: plan-execute, multi-draft panel w/ judge
- More userland: `/git`, `/docker`, `/net`, `/db`
