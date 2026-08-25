# The bashOS Desktop

The desktop is bashOS's interactive surface: a windowed terminal environment
built on [Textual](https://textual.textualize.io), replacing the line REPL.
It is the L6 interface layer from the reference architecture — the promised
"TUI dashboard" matured into the primary surface. It is a *client* of the
kernel and the engine: it builds payloads, renders results and typed engine
events, and never reasons or executes anything itself.

```
 ┌─ bashOS ────────────────────────────────────────────────┐
 │ ┌ AI Console ────────────────┐ ┌ Health ──────────────┐ │
 │ │ you ▸ /sys why is it slow  │ │ [ OK ] load          │ │
 │ │ ⚙ bash(bin/os-health)      │ │ [WARN] memory        │ │
 │ │ ✓ bash(df -Ph /) (0.2s)    │ │ [ OK ] disk          │ │
 │ │ The load average is…       │ │                      │ │
 │ │ ▸ _                        │ │ [refresh] [ask]      │ │
 │ └────────────────────────────┘ └──────────────────────┘ │
 │ [◫ apps] [AI Console] [Health]   ⏻ engine: ready  12:00 │
 └──────────────────────────────────────────────────────────┘
```

## Launching

| invocation | behavior |
|---|---|
| `bashos` (in a TTY) | opens the desktop |
| `bashos` (pipe / CI / `TERM=dumb`) | one-line guidance on stderr, exit 2 |
| `bashos desktop` | opens the desktop explicitly |
| `BASHOS_DESKTOP=0 bashos` | disables auto-launch (guidance + exit 2) |
| `bashos run "<request>"` | one-shot CLI — unchanged, for scripts and CI |
| `bashos repl` | deprecated alias → the desktop (one release, then gone) |

Compatibility: `ssh -t host bashos` and `docker compose run bashos` get the
desktop (both allocate a TTY); `ssh host 'bashos run "/health"'` and cron
jobs use the one-shot CLI as before. `NOTMUX=1` is a FORGE remote-box
convention consumed by `bashos run` over ssh and is unaffected.

## Keys

| key | action |
|---|---|
| `ctrl+p` | command palette (every action lives here too) |
| `F2` | launcher — app grid + all registry commands |
| `F1` | help |
| `ctrl+n` | new AI Console window |
| `ctrl+o` | cycle window focus |
| `ctrl+b` | maximize / restore the active window |
| `ctrl+shift+w` | close the active window |
| `ctrl+t` | cycle theme (dark/light) |
| `ctrl+q` | quit (with confirmation) |
| `esc` (in a console) | stop the running turn — the engine run is aborted |
| `up`/`down` (in a console) | input history (`~/.bashos_history` carries over) |

## The window model

Hybrid tiling. Under 110 columns one window is visible at a time and the
taskbar tabs switch between them; wider terminals tile up to four windows
(most recently active); any window maximizes over its siblings and
restores. Modal overlays (launcher, help, exec confirmation) float above.

## The apps

- **AI Console** — the old REPL, per window: slash commands, plain english
  (classified), follow-ups, `!` shell escapes, `exec`. Answers stream in;
  tool calls tick by in the activity feed; a route hint under the prompt
  shows where each line will go before you press enter (computed by the
  kernel's pure helpers — zero model calls). Each window has its own
  bounded conversation memory (3 turns × 280-char excerpts reach the
  model — the same contract the REPL had).
- **Health** — `bin/os-health` verdict lines parsed into a table with the
  worst-verdict header; "ask /health" hands investigation to the react
  command. Deterministic floor, model for causes — the FORGE split.
- **Doctor** — `bashos doctor`'s checks, in a window.
- **Engine** — status rows (loads on demand; loading boots the engine),
  the deny-by-default policy verbatim, and the live typed-event wire.
- **Commands** — any registry command with a free dry-run preview (exactly
  `bashos run -n`) before running it in a console.
- **Trace** — the kernel's append-only routing trace per finished turn
  (`bashos run -v`, but windowed).
- **OpenCode TUI** — suspends the desktop and hands the real terminal to
  `opencode`, restoring on exit. It runs as an independent process in the
  project root: sessions there are separate from bashOS console turns.
  (Embedding a live pty widget is deferred — no maintained Textual
  terminal emulator exists, and pyte lacks what OpenCode's TUI needs.)

## Shell escapes

Inherited-stdio subprocesses are incompatible with a full-screen app, so:

- `!cmd` and confirmed `exec` runs stream captured output into a window;
- "run attached" (offered in the exec dialog) suspends the whole desktop,
  gives the command the real terminal, and restores — for interactive
  commands (editors, `top`, ssh).

The safety contract is unchanged: only `!` lines and an explicitly
confirmed `exec` run anything, and the confirm dialog defaults to Cancel.
Approval requests from engine runs are still auto-refused everywhere — an
interactive approval queue remains a future, opt-in, separately-named
policy profile (see bashOS-architecture.md L6).

## Engine lifecycle

The desktop owns one engine for its whole lifetime: started lazily by the
first live turn, stopped exactly once when the desktop exits. One global
SSE subscription (the event bus) fans events out per session; a dead
stream releases every waiting prompt and reconnects with backoff. One-shot
`bashos run` keeps its own start/stop-per-invocation contract.

Engine-side session reuse (`EngineSession` — create once, prompt many) is
built and tested at the engine layer; the console currently keeps the
kernel's one-session-per-turn semantics with history injection, and
adopting per-window engine sessions is tracked as a follow-up.

## Testing

Everything runs offline: `KernelConfig(dry_run=True)` gives llm=None (no
auth, no network, no engine — loops short-circuit to their rendered-prompt
reports), and FakeChat pins exact model-call counts. Pilot drives the UI
headless; three SVG snapshots (`pytest --snapshot-update` after intentional
visual changes) are the visual regression net.
