# SPEC: bashOS L6 OS Shell (evolution of `gui/web`)

**Status:** Phase 0 implemented — ships with the desktop GUI in [PR #20](https://github.com/bamr87/bashos/pull/20)  
**Related:** [PRD-os-shell.md](./PRD-os-shell.md), [ROADMAP-os-shell.md](./ROADMAP-os-shell.md), [RELATION-TO-DESKTOP.md](./RELATION-TO-DESKTOP.md)  
**Foundation:** [`docs/DESKTOP.md`](../DESKTOP.md) (when #20 merges) — stack, scenes, guards  
**Evidence:** PostHog research = **inspiration only**. Proposals beyond #20 APIs labeled **Proposal**.

---


> **Status update — Phases 0–2 landed, and Phase 3's windowing with them.**
> Implemented: experiences `single` | `tiling` | `os` | `plain`, the four nav
> intents, pane chrome, floating windows (drag, resize, edge snap, z-order,
> minimize with a taskbar that restores), desktop icons, arrange tile/cascade,
> workspace layouts (`?windows=` + per-tab restore), context menus, palette
> depth and the keymap. The reducer is `src/bashos/gui/web/shell.js` with 36
> unit tests in `tests/shell.test.mjs`; the DOM consumers are asserted by
> `tools/capture_desktop.py` on every capture run. Still proposed: nostalgia
> themes, a full a11y audit, remote auth. Never needed: a bundler.

---

## 1. Scope

Technical specification for evolving the **existing** desktop GUI (`src/bashos/gui/`, `gui/web/`) into an optional multi-pane / OS-shell operator console. Does not replace CLI/REPL, SSH, TUI, or PR #20’s single-scene mode.

---

## 2. Architecture

### 2.1 Layer placement

```
L6 INTERFACE
├── bashos CLI / REPL (existing)
├── SSH / TUI (existing)
└── bashos gui  [PR #20 — current web/native surface]
      ├── gui/http.py      asyncio HTTP (~300 LOC)
      ├── gui/server.py    routes · guards · SSE
      ├── gui/runs.py      in-memory runs (cap 200)
      ├── gui/desktop.py   optional pywebview
      └── gui/web/         index.html + app.css + app.js  (no npm)
            ├── SCENES + scene*() builders   ← App Template today
            ├── hash router (#/console, #/runs/<id>)
            ├── ⌘K palette, sidebar, themes
            └── Shell Provider (this spec) wraps scene system
                  ├── single (today) | multi-pane | os (later)
                  └── scene instances as windows/panes
```

### 2.2 Incremental path (normative)

1. **Scene-as-window chrome** around current scenes (title, focus, close, maximize) without changing scene builders’ core contracts.  
2. **Side-by-side two scenes** (two instances visible; hash/layout state tracks both).  
3. **Optional floating** drag/resize later (Phase 3) — not MVP.

Do **not** introduce a parallel React tree or Vite app in Phases 0–2.

### 2.3 Shell component tree

```mermaid
flowchart TB
  subgraph L6["L6 bashos gui — evolve"]
    HTTP[gui/http.py + server.py]
    WEB[gui/web app.js]
    HTTP --> WEB
    WEB --> SP[ShellProvider / layout state]
    WEB --> PAL[CommandPalette ⌘K]
    WEB --> SB[Sidebar / window list]
    SP --> EXP{experience}
    EXP -->|single| ONE[Current one-scene mount]
    EXP -->|tiling| MP[MultiPane two+ scene instances]
    EXP -->|os later| OD[Floating scene windows]
    ONE --> SC[scene*() builders]
    MP --> SC
    OD --> SC
    SC --> S7[Overview Console Commands Runs Health Engine Settings]
  end
  subgraph Kernel["Same kernel as CLI"]
    BK[build_kernel]
  end
  HTTP --> BK
```

### 2.4 Wrap-at-root (conceptual — vanilla JS)

```
ShellRoot (index.html chrome)
├── Sidebar / WindowList     # evolve scene nav → open instances
├── TopBar                   # breadcrumb, dry-run, theme (#20)
├── LayoutViewport
│   ├── SingleScene | MultiPane | OsDesktop
│   └── SceneHost → scene*() / SCENES
├── CommandPalette           # existing ⌘K — global overlay
└── Toasts / locked screen   # existing patterns
```

**Live PostHog parallel (inspiration only):** side-by-side + context menus + maximize/close are high-confidence; free drag/resize and handbook shortcuts are not. Prefer side-by-side on #20 scenes.

### 2.5 State split (performance, no React required)

Keep layout state separate from scene DOM where possible (Console already keeps its own DOM across nav in #20 — preserve that):

| Concern | Owner |
|---|---|
| Actions | `navigate(intent)`, `focus`, `close`, `sideBySide` — stable functions |
| Settings / prefs | existing `store.prefs`, theme, future `experience` |
| UI flags | palette open, overlays |
| Windows/panes | list of scene instances (layout only) |
| Scene data | existing `store` + `/api/*` fetches |

---

## 3. Window / pane JSON schema

Binds to **scene id** + optional resource (e.g. run id). Geometry as percent of viewport when persisted. Compatible with #20 hashes.

```json
{
  "$schema": "https://bashos.dev/schemas/shell-window-v1.json",
  "schemaVersion": 1,
  "windows": [
    {
      "id": "win_01HZX...",
      "sceneId": "console",
      "title": "Console",
      "resourceId": null,
      "hash": "#/console",
      "zIndex": 2,
      "minimized": false,
      "expanded": false,
      "snapped": "left",
      "position": { "xPct": 0, "yPct": 0 },
      "size": { "wPct": 50, "hPct": 100 },
      "attribution": {
        "actor": "user:local",
        "runId": null,
        "sessionId": null
      },
      "createdAt": "2026-09-15T02:00:00Z"
    },
    {
      "id": "win_01HZY...",
      "sceneId": "runs",
      "title": "Run detail",
      "resourceId": "run_01HZY...",
      "hash": "#/runs/run_01HZY...",
      "zIndex": 3,
      "snapped": "right",
      "position": { "xPct": 50, "yPct": 0 },
      "size": { "wPct": 50, "hPct": 100 },
      "attribution": {
        "actor": "user:local",
        "runId": "run_01HZY...",
        "sessionId": null
      },
      "createdAt": "2026-09-15T02:01:00Z"
    }
  ]
}
```

### 3.1 TypeScript-shaped types (documentation only — implement in JS)

```ts
type Experience = 'single' | 'tiling' | 'os' | 'plain'
type SnapEdge = 'left' | 'right' | false
type NavIntent = 'replace' | 'new' | 'focus' | 'sideBySide'

type SceneId =
  | 'overview'
  | 'console'
  | 'commands'
  | 'runs'
  | 'health'
  | 'engine'
  | 'settings'
  // Could later: 'docs' | 'files'

interface ShellWindow {
  id: string
  sceneId: SceneId
  title: string
  resourceId?: string | null   // e.g. run id for #/runs/<id>
  hash: string                 // aligned with #20 routing
  zIndex: number
  minimized: boolean
  expanded: boolean
  snapped: SnapEdge
  position: { xPct: number; yPct: number }
  size: { wPct: number; hPct: number }
  attribution: {
    actor: string
    runId?: string | null
    sessionId?: string | null
  }
  createdAt: string
}

interface ShellSettings {
  experience: Experience
  // theme already in #20 localStorage; dryRun/model in prefs
  density?: 'comfortable' | 'compact'
  performanceBoost?: boolean
  keymapProfile?: 'default' | string
}
```

**As implemented:** every field above is real except `expanded` (tiling's maximize, kept separate from the desktop's `snapped: "max"`). Geometry is percentages, `zIndex` is a monotonic counter bumped on focus, and `snapped`
takes `left | right | max | null`. The serialized form is shorter than the
schema above — `{v,e,f,w:[{s,r,x,y,cx,cy,m,k}]}` — because it travels in a URL; `decodeLayout` validates the version, drops scenes this build does not have, dedupes the Console, and clamps every number.

---

## 4. Navigation intents

Aligned with #20 hash routing. Today’s `navigate(id)` / `location.hash` ≈ **`replace`**.

| Intent | Behavior | Trigger examples |
|---|---|---|
| `replace` | Mutate focused instance’s `sceneId` / `resourceId` / `hash` (current #20 behavior) | Sidebar click, in-scene link, default nav |
| `new` | **Append** a scene instance; bring to front | Context “Open in new pane/window”, palette “new …” |
| `focus` | If same `(sceneId, resourceId)` exists → focus only; no duplicate | Second activation of same run detail |
| `sideBySide` | Keep focused; open target as opposite pane; focus switch; close → single | Context / palette “Open side by side” |
| *(browser)* | `window.open` same origin + hash + token rules as #20 | “Open in new browser tab” — Must fallback |

```js
// Pseudocode — normative behavior; vanilla JS in app.js
function navigate(target, intent = 'replace') {
  const existing = findBySceneResource(target)
  if (intent === 'focus' && existing) return focus(existing.id)
  if (intent === 'new' || intent === 'sideBySide') {
    return appendWindow(target, intent === 'sideBySide' ? { snap: 'opposite' } : {})
  }
  return replaceFocused(target) // also updates location.hash like #20 today
}
```

**Hard rule:** Documented intent ⇒ tested consumer. Every row above has one, in `gui/web/shell.js`, asserted by `tests/shell.test.mjs` (unit) and `tools/capture_desktop.py` (DOM).

### 4.1 What the implementation settled

| Question the table left open | Decision, as implemented |
|---|---|
| What does a split do in `single`? | Asking for a split **is** the consumer of `tiling`: the mode turns on and the pane opens. `plain` is the deliberate exception — there a split falls back to `replace`, because `plain` exists to unmount chrome. |
| What happens at the pane cap? | `MAX_PANES = 2` in Phase 0. At the cap, a split replaces **the pane you are not watching** and focuses it; the pane you were reading survives. |
| Two instances of one scene? | Allowed where a resource distinguishes them — two run details (`#/runs/a` ‖ `#/runs/b`) are two windows. |
| Console? | **Singleton.** Any intent that targets an open Console focuses it instead of mounting a second composer and a second event stream. |
| Which hash wins with two panes? | The focused pane's, so every existing deep link still means what it did. |

---

## 5. App Template API = scene builder pattern

### 5.1 Contract (extend, don’t replace)

#20 already has:

```js
const SCENES = [
  { id: 'overview', label: 'Overview', icon: 'i-grid', group: 'Workspace' },
  { id: 'console', label: 'Console', icon: 'i-terminal', group: 'Workspace' },
  // ...
]

function sceneOverview() { /* ... */ }
// sceneCommands, sceneRuns, sceneRunDetail, sceneHealth, sceneEngine, sceneSettings
```

OS-shell extends registration optionally:

```js
/** @typedef {{ id: string, label: string, icon: string, group: string,
 *              build: (ctx) => Node, canOpen?: (resourceId) => boolean }} SceneModule */

// build(ctx) receives { windowId, resourceId, attribution } in multi-pane mode
// Console continues to own persistent DOM across instance swaps where #20 does today
```

Shared chrome: top bar breadcrumb / resource hash, window actions (close, maximize), dry-run switch stays global as in #20.

### 5.2 Initial apps = the seven scenes

| SceneId | Metaphor | Hash / resource | Notes |
|---|---|---|---|
| `overview` | Session home | `#/overview` | Quick-run chips, recent runs |
| `console` | Terminal-as-GUI | `#/console` | Composer, slash completion, SSE runs |
| `commands` | Userland registry | `#/commands` | `.claude/commands/*.md` |
| `runs` | Run list / detail | `#/runs`, `#/runs/<id>` | In-memory only |
| `health` | Host + allowlist view | `#/health` | **Renders** policy; does not extend it |
| `engine` | Doctor / engine state | `#/engine` | No secrets on wire |
| `settings` | Model, dry-run default, theme | `#/settings` | |

**Could later:** Docs, Files — only if they fit DESKTOP.md extension rules (JSON from existing state, `el()` not `innerHTML`, no inline styles).

**Won’t as MVP replacements:** Invented Terminal/Agent/Editor/Files/Inbox apps that ignore the seven scenes. Approvals remain engine/policy-gated; do not invent an Inbox that bypasses kernel policy. If an approvals surface appears later, it must call the same resolve path the runtime already uses (**Proposal**).

---

## 6. Keyboard map

### 6.1 PR #20 baseline (normative — do not break)

| Shortcut | Action | Notes |
|---|---|---|
| `⌘K` / `Ctrl+K` | Toggle command palette | Works in #20 |
| Composer `/` at line start | Slash command completion | **Composer-owned** — not global Spotlight |
| `Esc` | Dismiss palette / slash UI | |
| `Enter` / `Shift+Enter` | Run / newline in composer | Console |
| `↑`/`↓` / `Tab` | Slash list navigation | Console |
| Theme toggle / dry-run | UI controls in chrome | Settings + top bar |

Ignore OS-shell chords when focus is in composer `textarea` (and future inputs), except chords that intentionally include modifiers (e.g. ⌘K).

### 6.2 OS-shell additions (careful — avoid collisions)

| Shortcut | Action | Mode | Priority |
|---|---|---|---|
| `⌘K` / `Ctrl+K` | Palette (baseline) | all | Must |
| `Esc` | Close palette / overlays | all | Must |
| `Ctrl/Cmd+W` | Close focused pane/window | tiling, os | Must — **caveat:** browsers reserve it for the tab, so it lands only in the native window. The pane's ✕ and the palette's "Close focused pane" always work. Documenting it without that caveat would be exactly the folklore §6.3 warns about. |
| `Ctrl/Cmd+\\` | Cycle panes | tiling | Landed |
| Context / palette “Side by side” | `sideBySide` intent | tiling | Must (discoverable without new chord if needed) |
| `Ctrl/Cmd+,` | Focus Settings scene | all | Should — verify no conflict |

**Do not** steal bare `/` for a global search overlay while Console composer uses `/` for slash completion. PostHog’s live `/` → search is inspiration only.

### 6.3 PostHog drift (do not copy blindly)

PostHog: `/` worked, `Ctrl+K` failed live; snap shortcuts and minimize often folklore. bashOS already chose ⌘K successfully — keep it. Document from **#20 + our tests**, not PostHog handbook fiction.

---

## 7. Workspace deep-links

| Form | Example | Behavior |
|---|---|---|
| Single scene (#20) | `#/console`, `#/runs/<id>` | `single` / focused instance |
| Layout restore | `?windows=<url-encoded JSON>#/...` | Hydrate `ShellWindow[]` — **Proposal** encoding details |
| Experience override | `?experience=single` | Force mode |
| Token | `?k=` then sessionStorage (#20) | Unchanged — never put credentials in layouts |

Shareable layouts reproduce operator setups; they are not SEO and must not serialize secrets or full run transcripts to disk by default.

---

## 8. Runtime integration

### 8.1 Existing (#20 — real)

| Surface | Role |
|---|---|
| `POST /api/runs` + SSE | Console execution; same `build_kernel(...)` as CLI |
| `GET /api/state` | Overview, Settings, chrome |
| `GET /api/runs` | Runs scene |
| `GET /api/policy` | Health allowlist **render** |
| Doctor / engine routes | Engine scene; credential **source** only, never value |
| Dry-run switch | Same as CLI `-n` |

### 8.2 New endpoints — **Proposal only**

| Concern | Proposal |
|---|---|
| Layout persistence | **Client-only, as proposed** — `?windows=` plus `sessionStorage`; no endpoint was added |
| Approvals bus | Only if kernel already emits gates — GUI must not invent a bypass |
| Extra metrics | Status from `/api/state` extensions — Proposal |

Mark stubs `// Proposal`. Default: **no new server endpoints** for Phase 0–1 multi-pane.

---

## 9. Stack recommendation

| Concern | Recommendation | Justification |
|---|---|---|
| Phases 0–2 | **Stay on #20 stack** — `gui/http.py`, one HTML/CSS/JS, optional pywebview | Matches product philosophy; `pip install bashos` + `bashos gui` with nothing else |
| Bundler / npm | **Not required** for MVP | Explicit non-goal |
| Window motion | Side-by-side + maximize via CSS / DOM | PostHog free-drag unreliable; avoid Framer dependency |
| Terminal / streams | Existing Console + SSE | Do not add xterm.js unless Console needs it later |
| Palette | Existing ⌘K implementation | Extend `paletteItems()` |
| Test / capture | `tools/capture_desktop.py` (+ Playwright deps as today) | Update captures when chrome changes |
| Phase 3+ framework | React/Vite **only** as explicit tradeoff | Cost: rewrite capture tooling, abandon no-build story — do **not** prescribe as default |

**Rejected as default:** Vite+React+Tailwind+Radix MVP, Gatsby, Next SSG, Kea, hedgehog packages.

---

## 10. Security — PR #20 guards (normative)

OS-shell evolution **MUST preserve** these. Copy treated as constraints, not suggestions.

| Guard | What it stops |
|---|---|
| binds `127.0.0.1` | anything off this machine |
| per-process token on `/api/*` | every other process on the box |
| `Host` must be our own socket | DNS rebinding |
| `Origin`, when present, must be our own | drive-by browser pages |
| `Content-Security-Policy: default-src 'self'` | injected script, remote assets, framing |
| caps on line, header count, body size | malformed / oversized requests |
| 8000-character input limit | pathological prompts |

**Product refusals (also normative):**

- No shell passthrough (`!` → 403)  
- No wider tool policy (Health renders allowlist only)  
- No credentials on the wire  
- No history file (runs in-memory, cap 200)  
- No reasoning loop in `gui/`  

Multi-pane / window chrome is **not** a reason to relax any row above. New UI must use `el()`, not `innerHTML` (except existing escaped markdown path); no inline `style` (CSP).

---

## 11. Accessibility, mobile, performance

### 11.1 A11y

- Focus trap in palette; restore focus on close (#20 baseline)  
- Pane chrome labeled; keyboard close/cycle  
- `prefers-reduced-motion` honored when animations appear  
- `single`/`plain` fully usable without drag  

### 11.2 Mobile / narrow

- Force `single` when narrow — multi-pane optional later  
- Do not ship unbroken floating multi-window on small screens  

### 11.3 Performance

- Preserve Console DOM across scene switches where #20 already does  
- Avoid re-fetch storms when splitting panes — share `store`  
- Budget: two panes interactive; no bundler required  

---

## 12. Live UI evidence → spec decisions (inspiration)

| Live confirmation | Spec decision |
|---|---|
| Side-by-side + context menus | Must on **scenes**, Phase 0–1 |
| Free drag unreliable; minimize missing | Defer to Phase 3 Could |
| `/` search on PostHog | **Do not** steal composer `/`; keep ⌘K |
| Boring mode broken | Real `single`/`plain` consumer |
| Dense apps | Seven scenes already dense — wrap them |

---

## 13. Open questions (spec-level)

1. Persist multi-pane only in URL, or also `sessionStorage`?  
2. Should Console be **pinned** left when side-by-side with any System scene?  
3. Two instances of the same scene (two run details) — allow in Phase 1 or Phase 2?  
4. Any need for new `/api/*` for layouts, or client-only forever?  
5. Phase 3 framework trigger: what complexity metric forces the tradeoff?

---

*End of SPEC.*
