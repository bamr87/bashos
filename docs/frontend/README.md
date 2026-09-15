# bashOS L6 OS Shell — Frontend Docs

Documentation for an **OS-style web frontend** at bashOS layer **L6 (INTERFACE)**. These docs adapt patterns from PostHog.com’s desktop shell (windows, taskbar, Spotlight, app templates) to a **terminal-first AI runtime** — preferring IDE / tmux metaphors over marketing nostalgia.

**Repo:** [bamr87/bashos](https://github.com/bamr87/bashos)  
**Stack context:** Python 3.11+, LangGraph kernel, OpenCode engine; today’s product is CLI/REPL with slash commands in `.claude/commands/`.  
**Architecture:** `bashOS-architecture.md` layers L1–L6; L6 surfaces include bashos shell, SSH, TUI, and web console.

## Why this exists

bashOS already treats the agent as a system service (approval gates, attributable actions, immutable base OS, model-agnostic). L6 today is CLI/REPL-centric. As multi-agent sessions, terminals, edits, and approvals grow, a linear REPL alone does not solve **multitasking and context**. These docs define an optional **windowed / tiling web shell** that:

- Keeps several agent and tool surfaces open without tab explosion
- Makes navigation intents (`replace` | `new` | `focus`) explicit — a cautionary lesson from PostHog handbook drift (`boring` mode, `newWindow`)
- Stays keyboard-first and dense, not landing-page chrome
- Remains a proposal until Phase 0 spike validates stack and kernel wiring

Research basis: [posthog-os-research.md](./posthog-os-research.md) (PostHog.com public sources + live tour, 2026-09-15). No fake analytics claims; proposals marked clearly.

## Documents

| Doc | Purpose |
|---|---|
| [PRD-os-shell.md](./PRD-os-shell.md) | Product requirements: problem, goals, non-goals, JTBD, metrics, experience modes, MoSCoW, PostHog→bashOS map |
| [SPEC-os-shell.md](./SPEC-os-shell.md) | Technical spec: architecture, window schema, nav intents, app template API, initial apps, keymap, deep-links, stack, a11y/perf |
| [ROADMAP-os-shell.md](./ROADMAP-os-shell.md) | Phased delivery (0 spike → 1 MVP → 2 tiling → 3 polish), risks, open questions |

## Design goals (from bashOS)

1. **Agent as system service** — shell surfaces bind to runtime sessions, not ephemeral chat widgets  
2. **Human approval for irreversible acts** — Inbox/approvals is a first-class app  
3. **Attributable actions** — every window/session carries actor + run identity  
4. **Immutable base OS** — shell is L6 chrome; it does not mutate the base image  
5. **Model-agnostic** — UI never hard-codes a single LLM vendor  

## Status

**Documentation only.** No runtime APIs are claimed to exist beyond CLI/REPL and architecture whitepaper layers. Kernel / OpenCode integrations in the SPEC are labeled **Proposal**.
