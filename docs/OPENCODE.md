# The engine: OpenCode at the core of bashOS

> Why OpenCode is bashOS's engine and runs as a separate process, how the Claude Code credential reaches it, what the deny-by-default policy enforces, and how the command registry is compiled into its config.

bashOS's [reference architecture](ARCHITECTURE.md) is explicit that the agent kernel must not contain a reasoning loop:

> Note what `bashosd` does *not* contain: a specific model, a specific agent's
> reasoning loop. Claude Code, Codex CLI, Gemini CLI, OpenCode — any of them can
> run *on* bashOS as the reasoning engine, the way any POSIX program runs on
> Linux. The OS supplies scheduling, identity, policy, sandboxes, memory, and
> audit; the agent supplies the thinking.

This document describes that separation as it is actually built. **OpenCode is the engine.** It owns the agent loop, the tool broker, session state, and the permission gate. bashOS owns everything an OS owns: the userland registry, the routing kernel, the policy, the terminal, and the audit trace.

```
     .claude/commands/*.md          userland — one spec, three runtimes
              │
              ▼
     kernel/  parse → classify → dispatch          which program runs
              │
              ▼
     loops/   prompt · refine · react              how it is orchestrated
              │
              ▼
     opencode/ policy → project → auth → server    what it may touch, and on whose credential
              │
              ▼
     `opencode serve`   agent loop · tools · sessions · permission gate
```

## Why the engine is a separate process

OpenCode is a client/server system: the TUI, its SDKs, and bashOS are all clients of a local `opencode serve`. bashOS supervises one on a free loopback port, or attaches to one you already run.

That process boundary is doing real work. The engine's tool loop executes commands, so the socket that drives it is as sensitive as a shell. bashOS therefore starts the server with a random per-process password (`OPENCODE_SERVER_PASSWORD`) and speaks HTTP basic auth to it — an unauthenticated loopback port is reachable by every other process on the box, which is not a property you want on the thing holding your tool loop.

| | supervised (default) | attached (`BASHOS_OPENCODE_URL`) |
|---|---|---|
| lifecycle | started and stopped by bashOS | yours |
| port | free port, read back from the server's own startup line | yours |
| socket auth | random password per process | `BASHOS_OPENCODE_PASSWORD` |
| credentials | injected into the child environment | whatever it already has |
| logs | `.bashos/opencode.log` | yours |

Start a shared one with `bashos opencode serve`; it prints the two exports another terminal needs.

## Auth: Claude Code OAuth, by default

bashOS is subscription-native. The engine runs on the Claude Code login you already have, discovered in this order:

1. `CLAUDE_CODE_OAUTH_TOKEN` — an explicit override, and what CI uses
2. `~/.claude/.credentials.json` — the Linux/Windows CLI login (refreshable)
3. macOS Keychain, service `Claude Code-credentials`

`ANTHROPIC_API_KEY` is the fallback. `BASHOS_OPENCODE_AUTH=never` turns the whole bridge off and lets the engine use whatever it already has.

### How the credential actually reaches the engine

This part was built against the running server rather than its documentation, because the documentation is out of date. Three findings shaped it:

- **OpenCode 1.18 dropped Anthropic OAuth as a login method.** Its `anthropic`
integration advertises `key` and `env` only. A stored `{"type":"oauth"}` credential does not register the provider at all — verified by writing one and watching `anthropic` stay absent from `/config/providers`, while the same file with `{"type":"api"}` registered it immediately.
- **So the token is carried the way Claude Code carries it**: as an
`Authorization: Bearer` header declared through `provider.anthropic.options.headers`. The capital `A` matters — a lowercase `authorization` key is dropped before the request goes out. `apiKey` is pinned to `""` so a bearer token is never also sent as `x-api-key`, and `anthropic-beta: oauth-2025-04-20` is merged with the engine's own betas. Declaring `env` is what makes OpenCode register the provider in the first place.
- **The wiring is injected through the child's environment**, using
`OPENCODE_CONFIG_CONTENT` and `OPENCODE_AUTH_CONTENT`, which merge with the project config at engine start. Two consequences, both deliberate: no secret is ever written to disk, and bashOS never touches `~/.local/share/opencode/auth.json` — if you ran `opencode auth login` yourself, you keep exactly what you had.

Because the provider registry is built when the server boots, the credential has to exist before the process does. That is why it rides in on the environment rather than being pushed over the API afterwards.

OpenCode 2 reads the same `OPENCODE_CONFIG_CONTENT`, but measured against 2.0.20 it differs in two ways, so the wiring depends on the binary's major ([`opencode/auth.py`](../src/bashos/opencode/auth.py)):

- **A declared `env` is sent as `x-api-key`.** On 2.x the provider block leaves `env` out: the config alone registers the provider, and only the `Authorization` header goes out (checked by pointing the provider at a local server and reading the headers it received).
- **`OPENCODE_AUTH_CONTENT` is ignored.** An API key rides in its own variable, `BASHOS_ANTHROPIC_API_KEY`, which the provider's `apiKey` names; the config still carries only the variable's name.

`bashos opencode auth` reports which credential would be used and which variable names carry it — never the values.

**Attached engines are different.** A running server's environment is already fixed, so the bearer route is closed and its owner keeps its credentials. Only an API key can still be pushed in, and only when the engine has none.

## Policy: deny-by-default, bound to agents

`opencode/policy.py` is the single place where bashOS's blast radius is defined. It compiles to two agents in the generated project config:

| agent | used by | tools |
|---|---|---|
| `bashos` | the `react` loop — `/sys`, `/debug`, `/health` | `read`/`glob`/`grep`/`list`; `bash` deny-by-default with a probe allowlist |
| `bashos-sealed` | `prompt` and `refine` loops, and the kernel's classifier | none — `{"*": "deny"}` |

OpenCode resolves permission patterns with **last matching rule wins**, so every `"*": "deny"` catch-all is emitted first and its allowlist follows: once for the `bashos` agent's tools as a whole, so a tool `policy.py` never named is refused, and again for `bash`'s commands. `edit`, `write`, `apply_patch`, `webfetch`, `websearch`, `execute` and `task` are denied outright *and* hidden from the model, so a denied tool cannot even burn a turn.

The tool-level catch-all exists because engines add tools. OpenCode 2 ships `execute` ("Code Mode": JavaScript with `fetch`), and an engine offers any tool an agent's rules do not refuse; on 2.0.20, before the catch-all, the `bashos` agent's `execute` reached the network. Where the catch-all lands is the engine's decision: OpenCode 1.19 and 2.x both build an agent's rules from its `tools` map first and fold `permission` into that, so the catch-all leads the `tools` map too, and the engine contract checks the order the engine actually resolved.

The policy is attached to the two bashOS agents, never to the project's global `permission` block — running plain `opencode` in this repository to develop bashOS keeps a normal toolset.

Two boundaries are worth calling out because they are easy to get wrong:

- **`external_directory` is denied.** OpenCode contributes its own defaults and
its own trailing allows for the engine's state directories; bashOS's `deny` lands between them, so paths outside the project resolve to `deny` while the engine's own machinery keeps working.
- **Approval prompts are refused, not awaited.** bashOS is non-interactive by
construction: the policy *is* the answer, so a request for approval is a request the policy did not already allow. The engine watcher replies `reject` to `permission.asked` and `permission.v2.asked` (on OpenCode 2, through the session's `/api/session/{id}/permission/{request}/reply`). Without that, any rule resolving to `ask` would hang a headless run until it timed out.

See the live policy any time, before anything runs:

```bash
bashos run -n /sys
```

## The registry, compiled

`bashos opencode sync` compiles `.claude/commands/*.md` and the policy into `opencode.jsonc`. The file is generated and committed — policy-as-code in one reviewable place — and a test fails if it drifts from the registry.

One markdown file is now three runtimes:

| runtime | how you invoke it |
|---|---|
| Claude Code | `/sh …` in a Claude Code session |
| bashOS kernel | `bashos run /sh …` |
| OpenCode TUI | `/sh …` in `opencode` |

The generated config is a function of the registry and the *defaults* only, never of a per-invocation flag — `bashos run -m other-model` must not rewrite a committed file as a side effect, so runtime overrides go to the engine API per request. It carries no credentials.

The engine re-syncs before it boots, so editing a command file is enough; set `BASHOS_OPENCODE_SYNC=0` to pin the file.

## Command surface

```bash
bashos opencode sync      # compile the registry + policy into opencode.jsonc
bashos opencode status    # boot the engine and report what it is running
bashos opencode auth      # which credential will be used, and from where
bashos opencode verify    # prove the engine still enforces policy.py (exit 1 if not)
bashos opencode serve     # run a shared engine in the foreground
```

Inside the REPL, `engine` prints the same status table.

## Environment

| variable | effect |
|---|---|
| `BASHOS_OPENCODE_URL` | attach to this engine instead of supervising one |
| `BASHOS_OPENCODE_PASSWORD` | basic-auth secret for an attached engine |
| `BASHOS_OPENCODE_AUTH=never` | wire no credential; use whatever the engine has |
| `BASHOS_OPENCODE_SYNC=0` | do not regenerate `opencode.jsonc` at start |
| `BASHOS_BACKEND` | `opencode` (default), `claude-code`, or `api` |

## Keeping the engine current

bashOS follows OpenCode's latest release, but it trusts a new one only after proving it still enforces the policy. `bashos opencode verify [--binary PATH]` boots an engine with no credential and reads back the permission rules it resolved for each agent (`GET /agent`, an ordered rule list where the last match wins). It judges them with OpenCode's own matching ([`opencode/rules.py`](../src/bashos/opencode/rules.py) mirrors `Wildcard.match`) against `policy.py` ([`opencode/contract.py`](../src/bashos/opencode/contract.py)), and exits 1 on any gap. The test fixtures are real OpenCode 1.19.5 and 2.0.20 engines' answers, so the contract is held to each engine's format, not ours.

- **On a bashOS machine** the OS layer manages the engine: fetched from the registry, checked, verified, promoted, updated daily. See [OS.md § The engine](OS.md#the-engine).
- **Elsewhere:** `npm i -g opencode-ai` (npm's `latest` is OpenCode 1 today), or Homebrew's or Arch's `opencode` (OpenCode 2), then `bashos opencode verify`.
- **Which binary:** `BASHOS_OPENCODE_BIN`, then the OS layer's managed engine (`/etc/bashos/opencode`), then `PATH`. `bashos doctor` says which one it found and which API it speaks.
- **The canary:** `engine-canary.yml` runs the contract daily on npm's latest and on the newest OpenCode 2 GitHub release, so a release that reads the policy differently turns red the day it ships.

## Two engine majors

bashOS speaks OpenCode 1 and OpenCode 2 ([#71](https://github.com/bamr87/bashos/issues/71)); a later major is named in `bashos doctor` and at engine start instead of being run.

**How the major is detected.** A binary bashOS starts reports it: `opencode --version` (`1.19.5`, `opencode v2.0.20`); a binary that names no version is spoken to as OpenCode 1, as before. An engine bashOS attaches to (`BASHOS_OPENCODE_URL`) is probed: OpenCode 1 answers `/global/health` with JSON, while on OpenCode 2 that path is the web UI's HTML and `/api/info` answers instead. A wrong password is reported, never taken as a hint about the major.

**What differs, and where it is handled.** Everything above the client sees one dialect: [`opencode/client.py`](../src/bashos/opencode/client.py) holds one route table per major, and [`opencode/v2.py`](../src/bashos/opencode/v2.py) translates OpenCode 2's answers and events into OpenCode 1's shapes. Every OpenCode 2 shape it reads was captured from a live 2.0.20 engine (`tests/fixtures/opencode-2.0.20-*.json`).

| | OpenCode 1 | OpenCode 2 |
|---|---|---|
| spawn flags | `--log-level INFO` | `--log-level info` (2.x rejects `INFO` and does not start) |
| API root | `/` | `/api` (the root is the web UI) |
| health | `GET /global/health` | `GET /api/info` |
| a prompt | `POST /session/{id}/message` answers with the reply | `POST /api/session/{id}/prompt` admits it; bashOS waits for idle and reads the turn off `GET /api/session/{id}/message` |
| model, system prompt | per prompt | per session (`/model`, and an instruction entry named `bashos.system`) |
| stop | `POST /session/{id}/abort` | `POST /api/session/{id}/interrupt` |
| events | `GET /event`: cumulative parts | `GET /api/event`: text deltas and `session.tool.*`, normalized to OpenCode 1's events |
| resolved rules | `permission: [{permission, pattern, action}]` | `permissions: [{action, resource, effect}]`; `bash` is `shell`, `task` is `subagent`, `write` folds into `edit` |

**The contract on OpenCode 2.** An OpenCode 2 engine also evaluates a permission on request, so `verify` puts every sample to the engine itself as well (one throwaway session per bashOS agent) and requires its answers to match what `policy.py` allows. It also drives, on one more throwaway session and without running a turn, every route a turn uses besides the permission ones: it switches the agent and the model, puts and deletes the `bashos.system` instruction entry, waits on the idle session, reads its timeline, proves `POST /api/session/{id}/prompt` is served with a body the engine must refuse (400, where a route it no longer serves answers 404), and reads the event stream's first frame. Two of those routes sit under 2.x's `/api/experimental` (`…/wait` and `…/instructions/entries/{key}`), and a release that moved one would still resolve the policy correctly, so this check is what turns `verify`, the canary and the OS layer's promotion red on such a release. And because a Homebrew or `opencode upgrade --major` binary never went through the OS layer's promotion, every OpenCode 2 engine runs the resolved-rules contract at start: it boots, waits for bashOS's agents to load (2.x lists its built-in agents a moment before the project's), and refuses to run anything if the contract fails. On 2.3.0 both bashOS agents still list a `skill` tool; the engine refuses every call to it.

## When the engine is not installed

`resolve_backend()` falls back to the Claude Agent SDK (`claude-code`) and then to the direct API (`api`). Both are completion-only escape hatches: they can serve the `prompt` and `refine` loops, but not `react`, whose policy is expressed in OpenCode's permission model and has nowhere else to be enforced. `bashos doctor` reports which backend is live and why.

```bash
npm i -g opencode-ai        # or: curl -fsSL https://opencode.ai/install | bash
```
