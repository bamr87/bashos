# The bashOS Desktop

The desktop is bashOS's interactive surface: a windowed terminal environment built on [Textual](https://textual.textualize.io), replacing the line REPL. It is the L6 interface layer from the reference architecture — the promised "TUI dashboard" matured into the primary surface. It is a *client* of the kernel and the engine: it builds payloads, renders results and typed engine events, and never reasons or executes anything itself.

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

Compatibility: `ssh -t host bashos` and `docker compose run bashos` get the desktop (both allocate a TTY); `ssh host 'bashos run "/health"'` and cron jobs use the one-shot CLI as before. `NOTMUX=1` is a FORGE remote-box convention consumed by `bashos run` over ssh and is unaffected.

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

Hybrid tiling. Under 110 columns one window is visible at a time and the taskbar tabs switch between them; wider terminals tile up to four windows (most recently active); any window maximizes over its siblings and restores. Modal overlays (launcher, help, exec confirmation) float above.

## The apps

- **AI Console** — the old REPL, per window: slash commands, plain english
(classified), follow-ups, `!` shell escapes, `exec`. Answers stream in; tool calls tick by in the activity feed; a route hint under the prompt shows where each line will go before you press enter (computed by the kernel's pure helpers — zero model calls). Each window has its own bounded conversation memory (3 turns × 280-char excerpts reach the model — the same contract the REPL had).
- **Health** — `bin/os-health` verdict lines parsed into a table with the
worst-verdict header; "ask /health" hands investigation to the react command. Deterministic floor, model for causes — the FORGE split.
- **Doctor** — `bashos doctor`'s checks, in a window.
- **Engine** — status rows (loads on demand; loading boots the engine),
  the deny-by-default policy verbatim, and the live typed-event wire.
- **Commands** — any registry command with a free dry-run preview (exactly
  `bashos run -n`) before running it in a console.
- **Trace** — the kernel's append-only routing trace per finished turn
  (`bashos run -v`, but windowed).
- **OpenCode TUI** — suspends the desktop and hands the real terminal to
`opencode`, restoring on exit. It runs as an independent process in the project root: sessions there are separate from bashOS console turns. (Embedding a live pty widget is deferred — no maintained Textual terminal emulator exists, and pyte lacks what OpenCode's TUI needs.)

## Shell escapes

Inherited-stdio subprocesses are incompatible with a full-screen app, so:

- `!cmd` and confirmed `exec` runs stream captured output into a window;
- "run attached" (offered in the exec dialog) suspends the whole desktop,
gives the command the real terminal, and restores — for interactive commands (editors, `top`, ssh).

The safety contract is unchanged: only `!` lines and an explicitly confirmed `exec` run anything, and the confirm dialog defaults to Cancel. Approval requests from engine runs are still auto-refused everywhere — an interactive approval queue remains a future, opt-in, separately-named policy profile (see bashOS-architecture.md L6).

## Engine lifecycle

The desktop owns one engine for its whole lifetime: started lazily by the first live turn, stopped exactly once when the desktop exits. One global SSE subscription (the event bus) fans events out per session; a dead stream releases every waiting prompt and reconnects with backoff. One-shot `bashos run` keeps its own start/stop-per-invocation contract.

Engine-side session reuse (`EngineSession` — create once, prompt many) is built and tested at the engine layer; the console currently keeps the kernel's one-session-per-turn semantics with history injection, and adopting per-window engine sessions is tracked as a follow-up.

## Testing

Everything runs offline: `KernelConfig(dry_run=True)` gives llm=None (no auth, no network, no engine — loops short-circuit to their rendered-prompt reports), and FakeChat pins exact model-call counts. Pilot drives the UI headless; three SVG snapshots (`pytest --snapshot-update` after intentional visual changes) are the visual regression net. A GUI front end on the same kernel the terminal runs. Read [HARNESS.md](HARNESS.md) for the core architecture — this document covers the window: what it is, what it deliberately is not, and how it is wired. For the feature-by-feature walkthrough with screenshots and recordings, see [DESKTOP-TOUR.md](DESKTOP-TOUR.md).

```bash
bashos gui                 # native window if bashos[gui] is installed, else browser
bashos gui --browser       # skip the window, use the default browser
bashos gui --no-open       # just serve; print the URL
bashos gui --port 7800     # pin the port (default: a free one)
```

## What it is

One page, seven scenes, all of them views of things that already exist:

| Scene | What it shows | Where the data comes from |
|---|---|---|
| **Overview** | session stats, quick-run chips, recent runs, the path a line takes | `/api/state`, `/api/runs` |
| **Console** | the terminal, as a GUI: one composer, slash completion, live runs | `POST /api/runs` + SSE |
| **Commands** | userland — every `.claude/commands/*.md` with loop, agent, prompt spec | the registry |
| **Runs** | every line this window sent through the kernel, with its trace | the in-memory run store |
| **Health** | host facts, the react-loop sweeps, the probe allowlist | `/api/state`, `/api/policy` |
| **Engine** | `doctor` checks, live engine state, the tool policy, `opencode.jsonc` | `runtime/auth.py`, `opencode/*` |
| **Settings** | model, dry-run default, what this runtime resolved to | `/api/state` |

Nothing here is a second implementation. A console line goes through `build_kernel(...)` — the same call `bashos run` makes — and the streaming is LangGraph's own node updates plus the engine's tool events, the ones the REPL prints as `· read file`.

## What it is not

**It is not a second way into the machine.** The window runs kernel lines and nothing else:

- **No shell passthrough.** `!ls` is refused with a 403. In the terminal that
escape hatch is your own shell, by your own keystroke, in a process you started. A local HTTP server that executes arbitrary commands is a different object with a different blast radius, so the desktop does not have one.
- **No wider tool policy.** The react loop still reaches the real machine, and
still only through the engine's deny-by-default gate in `opencode/policy.py`. The Health scene *renders* that allowlist; it does not extend it.
- **No credentials on the wire.** `/api/doctor` reports where a credential came
from — the same line `bashos doctor` prints — never the value. Secrets stay in the engine process's environment.
- **No reasoning loop.** The GUI server dispatches and renders. If a feature
would need a loop in `src/bashos/gui/`, it belongs in a kernel loop or in the engine.

## How it is guarded

The socket drives a kernel that can read files and run diagnostic probes, so it is guarded the way the engine's own socket is (`opencode/server.py`): a secret generated per process, and nothing else trusted.

| Guard | What it stops |
|---|---|
| binds `127.0.0.1` | anything off this machine |
| per-process token, required on `/api/*` | every other process on the box |
| `Host` must be our own socket | DNS rebinding — a name that resolves to loopback |
| `Origin`, when present, must be our own | a page in the user's browser driving the API |
| `Content-Security-Policy: default-src 'self'` | injected script, remote assets, framing |
| caps on line, header count, body size | a malformed or oversized request |
| 8000-character input limit | a pathological prompt |

The token rides in the URL bashOS prints (`http://127.0.0.1:PORT/?k=…`). The page stores it in `sessionStorage`, strips it from the address bar, and sends it as `X-BashOS-Token`; the SSE stream takes it as `?k=` because `EventSource` cannot set headers. It dies with the process — there is no persisted session.

## The stack

```
 window  ── pywebview (platform webview) ─┐
                                          ├─▶ http://127.0.0.1:PORT
 browser ── whatever is default ──────────┘        │
                                                   ▼
                                   gui/http.py    asyncio HTTP/1.1 + SSE
                                   gui/server.py  routes · guard · streaming
                                   gui/runs.py    run history (memory only)
                                                   │
                                                   ▼
                                   kernel ── loops ── policy ── engine
```

- `gui/http.py` — ~300 lines of asyncio: request parsing, a path router, JSON,
static files, server-sent events. bashOS has no web framework in its dependency tree and the desktop does not add one, so `pip install bashos` followed by `bashos gui` works with nothing else installed.
- `gui/web/` — the front end: one HTML file, one stylesheet, two ES modules
(`app.js` draws, `shell.js` decides the layout). No bundler, no npm, no build step. Editing and reloading is the whole development loop.
- `gui/desktop.py` — the native window. `pip install "bashos[gui]"` adds
pywebview, which drives the platform's own webview (WebKit on macOS, WebKit2GTK/Qt on Linux, WebView2 on Windows) — no bundled browser, no second runtime. Without it, the same URL opens in your default browser.

The window toolkit owns the main thread on macOS, so the native path runs the asyncio server on a background loop and blocks the main thread in the toolkit. The browser path is a plain `asyncio.run`, the shape the rest of bashOS uses.

## Experience modes

`shell.js` is a pure reducer over one piece of state — which scenes are open, which is focused, which mode the window is in — with no DOM and no fetch, so it can be unit-tested (`tests/shell.test.mjs`, run by `pytest -q`) apart from whatever `app.js` draws.

| Mode | Consumer |
|---|---|
| `single` | one scene mounted, as it always was |
| `tiling` | two panes, each a scene instance, focus follows the click |
| `os` | floating windows over a desktop: icons, drag, resize, snap, a taskbar |
| `plain` | one scene, sidebar and top bar unmounted |

Four navigation intents move between them — `replace` (a click, unchanged), `new`, `focus` and `sideBySide` — each with a consumer in the reducer and a test. A mode or an intent with nothing behind it is the drift [frontend/](frontend/README.md) exists to avoid; `os` arrived only when windows you can actually drag, snap, minimize and restore did.

Window geometry is percentages of the desktop, so a layout survives a resize, and `minimize` exists only because the taskbar genuinely restores.

Layout lives in the client: no route was added, and `/api/*` is untouched. `encodeLayout`/`decodeLayout` serialize it into `?windows=` for a shareable workspace and into `sessionStorage` so a reload puts the windows back. A layout carries scene ids, resource ids and geometry — never a token, never run output, and `decodeLayout` drops any scene this build does not have.

The Console is a singleton — it owns persistent DOM and an event stream, so a split or a new window focuses it instead of mounting a second one.

## Runs are not history

A run lives in memory, in this process, and is gone when the window closes — bashOS writes no history file and the desktop is not a reason to start. Each run records what the terminal prints and then forgets: the route, each kernel node as it completed, every trace line, every tool call, and the answer. Two hundred runs are kept; older ones fall off.

## Adding a scene

1. Add a route in `gui/server.py` that returns JSON from something that already
   exists. If it needs new state, it probably belongs elsewhere.
2. Add a `scene*()` builder in `web/app.js` and an entry in `SCENES`. It works
   in a pane for free — panes host the same builders.
3. Build DOM with `el()`, never `innerHTML` — the one exception is
   `renderMarkdown()`, which escapes before it structures.
4. No inline `style` attributes: the CSP forbids them. Use a class.

## Keeping the docs honest

[`tools/capture_desktop.py`](../tools/capture_desktop.py) starts `bashos gui` on a private port, drives every scene with a real browser, and writes the stills and GIFs in [DESKTOP-TOUR.md](DESKTOP-TOUR.md), reporting any console error the page produced. It needs `playwright` and `pillow`, is not part of the package, and is not run by CI — run it when the front end changes:

```bash
python tools/capture_desktop.py     # writes docs/media/
```

## Design notes

The look is deliberate: paper-cream ground, white cards with a hard offset shadow, one loud accent, and mono for anything the machine said. Both themes are defined as CSS custom properties on `:root` and `[data-theme="dark"]`, so a new component gets dark mode by using the tokens. The whole stylesheet is `web/app.css` — around 650 lines, no preprocessor.
