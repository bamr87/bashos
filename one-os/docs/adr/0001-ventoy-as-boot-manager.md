# ADR-0001: Ventoy as the boot manager

Status: accepted · 2026-11-07

## Context
One stick must offer a menu of several bootable images, in UEFI and legacy BIOS,
with persistence for the home base, and adding an OS should be a file copy.

## Decision
Use **Ventoy** (pinned in `manifest.yaml`, release tarball verified by sha256),
installed with its CLI `Ventoy2Disk.sh -I [-g] [-s]`.

## Consequences
- ISOs boot in place; `ventoy.json` gives us persistence, menu aliases, a default
  entry and a timeout — the harness relies on the last two to auto-boot entries.
- Ventoy ships prebuilt binaries. We trust the upstream release checksum; building
  Ventoy from source is a possible later hardening step.
- Secure Boot needs a one-time MOK enrollment of Ventoy's key (T80, docs).
- Alternatives considered: hand-rolled GRUB loopback config (no persistence plumbing,
  per-distro quirks), YUMI/MultiBootUSB (less maintained, Windows-centric tooling),
  one partition per OS (wastes space, no drag-and-drop).
