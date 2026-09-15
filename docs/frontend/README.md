# bashOS L6 OS Shell — Frontend Docs

Documentation for an **OS-shell evolution** of the bashOS L6 web/native surface: multi-window / side-by-side / desktop metaphors on top of the existing desktop GUI — preferring IDE / tmux density over marketing nostalgia.

**Repo:** [bamr87/bashos](https://github.com/bamr87/bashos)  
**Surface:** `bashos gui` — [`../DESKTOP.md`](../DESKTOP.md), [`../DESKTOP-TOUR.md`](../DESKTOP-TOUR.md). These docs and that surface now ship together in [PR #20](https://github.com/bamr87/bashos/pull/20); **Phase 0 of the roadmap is implemented**.  
**Canonical desktop docs (when #20 merges):** [`../DESKTOP.md`](../DESKTOP.md), [`../DESKTOP-TOUR.md`](../DESKTOP-TOUR.md)  
**Relationship one-pager:** [RELATION-TO-DESKTOP.md](./RELATION-TO-DESKTOP.md)  
**Stack today (#20):** `src/bashos/gui/` — asyncio HTTP + routes/SSE + in-memory runs + optional pywebview; front end `gui/web/` = one HTML + one CSS + one ES module (**no npm, no bundler, no web framework**). Seven hash-routed scenes over the same kernel as the CLI (`build_kernel(...)`).

## Why this exists

PR #20 already ships a real L6 GUI **beside** the terminal: Overview, Console, Commands, Runs, Health, Engine, Settings; command palette ⌘K/Ctrl-K; slash completion; light/dark themes; sidebar chrome; dry-run = CLI `-n`.

That single-scene SPA is excellent for one console line of work. Operator **multitasking** (console + run detail + health + docs at once) still hits tab/scene friction. These docs adapt PostHog window/taskbar/Spotlight patterns to **evolve** that foundation — not replace it with a greenfield Vite/Next console.

Research basis: [posthog-os-research.md](./posthog-os-research.md) (PostHog.com public sources + live tour, 2026-09-15). Inspiration only; bashOS security and no-build philosophy win over marketing OS folklore.

## Documents

| Doc | Purpose |
|---|---|
| [RELATION-TO-DESKTOP.md](./RELATION-TO-DESKTOP.md) | #20 vs this folder — dependency and non-contradiction rule |
| [PRD-os-shell.md](./PRD-os-shell.md) | Product requirements: problem reframed on #20 scenes, JTBD, MoSCoW, PostHog→bashOS map |
| [SPEC-os-shell.md](./SPEC-os-shell.md) | Technical spec: evolve `gui/web`, window schema on scene ids, intents, stack Phases 0–2, security guards |
| [ROADMAP-os-shell.md](./ROADMAP-os-shell.md) | Prerequisite #20 merge; Phases 0–3; risks |

## Design goals (from bashOS + PR #20)

1. **Agent as system service** — shell surfaces bind to runtime sessions / runs, not ephemeral chat widgets  
2. **Human approval for irreversible acts** — policy stays in the engine; GUI never widens it  
3. **Attributable actions** — every window/scene instance carries actor + run identity where applicable  
4. **Immutable base OS** — shell is L6 chrome; it does not mutate the base image  
5. **Model-agnostic** — UI never hard-codes a single LLM vendor  
6. **Honor PR #20 refusals and guards** — no shell passthrough (`!` → 403); no wider tool policy; no credentials on the wire; no history file (runs in-memory, cap 200); no reasoning loop in `gui/`; bind `127.0.0.1`, per-process token, Host/Origin checks, CSP `default-src 'self'`, input caps  

## Status

**Phase 0 is implemented** in PR #20, which now carries both these docs and the
code they describe:

| Capability | State |
|---|---|
| Experiences `single` \| `tiling` \| `os` \| `plain` (each with a real consumer) | **Landed** — Settings → Workspace, or the palette |
| Nav intents `replace` \| `new` \| `focus` \| `sideBySide` | **Landed** — `gui/web/shell.js`, 36 unit tests |
| Pane chrome: focus, split, maximize/restore, close | **Landed** |
| Desktop: floating windows, drag, resize, edge snapping, z-order | **Landed** — phase 3, ahead of schedule |
| Desktop icons, taskbar/window list, minimize **with** restore | **Landed** |
| Arrange: tile and cascade | **Landed** |
| Workspace layouts: `?windows=` share + per-tab restore, schema v1 | **Landed** — client-only, no new endpoint |
| Context menus: open, side by side, new browser tab, copy link | **Landed** |
| Palette depth: scenes, commands, recent runs, windows, arrange, experience | **Landed** |
| Keymap: `⌘K`, `⌘\` cycle, `⌘W` close (native window) | **Landed** |
| Narrow viewport → single; Console singleton | **Landed** |
| Nostalgia theme pack; full a11y audit; remote auth | **Not built** — see ROADMAP |
| React/Vite migration | **Rejected** — never needed; still no npm |

No new server endpoints were needed: layout state is client-only, exactly as
§8.2 of the SPEC proposed. Every guard and refusal is unchanged.

**Research refresh (2026-09-15):** PostHog deep interaction pass refined live truth — side-by-side panes, context menus, maximize/close, overlays; free drag/resize unreliable. See [posthog-os-research.md](./posthog-os-research.md) §13. Alignment pass: these docs no longer assume a greenfield L6 stack; they build on #20’s scenes and no-build philosophy.
