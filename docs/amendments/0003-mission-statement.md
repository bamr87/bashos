<!-- kit: governance v0.1.0 -->
# 0003 — Missions

- **Status:** proposed
- **Date:** 2026-11-16
- **Proposed by:** Grok Bot (agent), at the maintainer's request
- **Ratified by:**
- **Affects:** constitution §1; docs/frontend/PRD-os-shell.md §1.1; BASHOS-044
- **Supersedes:** none
- **Related:** [docs/frontend/PRD-os-shell.md](../frontend/PRD-os-shell.md) §1.1

## Context

Constitution §1 was a single mission sentence or short paragraph, not one direction statement with exactly three numbered missions. The fleet rule is that every repo's constitution §1 uses that form, adopted through a numbered amendment the maintainer ratifies by merging. Mission 1 is the maintainer's own wording, adapted to this repo: provide data, tools, resources and transparency for all stakeholders, practitioners in the domain, and the general public. The ambition is the direction, not a claim that the work is already finished.

The earlier §1 text was:

> PR #20 proposes/lands `bashos gui`: a GUI access layer beside the terminal, not above it. One page, seven hash-routed scenes (Overview, Console, Commands, Runs, Health, Engine, Settings), same kernel as the CLI, no-build front end.

## Amendment

Retitle constitution §1 **Missions**. Replace the body of §1 with the following. Any invariants or other normative rules that already lived outside §1 are unchanged.

bashOS's direction is to become the ultimate open home for all things terminal-first AI runtime — data, tools, resources and transparency, gathered in one place that anyone can inspect and reuse.

1. **Provide data, tools, resources and transparency for all stakeholders, operators, AI practitioners and the general public.** Operators, contributors, agent builders, and the general public are first-class audiences. The aim is a shared, open commons: the same kernel, the same tools, and the same trail of evidence for everyone.
2. **Make AI assistance a first-class part of the terminal: route slash commands through a reliable kernel onto the engine, with runs, health and settings that anyone can inspect.** The path starts with Claude slash commands through a LangGraph kernel onto the OpenCode engine. The terminal remains the home of record; nothing important happens only in a hidden session.
3. **Put that runtime in every operator's hands, from the CLI and from a GUI access layer that sits beside the terminal, not above it.** The same kernel serves both; a no-build front end is one path to Overview, Console, Commands, Runs, Health, Engine and Settings — an open toolkit for working with all things terminal-first AI runtime.

These missions set the course; they do not claim the work is finished. They serve the README and the OS-shell PRD: a terminal-first runtime, with a GUI beside the terminal rather than above it. The earlier §1 text about `bashos gui` (one page, seven hash-routed scenes, same kernel, no-build front end) is absorbed into mission 3 and is kept as direction, not as a claim that the GUI already ships. Every feature must trace to them.

_Source: [frontend/PRD-os-shell.md](frontend/PRD-os-shell.md) §1.1._

## Consequences

Agents and reviewers judge fit against these three missions before inventing scope, treating them as the direction of the repo rather than a description of what already ships. The same text is added as docs/frontend/PRD-os-shell.md §1.1 so the constitution's `_Source:` line stays accurate. The PRD purpose, goals, feature catalog and invariants outside this addition are unchanged except for a new catalog entry (BASHOS-044) and a regenerated feature-catalog block where the repo already has one. This PR also aligns the README and AGENTS.md one-liners with the missions and links them to constitution §1.
