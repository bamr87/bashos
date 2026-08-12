# bashOS

[![CI](https://github.com/bamr87/bashos/actions/workflows/ci.yml/badge.svg)](https://github.com/bamr87/bashos/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A terminal-first AI runtime.** Claude slash commands routed through a
LangGraph kernel, running on your Claude Code OAuth — for all things software
development and information systems.

```
 _             _    ___  ____
| |__  __ _ __| |_ / _ \/ ___|
| '_ \/ _` (_-< ' \ (_) \___ \
|_.__/\__,_/__/_||_\___/|____/
```

The terminal is the core access point: one REPL (and one-shot CLI) reaches
every capability. Commands are markdown specs in `.claude/commands/` — the
exact files Claude Code loads as project slash commands — and the bashOS kernel
routes those same files through AI orchestration loops. One spec, two runtimes.

## Quickstart

```bash
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
```

## Auth — Claude Code OAuth first

bashOS needs **no API key**. Backends, in preference order:

| backend       | how it authenticates | setup |
|---------------|----------------------|-------|
| `claude-code` *(default)* | Claude Agent SDK → your Claude Code login (subscription OAuth) | install Claude Code, `claude` → log in — done |
| `claude-code` (headless)  | long-lived OAuth token | `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN=...` |
| `api` *(fallback)*        | direct Anthropic API billing | `ANTHROPIC_API_KEY=...` |

Force one with `BASHOS_BACKEND=claude-code|api`; pick a model with
`BASHOS_MODEL` or `-m` (default `claude-opus-5`). `bashos doctor` shows what
was detected. Copy `.env.example` to `.env` for persistent settings.

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
you open this repo — same file, no duplication.

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
 model runtime — Claude Code OAuth (Agent SDK) ▸ or ANTHROPIC_API_KEY fallback
    │
    ▼
 userland — .claude/commands/*.md  (shared with Claude Code)
```

The full design — layer contracts, loop semantics, tool policy, extension
guide — is in [docs/HARNESS.md](docs/HARNESS.md). The long-range vision (an
image-based Linux appliance with the agent kernel as a first-class OS service)
is the [bashOS reference architecture](bashOS-architecture.md); HARNESS.md maps
this runtime onto its layers.

## Extending

Add a command by dropping one markdown file into `.claude/commands/`:

```markdown
---
description: what it does
argument-hint: <what to pass>
bashos:
  loop: prompt        # or refine | react
---
Prompt body with $ARGUMENTS.
```

No registration, no code — it appears in `bashos list` and in Claude Code
immediately.

## Safety model

- `/sh` and friends **generate** commands; they never execute them.
- The react loop (`/sys`, `/debug`) runs under an explicit **read-only tool
  policy**: file reads plus an allowlist of diagnostic probes; write, edit, and
  network tools are denied; every tool action streams to your terminal live.
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
`ANTHROPIC_API_KEY` in `.env`. Already running a Phoenix elsewhere? Remap host
ports via `BASHOS_PHOENIX_*_PORT`, or point `PHOENIX_COLLECTOR_ENDPOINT` at it
— full guide in [docs/SERVICES.md](docs/SERVICES.md).

Local tracing without containers: `pip install -e ".[trace]"`, run Phoenix
anywhere, and set `PHOENIX_COLLECTOR_ENDPOINT`. On the claude-code backend,
spans cover the kernel and loop structure; use the `api` backend for
token-level LLM telemetry.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q            # offline: fake model, no auth needed
```

## Roadmap

- Session memory: LangGraph checkpointer so loops share conversational state
- An `--exec` confirm-then-run mode for `/sh`
- Streaming token output in the REPL
- More loops: plan-execute, multi-draft panel w/ judge
- More userland: `/git`, `/docker`, `/net`, `/db`
