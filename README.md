# bashOS

[![CI](https://github.com/bamr87/bashos/actions/workflows/ci.yml/badge.svg)](https://github.com/bamr87/bashos/actions/workflows/ci.yml) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A terminal-first AI runtime.** Claude slash commands routed through a LangGraph kernel onto the **OpenCode engine**, running on your Claude Code OAuth — for all things software development and information systems.

```
 _             _    ___  ____
| |__  __ _ __| |_ / _ \/ ___|
| '_ \/ _` (_-< ' \ (_) \___ \
|_.__/\__,_/__/_||_\___/|____/
```

The terminal is the core access point: a windowed **terminal desktop** (and a one-shot CLI) reaches every capability. Commands are markdown specs in `.claude/commands/` — the exact files Claude Code loads as project slash commands — and the bashOS kernel routes those same files through AI orchestration loops. One spec, three runtimes: Claude Code, the bashOS kernel, and the OpenCode TUI.

bashOS does not implement a reasoning loop. It runs one: [OpenCode](https://opencode.ai) — open source, client/server, provider-agnostic — supplies the agent loop, the tool broker, sessions, and the permission gate. bashOS supplies the userland, the routing kernel, the policy, and the terminal. That is the whole bet of the [reference architecture](bashOS-architecture.md): reasoning engines churn, the resource-management layer shouldn't.

## Quickstart

```bash
npm i -g opencode-ai         # the engine (or: curl -fsSL https://opencode.ai/install | bash)
./bin/bashos                 # first run bootstraps .venv, then opens the desktop
./bin/bashos                 # first run bootstraps .venv, then drops into the REPL
./bin/bashos gui             # …or the desktop window, on the same kernel
```

The desktop ([docs/DESKTOP.md](docs/DESKTOP.md)) is a windowed terminal environment: tiled windows that adapt to your terminal size, a launcher (`F2`) and command palette (`ctrl+p`), and an app suite — AI consoles, a live health monitor, the engine inspector, a kernel trace viewer, and the real OpenCode TUI a keypress away. In an AI Console window:

```text
you ▸ /sh find files over 100MB modified this week
you ▸ exec                                             # confirm-then-run the last bash fence
you ▸ /script rotate logs in /var/log, keep 7 days     # drafted, shellcheck-verified, repaired
you ▸ /health                                          # verdict floor + causes (bin/os-health)
you ▸ /sys why is this machine slow                    # read-only agent probes, streaming live
you ▸ count unique IPs in access.log                   # no slash → heuristic/classify → /pipe
you ▸ now exclude .venv                                # follow-up reuses the last command
you ▸ !git status                                      # your real shell, output in a window
```

Answers stream in as they generate; every tool call ticks by in the activity feed; `esc` stops a run mid-flight.

One-shot, from any terminal or script:

```bash
bashos run /explain "rsync -avz --delete src/ host:/dst"
bashos run -n /script backup my dotfiles     # -n dry-run: routing + rendered prompt, no model call
bashos run -v /sh list open ports            # -v prints the kernel trace
bashos run -x /sh list the 5 largest files   # -x confirm-then-run the first bash fence (-y skips prompt)
bashos list                                  # command table
bashos doctor                                # auth + environment checks
bashos opencode status                       # boot the engine and report what it runs
bashos gui                                   # the desktop: same kernel, GUI front end
```

## Auth — Claude Code OAuth, wired into the engine

bashOS needs **no API key**. It finds your Claude Code credential and hands it to the engine at start:

1. `CLAUDE_CODE_OAUTH_TOKEN` — explicit override, and what CI uses
2. `~/.claude/.credentials.json` — your Linux/Windows `claude` login
3. macOS Keychain — service `Claude Code-credentials`

`ANTHROPIC_API_KEY` is the fallback. The credential travels in the engine process's environment, so **no secret is written to disk** and bashOS never touches your own `opencode auth login` credentials.

Backends, in preference order:

| backend | how it authenticates | setup |
|---|---|---|
| `opencode` *(default)* | local `opencode serve`, given your Claude Code OAuth | `npm i -g opencode-ai`, then `claude` → log in |
| `claude-code` *(fallback)* | Claude Agent SDK → your Claude Code login | install Claude Code — completions only, no `react` |
| `api` *(fallback)* | direct Anthropic API billing | `ANTHROPIC_API_KEY=...` — completions only |

Force one with `BASHOS_BACKEND=opencode|claude-code|api`; pick a model with
`BASHOS_MODEL` or `-m` (default `claude-opus-5`). `bashos doctor` shows what was detected, `bashos opencode auth` shows which credential wins and from where. Copy `.env.example` to `.env` for persistent settings. Details, and why the token rides as a bearer header, are in [docs/OPENCODE.md](docs/OPENCODE.md).

## Commands

| command    | loop     | what it does |
|------------|----------|--------------|
| `/sh`      | prompt   | natural language → a safe, correct shell command |
| `/explain` | prompt   | explain any command, pipeline, error, or config like a man page |
| `/script`  | *refine* | production-grade bash script — drafted, **shellcheck-verified**, auto-repaired |
| `/debug`   | *react*  | diagnose a failure by **inspecting this machine** (read-only) |
| `/sys`     | *react*  | answer a system question from **live read-only probes** |
| `/health`  | *react*  | verdict-style health check (`bin/os-health` floor + causes) |
| `/dash`    | *refine* | generate a labeled, self-healing tmux monitoring dashboard |
| `/pipe`    | prompt   | design text/data pipelines (grep · sed · awk · sort · jq) |
| `/regex`   | prompt   | craft + explain + test regular expressions |
| `/cron`    | prompt   | build or explain cron expressions and schedules |
| `/port`    | prompt   | translate between bash ↔ POSIX sh ↔ zsh ↔ PowerShell ↔ Python |
| `/audit`   | prompt   | security-review a shell script, findings ranked by severity |

Every one of these also works as a plain slash command inside Claude Code when you open this repo, and — after `bashos opencode sync` — inside the OpenCode TUI. Same file, no duplication.

## Desktop

`bashos gui` opens a GUI front end on the same kernel — a native window with `pip install "bashos[gui]"`, your browser without it:

[![The bashOS desktop](docs/media/overview.png)](docs/DESKTOP-TOUR.md)


| scene | what it is |
|---|---|
| **Overview** | session stats, quick-run chips, recent runs, the path a line takes |
| **Console** | the terminal as a GUI — slash completion, live kernel trace, tool calls as they happen |
| **Commands** | userland: every `.claude/commands/*.md` with its loop, agent, and prompt spec |
| **Runs** | every line this window ran, with its trace, its tool calls, and its answer |
| **Health** | host facts, the react-loop sweeps, and the probe allowlist a sweep may use |
| **Engine** | `doctor` checks, live engine state, the tool policy, the generated `opencode.jsonc` |
| **Side by side** | any two scenes in one window — focus, maximize, close; Console stays a singleton |
| **Desktop** | scenes as floating windows: icons, drag, resize, edge snapping, minimize, a taskbar, shareable layouts |

It is a *view*, not a second runtime: a console line goes through the same `build_kernel(...)` call `bashos run` makes. The socket is loopback-only and token-guarded, `!` shell passthrough is refused (that stays in your terminal, where it is your own shell by your own keystroke), and the tool policy is unchanged — the Health scene renders the allowlist, it does not widen it. No bundler, no npm, no web framework in the dependency tree: one HTML file, one stylesheet, one ES module, served by ~300 lines of asyncio.

**[Take the tour](docs/DESKTOP-TOUR.md)** — every scene, with screenshots and recordings of the real thing. The architecture and guard model are in [docs/DESKTOP.md](docs/DESKTOP.md); where the window metaphors are going is in [docs/frontend/](docs/frontend/README.md).

## Architecture

```
<<<<<<< HEAD
 terminal (desktop · one-shot CLI — textual + typer + rich)
||||||| e147539
 terminal (REPL / CLI · typer + rich + prompt-toolkit)
=======
 terminal (REPL / CLI · typer + rich + prompt-toolkit)
 desktop  (`bashos gui` · loopback HTTP + SSE → one page, no build step)
>>>>>>> 4e04c89164334d9daf8762caec1f7bed433d776e
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

The engine — why it is a separate process, how the credential reaches it, and what the policy actually enforces — is in [docs/OPENCODE.md](docs/OPENCODE.md). The full harness design (layer contracts, loop semantics, extension guide) is in [docs/HARNESS.md](docs/HARNESS.md). The long-range vision (an image-based Linux appliance with the agent kernel as a first-class OS service) is the [bashOS reference architecture](bashOS-architecture.md); HARNESS.md maps this runtime onto its layers.

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

No registration, no code — it appears in `bashos list` and in Claude Code immediately, and reaches the engine on its next start.

## Safety model

- `/sh` and friends **generate** commands; they never execute them.
- The react loop (`/sys`, `/debug`, `/health`) runs under a **deny-by-default
policy the engine enforces**, not a prompt: file reads plus an allowlist of diagnostic probes; write, edit, network, subagent and outside-the-project tools are denied *and hidden*; every tool action streams to your terminal live. See it before anything runs with `bashos run -n /sys`.
- Approval prompts are **refused, not awaited** — the terminal is
  non-interactive, so a rule that resolves to "ask" is a no.
- The engine's loopback socket drives a tool loop, so bashOS guards it with a
random per-process password rather than leaving it open to every process on the box.
- Credentials live in the engine process's environment — never written to disk,
  never merged into your own `opencode` credential store.
- `/script` output is verified by shellcheck when installed, and labeled
  unverified when not.
<<<<<<< HEAD
- Only `!` lines and explicit `--exec` / console `exec` (confirm-then-run,
Cancel focused by default) execute anything by your intent — and that's your own shell. Approval requests from engine runs are auto-refused everywhere, the desktop included.
||||||| e147539
- Only `!` lines execute anything by your intent — and that's your own shell.
=======
- Only `!` lines execute anything by your intent — and that's your own shell.
The desktop has no `!` at all: it runs kernel lines, on a loopback socket guarded by a per-process token, and widens no policy.
>>>>>>> 4e04c89164334d9daf8762caec1f7bed433d776e

## Services (Docker)

LangChain and LangGraph run **in-process as libraries** — the terminal needs no services. The optional compose stack adds infrastructure *around* the terminal:

```bash
docker compose up -d           # phoenix + langgraph-dev
docker compose run bashos      # the terminal itself, containerized
```

| service        | port | what it is |
|----------------|------|------------|
| `phoenix`      | 6006 | [Arize Phoenix](https://github.com/Arize-ai/phoenix) — every kernel loop traced (UI + OTLP HTTP; gRPC on 4317) |
| `langgraph-dev`| 2024 | LangGraph API server exposing the **same kernel graph** over HTTP (`langgraph.json` → `kernel`; LangGraph Studio-compatible) |
| `bashos`       | —    | the terminal, containerized (`profiles: [cli]` — started explicitly) |

Container auth: interactive `claude` login isn't possible in a container, so set `CLAUDE_CODE_OAUTH_TOKEN` (mint with `claude setup-token`) or `ANTHROPIC_API_KEY` in `.env`. The image ships the engine and the Claude Code CLI. Already running a Phoenix elsewhere? Remap host ports via `BASHOS_PHOENIX_*_PORT`, or point `PHOENIX_COLLECTOR_ENDPOINT` at it — full guide in [docs/SERVICES.md](docs/SERVICES.md).

Local tracing without containers: `pip install -e ".[trace]"`, run Phoenix anywhere, and set `PHOENIX_COLLECTOR_ENDPOINT`. On the engine backend the model call happens inside the `opencode` process, so spans cover the kernel and loop structure; use the `api` backend for token-level LLM telemetry.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q            # offline: fake model, no engine, no auth needed
.venv/bin/bashos opencode sync # regenerate opencode.jsonc after editing a command
```

`opencode.jsonc` is generated and committed — a test fails if it drifts from the registry.

## Roadmap

- Adopt per-window engine sessions in the desktop console (the
`EngineSession` primitive is built and tested; the console still runs one engine session per turn with history injection)
- An opt-in interactive approval queue as a new, explicitly named policy
  profile (headless auto-refusal stays the default forever)
- A pty-embedded OpenCode TUI window (today: suspend/attach)
- More loops: plan-execute, multi-draft panel w/ judge
- More userland: `/git`, `/docker`, `/net`, `/db`
- Desktop: token streaming into the console, packaged app bundles
