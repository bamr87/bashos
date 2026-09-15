# ROADMAP: bashOS L6 OS Shell

**Status:** Draft for review  
**Related:** [PRD-os-shell.md](./PRD-os-shell.md), [SPEC-os-shell.md](./SPEC-os-shell.md)  
**Evidence note:** Live tour + **deep interaction pass** (2026-09-15) confirmed maximize/restore/close, **side-by-side panes**, context menus (new window / side-by-side / new tab / copy link), `/` search, `?` chat, `,` display options, Esc, toasts. Free drag/resize **unreliable**; snap shortcuts & minimize **not working/found**. Phase 0 validates side-by-side + menus first; drag/resize/snap are later risk.

---

## Phase 0 — Spike (1–2 weeks)

**Goal:** Prove stack + **side-by-side multitasking** + intent reducer + one real app bind before free-drag polish.

| Deliverable | Done when |
|---|---|
| Vite + React + Tailwind scaffold under agreed package path | Dev server boots; `experience` switch mounts/unmounts shell |
| Nav reducer: `replace` \| `new` \| `focus` \| `sideBySide` | Unit tests green; `new` **appends**; `sideBySide` splits + focus switch; close one → single |
| Context menus | Open in new window; Open side-by-side; Open in new browser tab; Copy link |
| Chrome spike | Maximize / restore / close on panes; **no** fake minimize required |
| Command palette | `/` (and optional Ctrl+K alias) opens palette; Esc closes; toast on a settings toggle |
| Motion / drag (optional) | Free floating drag/resize/snap is **out of Phase 0 exit criteria** — spike only if time; document as later risk |
| Terminal app stub | xterm.js renders; fake PTY or local echo |
| Agent app stub | Static transcript fixture; layout slots OK |
| Plain mode | `experience=plain` fully removes window/desktop chrome |
| Bridge sketch | `KernelBridge` / `OpenCodeBridge` interfaces only (**Proposal**); no fake endpoints |

**Exit criteria:** Demo Terminal + Agent **side-by-side** via context menu / intent; maximize/close; palette + Esc; intents tested; plain mode verified. Free drag/resize **not** required to exit.

**Kill / pivot signals:** Side-by-side + xterm unsustainable → simplify to single-pane + browser-tab fallback; do not burn schedule on Framer free-drag.

---

## Phase 1 — MVP

**Goal:** Usable operator console for a single-host bashOS session.

| Deliverable | Priority |
|---|---|
| `os` mode with side-by-side panes: focus, close, maximize/restore | Must |
| Context menus + browser-tab fallback | Must |
| Apps: Terminal, Agent, Editor, Files, Logs, Settings, Inbox | Must |
| Keyboard map (SPEC §6 live-aligned core) | Must |
| Command Palette (`/` primary; Ctrl+K optional alias) | Must |
| Deep-links per app path; `?experience=` | Must |
| Inbox wired to approval bus | Must — **Proposal** adapter |
| Attribution on window metadata | Must |
| StatusBar: host, agent count, model id | Should (**Proposal** feeds) |
| Settings: theme, experience, performanceBoost, reduceTransparency + toasts | Must |
| Narrow viewport → plain or single-pane | Should |
| Playwright: intents (incl. sideBySide), keymap, plain unmount, maximize/close | Must |

**Non-goals in Phase 1:** Free-floating drag/resize polish, snap-edge keyboard shortcuts, fake minimize/taskbar, shareable multi-window URL (Phase 2), nostalgia themes, remote multi-user auth.

**Exit criteria:** Operator can approve an irreversible act from Inbox while watching Agent + Terminal; layout survives reload for single focused deep-link.

---

## Phase 2 — Tiling, workspaces, palette depth

**Goal:** tmux/IDE-grade multitasking and reproducible setups.

| Deliverable | Notes |
|---|---|
| `tiling` experience with pane tree | Split, join, equalize; keyboard cycle (deepens Phase 0/1 side-by-side) |
| Free drag / resize / snap-edge polish in `os` | **Later risk** — PostHog live drag unreliable; only after side-by-side is solid |
| Minimize + taskbar/active-windows list | Only if restore path is complete end-to-end (PostHog: not found live) |
| Workspace serialize/restore (`?windows=` + `.bashos/workspace.json`) | Percent geometry schema v1 |
| Palette indexes skills, slash commands, files, runs | Local + runtime registry |
| Per-app `appSettings` policies | min/max, modal, center |
| In-window history back/forward | Could → Should if Editor/Files need it |
| Perf pass | Virtualize logs/transcripts; compositor gate if free-drag added |

**Exit criteria:** Share a workspace URL/file that restores ≥3 panes; tiling usable without mouse.

---

## Phase 3 — Polish

| Deliverable | Notes |
|---|---|
| Optional nostalgia / theme pack | Off by default; wallpaper skins |
| Animated open origins, snap indicators | Match PostHog feel only if perf budget holds |
| Run report “presentation” app | Could |
| Trace replay viewer | Could — MediaPlayer analogue |
| Fun mode (screensaver-equivalent) | Gated; never blocks Inbox |
| Remote daemon auth + multi-user attribution | After local-first is solid |
| a11y audit | Focus, SR labels, reduced motion |

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Handbook/code drift copied into bashOS (boring / newWindow) | High if unchecked | Operators distrust shell | Intent tests; real `plain` consumer |
| Framer + xterm + agent streams jank | Medium | Unusable console | Phase 0 spike; CSS drag fallback; tiling-first pivot |
| Kernel/OpenCode bridges vapor | Medium | Apps stay mock | Keep Proposal adapters; ship UI against fixtures |
| Approval bypass via UI | Low–medium | Safety regression | Inbox-only resolve; kernel enforces policy |
| Scope creep into marketing OS | Medium | Delayed MVP | Non-goals; nostalgia = Phase 3 optional |
| Mobile floating windows | High pain | Broken UX | Force plain/single-pane when narrow |
| Drag/snap assumed “done” because PostHog docs say so | High | Bad estimates | Deep pass: free drag unreliable; Shift+snap no effect — **do not** schedule as Phase 0 exit |
| Handbook keyboard folklore (`.`, `\|`, Ctrl+K, Shift+W/X) | High | Broken cheatsheets | Keymap from live pass; contract tests |
| Fake minimize / Trash / Bookmarks metaphors | Medium | Hollow UX | Skip until actions are real |

---

## Open questions

1. **Default experience:** `os` vs `tiling` for terminal-native users? Recommendation: Phase 1 `os` with **side-by-side-first** (matches PostHog-proven multitasking), Phase 2 promote full `tiling` tree as recommended default.  
2. **PTY protocol:** Does OpenCode expose web-ready PTY today, or new adapter?  
3. **Shared session protocol** with TUI — one pane model or divergent?  
4. **Workspace file** location and merge with existing project config.  
5. **StatusBar metrics** — which cost/model fields are stable from LangGraph kernel?  
6. **Slash commands** (`.claude/commands/`) — palette parity in Phase 1 or 2?  
7. **PostHog follow-ups (optional):** Re-check whether drag/resize improved upstream; mobile behavior; boring-mode consumer — does not block bashOS (deep pass already set Phase 0 priorities).  
8. **Auth boundary:** Local daemon only until when?  

---

## Suggested sequencing (summary)

```
Phase 0: scaffold → intents(+sideBySide) → context menus → maximize/close → palette → Terminal+Agent stubs → plain
Phase 1: full app set → Inbox bridge → live-aligned keymap → deep-links → tests
Phase 2: tiling depth → optional free drag/snap polish → workspaces → palette depth → perf
Phase 3: themes → replay/reports → remote auth → a11y audit
```

---

*End of ROADMAP.*
