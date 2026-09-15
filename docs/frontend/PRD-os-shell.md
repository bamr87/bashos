# PRD: bashOS L6 OS Shell (evolution of desktop GUI)

**Status:** Draft for review — aligned with [PR #20](https://github.com/bamr87/bashos/pull/20) desktop GUI  
**Audience:** bashOS maintainers, L6 implementers  
**Related:** [SPEC-os-shell.md](./SPEC-os-shell.md), [ROADMAP-os-shell.md](./ROADMAP-os-shell.md), [RELATION-TO-DESKTOP.md](./RELATION-TO-DESKTOP.md)  
**Foundation:** [`docs/DESKTOP.md`](../DESKTOP.md), [`docs/DESKTOP-TOUR.md`](../DESKTOP-TOUR.md) (paths when #20 merges)  
**Inspiration:** PostHog.com OS-style site (research brief 2026-09-15) — **inspiration only**; nostalgia optional  

---

## 1. Problem

[PR #20](https://github.com/bamr87/bashos/pull/20) proposes/lands `bashos gui`: a GUI access layer **beside** the terminal, not above it. One page, seven hash-routed scenes (Overview, Console, Commands, Runs, Health, Engine, Settings), same kernel as the CLI, no-build front end.

That **single-scene SPA** is great for one console line of work. Operators still hit friction when multitasking:

| Pain | Consequence |
|---|---|
| Only one scene visible at a time | Console + run detail + Health require hash hopping or extra browser tabs |
| Scene switcher ≠ window list | No durable “what’s open” model for side-by-side work |
| Approvals / policy visibility stay in Health / engine surfaces | Easy to miss when buried behind the active scene |
| Deep links are scene hashes (`#/runs/<id>`) | Strong start; lacks multi-pane layout serialization |
| PostHog-style marketing OS docs often ship incomplete intents | Handbook vs live drift — bashOS must implement consumers, not folklore |

PostHog’s transferable bet (multi-window, dense apps, keyboard-first, side-by-side) addresses **that** multitasking gap. Their brand nostalgia does **not**. bashOS already has the right L6 foundation in #20 — these docs evolve it.

---

## 2. Goals

1. Evolve the **existing** `gui/web` scene system into an L6 **OS shell**: scenes become apps/windows or panes, still bound to the same kernel and `/api/*` + SSE.  
2. Make **navigation intents explicit**: `replace` | `new` | `focus` | `sideBySide`, aligned with #20 hash routing (`#/console`, `#/runs/<id>`). Prefer **side-by-side of existing scenes** over free-floating drag for MVP.  
3. Provide experience modes that **wrap** #20 chrome: e.g. single-scene (today), multi-pane / tiling, optional floating later — each with a real mount consumer.  
4. Extend the **scene builder** pattern already in `app.js` (`scene*()`, `SCENES`) — do not invent a parallel app framework.  
5. Stay **keyboard-first**; baseline = #20 map (⌘K/Ctrl-K palette, composer `/` slash completion); add OS-shell keys carefully without colliding.  
6. Preserve bashOS design goals **and honor #20 refusals/guards** (see §9).  
7. Keep deep links and workspace layouts **serializable** (hash / URL / workspace file) without requiring a history file on disk.

---

## 3. Non-goals

- **Replacing PR #20** or shipping a second L6 web console beside `bashos gui`.  
- **Shell passthrough** (`!` or arbitrary host commands via HTTP).  
- **npm / bundler / web framework as MVP requirement** — Phases 0–2 stay on #20’s one HTML/CSS/JS stack.  
- **Widening tool policy** beyond what Health already renders from the engine allowlist.  
- **Persisting run history** to disk (runs stay in-memory, cap 200, process-lifetime).  
- **Credentials on the wire** or a reasoning loop inside `gui/`.  
- Replicating PostHog marketing whimsy (hedgehog, confetti, MS Paint, WordArt) as MVP features.  
- Replacing the CLI/REPL or TUI; those remain supported L6 surfaces.  
- Claiming new kernel/OpenCode HTTP APIs that #20 does not already expose — extras are **Proposal**.  
- Building a general-purpose window manager for arbitrary websites.  
- SEO marketing SSG as a primary driver.

---

## 4. Jobs to be done (JTBD)

Map jobs onto **existing #20 scenes** becoming apps/windows — not an invented Terminal/Agent/Editor set.

| Actor | Job | Outcome (on #20 foundation) |
|---|---|---|
| Operator | Run a line while watching its run card / detail | **Console** + **Runs** (or `#/runs/<id>`) side-by-side |
| Operator | Check policy / allowlist while a run streams | **Console** + **Health** side-by-side |
| Operator | Inspect engine/doctor without losing console | **Engine** in a second pane; Console stays mounted |
| Operator | Jump to a command or scene quickly | Existing ⌘K/Ctrl-K palette — **extend** (Spotlight analogue), don’t replace |
| Operator | Resume a multi-pane setup | Workspace deep-link / saved layout of scene instances |
| Contributor | Add a surface | New `scene*()` + `SCENES` entry (+ route in `server.py` if needed) — App Template = scene builder |
| Automator / a11y user | Use without multi-pane chrome | Single-scene / `plain` = today’s SPA behavior |
| Mobile / narrow viewport | Still reach Console + Settings | Degraded to single scene (current behavior) |

Future **Docs** / **Files** scenes are **Could** only — not MVP apps that displace the seven.

---

## 5. Success metrics

Metrics are **product intent**, not invented analytics sources.

| Metric | Target (directional) | How measured |
|---|---|---|
| Time to multi-surface session | &lt; 30s from `bashos gui` to Console + Runs (or Health) side-by-side | Manual / Phase 0 spike stopwatch |
| Guard integrity | All #20 refusals still hold (no `!`, no secrets, CSP, token, bind) | Existing GUI / capture tests + regression checklist |
| Intent correctness | `new` appends scene instance; `focus` no duplicate; `replace` = current hash nav | Unit + e2e on nav reducer |
| Keyboard coverage | #20 baseline + OS-shell Must keys documented and non-colliding with composer `/` and ⌘K | Keymap contract tests |
| No-build constraint | Phases 0–2: still one HTML + CSS + ES module; capture_desktop still works | Spike exit + `tools/capture_desktop.py` |
| Perf budget | Two-pane layout stays interactive; no npm required | Phase 1 manual; optional later instrumentation |

---

## 6. Experience modes

| Mode | Metaphor | Relation to #20 | Default when |
|---|---|---|---|
| `single` (today) | One scene, sidebar + top bar | **Current** `gui/web` behavior | Default until multi-pane ships; narrow viewports |
| `tiling` / multi-pane | IDE / tmux-like splits of **scenes** | Scene instances in panes; sidebar may become window list | Power users; Phase 1–2 |
| `os` (Could / Phase 3) | Floating windows over a desktop | Optional chrome around same scenes | Preference after tiling is solid |
| `plain` | Minimal chrome | Unmount multi-pane / desktop chrome; one scene content | Automation, screenshots, a11y |

**Lesson from PostHog:** docs-only “boring” mode with no consumer. bashOS **must** gate chrome on a real setting.

```
if experience == plain or single:
  render current #20 scene shell (hash → one scene)
else if experience == tiling:
  render MultiPane(sceneInstances)
else:
  render OsDesktop(sceneWindows)  # Phase 3+
```

---

## 7. MoSCoW features

### Must

- **Evolve #20 chrome** — sidebar / top bar / palette remain; add window/pane affordances around **existing scenes**  
- **Keep #20 guards and refusals** normative (see §9 and SPEC security table)  
- **Side-by-side of existing scenes** (e.g. Console ‖ Runs, Console ‖ Health) + focus switching; close one → single  
- Navigation intents: `replace` (current hash nav) \| `new` \| `focus` \| `sideBySide` — implemented, not docs-only  
- Context menus / palette actions: Open side-by-side, Open in new pane, Open in new browser tab, Copy hash/link  
- Documented keyboard map: **#20 baseline first**; OS-shell additions without colliding with composer `/` or ⌘K  
- Command palette remains global overlay (extend items; do not make it a managed window)  
- App/scene template = extend `scene*()` + `SCENES`; initial apps = **the seven scenes**  
- Deep-linkable hashes per scene / run (`#/runs/<id>`) preserved and extended for multi-pane  
- Attribution fields on window/scene-instance metadata when a run is bound  
- **Must not** break no-build constraint without an **explicit later phase** decision  

### Should

- Window / scene-instance **list** (taskbar analogue) — what’s open, focus, close  
- Shareable workspace layout serialization (`?windows=` or workspace JSON) of scene ids + resources  
- Palette depth: scenes, recent runs, commands registry, dry-run toggle  
- Narrow viewport → force `single`  
- Status affordances already in #20 project card / top bar — extend carefully from `/api/state`  

### Could

- Free-floating **drag / resize** (PostHog live: unreliable; after side-by-side)  
- Desktop icons = pinned scenes / slash commands  
- Future scenes: Docs, Files (only if they fit no-build + same API discipline)  
- Nostalgic theme pack (optional skin; off by default)  
- Minimize + restore **only if** end-to-end restore works  
- React/Vite migration (**Phase 3+** explicit tradeoff — rewrite capture tooling; not default)  

### Won’t (near term)

- Replacing #20 or prescribing Vite/Next as the default stack  
- Shell passthrough, wider policy, credential echo, on-disk run history, reasoning in `gui/`  
- Invented MVP app set (Terminal/Agent/Editor/Files…) that **ignores** the seven scenes  
- Fake minimize / Trash / Bookmarks metaphors  
- Hedgehog / confetti / custom face cursors as product surface  
- Replacing SSH or TUI paths  

---

## 8. PostHog → bashOS concept map

| PostHog | bashOS (on #20) |
|---|---|
| `AppWindow` | **Scene instance** (window/pane) bound to a scene id + optional resource (`#/runs/<id>`) |
| App route / content | Existing `scene*()` builders in `gui/web/app.js` |
| `siteSettings` | Extend #20 prefs / Settings scene (`shellSettings`: experience, theme already exists) |
| Desktop icons | Pinned scenes / commands (**Could**) |
| `?windows=` shareable desktop | Saved layout of scene instances |
| Spotlight | **Existing ⌘K/Ctrl-K palette** — extend |
| TaskBarMenu | Sidebar scene switcher → **window list** + status (evolve, don’t discard) |
| Ask Max overlay | Console composer / agent path already in kernel — not a second chat product |
| Boring mode (docs drift) | `single` / `plain` — **must** match real chrome unmount |
| `newWindow` (docs vs code) | Explicit `NavIntent.new` that appends a scene instance |
| Gatsby / React / Framer | **Inspiration only** — #20 stack for Phases 0–2 |

**Transferable bets:** windowed multitasking, dense apps, keyboard-first, explicit intents, shareable layouts, plain/single fallback.  
**Skip for MVP:** brand gimmicks; greenfield SPA frameworks.

---

## 9. Constraints & principles

1. **#20 is today’s L6 surface** — OS-shell docs propose evolution; cite “as proposed/landed in PR #20.”  
2. **Intent over folklore** — documented flag ⇒ reducer consumer.  
3. **CLI remains canonical** — GUI stays beside the terminal.  
4. **Proposals labeled** — existing `/api/*` + SSE are real in #20; new endpoints are Proposal.  
5. **Density over decoration.**  
6. **Security posture (normative — copy from DESKTOP.md):**  
   - No shell passthrough (`!` → 403)  
   - No wider tool policy (Health renders allowlist only)  
   - No credentials on the wire  
   - No history file (runs in-memory, cap 200)  
   - No reasoning loop in `gui/`  
   - Bind `127.0.0.1`, per-process token, Host/Origin checks, CSP `default-src 'self'`, input caps  
7. **Model-agnostic** — Settings/model from runtime state, not hard-coded vendor UI.  
8. **No-build until Phase 3+ explicit tradeoff.**

---

## 10. Out-of-scope decisions deferred to SPEC / ROADMAP

- Floating-first vs tiling-first — ROADMAP: side-by-side first on current scenes  
- Whether any new `/api/*` is needed for layouts — default: client-only layout state  
- Framework migration — Phase 3+ only, with capture_desktop rewrite cost  
- Dependency: **merge PR #20 first** (or rebase this work onto it)

---

## 11. Live evidence (PostHog.com browser tour) — inspiration only

**Scope:** Public marketing site only (`posthog.com`). Did **not** use `app.posthog.com` or login.  
**Date:** 2026-09-15.  
**Caveat:** Evidence informs multitasking UX patterns. It does **not** authorize replacing #20’s stack or security model.

### Confirmed live

| Observation | Implication for bashOS |
|---|---|
| Desktop wallpaper + icon catalogs | Optional pinned scenes/commands later; not MVP |
| Fixed top taskbar | Evolve #20 top bar / sidebar; don’t discard |
| Routes inside AppWindow panels; maximize/close | Window chrome around **scenes** |
| Standard navigation **replaces** active window | Matches #20 hash `replace`; still need `new` / `sideBySide` |
| `/` opens search; Esc closes | #20 already uses ⌘K for palette; composer owns `/` — do not blindly copy PostHog `/` |
| Display Options / themes | Settings scene + theme toggle already in #20 |

### Deep interaction pass (2026-09-15) — refined live truth

Full detail: research brief §13.

| Observation | bashOS stance |
|---|---|
| Context menu: new window, side-by-side, new tab, copy link | Must intents + browser-tab fallback |
| Maximize / restore / close; side-by-side + focus | Must; **prefer side-by-side over free drag** |
| Free drag/resize unreliable; minimize not found | Defer |
| Ctrl+K failed on PostHog; `/` worked | bashOS #20 already uses ⌘K successfully — keep #20 baseline |
| Boring mode with no visible change | `single`/`plain` need real consumers |

### URLs toured (evidence set)

`/`, `/self-driving`, `/pricing`, `/products`, `/docs`, `/merch`, `/trash`, `/changelog`, `/display-options`, `/blog/why-os`, handbook technical-architecture, handbook presentations; plus deep interaction on desktop icons, context menus, side-by-side, overlays, and keyboard map.

---

*End of PRD (aligned with PR #20 desktop GUI).*
