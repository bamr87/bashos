# PRD: bashOS L6 OS Shell

**Status:** Draft for review  
**Audience:** bashOS maintainers, L6 implementers  
**Related:** [SPEC-os-shell.md](./SPEC-os-shell.md), [ROADMAP-os-shell.md](./ROADMAP-os-shell.md)  
**Inspiration:** PostHog.com OS-style site (research brief 2026-09-15) — patterns adapted; nostalgia optional  

---

## 1. Problem

bashOS is a terminal-first AI runtime. Operators already juggle:

- One or more agent runs (transcripts, tool calls, costs)
- PTYs / shells attached to those runs
- Specs, diffs, and editable buffers
- Workspace files and artifacts
- Approval queues for irreversible actions
- Logs / traces for attribution and debug

Today’s L6 surface is primarily **CLI/REPL + slash commands**. That works for a single linear session. It breaks down when:

| Pain | Consequence |
|---|---|
| Tab / pane explosion across terminals and browsers | Lost context; no shareable layout |
| Approvals buried in scrollback | Missed or delayed irreversible gates |
| No first-class multitasking model | Users invent ad-hoc tmux + browser stacks |
| Deep links point at “the CLI,” not a concrete pane | Hard to reproduce multi-agent setups |
| Docs and marketing sites that *look* like OS shells often ship incomplete intents | Handbook says `newWindow` / boring mode; code drifts — operators cannot rely on behavior |

PostHog’s product bet (multi-window, dense apps, keyboard-first) maps cleanly to this operational problem. Their brand nostalgia does **not** — bashOS users already live in IDE/tmux mental models.

---

## 2. Goals

1. Ship an L6 **web shell** that hosts multiple apps as windows or panes bound to runtime sessions.  
2. Make **navigation intents explicit**: `replace` | `new` | `focus` (| `sideBySide` in Phase 2). Implement consumers, not docs-only flags.  
3. Provide **three experience modes**: `os` | `tiling` | `plain` — each with a real shell consumer that mounts or unmounts chrome.  
4. Expose an **app template API** so Terminal, Agent, Editor, Files, Logs, Settings, Inbox ship as first-class surfaces.  
5. Stay **keyboard-first**; mouse polish is secondary.  
6. Preserve bashOS design goals: approval gates, attribution, immutable base, model-agnostic UI.  
7. Keep deep links and workspace layouts **serializable** (URL and/or workspace file).

---

## 3. Non-goals

- Replicating PostHog marketing whimsy (hedgehog, confetti, MS Paint, WordArt, custom face cursors) as MVP features.  
- Replacing the CLI/REPL or TUI; those remain supported L6 surfaces.  
- Claiming existing kernel/OpenCode HTTP APIs that are not yet specified — integrations are **proposals** (see SPEC).  
- Building a general-purpose window manager for arbitrary websites.  
- SEO marketing SSG as a primary driver (bashOS shell is an operator console, not a brochure site).  
- Account-gated personalization in Phase 0–1 (local/workspace settings only).

---

## 4. Jobs to be done (JTBD)

| Actor | Job | Outcome |
|---|---|---|
| Operator | Run an agent while watching its PTY and logs | Side-by-side Agent + Terminal + Logs without losing either |
| Operator | Approve or reject an irreversible action | Inbox surfaces the gate with actor, tool, and blast radius |
| Operator | Resume yesterday’s multi-pane setup | Open a workspace deep-link / saved layout |
| Operator | Find a command, skill, file, or agent | Command palette (`Ctrl+K`) — not a marketing Spotlight clone |
| Contributor | Add a new L6 app | Implement against App Template API; register `appId` + chrome slots |
| Automator / a11y user | Use bashOS without window chrome | `plain` mode: linear console, no drag/snap |
| Mobile / narrow viewport | Still reach Agent + Inbox | Degraded layout or forced `plain` / single-pane |

---

## 5. Success metrics

Metrics are **product intent**, not invented analytics sources.

| Metric | Target (directional) | How measured |
|---|---|---|
| Time to multi-surface session | &lt; 30s from shell load to Terminal + Agent open | Manual / Phase 0 spike stopwatch; later: local telemetry opt-in |
| Approval visibility | 100% of irreversible gates appear in Inbox when shell is connected | Integration test against approval bus (**Proposal**) |
| Intent correctness | `new` always appends; `focus` never duplicates; `replace` only mutates focused | Unit + e2e tests on nav reducer |
| Keyboard coverage | All Must keymap entries documented and testable | Keymap contract tests |
| Plain mode | Shell chrome fully unmounted; content still deep-linkable | E2E: `experience=plain` |
| Perf budget | Drag/resize of 4 windows stays interactive on mid-tier laptop | Frame-time check in Phase 2; `performanceBoost` equivalent |

---

## 6. Experience modes

| Mode | Metaphor | Chrome | Default when |
|---|---|---|---|
| `os` | Floating windows over a desktop | Menu/status bar, optional icons, window chrome, z-order | Desktop / wide viewport; preference |
| `tiling` | IDE / tmux-like splits | Menu/status bar, pane borders, no free drag | Power users; Phase 2 default option |
| `plain` | Traditional single-pane console | Minimal header; no windows/desktop | Mobile, automation, screenshots, a11y preference |

**Lesson from PostHog:** handbook documented `experience: 'posthog' | 'boring'`, but live `SiteSettings` lacked a reader for boring mode (only a Spotlight writer). bashOS **must** gate shell mount on `shellSettings.experience` with an actual consumer.

```
if experience == plain:
  render PlainConsole(route)
else if experience == tiling:
  render TilingLayout(panes)
else:
  render OsDesktop(windows)
```

---

## 7. MoSCoW features

### Must

- Multi-window **or** multi-pane with focus, z-order (os) / layout tree (tiling), minimize (os), close  
- Navigation intents: `replace` | `new` | `focus` — all implemented in the nav reducer  
- Documented, testable keyboard map (core set; see SPEC)  
- App Template API: chrome slots `title`, `toolbar`, `sidebar`, `main`, `status`  
- Initial apps: **Terminal**, **Agent**, **Editor**, **Files**, **Logs/trace**, **Settings**, **Inbox/approvals**  
- Deep-linkable URLs per window/pane content  
- `plain` mode without window chrome  
- Attribution fields on window/session metadata (actor, runId)  
- Inbox as the human-approval surface for irreversible acts  

### Should

- Snap / split (`sideBySide`) and expand/minimize shortcuts  
- Shareable workspace layout serialization (`?windows=` or workspace JSON)  
- Command palette over agents, skills, files, slash commands  
- Per-app min/max size and modal policies (`appSettings[appId]`)  
- Narrow / mobile fallback (simplify chrome or force `plain`)  
- Split React (or equivalent) contexts so drag does not re-render Terminal/Logs  
- Status bar: host, agent count, model id, session cost (**Proposal:** fed by kernel)  

### Could

- Nostalgic theme pack (optional skin; off by default)  
- In-window back/forward history  
- Animated open-from-icon origins  
- Screensaver / fun mode (gated)  
- Presentation-style run report decks  
- Media-style run replay player  

### Won’t (near term)

- Hedgehog / confetti / custom face cursors as product surface  
- Merch / marketing Explorer metaphors  
- Replacing SSH or TUI paths  

---

## 8. PostHog → bashOS concept map

| PostHog | bashOS |
|---|---|
| `AppWindow` | `ShellWindow` bound to a **pane session** (PTY, agent run, file URI, URL) |
| `appSettings[route]` | `appSettings[appId]` + resource URI |
| `siteSettings` | `shellSettings` (theme, keymap, `experience`, density, performanceBoost) |
| Desktop icons | Pinned agents / skills / workspaces |
| `?windows=` shareable desktop | Saved workspace layouts |
| Inbox (Outlook forums) | Notification / human-input / **approvals** queue |
| Explorer | Workspace FS + artifact browser |
| MediaPlayer | Run replay / trace viewer (**Could**) |
| Presentation | Structured run-report decks (**Could**) |
| Editor | Markdown/spec + agent-editable buffers |
| Spotlight (Algolia) | Command palette (local index + runtime registry) |
| Ask Max overlay | Agent app / optional always-on dock |
| TaskBarMenu | MenuBar + StatusBar (host, agents, model, cost) |
| Boring mode (docs drift) | `plain` — **must** unmount shell |
| `newWindow` (docs vs code) | Explicit `NavIntent.new` that **appends** |
| Framer-heavy chrome | Prefer lighter drag if beside heavy agent UIs; see SPEC stack |
| Gatsby SSG | Vite or Next operator console; wrap-at-root pattern kept |

**Transferable bets:** windowed multitasking, dense apps, keyboard-first, explicit intents, shareable layouts, plain fallback.  
**Optional later:** nostalgia skins.  
**Skip for MVP:** brand gimmicks that do not serve agent workflows.

---

## 9. Constraints & principles

1. **Intent over folklore** — if a flag is documented, a reducer must honor it.  
2. **CLI remains canonical** — web shell is additive L6.  
3. **Proposals labeled** — no invented kernel endpoints.  
4. **Density over decoration** — apps look like tools (tables, sidebars, transcripts), not heroes.  
5. **Security posture** — shell never bypasses approval gates; irreversible actions require Inbox confirmation when policy says so.  
6. **Model-agnostic** — Settings shows model as data from runtime, not hard-coded vendor UI.

---

## 10. Out-of-scope decisions deferred to SPEC / ROADMAP

- Exact SPA framework (Vite+React vs Next) — SPEC recommends with justification  
- Floating-first vs tiling-first default — ROADMAP Phase 1 = floating MVP; Phase 2 = tiling  
- Websocket protocol to LangGraph / OpenCode — **Proposal** surfaces only  
- Whether TUI and web shell share a pane-session protocol — open question  

---

*End of PRD.*

---

## 11. Live evidence (PostHog.com browser tour)

**Scope:** Public marketing site only (`posthog.com`). Did **not** use `app.posthog.com` or login.  
**Date:** 2026-09-15 (same research window as brief).

### Confirmed live

| Observation | Implication for bashOS |
|---|---|
| Desktop wallpaper + left/right icon catalogs (Home, Self-driving, Context warehouse, Pricing, Docs, Demo; About, Changelog, Handbook, Store, Careers, Trash) | Icon rail as pinned entry points is viable; map to agents/skills/workspaces, not merch |
| Fixed top taskbar | MenuBar/StatusBar should be persistent chrome in `os` / `tiling` |
| Routes render inside AppWindow panels: rounded chrome, scrollbars, close + maximize/restore (**maximize verified**) | Window chrome + expand/restore are real; include in Must |
| Standard navigation **replaces** the active window | Matches “replace focused” default; bashOS must still implement explicit `new` / `focus` |
| Blog / handbook show multi-pane reader (sidebar + article + jump panel) | Reader/dense multi-column template informs Editor/Docs-like apps |
| `/` opens centered global search; Esc closes | Command palette as global overlay (not a managed window) is proven UX |
| Display Options: System/Light/Dark, scrollbars, cursors, wallpaper, screensaver preview, transparency, hedgehog | Settings app pattern; hedgehog/cursors → Could / fun pack only |
| Screensaver preview works; click exits; wallpaper changeable | Personalization via `shellSettings` is fine; keep off critical path |
| Visible apps: merch/File Explorer, trash, docs hub, blog reader, handbook, changelog spreadsheet/timeline, product carousel, presentation/slides, product detail | App-template diversity works; prefer Terminal/Agent/Files/Logs metaphors for bashOS |

### Not independently verified live

| Claim (docs / code) | Live status | bashOS stance |
|---|---|---|
| Drag / resize / snap / minimize | Not verified in tour (only maximize/restore + docs/code) | Spec them; spike in Phase 0 before committing Framer-heavy path |
| `experience: boring` unmounts desktop | Not observed as working consumer | Implement `plain` with a real unmount gate |
| `newWindow` appends a second content window | Standard nav replaces; append not confirmed from tour | Spec + test `NavIntent.new` → append explicitly |
| Mobile boring auto-switch | Not toured | Narrow → simplify or force `plain` |

### URLs toured (evidence set)

`/`, `/self-driving`, `/pricing`, `/products`, `/docs`, `/merch`, `/trash`, `/changelog`, `/display-options`, `/blog/why-os`, handbook technical-architecture, handbook presentations.

---

*End of PRD (incl. live evidence).*
