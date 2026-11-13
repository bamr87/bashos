# one-os

> How bashOS builds, boots, manages and deploys machines: one manifest and one test harness that put the right operating system on a machine from a USB stick, over the network, or as a native disk image.

one-os is the part of bashOS that touches hardware. It lives in [`one-os/`](../one-os/README.md) with its own Makefile, builder container, documentation and tests; why it is here is [ADR 0004](adr/0004-one-os.md).

| Verb | What one-os does | Where |
| --- | --- | --- |
| **Build** | Downloads and verifies every pinned ISO and tool, builds the Debian home base, stages the stick and a test image | `one-os/manifest.yaml`, `make -C one-os fetch lightos payload image` |
| **Boot** | A Ventoy stick (UEFI and BIOS), a PXE server for machines with no stick, or a plain image written to a card | `one-os/docs/user-guide/02-booting.md`, `one-os/docs/operator-guide/05-network-boot-server.md` |
| **Manage** | A rescue system with the operator's SSH key: read an install's journal offline, change it before its first boot, drive VMs through a guest agent | `one-os/docs/reference/oneos-vm.md`, `one-os/docs/field-reports/` |
| **Deploy** | Installs Debian or Ubuntu onto another drive, deploys SteamOS onto an NVMe drive over the network, clones a disk | `one-os/docs/user-guide/05-install-an-os.md`, `one-os/docs/user-guide/07-steamos.md` |

```bash
bin/bashos one-os                    # every target
bin/bashos one-os lint               # shellcheck, ruff, manifest schema
bin/bashos one-os test ARGS="-k t21" # one harness test in QEMU
bin/bashos one-os vm start dev       # a named VM you can exec into, screenshot and stop
```

An agent never writes a real disk: flashing a stick and installing onto hardware are the maintainer's steps ([one-os/AGENTS.md](../one-os/AGENTS.md)).

Next: bashOS and Amrchy as operating systems one-os can put on a machine ([the epic](../one-os/docs/epics/0001-bashos-and-amrchy.md)).
