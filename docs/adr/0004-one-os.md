# ADR 0004 — one-os lives in bashos: one tool to build, boot, manage and deploy machines

> The standalone `one-usb` project (a Ventoy multiboot stick, a network boot server and a QEMU test harness) moves into this repo as `one-os/`, renamed throughout, and becomes the one way bashOS puts an operating system on a machine.

- **Status**: proposed
- **Date**: 2026-11-13
- **Deciders**: the maintainer (decided 2026-11-13; ratified by merging this PR)
- **Related**: [ADR 0002](0002-bashos-os-debian-mkosi.md), [ADR 0003](0003-bashos-on-omarchy.md), epic [#73](https://github.com/bamr87/bashos/issues/73), [one-os/README.md](../../one-os/README.md), [the next epic](../../one-os/docs/epics/0001-bashos-and-amrchy.md)

## Context

bashOS has two operating systems of its own: the Debian 13 mkosi image in `os/image/` (ADR 0002) and the Omarchy fork `bamr87/amrchy` (ADR 0003). Each has its own way onto a disk: `dd` by hand for the first, an ISO not yet built for the second.

Separately, `one-usb` grew into a general answer to "get an OS onto this machine". It builds a stick from a pinned manifest, boots a persistent Debian home base, installs Debian or Ubuntu onto another drive, serves the same home base over PXE, deploys SteamOS onto an NVMe drive over the network, and proves each of those in QEMU before hardware is touched. Its first real deployment (SteamOS on an ASUS X870E desktop, [field report](../../one-os/docs/field-reports/2026-11-12-steamos-silent-network.md)) showed the hard part is the same for every OS: which media, which kernel drives which chip, which disk actually booted, and how to look inside a machine that has no network.

That project had one commit, no remote and a name that no longer described it: the stick is one of three media.

## Decision

1. **`one-usb` moves into this repo as `one-os/`.** It is copied as it stood on 2026-11-13 (the one commit plus the uncommitted SteamOS, netboot and field-report work). There was no history worth a subtree merge.
2. **The name is one-os, everywhere.** Tools are `oneos-*` (`oneos-vm`, `oneos-install`, `oneos-restock`, `oneos-steamos`, …), the Python package is `oneos_harness`, environment variables are `ONEOS_*`, and the home-base ISO is `oneos-lightos.iso`.
3. **Its scope is the machine lifecycle:** *build* media and images from a manifest, *boot* a machine from a stick, the network or a native image, *manage* it through a rescue system with the operator's SSH key, and *deploy* the operating system that fits its hardware.
4. **It stays self-contained.** `one-os/` keeps its own Makefile, Docker builder, manifest, docs tree, ADRs (`one-os/docs/adr/`) and tests. `bin/bashos one-os <target>` forwards to that Makefile and `bin/bashos one-os vm …` to `scripts/oneos-vm`. Nothing in `src/bashos/` imports it.
5. **Its tests are not part of `make test`.** The harness boots VMs and takes about 30 minutes under emulation; it runs through `make -C one-os test` and the `one-os` workflow (only when `one-os/**` changes). `make lint` covers its dispatcher and, through `one-os/ruff.toml`, its Python.
6. **Its safety rule becomes a repo rule:** an agent never writes a real disk. Flashing a stick, `dd`, and installing onto hardware are the maintainer's steps. This is the same rule `os/` already states for forge.
7. **bashOS's hard rules are untouched.** one-os gives no loop a tool, never touches `opencode/policy.py`, and holds no credential; the only key it serves is a public SSH key.

## Consequences

**Positive**
- One place, one manifest and one test harness for every OS bashOS ships or installs, instead of a method per OS.
- `os/image/` and amrchy gain a tested path onto hardware (stick, PXE, native image) and a rescue system to debug first boots.
- The lessons of the first deployment (driver-versus-kernel checks, "which disk booted", offline journals) live beside the code that can act on them.

**Negative / risks**
- The repo grows by about 130 files and 3 MB (mostly documentation screenshots).
- Media made before the rename still carry `oneusb` names: their home base has `oneusb-*` tools, and the SteamOS install of 2026-11-12 has a unit called `oneusb-nm-guard.service`. Sticks are rebuilt from code, so the fix is to reflash.
- The documentation screenshots under `one-os/docs/images/` still show the old name until `make -C one-os docs-screenshots` is run.
- one-os's imported documents are hard-wrapped, unlike the rest of this repo (recorded under **Standard deviations** in AGENTS.md).

## Alternatives considered

- **Keep it a separate repository:** two places to change for every OS bashOS ships, and the image builders here could not use its harness without a submodule. Rejected.
- **Merge it into `os/`:** `os/` is one specific OS layer that ADR 0003 retires; one-os is the delivery method for any OS. Rejected.
- **Keep the `oneusb` identifiers and rename only the directory:** cheaper today, a permanent mismatch between the name people say and the commands they type. Rejected while the only media in existence are two cards.

## Supersedes / Superseded by

Supersedes nothing. It gives ADR 0002's image and ADR 0003's ISO their delivery path.
