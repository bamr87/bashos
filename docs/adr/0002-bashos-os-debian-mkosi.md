# ADR 0002 — bashOS the OS is an Omarchy-style layer on Debian 13, imaged with mkosi

- **Status**: proposed
- **Date**: 2026-10-30
- **Deciders**: the maintainer (ratified by merging the PR that adds `os/`)
- **Related**: [docs/OS.md](../OS.md), [docs/FORGE.md](../FORGE.md), [docs/ARCHITECTURE.md](../ARCHITECTURE.md) L0

## Context

bashOS should become the machine forge boots into, and serve the bamr87 hub's Harness Console from it, with [Omarchy](https://github.com/basecamp/omarchy) as the model: a layer installable on top of a base system, plus a bootable image with that layer pre-applied, unattended first-boot provisioning, and git-plus-migrations updates.

Three forces pull on the base:

- **forge runs Debian 13** and every rule in FORGE.md (absolute pane paths, `window-size latest`, `sudo -n` probes, never-sleep, the WoL broadcast) was learned on it, along with its `~/setup/01…06` scripts, restic backups, Docker stack and LVM layout.
- **Omarchy is Arch**: archiso, pacman, limine, btrfs + snapper.
- **The reference architecture** ([ARCHITECTURE.md](../ARCHITECTURE.md) L0) names an image-based, immutable root built with bootc from the Fedora CoreOS lineage, and its MVP's Phase 1 is "the daemon on any existing Linux host" before Phase 2's appliance image.

Without a decision the OS work either forks into three half-built bases or quietly drags forge onto a distribution its operator never chose.

## Decision

1. **The base is Debian 13 (trixie).** The OS layer (`os/`) installs with apt and systemd on Debian 13 and refuses other distributions outside a dry run.
2. **The layer follows Omarchy's structure**: `os/boot.sh` (the one-liner), `os/install.sh` with ordered phases (`os/install/*.sh`, system phases through sudo, user phases as the user), package lists (`os/packages/*.list`), a command namespace (`bashos os …`, `bashos-console`, `bashos-harness`, `bashos-provision`), managed blocks in dotfiles instead of overwriting them, timestamped migrations (`os/migrations/`), and `bashos os update` = fetch + re-apply + migrate. It installs to `/opt/bashos`, root-owned.
3. **The image is built with mkosi** (≥ 25, Debian's package) from `os/image/`: a GPT disk image with systemd-boot and a unified kernel image, root found by GPT auto-discovery and grown to the disk on first boot (systemd-repart + systemd-growfs), the layer applied in the image by `os/install.sh --image`, and first-boot provisioning by `bashos-provision` from a `BASHOS-SEED` drive (Omarchy's `cidata`). The root is mutable ext4 in this first form.
4. **The console stays the shared tmux session** of FORGE.md, shown on tty1 through a `cage` + `foot` kiosk when a GPU allows, else the Linux console.
5. **The harness is the hub's own console**, run unmodified (`tools/console/run.sh`, or its compose service) by a supervised user unit, loopback-only unless a token is configured.

## Consequences

**Positive**

- forge keeps its distribution, packages and every hard-won rule; the in-place install is additive and has an uninstall, so the move is incremental and reversible.
- forge can build its own image (`apt install mkosi`), and CI builds and boots it under KVM on every change to `os/`.
- mkosi is systemd's own image tool, so the reference architecture's L0 properties — read-only `/usr`, dm-verity, A/B updates with systemd-sysupdate, a signed UKI — are reachable later without changing the base or the build tool.
- No kernel, loop or policy code changes: the hard rules in AGENTS.md hold untouched.

**Negative**

- The first form is a mutable root. "Immutable by policy" is approximated by a root-owned `/opt/bashos`, not enforced by a read-only filesystem; rollback is re-imaging, not a boot-menu entry.
- mkosi builds on Linux only (macOS builds go through a privileged container), and its configuration keys still move between releases.
- Writing the whole disk image replaces a disk; installing beside forge's LVM layout needs a dedicated partition (systemd-boot discovers roots by GPT type, not inside LVM).
- The image's systemd-boot is unsigned until Secure Boot signing is added.

## Alternatives considered

- **Arch + archiso, like Omarchy** — closest to the model, but it moves forge to a different distribution, package names and release cadence, discards the Debian setup it already runs, and its value for bashOS is Omarchy's *shape*, which carries over to Debian intact.
- **bootc (Fedora/CentOS lineage), as ARCHITECTURE.md L0 proposes** — the cleanest immutable story ("the OS is a container image"), but it means leaving Debian, and the architecture's own MVP puts the appliance image after the layer on an existing host; mkosi keeps that path open on Debian.
- **Debian live-build ISO + a scripted installer** — a familiar ISO, but an installer to maintain and no first-class path to image-based updates; mkosi's disk image is written and booted directly and grows itself.
- **Provisioning with cloud-init or Ignition** — powerful, but a second configuration language for one user, a hostname and some keys; a `KEY=value` seed read as data covers it, and systemd credentials remain available later.

## Supersedes / Superseded by

- Supersedes: none (narrows ARCHITECTURE.md's L0 choice for machines like forge; the appliance product may still choose bootc)
- Superseded by: none
