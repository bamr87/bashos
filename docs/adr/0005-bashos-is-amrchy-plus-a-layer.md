# ADR 0005 — The bootable bashOS is Amrchy plus the bashOS layer, and amrchy lives in this repo

> amrchy, the Omarchy fork, is folded into this repo as a squashed git subtree and becomes bashOS's core framework. The bashOS that boots on a machine is Amrchy's ISO with bashOS installed as a layer, delivered and checked by one-os, and the X870E desktop is its first target.

- **Status**: proposed
- **Date**: 2026-11-13
- **Deciders**: the maintainer (direction given 2026-11-13: "bashos needs to be a combination that can be bootable onto the custom machine with amrchy as a core framework forked from Omarchy"; the subtree, chosen over a submodule or a full history merge, the same day; ratified by merging this PR)
- **Related**: [ADR 0003](0003-bashos-on-omarchy.md), [ADR 0004](0004-one-os.md), epic [#73](https://github.com/bamr87/bashos/issues/73), [the one-os epic](../../one-os/docs/epics/0001-bashos-and-amrchy.md), [docs/AMRCHY.md](../AMRCHY.md), [docs/OS.md](../OS.md)

## Context

ADR 0003 made bashOS a fork of Omarchy (`bamr87/amrchy`) and named its ISO the image, but left two things open. The one-os epic asked the first outright: is bashOS the Debian image of ADR 0002, the branded Amrchy build, or both? The second was how the fork and this repo fit together: until now they were two repositories with no shared build.

What was found when the two were put together:

- amrchy's `main` never received its first upstream sync. PR #2 merged the sync (Omarchy quattro@175e63b6, 625 changes) into the `upstream-sync-tool` branch seconds after PR #1 had merged that branch into `main`. `main` was Omarchy as of late September, and Omarchy's ISO builder of 1 November refuses it (it lacks `install/provisioning/progress-icon.sh`).
- Omarchy's builder (`omarchy-iso`, with the recipes in `omarchy-pkgs`) builds an ISO from a local checkout of the framework (`--local-source`). Whatever is under the checkout's `install/` ships in the runtime package and runs during the install, as root in the target with no network, then once per user.
- The X870E desktop needs a 7.2 kernel for its Wi-Fi and a 6.16 kernel for its 10 GbE port. Debian 13 ships 6.12. Amrchy's kernel is Omarchy's `linux-omarchy`, 7.2.15 in the 4.5.0 image of 5 November.

## Decision

1. **amrchy is folded into this repo as `amrchy/`, a squashed git subtree of `bamr87/amrchy`.** It is one commit, with none of Omarchy's 6,640. `bamr87/amrchy` stays the fork of record, and its daily AI upstream sync keeps running there. `bashos os amrchy pull` brings it in, and `bashos os amrchy push BRANCH` sends changes made here back as a pull request there. The tree folded is amrchy's `main` merged with its sync branch, conflict-free: Omarchy 175e63b6 plus the fork's own files. Landing that same merge on `bamr87/amrchy` is a pull request there.
2. **amrchy is the framework; a product sits on it as a layer.** amrchy gains one generic extension point, `install/layers/<name>/{system.sh,user.sh}`, run last by the installer ([amrchy/docs/layers.md](../../amrchy/docs/layers.md)). Upstream files get only the two `run_logged` lines that call it. bashOS is the first layer. The framework ships none.
3. **The bootable bashOS is Amrchy's ISO with the bashOS layer.** `bashos os iso build` stages `amrchy/` with the layer and the bashOS tree as its payload, then runs Omarchy's builder at the commits `os/iso/iso.conf` pins (the day of amrchy's upstream base). The install is the framework's: the configurator, or unattended from a `cidata` drive that `bashos os iso seed` writes for one machine and disk.
4. **The network part of the install happens at first boot.** The layer works offline: it copies bashOS to `/opt/bashos` and arms `bashos-firstboot`. Once a user exists and PyPI and npm answer, `bashos-firstboot` runs `bashos os install`, which now knows Amrchy as a base. A failure is recorded and reported, and never loops.
5. **`os/` is the bashOS layer for both bases.** Amrchy is the primary base: its package names, pacman, and a console that opens in a window on the Hyprland desktop instead of taking tty1. Debian 13 stays a supported base for machines already on it, and for the Raspberry Pi path. The Debian mkosi image (`os/image/`) gets no new work.
6. **one-os checks a machine before it deploys a system.** Machine profiles (`one-os/machines/`) record a custom PC's parts and the first kernel each chip needs; `oneos-machine check` compares them with a system's kernel. The X870E desktop is the first profile.
7. **The product is bashOS; the framework keeps its name.** The framework's commands, paths and packages stay in Omarchy's naming in source, as ADR 0003 decided. bashOS's own branding of the image (`bin/rebrand`, the boot and login screens) is a separate step, not done here.

## Consequences

**Positive**
- One checkout holds everything a bashOS machine is: the framework, the layer, the runtime, the delivery tool and the machine it targets.
- The framework stays close to upstream. The layer contract is the only lasting divergence an upstream sync has to keep, and it is two lines in upstream files.
- The X870E gets a kernel that drives every chip whose first kernel is known. Debian 13 could not.
- The layer and its first boot ran on Omarchy's own 4.5.0 image (kernel 7.2.15, QEMU, no desktop session) before any ISO was built. First boot finished in about five minutes, with the managed engine verified, and `bashos os status` reported the base, layer, runtime, engine and harness OK. The run also found a real fault, now fixed: a fresh install has only the installer's `offline.db` for pacman.

**Negative / risks**
- **Size:** `amrchy/` is 212 MB, 86 MB of it theme intro videos. Every later pull that changes media adds to this repo's history, and to the hub's, which vendors bashos.
- **Two places to change the framework:** a change made here must go back to `bamr87/amrchy` (`bashos os amrchy push`), or the next pull conflicts with it.
- **Builder drift:** the ISO builder is pinned to the framework's upstream base. Each amrchy upstream sync must move `os/iso/iso.conf` with it, or the builder rejects the tree.
- **Build cost:** an x86_64 ISO needs Docker with privileges and about 30 GB free. On Apple Silicon it runs emulated, so a Linux x86_64 host (forge, or CI) is the practical builder.
- **Not yet proven:** neither the ISO build nor an unattended install of it has run, and nothing has run on the X870E. The epic's stories 5 to 7 hold those tests.

## Alternatives considered

- **A submodule** (`amrchy/` as a pinned pointer): no size cost and the sync untouched, but two pull requests for every cross-cutting change, and `--recursive` clones. Offered; the maintainer chose the subtree.
- **A full history merge:** bashos takes in all 6,640 commits (1.2 GB, which the hub would carry too), `bamr87/amrchy` is archived and the sync moves here. The most complete merge, and rejected as the heaviest.
- **Fold `main` as it stood:** the September tree, which the November builder rejects. Rejected once the missing sync was found.
- **bashOS as packages in Omarchy's repository** (a `bashos` PKGBUILD in `omarchy-pkgs`): the stock builder only builds the framework's own three packages from local source. It stays a later option for updates through pacman.

## Supersedes / Superseded by

Refines ADR 0003, decisions 3 and 4 (the brand and the image), and answers the open question "Which bashOS?" in the one-os epic. Supersedes nothing.
