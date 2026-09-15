# ROADMAP: bashOS L6 OS Shell

**Status:** Draft for review  
**Related:** [PRD-os-shell.md](./PRD-os-shell.md), [SPEC-os-shell.md](./SPEC-os-shell.md)  
**Evidence note:** Live PostHog tour confirmed maximize/restore, replace-nav, search overlay, Display Options; drag/resize/snap/minimize **not** independently verified — Phase 0 must de-risk motion.

---

## Phase 0 — Spike (1–2 weeks)

**Goal:** Prove stack + intent reducer + one real app bind before chrome polish.

| Deliverable | Done when |
|---|---|
| Vite + React + Tailwind scaffold under agreed package path | Dev server boots; `experience` switch mounts/unmounts shell |
| Nav reducer: `replace` \| `new` \| `focus` | Unit tests green; `new` **appends** (explicit; not docs-only) |
| Motion spike | Either CSS pointer-drag **or** Framer: open + move + resize + maximize/restore on 2 windows; document FPS notes |
| Terminal app stub | xterm.js renders; fake PTY or local echo |
| Agent app stub | Static transcript fixture; layout slots OK |
| Plain mode | `experience=plain` fully removes window/desktop chrome |
| Bridge sketch | `KernelBridge` / `OpenCodeBridge` interfaces only (**Proposal**); no fake endpoints |

**Exit criteria:** Team can demo Terminal + Agent as two windows; intents tested; motion approach chosen; plain mode verified.

**Kill / pivot signals:** Motion + xterm unsustainable on target hardware → tiling-first, drop free drag for Phase 1.

---

## Phase 1 — MVP

**Goal:** Usable operator console for a single-host bashOS session.

| Deliverable | Priority |
|---|---|
| Floating `os` mode: focus, z-order, close, maximize/restore | Must |
| Apps: Terminal, Agent, Editor, Files, Logs, Settings, Inbox | Must |
| Keyboard map (core SPEC table) | Must |
| Command Palette (`Ctrl+K` / `/`) over local app/command registry | Should → treat as Must if slash-command parity needed |
| Deep-links per app path; `?experience=` | Must |
| Inbox wired to approval bus | Must — **Proposal** adapter |
| Attribution on window metadata | Must |
| StatusBar: host, agent count, model id | Should (**Proposal** feeds) |
| Settings: theme, experience, performanceBoost, reduceTransparency | Must |
| Narrow viewport → plain or single-pane | Should |
| Playwright: intents, keymap, plain unmount, maximize/restore | Must |

**Non-goals in Phase 1:** Snap/sideBySide, shareable multi-window URL, nostalgia themes, Framer polish, remote multi-user auth.

**Exit criteria:** Operator can approve an irreversible act from Inbox while watching Agent + Terminal; layout survives reload for single focused deep-link.

---

## Phase 2 — Tiling, workspaces, palette depth

**Goal:** tmux/IDE-grade multitasking and reproducible setups.

| Deliverable | Notes |
|---|---|
| `tiling` experience with pane tree | Split, join, equalize; keyboard cycle |
| `sideBySide` nav intent + snap edges in `os` | Only after Phase 0 motion confidence |
| Minimize + taskbar/active-windows list | PostHog pattern; verify live behavior in our shell |
| Workspace serialize/restore (`?windows=` + `.bashos/workspace.json`) | Percent geometry schema v1 |
| Palette indexes skills, slash commands, files, runs | Local + runtime registry |
| Per-app `appSettings` policies | min/max, modal, center |
| In-window history back/forward | Could → Should if Editor/Files need it |
| Perf pass | Virtualize logs/transcripts; compositor gate while dragging |

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
| Drag/snap assumed “done” because PostHog docs say so | Medium | Bad estimates | Live tour did **not** verify drag/snap — spike explicitly |

---

## Open questions

1. **Default experience:** `os` vs `tiling` for terminal-native users? Recommendation: Phase 1 `os` (matches PostHog-proven maximize/replace), Phase 2 promote `tiling` as recommended default.  
2. **PTY protocol:** Does OpenCode expose web-ready PTY today, or new adapter?  
3. **Shared session protocol** with TUI — one pane model or divergent?  
4. **Workspace file** location and merge with existing project config.  
5. **StatusBar metrics** — which cost/model fields are stable from LangGraph kernel?  
6. **Slash commands** (`.claude/commands/`) — palette parity in Phase 1 or 2?  
7. **PostHog follow-ups (optional):** Re-verify drag/resize/snap/minimize on posthog.com; confirm whether desktop icons use append vs replace; confirm mobile behavior — does not block bashOS if Phase 0 covers motion.  
8. **Auth boundary:** Local daemon only until when?  

---

## Suggested sequencing (summary)

```
Phase 0: scaffold → intents → motion spike → Terminal+Agent stubs → plain
Phase 1: full app set → Inbox bridge → keymap → deep-links → tests
Phase 2: tiling → snap/sideBySide → workspaces → palette depth → perf
Phase 3: themes → replay/reports → remote auth → a11y audit
```

---

*End of ROADMAP.*
