# SPEC: bashOS L6 OS Shell

**Status:** Draft for review  
**Related:** [PRD-os-shell.md](./PRD-os-shell.md), [ROADMAP-os-shell.md](./ROADMAP-os-shell.md)  
**Evidence:** PostHog research brief + live browser tour (2026-09-15). Proposals labeled **Proposal**.

---

## 1. Scope

Technical specification for an optional L6 **web OS shell**: multi-window / tiling operator console over bashOS runtime sessions. Does not replace CLI/REPL, SSH, or TUI.

---

## 2. Architecture

### 2.1 Layer placement

```
L6 INTERFACE
├── bashos CLI / REPL (existing)
├── SSH / TUI (existing)
└── Web OS Shell (this spec)
      ├── Shell Provider (experience, settings, nav)
      ├── Layout: OsDesktop | TilingLayout | PlainConsole
      ├── Apps (Terminal, Agent, Editor, Files, Logs, Settings, Inbox)
      └── Bridges → runtime  [Proposal]
            ├── LangGraph kernel (runs, graph state, approvals)
            └── OpenCode engine (tools, PTY, workspace FS)
```

### 2.2 Shell component tree (mermaid)

```mermaid
flowchart TB
  subgraph L6["L6 Web Shell"]
    SP[ShellProvider]
    MB[MenuBar / StatusBar]
    CP[CommandPalette]
    ND[NotificationDock]
    SP --> MB
    SP --> CP
    SP --> ND
    SP --> EXP{experience}
    EXP -->|os| OD[OsDesktop]
    EXP -->|tiling| TL[TilingLayout]
    EXP -->|plain| PC[PlainConsole]
    OD --> WL[WindowList]
    OD --> DI[PinnedIcons optional]
    WL --> SW[ShellWindow x N]
    TL --> PN[Pane nodes]
    SW --> AT[AppTemplate]
    PN --> AT
    AT --> APP[Terminal / Agent / Editor / Files / Logs / Settings / Inbox]
  end
  subgraph Runtime["Runtime — Proposal"]
    KG[LangGraph kernel]
    OC[OpenCode engine]
  end
  APP -.->|session bind| KG
  APP -.->|PTY / FS / tools| OC
```

### 2.3 Text tree (parity with PostHog wrap-at-root)

```
ShellRoot
├── ShellProvider          # windows/panes, shellSettings, actions
├── MenuBar / StatusBar    # host, agent count, model, cost  [Proposal: cost feed]
├── LayoutViewport
│   ├── OsDesktop | TilingLayout | PlainConsole
│   └── WindowList | PaneTree → ShellWindow → AppTemplate → App
├── CommandPalette         # Ctrl+K / `/` — global overlay, not a managed window
└── NotificationDock       # toasts; irreversible prompts may deep-link to Inbox
```

**Live PostHog parallel (confirmed):** fixed top taskbar; routes inside rounded AppWindow chrome; `/` → centered search overlay; Esc closes; Display Options as a settings surface; maximize/restore verified. Drag/resize/snap/minimize claimed in code/docs, **not** independently verified in the live tour — treat motion stack as Phase 0 risk.

### 2.4 Context split (performance)

Mirror PostHog’s split-context pattern so Terminal/Logs do not re-render on every drag frame:

| Context | Hook | Contents |
|---|---|---|
| Actions | `useShellActions()` | open/close/focus/snap/navigate — stable identity |
| Settings | `useShellSettings()` | `shellSettings`, `experience`, `isNarrow` |
| UI flags | `useShellUI()` | palette open, docks, screensaver-equivalent |
| Windows/panes | `useShellWindows()` / `useShellPanes()` | layout state only |

---

## 3. Window / pane JSON schema

Serializable for deep-links and workspace files. Geometry as **percent of viewport** when persisted (PostHog `?windows=` pattern).

```json
{
  "$schema": "https://bashos.dev/schemas/shell-window-v1.json",
  "schemaVersion": 1,
  "windows": [
    {
      "id": "win_01HZX...",
      "appId": "terminal",
      "title": "pty:agent-17",
      "resourceUri": "pty://session/agent-17",
      "path": "/app/terminal/agent-17",
      "zIndex": 3,
      "minimized": false,
      "expanded": false,
      "snapped": false,
      "position": { "xPct": 5, "yPct": 8 },
      "size": { "wPct": 45, "hPct": 50 },
      "sizeConstraints": {
        "min": { "width": 320, "height": 200 },
        "max": { "width": null, "height": null }
      },
      "fixedSize": false,
      "attribution": {
        "actor": "user:amr",
        "runId": "run_01HZY...",
        "sessionId": "sess_01HZY..."
      },
      "appSettingsKey": "terminal",
      "createdAt": "2026-09-15T02:00:00Z"
    }
  ]
}
```

### 3.1 TypeScript shape (normative for implementers)

```ts
type Experience = 'os' | 'tiling' | 'plain'
type SnapEdge = 'left' | 'right' | false
type NavIntent = 'replace' | 'new' | 'focus' | 'sideBySide'

interface ShellWindow {
  id: string
  appId: AppId
  title: string
  resourceUri: string          // pty:// | agent:// | file:// | log:// | inbox:// | settings://
  path: string                 // deep-link path
  zIndex: number
  minimized: boolean
  expanded: boolean
  snapped: SnapEdge
  position: { xPct: number; yPct: number }
  size: { wPct: number; hPct: number }
  sizeConstraints: {
    min: { width: number; height: number }
    max: { width: number | null; height: number | null }
  }
  fixedSize: boolean
  attribution: {
    actor: string
    runId?: string
    sessionId?: string
  }
  appSettingsKey: string
  createdAt: string            // ISO-8601
}

interface ShellSettings {
  experience: Experience
  colorMode: 'light' | 'dark' | 'system'
  density: 'comfortable' | 'compact'
  performanceBoost: boolean    // reduce motion / wallpaper cost
  reduceTransparency: boolean
  keymapProfile: 'default' | string
  wallpaperId?: string         // Could — optional theme pack
}

interface AppSetting {
  size?: {
    min: { width: number; height: number }
    max?: { width: number; height: number }
    fixed?: boolean
  }
  position?: { center?: boolean }
  modal?: { type: 'standard' | 'side' | 'floating' }
  closeOnEscape?: boolean
  toolbar?: boolean
  hideTitle?: boolean
}
```

**Tiling mode** uses a binary tree of panes instead of free `position`/`size`; persistence schema v1 may store `layoutTree` alongside or instead of `windows` (Phase 2).

---

## 4. Navigation intents

PostHog handbook claimed `newWindow` / focus / replace; live tour confirmed **standard nav replaces** the active window; append-on-`newWindow` was **not** verified live; code lacked an explicit `newWindow` branch in `updatePages` (research brief). bashOS implements intents in the reducer with tests.

| Intent | Behavior | Trigger examples |
|---|---|---|
| `replace` | Mutate focused window’s `appId` / `resourceUri` / `path`; preserve others | Default in-app link, address bar submit |
| `new` | **Append** a window/pane; bring to front | Pinned icon open, “Open in new pane”, palette “new …” |
| `focus` | If same `path` or `(appId, resourceUri)` exists → bringToFront only; no duplicate | Second click on same agent, taskbar entry |
| `sideBySide` | Phase 2: snap/split focused + open target on opposite edge | Context menu “Open side by side” |

```ts
function navigate(target: { path: string; appId: AppId; resourceUri: string }, intent: NavIntent) {
  // Pseudocode — normative behavior
  const existing = findByPathOrResource(target)
  if (intent === 'focus' || (intent === 'replace' && existing)) {
    if (existing) return bringToFront(existing.id)
  }
  if (intent === 'new' || intent === 'sideBySide') {
    return appendWindow(target, intent === 'sideBySide' ? { snap: 'opposite' } : {})
  }
  return replaceFocused(target)  // intent === 'replace'
}
```

**Hard rule:** Documented intent ⇒ tested consumer. No docs-only flags.

---

## 5. App Template API

### 5.1 Contract

```ts
type AppId =
  | 'terminal'
  | 'agent'
  | 'editor'
  | 'files'
  | 'logs'
  | 'settings'
  | 'inbox'

interface AppTemplateSlots {
  title: ReactNode | string
  toolbar?: ReactNode
  sidebar?: ReactNode
  main: ReactNode
  status?: ReactNode
}

interface AppModule {
  id: AppId
  displayName: string
  icon: string
  defaultSettings: AppSetting
  canOpen: (resourceUri: string) => boolean
  render: (props: {
    windowId: string
    resourceUri: string
    attribution: ShellWindow['attribution']
  }) => AppTemplateSlots
}
```

Shared chrome (HeaderBar analogue): back (if in-window history), address/resource URI, search affordance, window actions. Live PostHog apps (Explorer, Reader, Presentation, changelog timeline) validate that **one chrome + many content shells** scales; bashOS maps metaphors to operator tools (below).

### 5.2 Initial apps

| AppId | Metaphor | Binds to (resource) | Notes |
|---|---|---|---|
| `terminal` | PTY / tmux pane | `pty://session/{id}` | Primary; **Proposal:** OpenCode PTY |
| `agent` | Transcript + tool calls | `agent://run/{id}` | **Proposal:** LangGraph run stream |
| `editor` | Buffer / diff / markdown | `file://{workspace-path}` | Specs + agent-editable buffers |
| `files` | Workspace FS explorer | `files://{root}` | Artifacts + workspace tree |
| `logs` | Trace / structured log | `log://run/{id}` | Attribution & debug |
| `settings` | Display / shell / model | `settings://shell` | Includes `experience` toggle |
| `inbox` | Approvals / human input | `inbox://queue` | Irreversible act gates — **Must** |

Registry: `appSettings: Record<AppId, AppSetting>` keyed by `appId`, not marketing route.

---

## 6. Keyboard map

Ignore when focus is in `INPUT` / `TEXTAREA` / contenteditable / terminal xterm (terminal owns keys when focused).

| Shortcut | Action | Mode |
|---|---|---|
| `Ctrl/Cmd+K` or `/` | Open Command Palette | all |
| `Esc` | Close palette / modal / cancel | all |
| `Ctrl/Cmd+Shift+T` | New Terminal | os, tiling |
| `Ctrl/Cmd+Shift+A` | New / focus Agent for current run | os, tiling |
| `Ctrl/Cmd+Shift+I` | Focus Inbox | all |
| `Ctrl/Cmd+W` | Close focused window/pane | os, tiling |
| `Ctrl/Cmd+Shift+W` | Close all | os, tiling |
| `Ctrl/Cmd+`` ` | Cycle next window/pane | os, tiling |
| `Ctrl/Cmd+Shift+`` ` | Cycle previous | os, tiling |
| `Ctrl/Cmd+← / →` | Snap left / right (**Should**; Phase 2 if drag unverified) | os |
| `Ctrl/Cmd+↑` | Expand / restore | os |
| `Ctrl/Cmd+↓` | Minimize | os |
| `Ctrl/Cmd+,` | Open Settings | all |
| `?` | Shortcuts cheatsheet | all |

PostHog live: `/` opens search, Esc closes — retained. Snap/minimize shortcuts follow PostHog docs; live tour only verified maximize/restore — implement expand first in MVP.

---

## 7. Workspace deep-links

| Form | Example | Behavior |
|---|---|---|
| Single app | `/app/agent/run_01HZY` | `plain` or single focused window |
| Layout restore | `/?windows=<url-encoded JSON>` | Hydrate `ShellWindow[]` from schema v1 |
| Workspace file | `bashos://workspace/{id}` or local `.bashos/workspace.json` | **Proposal:** load layout + resource bindings |
| Experience override | `?experience=plain` | Force mode for automation / embeds |

Shareable layouts are for reproducing multi-agent setups (operator demos), not SEO.

---

## 8. Runtime integration — **Proposal**

No fake existing APIs. Until kernel/OpenCode expose stable contracts, the shell uses adapters behind interfaces:

```ts
/** Proposal — not claimed as shipping API */
interface KernelBridge {
  listRuns(): Promise<RunSummary[]>
  subscribeRun(runId: string): AsyncIterable<RunEvent>
  listApprovals(): Promise<Approval[]>
  resolveApproval(id: string, decision: 'allow' | 'deny', note?: string): Promise<void>
}

/** Proposal */
interface OpenCodeBridge {
  openPty(sessionId: string): PtyHandle
  listWorkspace(path: string): Promise<FsEntry[]>
  readFile(path: string): Promise<Uint8Array | string>
  watchLogs(runId: string): AsyncIterable<LogLine>
}
```

| Concern | Proposal |
|---|---|
| Transport | WebSocket or SSE from local bashOS daemon to web shell |
| Auth | Same-machine first; token for remote later |
| Attribution | Every bridge event carries `actor` + `runId` into window metadata |
| Approvals | Kernel emits approval → Inbox app; UI cannot bypass policy |
| Model list | Settings reads model catalog from kernel; UI remains vendor-agnostic |

Mark any stub with `// Proposal` and feature-flag off by default until Phase 1 bridge spike lands.

---

## 9. Stack recommendation

| Concern | Recommendation | Justification |
|---|---|---|
| App framework | **Vite + React 18** (or 19) | Operator SPA; no Gatsby SSG need; fast HMR for shell iteration |
| Optional SSR | Next only if public docs share the shell later | Avoid premature SSG complexity |
| Styling | Tailwind + `data-experience` / `data-color-mode` | Matches PostHog token approach without CSS-in-JS cost |
| Primitives | Radix UI (menus, dialogs, focus traps) | A11y baseline for chrome |
| Window motion | Phase 0 spike: CSS + pointer events **or** Framer Motion | Live tour did not verify drag/snap cost; prefer lighter path if agent UIs are heavy |
| Terminal | xterm.js | Standard for web PTYs |
| State | React context split (+ optional Zustand for layout tree) | PostHog split-context lesson |
| Search/palette | cmdk or custom over local registry | No Algolia dependency for operator console |
| Test | Playwright (intents, keymap, plain unmount) + Vitest (reducer) | Intent correctness is a Must metric |

**Rejected for MVP:** Gatsby (marketing SSG), Kea (unless already in monorepo), hedgehog-mode packages.

---

## 10. Accessibility, mobile, performance

### 10.1 A11y

- Focus trap in modals and palette; restore focus on close  
- Window chrome: `role="dialog"` or document landmark per window; labeled title  
- `prefers-reduced-motion` ⇒ disable entrance/snap animations; honor `performanceBoost`  
- `plain` mode must be fully usable with keyboard and screen reader (no drag dependency)  
- Inbox approvals: explicit Allow/Deny buttons with confirm for destructive tools  

### 10.2 Mobile / narrow

- `isNarrow` (e.g. `innerWidth < 768`): collapse MenuBar; prefer single pane or force `experience=plain`  
- Do not ship unbroken floating multi-window on small screens (PostHog simplifies taskbar; boring consumer was drifted — we do not repeat that)  

### 10.3 Performance

- Split contexts (§2.4)  
- Virtualize Agent transcripts and Logs  
- Compositor gate while dragging/resizing (skip wallpaper/expensive panes)  
- Budget: 4 windows interactive on mid-tier laptop; document if Framer fails spike  

---

## 11. Live UI evidence → spec decisions

| Live confirmation | Spec decision |
|---|---|
| Wallpaper + icon rails + fixed taskbar | Optional icons in `os`; MenuBar always on in `os`/`tiling` |
| Rounded panels, scrollbars, close, maximize/restore | Must chrome; expand/restore in Phase 1 |
| Replace-on-standard-nav | Default intent = `replace` |
| Multi-pane reader (handbook/blog) | App templates may use sidebar + main + aux columns |
| `/` search + Esc | Palette global overlay |
| Display Options surface | Settings app owns theme/experience/performance |
| Explorer / slides / changelog density | Validates dense apps; map to Files / Agent report / Logs |
| Drag/resize/snap/minimize unverified | Phase 0 motion spike; don’t block MVP on snap |
| No app.posthog.com | Spec ignores product-app auth; local daemon first |

---

## 12. Open questions (spec-level)

1. Does OpenCode already expose a web-consumable PTY protocol, or does L6 need a new adapter? **Proposal until answered.**  
2. Should tiling be the default for terminal users, with `os` as optional skin? (Product: ROADMAP Phase 2.)  
3. Single shared pane-session protocol between TUI and web shell?  
4. Workspace file format: extend existing bashOS project config or new `.bashos/workspace.json`?  
5. Cost/model StatusBar feeds — which kernel metrics are stable?  

---

*End of SPEC.*
