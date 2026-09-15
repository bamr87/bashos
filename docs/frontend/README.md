# bashOS L6 OS Shell — Frontend Docs

Documentation for an **OS-shell evolution** of the bashOS L6 web/native surface: multi-window / side-by-side / desktop metaphors on top of the existing desktop GUI — preferring IDE / tmux density over marketing nostalgia.

**Repo:** [bamr87/bashos](https://github.com/bamr87/bashos)  
**Prerequisite surface:** [PR #20 — desktop GUI](https://github.com/bamr87/bashos/pull/20) (`bashos gui`) — treat as **current L6 web/native surface** (as proposed/landed in that PR).  
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

**Documentation only** for the OS-shell evolution. The desktop GUI itself is proposed/landed in [PR #20](https://github.com/bamr87/bashos/pull/20). New endpoints or chrome beyond existing `/api/*` + SSE are labeled **Proposal**. OS-shell work assumes **#20 merges first** (or rebase onto it).

**Research refresh (2026-09-15):** PostHog deep interaction pass refined live truth — side-by-side panes, context menus, maximize/close, overlays; free drag/resize unreliable. See [posthog-os-research.md](./posthog-os-research.md) §13. Alignment pass: these docs no longer assume a greenfield L6 stack; they build on #20’s scenes and no-build philosophy.
