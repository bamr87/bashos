# ROADMAP: bashOS L6 OS Shell (on desktop GUI)

**Status:** Phases 0–2 complete and Phase 3's windowing delivered — see "What landed"  
**Related:** [PRD-os-shell.md](./PRD-os-shell.md), [SPEC-os-shell.md](./SPEC-os-shell.md), [RELATION-TO-DESKTOP.md](./RELATION-TO-DESKTOP.md)  
**Prerequisite:** Merge [PR #20](https://github.com/bamr87/bashos/pull/20) (`bashos gui`) — or rebase OS-shell implementation onto that branch. Desktop docs: [`DESKTOP.md`](../DESKTOP.md), [`DESKTOP-TOUR.md`](../DESKTOP-TOUR.md) when present.  
**Evidence note:** PostHog live pass = inspiration for side-by-side / menus; stack and guards come from #20.

---

## What landed (2026-09-15)

<<<<<<< Updated upstream
The prerequisite and Phase 0 are **done**, in the same PR as the desktop GUI — these docs were merged into that branch rather than waiting on it.

| Phase 0 deliverable | Where |
|---|---|
| Layout state for two scene instances | `gui/web/shell.js` — pure reducer, no DOM |
| Intents `replace` \| `new` \| `focus` \| `sideBySide` | same, 19 unit tests in `tests/shell.test.mjs` (run by `pytest -q` through `tests/test_shell.py`) |
| Scene-as-window chrome: focus, split, maximize/restore, close | `gui/web/app.js` `paneNode()`, `app.css` `.pane*` |
| Context / palette actions | right-click any scene or run row; palette gained side-by-side, close, cycle, experience |
| Palette baseline unchanged | ⌘K still opens it; composer `/` untouched |
| No new deps | still one HTML + one CSS + two ES modules; no bundler |
| `tools/capture_desktop.py` | new side-by-side still and reel, **plus** `check_shell()` asserting the intents against the DOM |
| Guard regression | `!` still 403; token/CSP/Host/Origin unchanged; no new endpoints |

Exit criteria met: two scenes open side by side from palette or context menu, maximize/close work, the focused pane's hash still deep-links, and the capture tool regenerates the tour. Free drag/resize deliberately absent.

**Also settled while implementing** (open questions 2, 3 and 5): the Console is a singleton; two run details may share the screen because a resource id distinguishes them; and the capture tool grew multi-pane scenarios now, in Phase 0.

### Phases 1–3 (2026-09-15, same day)

| Deliverable | Phase | Where |
|---|---|---|
| Window / open-instance list | 1 (Should) | the taskbar — focus, minimize, restore, per window |
| `tiling` usable, default still `single` | 1 | unchanged |
| Workspace serialize / restore (`?windows=`, schema v1) | 2 | `encodeLayout` / `decodeLayout`, plus per-tab `sessionStorage` |
| Window list polish: focus, close, order | 2 | taskbar, in open order |
| Palette depth: scenes, runs, commands, dry-run, side-by-side | 2 | recent runs and per-scene window actions added |
| More than two surfaces | 2 | the desktop holds up to eight; `tiling` stays two by design |
| Floating drag / resize / desktop icons | 3 (Could) | pointer-driven drag, corner resize, edge snapping, icons |
| Minimize + restore **only if** restore works end to end | 3 (Could) | it does: the taskbar restores, and a test proves it |
| `prefers-reduced-motion` | 3 | honoured — the desktop animates nothing |

Free drag was the PostHog failure mode this roadmap flagged. It works here because it is pointer-capture based, writes geometry straight to the node during the gesture, and commits to the reducer once on release — the browser never fights a re-render mid-drag. A Playwright pass drags, snaps, minimizes, restores and tiles on every capture run, so a regression fails the docs build.

**Still not built, deliberately:** the nostalgia theme pack (Phase 3 Could, off by default — no product reason yet), a full a11y audit (Phase 3), and remote auth (out of scope; the loopback + token model stands). The React/Vite tradeoff was never triggered: the whole desktop is still one HTML file, one stylesheet and two ES modules, with no bundler and no npm.

**Open, for whoever picks it up:** should a wide viewport ever default to `tiling` or `os` rather than `single`; desktop icons for slash commands as well as scenes; and whether a tiling *tree* (beyond two panes) earns its complexity now that the desktop exists.
||||||| Stash base
======= The prerequisite and Phase 0 are **done**, in the same PR as the desktop GUI — these docs were merged into that branch rather than waiting on it.

| Phase 0 deliverable | Where |
|---|---|
| Layout state for two scene instances | `gui/web/shell.js` — pure reducer, no DOM |
| Intents `replace` \| `new` \| `focus` \| `sideBySide` | same, 19 unit tests in `tests/shell.test.mjs` (run by `pytest -q` through `tests/test_shell.py`) |
| Scene-as-window chrome: focus, split, maximize/restore, close | `gui/web/app.js` `paneNode()`, `app.css` `.pane*` |
| Context / palette actions | right-click any scene or run row; palette gained side-by-side, close, cycle, experience |
| Palette baseline unchanged | ⌘K still opens it; composer `/` untouched |
| No new deps | still one HTML + one CSS + two ES modules; no bundler |
| `tools/capture_desktop.py` | new side-by-side still and reel, **plus** `check_shell()` asserting the intents against the DOM |
| Guard regression | `!` still 403; token/CSP/Host/Origin unchanged; no new endpoints |

Exit criteria met: two scenes open side by side from palette or context menu, maximize/close work, the focused pane's hash still deep-links, and the capture tool regenerates the tour. Free drag/resize deliberately absent.

**Also settled while implementing** (open questions 2, 3 and 5): the Console is a singleton; two run details may share the screen because a resource id distinguishes them; and the capture tool grew multi-pane scenarios now, in Phase 0.

### Phases 1–3 (2026-09-15, same day)

| Deliverable | Phase | Where |
|---|---|---|
| Window / open-instance list | 1 (Should) | the taskbar — focus, minimize, restore, per window |
| `tiling` usable, default still `single` | 1 | unchanged |
| Workspace serialize / restore (`?windows=`, schema v1) | 2 | `encodeLayout` / `decodeLayout`, plus per-tab `sessionStorage` |
| Window list polish: focus, close, order | 2 | taskbar, in open order |
| Palette depth: scenes, runs, commands, dry-run, side-by-side | 2 | recent runs and per-scene window actions added |
| More than two surfaces | 2 | the desktop holds up to eight; `tiling` stays two by design |
| Floating drag / resize / desktop icons | 3 (Could) | pointer-driven drag, corner resize, edge snapping, icons |
| Minimize + restore **only if** restore works end to end | 3 (Could) | it does: the taskbar restores, and a test proves it |
| `prefers-reduced-motion` | 3 | honoured — the desktop animates nothing |

Free drag was the PostHog failure mode this roadmap flagged. It works here because it is pointer-capture based, writes geometry straight to the node during the gesture, and commits to the reducer once on release — the browser never fights a re-render mid-drag. A Playwright pass drags, snaps, minimizes, restores and tiles on every capture run, so a regression fails the docs build.

**Still not built, deliberately:** the nostalgia theme pack (Phase 3 Could, off by default — no product reason yet), a full a11y audit (Phase 3), and remote auth (out of scope; the loopback + token model stands). The React/Vite tradeoff was never triggered: the whole desktop is still one HTML file, one stylesheet and two ES modules, with no bundler and no npm.

**Open, for whoever picks it up:** should a wide viewport ever default to `tiling` or `os` rather than `single`; desktop icons for slash commands as well as scenes; and whether a tiling *tree* (beyond two panes) earns its complexity now that the desktop exists.
>>>>>>> Stashed changes

---

## Prerequisite — Merge PR #20 *(done — merged into that branch instead)*

| Deliverable | Done when |
|---|---|
| `bashos gui` on main (or integration branch) | Seven scenes, palette, guards, capture pipeline available |
| `docs/DESKTOP.md` + tour + `tools/capture_desktop.py` | Linked from these OS-shell docs without broken paths |
| No parallel greenfield SPA started | OS-shell work targets `src/bashos/gui/web/` only |

**Until merged:** Treat desktop behavior as “as proposed/landed in PR #20.”

---

## Phase 0 — Spike on current `gui/web` (1–2 weeks)

**Goal:** Prove **side-by-side + window chrome** on the existing one HTML/CSS/JS app **without new npm deps**.

| Deliverable | Done when |
|---|---|
| Layout state for two scene instances | Can show Console ‖ Runs (or Health) |
| Nav intents: `replace` \| `new` \| `focus` \| `sideBySide` | Unit tests; `replace` preserves #20 hash behavior |
| Scene-as-window chrome | Focus, close, maximize/restore on panes — no fake minimize |
| Context / palette actions | Open side-by-side; open in new browser tab; copy hash |
| Palette baseline | ⌘K unchanged; items may include “Side by side: …” |
| No new deps | Still no bundler; edit `app.js` / `app.css` + reload |
| `tools/capture_desktop.py` | Updated if chrome selectors change; tour still regenerates |
| Guard regression | `!` still 403; token/CSP/Host/Origin unchanged |

**Exit criteria:** Demo two existing scenes side-by-side from palette or menu; maximize/close; hash deep links still work for focused pane; capture script green enough for docs. Free drag/resize **not** required.

**Kill / pivot signals:** Dual scene mount breaks Console SSE/DOM → keep Console singleton + second pane for non-console scenes only; do not add React to “fix” it in Phase 0.

---

## Phase 1 — MVP multi-pane beside CLI

**Goal:** Usable multi-pane operator console **still one HTML/CSS/JS**, beside CLI.

| Deliverable | Priority |
|---|---|
| `tiling` / multi-pane usable; default remains `single` | Must |
| Side-by-side of any two of the seven scenes | Must |
| Window / open-instance list (Should if not in Phase 0) | Should |
| Keyboard: #20 baseline + close/cycle without composer collisions | Must |
| Deep-links: focused hash + optional layout query (**Proposal**) | Must / Should |
| Settings: `experience` toggle with real consumer | Must |
| Narrow → force `single` | Should |
| Capture + manual regression of #20 refusals | Must |
| **No** Vite/React; **no** shell passthrough; **no** run history file | Must |

**Non-goals in Phase 1:** Free-floating drag/resize, nostalgia themes, new Docs/Files scenes, new approval bypass UI, npm build.

**Exit criteria:** Operator runs a line in Console while Run detail or Health is visible beside it; closing the second pane returns to single-scene; guards intact.

---

## Phase 2 — Workspace layouts, window list, palette depth

**Goal:** Reproducible setups and denser navigation — still on #20 stack.

| Deliverable | Notes |
|---|---|
| Workspace serialize/restore (`?windows=` / local JSON) | Scene id + resourceId schema v1 |
| Window list polish | Focus, close, reorder; taskbar analogue |
| Palette depth | Scenes, recent runs, commands, dry-run, side-by-side actions |
| Two instances of same scene (e.g. two run details) | If Phase 0 deferred it |
| Perf pass | Share `store`; don’t double-SSE Console |
| Optional tiling tree beyond 2 panes | Split/join if needed |

**Exit criteria:** Share a URL/file that restores ≥2 panes; keyboard cycle works; capture tour documents multi-pane.

---

## Phase 3 — Optional nostalgia / drag — or framework tradeoff

| Deliverable | Notes |
|---|---|
| Optional floating drag/resize / desktop icons | Only after side-by-side solid; PostHog risk applies |
| Nostalgia / theme pack | Off by default |
| Evaluate React/Vite **only if** complexity forces it | Explicit ADR: cost includes rewriting `capture_desktop` and abandoning no-build MVP story — **not** default |
| a11y audit | Focus, SR labels, reduced motion |
| Remote auth | Out of scope until local-first multi-pane is solid; never weaken loopback/token model casually |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fighting no-build constraint with premature React/Vite | High if unchecked | Diverges from #20; breaks simple install | Phases 0–2 ban new bundler; Phase 3 ADR only |
| Shortcut collisions with composer `/` and ⌘K | High | Broken Console UX | Never steal bare `/`; test composer focus |
| pywebview quirks with multi-pane CSS | Medium | Native window layout bugs | Test browser path + pywebview; capture in both when possible |
| Violating #20 refusals while “just adding chrome” | Medium | Security regression | Guard checklist every phase; no `!`, no secrets, no history file |
| PostHog folklore (drag, minimize, Ctrl+K) copied blindly | High | Bad estimates / broken cheatsheets | Inspiration only; keymap from #20 + our tests |
| Console DOM/SSE broken by dual mount | Medium | Unusable MVP | Console singleton pattern; second pane for other scenes |
| Scope creep into marketing OS / greenfield apps | Medium | Delayed MVP | Non-goals; seven scenes only |
| Implementing before #20 merges | Medium | Rebase pain / duplicate stack | Prerequisite gate |

---

## Open questions

1. Default experience after Phase 1: stay `single` with opt-in multi-pane, or detect wide viewports?  
2. Console singleton vs multiple Console instances?  
3. Layout persistence: URL only vs `sessionStorage` vs file under project?  
4. When (if ever) is framework complexity justified — LOC? pane count? test pain?  
5. Should `capture_desktop.py` grow multi-pane scenarios in Phase 0 or Phase 1?  
6. Approvals UI: stay policy-in-engine only, or future scene that **cannot** widen allowlist?

---

## Suggested sequencing (summary)

```
Prerequisite: merge PR #20 (desktop GUI)
Phase 0: side-by-side + chrome on gui/web (no new deps) → update capture if needed
Phase 1: MVP multi-pane beside CLI; seven scenes; guards intact; still one HTML/CSS/JS
Phase 2: workspace layouts, window list, deeper palette
Phase 3: optional drag/nostalgia OR evaluate framework only with explicit tradeoff
```

---

*End of ROADMAP.*
