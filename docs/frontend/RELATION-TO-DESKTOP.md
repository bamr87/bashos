# Relation: desktop GUI (PR #20) ↔ OS-shell evolution (this folder)

**Audience:** Anyone reading these OS-shell docs before or after the desktop GUI lands.  
**Source of truth for “today”:** [PR #20](https://github.com/bamr87/bashos/pull/20) (`claude/desktop-gui-frontend-ccib8b`) — `bashos gui`.  
**This folder:** Proposals for **evolving** that surface toward multi-window / side-by-side / desktop metaphors inspired by PostHog research — not a greenfield L6 rewrite.

| | PR #20 — desktop GUI | This PR — OS-shell docs |
|---|---|---|
| Status | Open feature PR — now carries both | Merged into it; Phase 0 implemented |
| Command | `bashos gui` | N/A (docs only until implemented on top of #20) |
| Code | `src/bashos/gui/` + `gui/web/` (one HTML + CSS + ES module) | Proposes changes to that stack |
| Surface | Seven hash-routed **scenes**, sidebar chrome, ⌘K palette | Treat scenes as **apps/windows**; add chrome, side-by-side, layouts |
| Docs | [`docs/DESKTOP.md`](../DESKTOP.md), [`docs/DESKTOP-TOUR.md`](../DESKTOP-TOUR.md) (paths when #20 merges) | [`README.md`](./README.md), PRD / SPEC / ROADMAP here |
| Stack philosophy | **No npm, no bundler, no web framework** | Phases 0–2 **stay** on that stack; framework migration only Phase 3+ tradeoff |
| Security | Normative refusals & guards (see DESKTOP.md) | OS-shell **must preserve** them — never widen policy or add shell passthrough |

## Dependency — resolved

The dependency was resolved by merging **this** documentation into PR #20, so the docs and the surface they describe review and ship together. Phase 0 of the roadmap is implemented there; desktop paths below are live, not proposed.

## One-line rule

**Extend `gui/web` scene system; do not invent a parallel Vite/Next console that contradicts #20.**
