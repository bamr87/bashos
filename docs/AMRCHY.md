# amrchy, the framework under bashOS

> How bashOS boots on a machine: amrchy (the Omarchy fork, kept in `amrchy/` as a squashed subtree of bamr87/amrchy) is the framework, bashOS is the layer on it, and `bashos os iso` builds the two into one ISO that installs unattended from a `cidata` drive.

bashOS is a terminal-first AI runtime; on a machine of its own it needs an operating system around it. That operating system is [Amrchy](../amrchy/README.md), the maintainer's fork of [Omarchy](https://omarchy.org): Arch Linux, the Hyprland compositor, a Quickshell desktop, Omarchy's installer, updates and migrations. bashOS sits on it as a layer. Why it is built this way is [ADR 0005](adr/0005-bashos-is-amrchy-plus-a-layer.md); why a fork of Omarchy at all is [ADR 0003](adr/0003-bashos-on-omarchy.md).

```text
 omacom/omarchy ──daily AI sync──▶ bamr87/amrchy ──git subtree pull──▶ bashos/amrchy/   the framework
                                          ▲                                 │
                                          └──── git subtree push (a PR) ────┘
 bashos/os/amrchy/layer + the bashOS tree ──▶ amrchy/install/layers/bashos/          the layer
 omarchy-iso + omarchy-pkgs (pinned) ──build──▶ bashos-*.iso ──one-os──▶ a machine    the image
```

## The framework: `amrchy/`

`amrchy/` is a squashed git subtree of [bamr87/amrchy](https://github.com/bamr87/amrchy): Omarchy's tree at the upstream commit the fork last synced to, plus the fork's own files. Those are `bin/rebrand` and `default/brand.toml` (the brand applied at build time), and `bin/upstream-sync`, `default/upstream.toml` and `.upstream/ledger.tsv` (the AI upstream sync). bamr87/amrchy is still the fork of record. Its daily sync opens a pull request there, and this repo follows it:

```bash
bin/bashos os amrchy status         # the commit amrchy/ holds, what bashos changed in it since, bamr87/amrchy's main
bin/bashos os amrchy pull           # bamr87/amrchy main → amrchy/, one squashed commit (then make test, make lint)
bin/bashos os amrchy push BRANCH    # bashos's commits to amrchy/ → bamr87/amrchy BRANCH, for a pull request there
```

Rules for `amrchy/`:

- **It is upstream's code, in upstream's naming and style.** Commands stay `omarchy-*`, paths `/usr/share/omarchy`. Its own [AGENTS.md](../amrchy/AGENTS.md) governs it: bash 5 conditionals, `#!/bin/bash`, and its tests in `amrchy/test/`. This repo's ruff skips it, and its Markdown is not held to this repo's rules.
- **Change the framework only where every layer gets the change.** A bashOS-specific change belongs in the layer (`os/amrchy/layer/`), not in `amrchy/`.
- **A change made here goes back.** Push it as a branch, merge it on bamr87/amrchy, then pull. Otherwise the next upstream sync there does not have it.
- **The upstream sync runs there, not here.** Its policy (`amrchy/default/upstream.toml`) lists the fork-owned paths, the layers runner among them.

## The layer: `os/amrchy/layer/`

amrchy runs a product's setup through **layers** ([amrchy/docs/layers.md](../amrchy/docs/layers.md)). A layer is `install/layers/<name>/` with a `system.sh`, which runs as root in the installed target after the framework's own system setup, and a `user.sh`, which runs once for each user. bashOS's layer is [`os/amrchy/layer/system.sh`](../os/amrchy/layer/system.sh). The installer has no network, so it does only the offline part:

1. It copies the bashOS tree the layer carries to `/opt/bashos`, root-owned.
2. It writes `/etc/bashos/os.conf` if there is none, and the build stamp `/etc/bashos/build-info`.
3. It records the person the installer created (`/etc/bashos/firstboot.env`) and arms `bashos-firstboot.service`.

At first boot, [`bashos-firstboot`](../os/bin/bashos-firstboot) waits for a user and for PyPI and npm to answer. Until both are there it exits 75, and the unit starts it again a minute later. Then it runs the system phases of `bashos os install` (packages through pacman, the Python runtime, the managed OpenCode engine, the units) and the user phases as that user. It disarms itself and prints `bashos-firstboot: ready user=… host=…` on the console. A failure is recorded in `/var/lib/bashos/firstboot-failed` and shown by `bashos os status`; `sudo bashos-firstboot` tries again.

On Amrchy the console is a window, not tty1. The login screen keeps tty1. Hyprland opens the shared tmux console in a terminal at login (a managed block in `~/.config/hypr/autostart.lua`), and the app launcher lists **bashOS Console** and **bashOS** ([OS.md](OS.md)).

## The image: `bashos os iso`

```bash
bin/bashos os iso build --print-pins     # the builder commits and the amrchy commit
bin/bashos os iso build --stage-only     # build/iso/stage/amrchy: the framework with the layer, nothing built
bin/bashos os iso build                  # build/iso/bashos-<date>-<commit>-x86_64.iso (+ .sha256, .build-info)
bin/bashos os iso seed --user amr --disk /dev/nvme0n1 --disk-bytes N --hostname x870e
                                         # build/iso/cidata/ and cidata.iso: the unattended install for one machine
```

`build` fetches Omarchy's ISO builder ([omarchy-iso](https://github.com/omacom/omarchy-iso)) and package recipes ([omarchy-pkgs](https://github.com/omacom/omarchy-pkgs)) at the commits [`os/iso/iso.conf`](../os/iso/iso.conf) pins. It stages `amrchy/` with the layer and runs `omarchy-iso-make --local-source`, which builds the framework's packages from the staged tree and the ISO around them in a privileged Docker container. It needs Docker and about 30 GB free. On Apple Silicon the x86_64 builder runs emulated and slowly, so a Linux x86_64 machine is the practical builder. **The pins move with the framework:** the builder checks the tree it is given, so after `bashos os amrchy pull` brings in a newer upstream, take each builder repository's last commit from the day of the new upstream base.

`seed` writes the configurator's answer files for one machine. You give it the disk to erase and that disk's exact size: run `lsblk -bdno SIZE DEV` on the machine from the one-os home base first, because the layout must fill the disk to the byte. It also writes the user, with sudo, a password hash that is asked for and never stored in clear, and your ssh public keys, which turn sshd on. Attach the result beside the ISO and the install runs with nobody at the keyboard. An unattended install is never encrypted: the passphrase would have to sit on the drive in clear and would still be asked for at the first boot. For an encrypted disk, use the interactive installer.

## Onto a machine

one-os puts the ISO on a machine and checks the machine first ([ONE-OS.md](ONE-OS.md)):

```bash
bin/bashos one-os machine check x870e-dark-hero --system bashos   # every known chip driven by Amrchy's 7.2 kernel?
```

The first target is the ASUS ROG Crosshair X870E Dark Hero desktop ([its profile](../one-os/machines/x870e-dark-hero.yaml)). Its Wi-Fi needs kernel 7.2 and its 10 GbE port needs 6.16. Debian 13's 6.12 drives neither; Amrchy's `linux-omarchy` drives both. Booting the ISO there, from the stick or over PXE, is the maintainer's step: an agent never writes a real disk.

## What is proven, and what is not

| Step | State |
| --- | --- |
| The layer's install step, first boot, `bashos os install` on Amrchy | Run on Omarchy's own 4.5.0 VM image under QEMU, booted to the multi-user target: first boot was ready in about five minutes, and `bashos os status` reported the base, layer, runtime, engine, heal timer and provisioning OK. Offline tests in `os/tests/` |
| The console window on the Hyprland desktop | The autostart block and launchers are written (seen in that run); no desktop session was started under emulation |
| Staging the ISO tree, the seed files | Offline tests (`os/tests/test_iso.py`) |
| amrchy's layers runner | `amrchy/test/shell.d/layers-test.sh` |
| Building the ISO | Not yet run (Docker, about 30 GB) |
| Installing the ISO unattended in QEMU, then on the X870E | Not yet run; the [one-os epic](../one-os/docs/epics/0001-bashos-and-amrchy.md) holds both |
| bashOS's branding of the image | Not started (`bin/rebrand`, the boot and login screens) |
