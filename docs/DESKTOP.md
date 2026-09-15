# The bashOS Desktop

A GUI front end on the same kernel the terminal runs. Read
[HARNESS.md](HARNESS.md) for the core architecture — this document covers the
window: what it is, what it deliberately is not, and how it is wired.

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

Nothing here is a second implementation. A console line goes through
`build_kernel(...)` — the same call `bashos run` makes — and the streaming is
LangGraph's own node updates plus the engine's tool events, the ones the REPL
prints as `· read file`.

## What it is not

**It is not a second way into the machine.** The window runs kernel lines and
nothing else:

- **No shell passthrough.** `!ls` is refused with a 403. In the terminal that
  escape hatch is your own shell, by your own keystroke, in a process you
  started. A local HTTP server that executes arbitrary commands is a different
  object with a different blast radius, so the desktop does not have one.
- **No wider tool policy.** The react loop still reaches the real machine, and
  still only through the engine's deny-by-default gate in
  `opencode/policy.py`. The Health scene *renders* that allowlist; it does not
  extend it.
- **No credentials on the wire.** `/api/doctor` reports where a credential came
  from — the same line `bashos doctor` prints — never the value. Secrets stay
  in the engine process's environment.
- **No reasoning loop.** The GUI server dispatches and renders. If a feature
  would need a loop in `src/bashos/gui/`, it belongs in a kernel loop or in the
  engine.

## How it is guarded

The socket drives a kernel that can read files and run diagnostic probes, so it
is guarded the way the engine's own socket is (`opencode/server.py`): a secret
generated per process, and nothing else trusted.

| Guard | What it stops |
|---|---|
| binds `127.0.0.1` | anything off this machine |
| per-process token, required on `/api/*` | every other process on the box |
| `Host` must be our own socket | DNS rebinding — a name that resolves to loopback |
| `Origin`, when present, must be our own | a page in the user's browser driving the API |
| `Content-Security-Policy: default-src 'self'` | injected script, remote assets, framing |
| caps on line, header count, body size | a malformed or oversized request |
| 8000-character input limit | a pathological prompt |

The token rides in the URL bashOS prints (`http://127.0.0.1:PORT/?k=…`). The
page stores it in `sessionStorage`, strips it from the address bar, and sends
it as `X-BashOS-Token`; the SSE stream takes it as `?k=` because `EventSource`
cannot set headers. It dies with the process — there is no persisted session.

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
  static files, server-sent events. bashOS has no web framework in its
  dependency tree and the desktop does not add one, so `pip install bashos`
  followed by `bashos gui` works with nothing else installed.
- `gui/web/` — the front end: one HTML file, one stylesheet, one ES module. No
  bundler, no npm, no build step. Editing `app.js` and reloading is the whole
  development loop.
- `gui/desktop.py` — the native window. `pip install "bashos[gui]"` adds
  pywebview, which drives the platform's own webview (WebKit on macOS,
  WebKit2GTK/Qt on Linux, WebView2 on Windows) — no bundled browser, no second
  runtime. Without it, the same URL opens in your default browser.

The window toolkit owns the main thread on macOS, so the native path runs the
asyncio server on a background loop and blocks the main thread in the toolkit.
The browser path is a plain `asyncio.run`, the shape the rest of bashOS uses.

## Runs are not history

A run lives in memory, in this process, and is gone when the window closes —
bashOS writes no history file and the desktop is not a reason to start. Each
run records what the terminal prints and then forgets: the route, each kernel
node as it completed, every trace line, every tool call, and the answer. Two
hundred runs are kept; older ones fall off.

## Adding a scene

1. Add a route in `gui/server.py` that returns JSON from something that already
   exists. If it needs new state, it probably belongs elsewhere.
2. Add a `scene*()` builder in `web/app.js` and an entry in `SCENES`.
3. Build DOM with `el()`, never `innerHTML` — the one exception is
   `renderMarkdown()`, which escapes before it structures.
4. No inline `style` attributes: the CSP forbids them. Use a class.

## Design notes

The look is deliberate: paper-cream ground, white cards with a hard offset
shadow, one loud accent, and mono for anything the machine said. Both themes
are defined as CSS custom properties on `:root` and `[data-theme="dark"]`, so a
new component gets dark mode by using the tokens. The whole stylesheet is
`web/app.css` — around 650 lines, no preprocessor.
