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
bin/bashos os iso test                   # install the newest ISO unattended in a KVM VM, check first boot and status
```

`build` fetches Omarchy's ISO builder ([omarchy-iso](https://github.com/omacom/omarchy-iso)) and package recipes ([omarchy-pkgs](https://github.com/omacom/omarchy-pkgs)) at the commits [`os/iso/iso.conf`](../os/iso/iso.conf) pins. It stages `amrchy/` with the layer and runs `omarchy-iso-make --local-source`, which builds the framework's packages from the staged tree and the ISO around them in a privileged Docker container. It needs Docker and about 30 GB free; on Apple Silicon the x86_64 builder runs emulated and slowly. CI is the builder: the `os iso` workflow runs the build and the install test on GitHub's standard runners, as Omarchy builds and tests its own ISO. **The pins move with the framework:** the builder checks the tree it is given, so after `bashos os amrchy pull` brings in a newer upstream, take each builder repository's last commit from the day of the new upstream base.

`seed` writes the configurator's answer files for one machine. You give it the disk to erase and that disk's exact size: run `lsblk -bdno SIZE DEV` on the machine from the one-os home base first, because the layout must fill the disk to the byte. It also writes the user, with sudo, a password hash that is asked for and never stored in clear, and your ssh public keys, which turn sshd on. Attach the result beside the ISO and the install runs with nobody at the keyboard. An unattended install is never encrypted: the passphrase would have to sit on the drive in clear and would still be asked for at the first boot. For an encrypted disk, use the interactive installer.

`test` does in a VM what the ISO will do on a machine. It writes a seed for a 40 GB virtual disk with a key made for the run, boots the ISO beside it in QEMU with KVM, and waits for ssh from the installed system: the live installer has no such user, so only the installed disk answers. It then waits for `bashos-firstboot` to finish and requires `bashos os status` to show base, layer, runtime, engine and provisioning OK, with no CRIT. It keeps a screenshot every three minutes, the serial log, the first-boot log and the status in `build/iso/test/`.

## In CI

[`.github/workflows/os-iso.yml`](../.github/workflows/os-iso.yml) runs `bashos os iso build` then `bashos os iso test` on `ubuntu-26.04`, under KVM. It runs when a pull request or a push to main changes `amrchy/`, `os/iso/`, `os/amrchy/`, the install phases or first boot, and it can be run by hand. It takes about an hour and needs about 40 GB, which the job frees and checks first. The evidence above is uploaded on every run, and the ISO itself (about 6.5 GB, kept 7 days) when a run by hand asks for it with `upload_iso`. The seed's credentials and the run's key are never uploaded.

## Onto a machine

one-os puts the ISO on a machine and checks the machine first ([ONE-OS.md](ONE-OS.md)):

```bash
bin/bashos one-os machine check x870e-dark-hero --system bashos   # every known chip driven by Amrchy's 7.2 kernel?
```

bashOS's machine is the ASUS ROG Crosshair X870E Dark Hero desktop, in forge's place ([its profile](../one-os/machines/x870e-dark-hero.yaml)). Its Wi-Fi needs kernel 7.2 and its 10 GbE port needs 6.16. Debian 13's 6.12 drives neither; Amrchy's `linux-omarchy` drives both. bashOS installs onto its empty 2 TB SATA SSD, and SteamOS stays on the NVMe drive beside it. The profile names the target, so the seed is `bashos os iso seed --user U --hostname x870e $(bin/bashos one-os machine seed-args x870e-dark-hero)`. Installing there is the maintainer's step, because an agent never writes a real disk. The runbook is [OS.md](OS.md#the-x870e-step-by-step).

## What is proven, and what is not

| Step | State |
| --- | --- |
| The layer's install step, first boot, `bashos os install` on Amrchy | Run on Omarchy's own 4.5.0 VM image under QEMU, booted to the multi-user target: first boot was ready in about five minutes, and `bashos os status` reported the base, layer, runtime, engine, harness (answering on :4001), heal timer and provisioning OK; the only warnings were no Claude sign-in and no desktop session. Offline tests in `os/tests/` |
| The console window on the Hyprland desktop | The autostart block and launchers are written (seen in that run); no desktop session was started under emulation |
| Staging the ISO tree, the seed files | Offline tests (`os/tests/test_iso.py`) |
| amrchy's layers runner | `amrchy/test/shell.d/layers-test.sh` |
| Building the ISO, installing it unattended in a VM | The `os iso` workflow, first passed 2026-11-14 ([run](https://github.com/bamr87/bashos/actions/runs/43557590289)). The build took 21 minutes, and the unattended install with first boot 4 minutes under KVM, on kernel 7.2.15-2-omarchy. First boot retried once while the network came up. `bashos os status` showed base, layer, runtime, engine, heal and provisioning OK |
| Installing it on the X870E | The maintainer's step, from the stick or PXE; the [one-os epic](../one-os/docs/epics/0001-bashos-and-amrchy.md), story 7 |
| bashOS's branding of the image | Not started: the installed system's login screen still says Omarchy (`bin/rebrand`, the boot and login screens) |
