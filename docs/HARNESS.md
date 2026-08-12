# The bashOS Orchestration Harness

This is the design document for the AI harness at the core of bashOS: what the
layers are, what a loop is, and how to extend each one.

## Design goals

1. **The terminal is the core access point.** Every capability — commands,
   agent runs, diagnostics, raw shell — is reachable from one prompt. There is
   no web UI and no daemon; the REPL and one-shot CLI are the whole surface.
2. **Libraries everywhere.** Orchestration is LangGraph, the model runtime is
   the Claude Agent SDK and langchain-anthropic, the terminal is Typer + Rich +
   prompt-toolkit, config is Pydantic. bashOS writes glue and policy, not
   infrastructure.
3. **One spec, two runtimes.** A command is a markdown file in
   `.claude/commands/`. Claude Code loads it as a project slash command;
   the bashOS kernel loads the same file and routes it through a loop. There is
   exactly one source of truth for what a command does.
4. **Subscription-native auth.** The default model runtime rides the user's
   Claude Code OAuth (CLI login or `claude setup-token`). An API key is a
   fallback backend, not a requirement.
5. **Checked generation, least-privilege agency.** Generated scripts pass
   through a deterministic verifier (shellcheck), and agentic runs execute
   under an explicit read-only tool policy. The model proposes; policy and
   tooling dispose.

## Layers

```
 ┌─────────────────────────────────────────────────────────────┐
 │ shell/        terminal layer: REPL · CLI · rich rendering   │  access point
 ├─────────────────────────────────────────────────────────────┤
 │ kernel/       LangGraph state machine: parse → route → loop │  orchestration
 ├─────────────────────────────────────────────────────────────┤
 │ loops/        prompt · refine · react                       │  harness
 ├─────────────────────────────────────────────────────────────┤
 │ runtime/      backend resolution · Claude Code OAuth adapter│  model I/O
 ├─────────────────────────────────────────────────────────────┤
 │ registry.py   .claude/commands/*.md  (shared with Claude    │  userland
 │               Code as slash commands)                       │
 └─────────────────────────────────────────────────────────────┘
```

## The kernel

`kernel/graph.py` compiles a LangGraph `StateGraph` over `KernelState`:

```
 input ─▶ parse ─┬─▶ dispatch ──▶ loop_prompt ─┐
                 │       ▲   └──▶ loop_refine ─┼─▶ respond ─▶ output
                 │       │   └──▶ loop_react ──┘
                 └─▶ classify
```

- **parse** splits `/command args` deterministically. Unknown commands
  short-circuit to `respond` with a `difflib` did-you-mean.
- **classify** handles bare natural language: one model call picks the best
  command from the registry menu, falling back to `/sh` on any doubt. Routing
  is itself model-driven — the terminal accepts plain English.
- **dispatch** is a conditional edge keyed on the command's declared loop.
- **respond** normalizes errors into output.

State is a `TypedDict` with one reducer: `trace` is an append-only log
(`operator.add`) every node contributes to — `bashos run -v` prints it, so the
harness's routing decisions are always inspectable from the terminal.

The whole kernel is async (`ainvoke`); sync CLIs wrap it in one `asyncio.run`.

## Loop contract

A loop is a **node factory**: it takes `(registry, llm, config)` and returns an
async LangGraph node (or a compiled subgraph) that:

- reads `command` / `args` from `KernelState`,
- returns `{"output": ...}` (plus `trace` entries), or `{"error", "route": "error"}`,
- short-circuits on missing args (usage text) and on `dry_run` (rendered
  prompt + routing report, no model call).

The kernel maps loop names to nodes in `_LOOP_NODES`. Three loops ship:

### `prompt` — one call

```
render(spec, args) + host context ──▶ model ──▶ output
```

The syscall of loops. Used by `/sh /explain /pipe /regex /cron /port /audit`.

### `refine` — generate → verify → repair

```
draft ──▶ verify(shellcheck) ──▶ finalize
             │        ▲
             ▼        │
           repair ────┘        bounded by refine_max_iters
```

A LangGraph cycle whose critic is an *external deterministic verifier*, not
model self-review. The draft is linted via `shellcheck -` on stdin; a failing
report is fed back verbatim for a repair pass; iteration is bounded. Output is
labeled `verified` / `still reports issues` / `unverified` (no shellcheck).
Implemented as a compiled subgraph mounted as a kernel node — its private state
keys (`draft`, `critique`, `lint_status`, `iterations`) stay internal.
Used by `/script`.

### `react` — reason ↔ act on the real machine

```
task ──▶ Claude Code harness (Agent SDK)
           │  Read/Glob/Grep + Bash(probe allowlist), Write/Edit/network denied
           └─▶ tool events stream to the terminal ──▶ final report
```

Agentic work is delegated to the harness the user already trusts — Claude
Code — under an explicit policy: `allowed_tools` is a read-only allowlist
(`Bash(uname:*)`, `Bash(df:*)`, ... plus file reads under `cwd`), destructive
and network tools are in `disallowed_tools`, and turns are capped by
`react_max_turns`. Every `ToolUseBlock` is surfaced live via `on_event`.
Used by `/sys` and `/debug`.

## Model runtime

`runtime/llm.py` resolves a backend and returns one LangChain interface:

| backend       | transport                          | auth                                   |
|---------------|------------------------------------|----------------------------------------|
| `claude-code` | Claude Agent SDK → `claude` binary | Claude Code login / CLAUDE_CODE_OAUTH_TOKEN (subscription) |
| `api`         | langchain-anthropic ChatAnthropic  | ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN |

Preference: Claude Code wins when available; `BASHOS_BACKEND` overrides.
`runtime/claude_code.py` is the adapter — a `BaseChatModel` whose `_agenerate`
drives `claude_agent_sdk.query()` with tools off and `max_turns=1`, so every
LangGraph loop (including the classifier) runs on OAuth with no API key. The
react loop bypasses the adapter and drives the SDK directly, because there the
harness's own tool loop *is* the feature.

Default model: `claude-opus-5` (`BASHOS_MODEL` / `-m` to override).

## Extending

**Add a command** — drop one markdown file in `.claude/commands/`:

```markdown
---
description: what it does
argument-hint: <what to pass>
bashos:
  loop: prompt        # or refine | react
---
Prompt body with $ARGUMENTS.
```

It is immediately a Claude Code slash command and a bashOS-routable program.
No registration, no code.

**Add a loop** — one module in `loops/` exposing a node factory, one entry in
the kernel's `_LOOP_NODES`, and commands can declare it. Candidates: a
`plan-execute` loop (plan once, execute steps with per-step verification), a
`panel` loop (N parallel drafts, judge, synthesize).

**Add a backend** — one branch in `get_chat_model()` returning any
`BaseChatModel`. Loops never know which backend they run on.

## Services and observability

The harness needs no daemons — LangChain/LangGraph run in-process. An optional
compose stack ([SERVICES.md](SERVICES.md)) wraps the same kernel in service
form: `langgraph-dev` serves `bashos.kernel.server:graph` over HTTP at :2024
(LangGraph Studio-compatible), `phoenix` collects OpenInference traces of every
kernel run at :6006, and a `bashos` service containerizes the terminal itself.
Tracing (`runtime/tracing.py`) activates on `PHOENIX_COLLECTOR_ENDPOINT` /
`BASHOS_TRACE=1` when the `trace` extras are installed, and is a silent no-op
otherwise — observability never becomes a dependency of the terminal.

## Relation to the appliance reference architecture

[bashOS-architecture.md](../bashOS-architecture.md) is the long-range vision:
an image-based Linux appliance where the agent kernel is a first-class OS
service (`bashosd`), with microVM sandboxes and a SPIFFE/OPA policy plane.
This repository is the Phase-1-spirit incarnation of that architecture as a
portable Python runtime — same layer boundaries, lighter enforcement:

| appliance layer (whitepaper) | shipped today (this repo) |
|---|---|
| L6 interface — shell with `::` intent channel | REPL where slash commands, plain English (classified), and `!` POSIX passthrough share one session |
| L5 agent kernel — `bashosd` scheduler/broker | LangGraph kernel: parse → classify/dispatch → loops; Claude Code harness as the tool broker |
| L4 policy & audit — OPA gate, OTel audit log | deny-by-default read-only tool allowlist in the react loop; OpenInference traces to Phoenix; append-only `trace` in state |
| L3 knowledge — AGENTS.md, git-backed skills | `.claude/commands/*.md` as versioned, dual-runtime command specs; CLAUDE.md |
| L2 sandboxes — Firecracker/bubblewrap tiers | the Claude Code harness's permission boundary (no write/network tools); containers for services |
| L1 inference gateway — model router | `runtime/llm.py` backend resolution: Claude Code OAuth ↔ API |
| L0 immutable base | docker images for the service plane |

Each row is a deliberate down-payment: tightening it toward the appliance
(bashosd as a daemon, OPA in front of the loops, microVM execution) changes a
layer's implementation, not the architecture.

## Failure semantics

- Unknown command, agent-loop failure, and runtime errors all land in
  `route="error"` and render as a red panel with exit code 1.
- The REPL catches everything per-line; a failed command never kills the shell.
- With no working auth, commands fail with a pointer to `bashos doctor`, which
  reports exactly what is missing.
