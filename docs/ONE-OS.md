# one-os

> How bashOS builds, boots, manages and deploys machines: one manifest and one test harness that put the right operating system on a machine from a USB stick, over the network, or as a native disk image.

one-os is the part of bashOS that touches hardware. It lives in [`one-os/`](../one-os/README.md) with its own Makefile, builder container, documentation and tests; why it is here is [ADR 0004](adr/0004-one-os.md).

| Verb | What one-os does | Where |
| --- | --- | --- |
| **Build** | Downloads and verifies every pinned ISO and tool, builds the Debian home base, stages the stick and a test image | `one-os/manifest.yaml`, `make -C one-os fetch lightos payload image` |
| **Boot** | A Ventoy stick (UEFI and BIOS), a PXE server for machines with no stick, or a plain image written to a card | `one-os/docs/user-guide/02-booting.md`, `one-os/docs/operator-guide/05-network-boot-server.md` |
| **Manage** | A rescue system with the operator's SSH key: read an install's journal offline, change it before its first boot, drive VMs through a guest agent. On an installed machine: screenshots, input and recorded Claude Code sessions over SSH | `one-os/docs/reference/oneos-vm.md`, `one-os/docs/operator-guide/06-remote-sessions.md`, `one-os/docs/field-reports/` |
| **Check** | Records a machine's parts and the first kernel each chip needs, and checks them against a system's kernel before anything is deployed: the X870E desktop's Wi-Fi has no driver in SteamOS 3.8, and every chip with a known first kernel is driven in bashOS | `one-os/machines/`, `one-os/docs/reference/machines.md` |
| **Deploy** | Installs Debian or Ubuntu onto another drive, deploys SteamOS onto an NVMe drive over the network, clones a disk | `one-os/docs/user-guide/05-install-an-os.md`, `one-os/docs/user-guide/07-steamos.md` |

```bash
bin/bashos one-os                    # every target
bin/bashos one-os lint               # shellcheck, ruff, manifest schema
bin/bashos one-os test ARGS="-k t21" # one harness test in QEMU
bin/bashos one-os vm start dev       # a named VM you can exec into, screenshot and stop
bin/bashos one-os machine check x870e-dark-hero --system bashos   # a machine's chips against a system's kernel
```

An agent never writes a real disk: flashing a stick and installing onto hardware are the maintainer's steps ([one-os/AGENTS.md](../one-os/AGENTS.md)).

Next: the bashOS ISO (Amrchy with the bashOS layer, [AMRCHY.md](AMRCHY.md)) as a system one-os puts on the stick and the PXE menu, deploys unattended and proves in QEMU, then on the X870E ([the epic](../one-os/docs/epics/0001-bashos-and-amrchy.md)).
