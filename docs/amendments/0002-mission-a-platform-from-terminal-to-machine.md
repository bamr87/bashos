<!-- kit: governance v0.1.0 -->
# 0002 — The mission: one platform, from the terminal to the machine it boots on

- **Status:** proposed
- **Date:** 2026-11-13
- **Proposed by:** Claude Code (Opus 5.5), from the maintainer's direction of 2026-11-13
- **Ratified by:** the merged PR that adds this record (leave blank until merged)
- **Affects:** constitution § 1; feature ids BASHOS-037, BASHOS-039, BASHOS-040, BASHOS-041, BASHOS-042
- **Supersedes:** none
- **Related:** [ADR 0004](../adr/0004-one-os.md), [ADR 0005](../adr/0005-bashos-is-amrchy-plus-a-layer.md), [docs/AMRCHY.md](../AMRCHY.md)

## Context

§ 1 states the mission as the GUI pull request of August: one page, seven scenes, beside the terminal. The repo has outgrown that. It now holds a framework operating system (`amrchy/`, the Omarchy fork), the bashOS layer that boots on it (`os/`), and one-os, which builds, checks and deploys the machines bashOS runs on. On 2026-11-13 the maintainer stated the goal: bashOS is *"a universal, customizable, versatile, cross platform, cross UI platform that also includes building custom PCs"*, and it must be *"bootable onto the custom machine with amrchy as a core framework forked from Omarchy."*

## Amendment

Replace § 1 with:

> bashOS is one platform from the terminal to the machine it runs on: a terminal-first AI runtime whose Markdown slash commands run on one kernel behind every surface (the CLI, the Textual desktop and the loopback GUI), on any machine that has a terminal. On a machine of its own it boots as Amrchy, the maintainer's fork of Omarchy, with bashOS as its layer. one-os builds, checks and deploys those machines, custom-built PCs among them, and proves each step in a VM before hardware is touched. Every part stays customizable and versatile, and nothing in the operating system or the hardware tooling widens what the AI loops can touch.

Its sources line names AGENTS.md, ADR 0005 and the PRD, and this record.

## Consequences

- The invariants in § 2 are unchanged. The amended mission repeats one of them: the hardware and operating-system work never widens the loops' tools.
- The PRD's requirements still describe only the GUI. New features for the framework, the ISO and machine profiles are traced `prd: [TBD]` until the PRD gains requirements for them, a follow-up for the maintainer.
- AGENTS.md's "What this repo is" already says the same in its own words (changed in the same PR).
