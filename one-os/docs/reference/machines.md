# Machine profiles

> What a machine one-os deploys to is built from, which kernel first drives each of its chips, and how its firmware boots, checked against an operating system's kernel before anything is written to a disk.

A custom PC is a list of parts, and the parts decide which operating systems can run on it. The first deployment showed the cost of finding that out on the machine: SteamOS 3.8 installed cleanly on the X870E desktop and then had no Wi-Fi, because its kernel predates the MediaTek MT7927's driver ([field report](../field-reports/2026-11-12-steamos-silent-network.md)). A profile records the parts once; `scripts/oneos-machine` answers the question in a second.

## Files

| File | What it holds |
| --- | --- |
| `machines/<name>.yaml` | One machine: its parts (`build`), how it boots (`firmware`), the chips that need a driver (`devices`) and where each fact was read (`sources`) |
| `machines/systems.yaml` | The kernel each operating system one-os deploys boots with, and where that version was read |

A device carries its `chip`, its PCI id (`vendor:device`, as `lspci -nn` prints it), the `driver` that takes it, the first `kernel` with that driver, and a `role` (`network`, `display`, `storage`, `audio`, `input`, `other`). A fact not yet read off the machine is `TBD`; the check reports such a chip as unknown and never guesses.

## The check

```bash
scripts/oneos-machine list                                   # the profiles
scripts/oneos-machine show x870e-dark-hero                   # its build sheet
scripts/oneos-machine check x870e-dark-hero --system bashos  # every chip against bashOS's kernel
scripts/oneos-machine check x870e-dark-hero --kernel 6.12    # or against any kernel
lspci -nn | scripts/oneos-machine check --lspci - --system steamos-3.8   # the hardware in front of you
scripts/oneos-machine lint                                   # part of make lint
```

`check` prints one line per chip, `[ OK ]`, `[MISS]` or `[ ?? ]` (first kernel unknown), and exits:

| Exit | Meaning |
| --- | --- |
| 0 | Every chip with a known first kernel is driven |
| 1 | At least one chip has no driver in that kernel |
| 2 | No network chip is driven: an unattended install or deploy cannot finish |

The `--lspci` form is for the home base: boot the machine into it, pipe `lspci -nn` in, and every chip any profile knows is checked, so a machine with no profile yet still gets an answer for the parts it shares with one that has.

## The X870E desktop

[`machines/x870e-dark-hero.yaml`](../../machines/x870e-dark-hero.yaml) is the first profile: an ASUS ROG Crosshair X870E Dark Hero with an RX 9070 XT, 64 GB and a 2 TB WD_BLACK SN8100.

| System | Kernel | Result |
| --- | --- | --- |
| bashOS (Amrchy) | 7.2 | Every known chip driven, Wi-Fi included |
| SteamOS 3.9, the home base | 7.2 | Every known chip driven |
| SteamOS 3.8 | 6.16 | No Wi-Fi (MT7927 needs 7.2); both Ethernet ports work |
| Debian 13 | 6.12 | No 10 GbE (needs 6.16), no Wi-Fi |

Still `TBD` on it: the CPU, the graphics card's PCI id and first kernel, and the NVMe drive's exact size in bytes, which the unattended bashOS installer needs (`bashos os iso seed --disk-bytes`). Read them from the home base: `lscpu`, `lspci -nn`, `lsblk -bdno SIZE /dev/nvme0n1`.

## Adding a machine

1. Boot it into the home base (stick or PXE) and collect `lspci -nnk`, `lsblk -b`, `lscpu` and `efibootmgr`.
2. Copy `machines/x870e-dark-hero.yaml` to `machines/<name>.yaml`, where `name` is the file's name, and fill in what you read. Leave anything you did not read as `TBD`.
3. For each chip that needs a driver, find the first kernel that has it (the driver's commit or the kernel's release notes) and record it with a source.
4. `make lint`, then `scripts/oneos-machine check <name> --system <the one you mean to deploy>`.
