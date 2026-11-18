# Documentation tools

`make docs-screenshots` regenerates `docs/images/`:

| Script | Captures | Needs |
|---|---|---|
| `capture_vm.py` | Ventoy menu (UEFI, BIOS), home-base desktop and tools, netboot.xyz menu — from real VMs via `scripts/oneos-vm` | a built stick image; internet for netboot.xyz; ~15 min under emulation |
| `capture_wizard.mjs` | the flash wizard (overview, confirmation, progress, finished, boot-test, dark mode) via headless Chrome + DevTools protocol | Node ≥ 22, Google Chrome (`CHROME=` to override) |

The wizard capture runs a real wizard server. Progress/finished/boot-test views inject
sample job data into the page (a docs run never writes a disk); the boot-test view embeds
the last real boot-test screenshot (`build/wizard/test-screen.png`). With no removable disk
named like `$DOCS_DISK_MATCH` (default `SDXC`) plugged in, it shows a sample SD-card entry.

Check the images by eye before committing: menus change upstream (netboot.xyz) and frame
picking is heuristic.
