# The bashOS Orchestration Harness

This is the design document for the AI harness at the core of bashOS: what the
layers are, what a loop is, and how to extend each one.

## Design goals

1. **The terminal is the core access point.** Every capability — commands,
   agent runs, diagnostics, raw shell — is reachable from one prompt. There is
   no web UI; the REPL and one-shot CLI are the whole surface.
2. **Bring an existing agent; never build a reasoning loop.** The reasoning
   engine is [OpenCode](OPENCODE.md) — open source, client/server,
   provider-agnostic — running as a supervised local server. It owns the agent
   loop, the tool broker, sessions, and the permission gate. bashOS owns
   routing, policy, userland, and the terminal. This is the whitepaper's L5
   separation, and it is why swapping engines is a module, not a rewrite.
3. **Libraries everywhere.** Orchestration is LangGraph, the engine is
   OpenCode, the terminal is Typer + Rich + prompt-toolkit, config is Pydantic.
   bashOS writes glue and policy, not infrastructure.
4. **One spec, three runtimes.** A command is a markdown file in
   `.claude/commands/`. Claude Code loads it as a project slash command, the
   bashOS kernel routes it through a loop, and `bashos opencode sync` compiles
   it into the engine's project config. One source of truth for what a command
   does.
5. **Subscription-native auth.** The engine runs on the user's Claude Code
   OAuth (CLI login, keychain, or `claude setup-token`), bridged in at engine
   start. An API key is a fallback, not a requirement.
6. **Checked generation, least-privilege agency.** Generated scripts pass
   through a deterministic verifier (shellcheck), and agentic runs execute
   under a deny-by-default permission ruleset the *engine* enforces. The model
   proposes; policy and tooling dispose.

## Layers

```
 ┌─────────────────────────────────────────────────────────────┐
 │ shell/        terminal layer: REPL · CLI · rich rendering   │  access point
 ├─────────────────────────────────────────────────────────────┤
 │ kernel/       LangGraph state machine: parse → route → loop │  orchestration
 ├─────────────────────────────────────────────────────────────┤
 │ loops/        prompt · refine · react                       │  harness
 ├─────────────────────────────────────────────────────────────┤
 │ opencode/     policy · projection · auth bridge · engine    │  the core
 │ runtime/      backend resolution (engine ↔ fallbacks)       │  model I/O
 ├─────────────────────────────────────────────────────────────┤
 │ registry.py   .claude/commands/*.md  (shared with Claude    │  userland
 │               Code as slash commands)                       │
 └─────────────────────────────────────────────────────────────┘
              │
              ▼
     `opencode serve`   agent loop · tool broker · sessions · permission gate
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
task ──▶ engine.act()  →  opencode session on the `bashos` agent
           │  read/glob/grep/list + bash(probe allowlist)
           │  edit/write/webfetch/websearch/task denied and hidden
           └─▶ tool events stream to the terminal ──▶ final report
```

Agentic work is delegated to the engine under the deny-by-default ruleset in
`opencode/policy.py`. The gate is the engine's, not a prompt's: a denied
command never executes. Tool calls stream live through `on_event`, approval
requests are auto-refused (the terminal is non-interactive, so an `ask` is a
`no`), and steps are capped by `react_max_turns`. Used by `/sys`, `/debug`,
and `/health`.

## The engine and the model runtime

The core is a supervised `opencode serve` process. `opencode/engine.py` exposes
exactly two verbs, and every loop is built on one of them:

- `complete(prompt, system)` — one answer, no tools, on the `bashos-sealed`
  agent. Backs the prompt/refine loops and the kernel's classifier.
- `act(prompt, agent, on_event)` — a full reason ↔ act loop under policy.
  Backs the react loop.

`runtime/llm.py` resolves which backend serves `complete()` and returns one
LangChain interface:

| backend                | transport                              | auth                                   |
|------------------------|----------------------------------------|----------------------------------------|
| `opencode` *(default)* | local `opencode serve` over HTTP       | Claude Code OAuth, bridged in at engine start |
| `claude-code`          | Claude Agent SDK → `claude` binary     | Claude Code login / CLAUDE_CODE_OAUTH_TOKEN |
| `api`                  | langchain-anthropic ChatAnthropic      | ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN |

Preference: the engine wins when installed or pinned; `BASHOS_BACKEND`
overrides. The two fallbacks are completion-only — they can serve `prompt` and
`refine`, but not `react`, whose policy is expressed in OpenCode's permission
model and has nowhere else to be enforced.

Auth is the headline: the user's Claude Code credential is discovered (env
token → `~/.claude/.credentials.json` → macOS Keychain) and injected into the
engine process's environment, so no API key is required and no secret is
written to disk. The mechanism — and why it is an `Authorization: Bearer`
header rather than a stored OAuth credential — is documented in
[OPENCODE.md](OPENCODE.md#auth-claude-code-oauth-by-default).

Default model: `claude-opus-5` (`BASHOS_MODEL` / `-m` to override), qualified
to `anthropic/claude-opus-5` for the engine.

## Extending

**Add a command** — drop one markdown file in `.claude/commands/`:

```markdown
---
description: what it does
argument-hint: <what to pass>
bashos:
  loop: prompt        # or refine | react
  agent: bashos       # optional; defaults from the loop
---
Prompt body with $ARGUMENTS.
```

It is immediately a Claude Code slash command, a bashOS-routable program, and —
after the engine re-syncs at next start — an OpenCode command. No registration,
no code.

**Add a loop** — one module in `loops/` exposing a node factory, one entry in
the kernel's `_LOOP_NODES`, and commands can declare it. Candidates: a
`plan-execute` loop (plan once, execute steps with per-step verification), a
`panel` loop (N parallel drafts, judge, synthesize).

**Widen the policy** — `opencode/policy.py` is the only place that can widen
bashOS's blast radius. Adding a probe is one entry in `PROBE_COMMANDS`; the
generated config, the dry-run report, and the tests all follow from it.

**Add a backend** — one branch in `get_chat_model()` returning any
`BaseChatModel`. Loops never know which backend they run on.

**Swap the engine** — implement `complete()`/`act()` against another
client/server agent and point `opencode/engine.py` at it. Nothing above
`opencode/` knows which engine is underneath, which is the whole point of the
separation.

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
| L5 agent kernel — `bashosd` scheduler/broker | LangGraph kernel: parse → classify/dispatch → loops; the supervised OpenCode server as the tool broker and session store — the whitepaper's "tool broker fronting one existing agent CLI", literally |
| L4 policy & audit — OPA gate, OTel audit log | `opencode/policy.py` compiled into an engine-enforced deny-by-default ruleset; OpenInference traces to Phoenix; append-only `trace` in state |
| L3 knowledge — AGENTS.md, git-backed skills | `.claude/commands/*.md` as versioned, three-runtime command specs, compiled to `opencode.jsonc`; CLAUDE.md |
| L2 sandboxes — Firecracker/bubblewrap tiers | the engine's permission gate (no write/network tools, no external directories); containers for services |
| L1 inference gateway — model router | `runtime/llm.py` backend resolution (engine ↔ Claude Code SDK ↔ API) over the engine's own provider layer |
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
- Engine errors carry their own context: the resolved credential, `bashos
  doctor`, and the path to `.bashos/opencode.log` — because the engine reports
  most provider problems as an opaque 500, and the log is where the real cause
  is.
- A supervised engine is stopped in a `finally`: one-shot runs and REPL exits
  never leave a server behind.
- Nothing waits on a human. Approval requests are auto-refused, and a broken
  event stream releases the prompt rather than wedging it.
