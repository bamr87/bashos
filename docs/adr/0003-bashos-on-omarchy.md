# ADR 0003 — bashOS by BASH Consulting is a fork of Omarchy, kept current by an AI-assisted upstream sync

> bashOS stops building its own operating system and forks Omarchy (Arch + Hyprland + Quickshell) as [`bamr87/amrchy`](https://github.com/bamr87/amrchy), branded for BASH Consulting. It diverges technically where it needs to, an AI agent brings upstream's new features and improvements in through a reviewed pull request each day, and the Debian 13 base of ADR 0002 is retired.

- **Status**: proposed
- **Date**: 2026-11-01
- **Deciders**: the maintainer (decided 2026-11-01, revised the same day from an extension layer to a fork; ratified by merging this PR)
- **Supersedes**: [ADR 0002](0002-bashos-os-debian-mkosi.md)
- **Related**: epic [#73](https://github.com/bamr87/bashos/issues/73), [docs/OS.md](../OS.md), [docs/OPENCODE.md](../OPENCODE.md)

## Context

ADR 0002 built bashOS as an Omarchy-*style* layer on Debian 13 with its own mkosi image. That layer works: forge ran it in place, then booted its image from USB on real hardware. The first run as an everyday machine showed where the effort was going, though. The human side (a desktop worth sitting at, settings reachable everywhere, monitor rotation, remote keyboard and mouse) was all being rebuilt from parts (`cage`, `foot`, `wlr-randr`, `wayvnc`), and every one of those parts already exists, finished, in [Omarchy](https://omarchy.org).

What Omarchy is today (4.0.6, MIT):
- **The OS:** Arch Linux, rolling (always the latest packages, which is the fleet's dependency policy), with the Hyprland compositor and a Quickshell desktop shell.
- **Packaging:** two Arch packages, `omarchy` (commands, the shell, themes, migrations) and `omarchy-settings` (`/etc/skel`, boot and login screens, branding). Its own package repository and mirror, signed with key `40DFB630FF42BCFFB047046CF0134EE680CAC571`.
- **Install:** an ISO (`omarchy-iso`, with acceptance tests) for full-disk or free-space installs, encrypted by default, unattended from a `cidata` drive. `authorized_keys` on that drive enables sshd behind a default-deny firewall.
- **Extension points** that need no fork: themes (`~/.config/omarchy/themes/<slug>`), hooks (`~/.config/omarchy/hooks/{post-boot,post-update,theme-set,…}.d/`), shell plugins (`~/.config/omarchy/plugins/<id>`), `shell.json` overrides, migrations.

The goal, in the maintainer's words: *not to reinvent the wheel but to upgrade it*, with a customized OS carrying the BASH Consulting brand ([bash-365.com](https://bash-365.com)) and focus areas.

## Decision

1. **bashOS forks Omarchy.** The fork is the maintainer's existing [`bamr87/amrchy`](https://github.com/bamr87/amrchy), extended for bashOS. It may diverge technically anywhere bashOS needs it to: the runtime, the managed OpenCode engine and its policy contract, the Harness Console service, the shared tmux console, the desktop's menus and settings.
2. **An AI layer keeps it current with upstream** ([amrchy#1](https://github.com/bamr87/amrchy/pull/1)). Sync is *merge, then diverge*: upstream is merged onto a sync branch, so git keeps it as an ancestor and each sync brings only what's new.
   - `bin/upstream-sync` does the mechanical half (`status`, `plan`, `merge`, `decline`, `check`, `finish`).
   - `default/upstream.toml` is the policy: what to follow, fork-owned paths whose version wins a conflict, decline rules.
   - An agent following `agents/skills/upstream-sync.md` makes the calls. It takes upstream's features, improvements, fixes and security work; declines, by an explicit recorded revert, what would reverse the fork's divergence; and resolves conflicts in the fork's favour.
   - `.upstream/ledger.tsv` records every decision.
   - It runs daily through the hub's `ai-lane` (kill switch `UPSTREAM_SYNC_ENABLED`, budget cap) and opens **one pull request a person merges**. Agents never merge.
3. **Source stays in upstream's naming; the brand is applied to builds.** The fork's `bin/rebrand` rewrites the tree from `default/brand.toml` when a package or ISO is built, so a sync conflicts only where bashOS really changed code. The name is "bashOS by BASH Consulting", from bash-365.com's brand (navy `#001138`, gold `#FFD42A`, the pyramid mark). BASH Consulting's focus areas (cloud, ERP and accounting systems for small and medium businesses) become menu sections and tooling.
4. **The image is the fork's ISO.** It's built with `omarchy-iso` against the fork's packages and installs unattended from a `cidata` seed, which replaces `BASHOS-SEED`.
5. **The Debian 13 base is retired now.**
   - **Retired** (no further work, removed once the fork reaches it): `os/` as an apt/Debian installer, `os/image/` (mkosi), `os-image.yml`, the Debian package lists, the networkd/repart extras.
   - **Carried over**, because it's distro-agnostic: the runtime and its surfaces; the managed engine, contract and canary (#72); `policy.py`; the harness service; the console session; the migrations idea (Omarchy has its own).
6. **Unchanged:** `policy.py` is the only place that widens the blast radius; loops never get network or write tools; `opencode.jsonc` stays generated and credential-free; nothing blocks on a human.

## Consequences

**Positive**
- A finished, maintained human desktop (compositor, shell, launcher, menus, themes, settings) on day one, instead of a kiosk.
- Always-latest packages from Arch match the fleet policy; the engine's own currency is #72's job and works the same on Arch.
- One installer and one update path (Omarchy's), with bashOS riding its hooks and migrations, and much less OS code to own.
- bashOS can change any part of the OS, without being limited to the extension points upstream happens to offer.
- Keeping up costs a reviewed PR a day instead of a person tracking a fast upstream (100+ commits a fortnight per repo): the agent does the reading and merging, a human the deciding. The first sync took the fork from 919 commits behind to current (amrchy#2).

**Negative / risks**
- **Hardware:** Omarchy targets modern laptops and desktops. forge's GTX 660 runs Hyprland on nouveau, which can't reclock that card. The spike (#74) is the gate.
- **Rolling release:** Arch updates can break things on a dev box that also serves the harness. Omarchy's btrfs + snapper snapshots are the rollback; `omarchy update` is the controlled path.
- **Full-disk install:** encrypted by default and takes the disk (or its free space). Moving forge's internal disk to Omarchy needs an off-box backup first, as ADR 0002 already required.
- **Divergence cost:** every bashOS change to a file upstream also edits is a future conflict the agent must resolve. Fork-owned paths and the ledger keep that visible; heavy divergence in a busy upstream area deserves a second look before it's made.
- **AI judgment:** the agent can misjudge what counts as an improvement. Every decision is in the PR and the ledger, a person merges, and the policy file is where recurring calls become rules.

## Alternatives considered

- **Extension layer on unmodified Omarchy** (this ADR's first draft, the same day): least upkeep, but bashOS could only change what Omarchy's themes, hooks and plugins expose. The maintainer chose to diverge technically. Rejected.
- **A fork synced by hand:** the same freedom, but nobody can read 100+ upstream commits a fortnight per repo. Rejected in favour of the AI layer.
- **Keep Debian, borrow the UX:** most work, least reuse. Rejected.
- **Keep both** (Omarchy desktop, Debian server edition): double the OS maintenance. Rejected in favour of retiring Debian now.
