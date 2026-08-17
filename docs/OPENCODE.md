# The engine: OpenCode at the core of bashOS

bashOS's [reference architecture](../bashOS-architecture.md) is explicit that
the agent kernel must not contain a reasoning loop:

> Note what `bashosd` does *not* contain: a specific model, a specific agent's
> reasoning loop. Claude Code, Codex CLI, Gemini CLI, OpenCode — any of them can
> run *on* bashOS as the reasoning engine, the way any POSIX program runs on
> Linux. The OS supplies scheduling, identity, policy, sandboxes, memory, and
> audit; the agent supplies the thinking.

This document describes that separation as it is actually built. **OpenCode is
the engine.** It owns the agent loop, the tool broker, session state, and the
permission gate. bashOS owns everything an OS owns: the userland registry, the
routing kernel, the policy, the terminal, and the audit trace.

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

OpenCode is a client/server system: the TUI, its SDKs, and bashOS are all
clients of a local `opencode serve`. bashOS supervises one on a free loopback
port, or attaches to one you already run.

That process boundary is doing real work. The engine's tool loop executes
commands, so the socket that drives it is as sensitive as a shell. bashOS
therefore starts the server with a random per-process password
(`OPENCODE_SERVER_PASSWORD`) and speaks HTTP basic auth to it — an unauthenticated
loopback port is reachable by every other process on the box, which is not a
property you want on the thing holding your tool loop.

| | supervised (default) | attached (`BASHOS_OPENCODE_URL`) |
|---|---|---|
| lifecycle | started and stopped by bashOS | yours |
| port | free port, read back from the server's own startup line | yours |
| socket auth | random password per process | `BASHOS_OPENCODE_PASSWORD` |
| credentials | injected into the child environment | whatever it already has |
| logs | `.bashos/opencode.log` | yours |

Start a shared one with `bashos opencode serve`; it prints the two exports
another terminal needs.

## Auth: Claude Code OAuth, by default

bashOS is subscription-native. The engine runs on the Claude Code login you
already have, discovered in this order:

1. `CLAUDE_CODE_OAUTH_TOKEN` — an explicit override, and what CI uses
2. `~/.claude/.credentials.json` — the Linux/Windows CLI login (refreshable)
3. macOS Keychain, service `Claude Code-credentials`

`ANTHROPIC_API_KEY` is the fallback. `BASHOS_OPENCODE_AUTH=never` turns the
whole bridge off and lets the engine use whatever it already has.

### How the credential actually reaches the engine

This part was built against the running server rather than its documentation,
because the documentation is out of date. Three findings shaped it:

- **OpenCode 1.18 dropped Anthropic OAuth as a login method.** Its `anthropic`
  integration advertises `key` and `env` only. A stored `{"type":"oauth"}`
  credential does not register the provider at all — verified by writing one
  and watching `anthropic` stay absent from `/config/providers`, while the same
  file with `{"type":"api"}` registered it immediately.
- **So the token is carried the way Claude Code carries it**: as an
  `Authorization: Bearer` header declared through
  `provider.anthropic.options.headers`. The capital `A` matters — a lowercase
  `authorization` key is dropped before the request goes out. `apiKey` is
  pinned to `""` so a bearer token is never also sent as `x-api-key`, and
  `anthropic-beta: oauth-2025-04-20` is merged with the engine's own betas.
  Declaring `env` is what makes OpenCode register the provider in the first
  place.
- **The wiring is injected through the child's environment**, using
  `OPENCODE_CONFIG_CONTENT` and `OPENCODE_AUTH_CONTENT`, which merge with the
  project config at engine start. Two consequences, both deliberate: no secret
  is ever written to disk, and bashOS never touches
  `~/.local/share/opencode/auth.json` — if you ran `opencode auth login`
  yourself, you keep exactly what you had.

Because the provider registry is built when the server boots, the credential
has to exist before the process does. That is why it rides in on the
environment rather than being pushed over the API afterwards.

`bashos opencode auth` reports which credential would be used and which
variable names carry it — never the values.

**Attached engines are different.** A running server's environment is already
fixed, so the bearer route is closed and its owner keeps its credentials. Only
an API key can still be pushed in, and only when the engine has none.

## Policy: deny-by-default, bound to agents

`opencode/policy.py` is the single place where bashOS's blast radius is
defined. It compiles to two agents in the generated project config:

| agent | used by | tools |
|---|---|---|
| `bashos` | the `react` loop — `/sys`, `/debug`, `/health` | `read`/`glob`/`grep`/`list`; `bash` deny-by-default with a probe allowlist |
| `bashos-sealed` | `prompt` and `refine` loops, and the kernel's classifier | none — `{"*": "deny"}` |

OpenCode resolves permission patterns with **last matching rule wins**, so the
`"*": "deny"` catch-all is emitted first and the probe allowlist follows.
`edit`, `write`, `apply_patch`, `webfetch`, `websearch` and `task` are denied
outright *and* hidden from the model, so a denied tool cannot even burn a turn.

The policy is attached to the two bashOS agents, never to the project's global
`permission` block — running plain `opencode` in this repository to develop
bashOS keeps a normal toolset.

Two boundaries are worth calling out because they are easy to get wrong:

- **`external_directory` is denied.** OpenCode contributes its own defaults and
  its own trailing allows for the engine's state directories; bashOS's `deny`
  lands between them, so paths outside the project resolve to `deny` while the
  engine's own machinery keeps working.
- **Approval prompts are refused, not awaited.** bashOS is non-interactive by
  construction: the policy *is* the answer, so a request for approval is a
  request the policy did not already allow. The engine watcher replies `reject`
  to `permission.asked` and `permission.v2.asked`. Without that, any rule
  resolving to `ask` would hang a headless run until it timed out.

See the live policy any time, before anything runs:

```bash
bashos run -n /sys
```

## The registry, compiled

`bashos opencode sync` compiles `.claude/commands/*.md` and the policy into
`opencode.jsonc`. The file is generated and committed — policy-as-code in one
reviewable place — and a test fails if it drifts from the registry.

One markdown file is now three runtimes:

| runtime | how you invoke it |
|---|---|
| Claude Code | `/sh …` in a Claude Code session |
| bashOS kernel | `bashos run /sh …` |
| OpenCode TUI | `/sh …` in `opencode` |

The generated config is a function of the registry and the *defaults* only,
never of a per-invocation flag — `bashos run -m other-model` must not rewrite a
committed file as a side effect, so runtime overrides go to the engine API per
request. It carries no credentials.

The engine re-syncs before it boots, so editing a command file is enough; set
`BASHOS_OPENCODE_SYNC=0` to pin the file.

## Command surface

```bash
bashos opencode sync      # compile the registry + policy into opencode.jsonc
bashos opencode status    # boot the engine and report what it is running
bashos opencode auth      # which credential will be used, and from where
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

## When the engine is not installed

`resolve_backend()` falls back to the Claude Agent SDK (`claude-code`) and then
to the direct API (`api`). Both are completion-only escape hatches: they can
serve the `prompt` and `refine` loops, but not `react`, whose policy is
expressed in OpenCode's permission model and has nowhere else to be enforced.
`bashos doctor` reports which backend is live and why.

```bash
npm i -g opencode-ai        # or: curl -fsSL https://opencode.ai/install | bash
```
