# bashOS, the operating system

> How bashOS becomes the machine itself: one OS layer (`os/`) that turns an Amrchy (Arch) or Debian 13 machine into a bashOS machine, with the shared console and the bamr87 Harness Console. It arrives in place (`bashos os install`), as the Amrchy ISO with bashOS as its layer (`bashos os iso`, the primary path), or as the Debian disk image built with mkosi, and this page also covers how forge moves onto it.

bashOS started as a program you run in a terminal. `os/` makes it the terminal a machine boots into: the monitor auto-logs in to one shared tmux session whose first window is the bashOS desktop, every ssh login joins the same session, the hub's Harness Console runs as a supervised service, and the whole thing updates itself the way Omarchy does. Nothing in the kernel, the loops or the policy changes — this is userland and plumbing around them, so every hard rule in [AGENTS.md](../AGENTS.md) holds as before.

The machine it was built for is **forge** ([FORGE.md](FORGE.md)): an i7-3820 with 32 GB, a 1 TB SATA SSD, a GTX 660 on nouveau, UEFI, Debian 13. Its hand-written `~/setup/01…06` scripts are the prior art this layer generalises.

## Two bases

The layer installs on either of two operating systems, and reads which one it is on from `/etc/os-release` (`os_base` in [`os/lib.sh`](../os/lib.sh)):

| Base | What it is | Packages | The console | How it arrives |
| --- | --- | --- | --- | --- |
| **Amrchy** (primary, [ADR 0005](adr/0005-bashos-is-amrchy-plus-a-layer.md)) | The Omarchy fork in [`amrchy/`](../amrchy/README.md): Arch, Hyprland, Omarchy's installer and updates | `os/packages/arch/*.list` through pacman (`--needed`, refreshing the sync databases a fresh install lacks) | `desktop`: a terminal window opened at login (a managed block in `~/.config/hypr/autostart.lua`) and two launcher entries; the login screen keeps tty1 | The bashOS ISO, whose layer arms `bashos-firstboot` ([AMRCHY.md](AMRCHY.md)), or `bashos os install` on an existing Amrchy |
| **Debian 13** ([ADR 0002](adr/0002-bashos-os-debian-mkosi.md)) | Debian 13 or a derivative (Raspberry Pi OS); forge today | `os/packages/*.list` through apt | tty1 autologin into a kiosk (cage + foot) or the Linux console | `bashos os install` in place, or the mkosi image below (no new work, per ADR 0005) |

Everything else is the same on both: `/opt/bashos`, the runtime, the managed engine, the units, the shared tmux session that ssh logins join, the harness, migrations, `bashos os status`. The rest of this page was written for forge, on Debian; where Amrchy differs, the table above says how.

## The shape, borrowed from Omarchy

[Omarchy](https://github.com/basecamp/omarchy) is an opinionated layer on Arch Linux shipped two ways: a one-line install on top of a base system, and an ISO that writes a pre-built root image with the layer already applied, provisions the machine (unattended from a `cidata` drive, or with a configurator) and boots into it. Updates are `git pull` plus timestamped migrations. bashOS takes the same shape and keeps Debian, because forge runs it and every hard-won rule in FORGE.md was learned on it:

| Omarchy | bashOS | Where |
| --- | --- | --- |
| `curl … \| bash` onto a base install | `curl -fsSL …/os/boot.sh \| bash`, or `bashos os install` from a checkout | [`os/boot.sh`](../os/boot.sh), [`os/install.sh`](../os/install.sh) |
| Ordered install phases (`install/*/all.sh`) | `preflight → packages → runtime → system` (root) then `console → harness → finish` (the user) | [`os/install/`](../os/install/) |
| Package lists (`omarchy-base.packages`) | `os/packages/*.list`, with a `cmd:` guard so an existing tool is never swapped out | [`os/packages/`](../os/packages/) |
| `omarchy-*` commands | `bashos os <verb>` (`/usr/local/bin/bashos-os`), `bashos-console`, `bashos-harness`, `bashos-provision` | [`os/os.sh`](../os/os.sh), [`os/bin/`](../os/bin/) |
| `default/` sourced by user configs | Managed blocks in dotfiles; `~/.tmux.conf` sources `os/config/tmux.conf` first, so the user's lines win | [`os/lib.sh`](../os/lib.sh) `os_block_put` |
| `migrations/<timestamp>.sh`, state in `~/.local/state` | the same, run by `bashos os update`; a fresh install marks them applied | [`os/migrations/`](../os/migrations/README.md) |
| The ISO: a pre-built root image, dd, grow, provision | A mkosi GPT disk image: systemd-boot + UKI, root grows to the disk on first boot, `bashos-provision` sets it up | [`os/image/`](../os/image/README.md) |
| `cidata` drive for unattended installs | a `BASHOS-SEED` drive (`seed.env`, `authorized_keys`, `harness.env`) | [`os/image/seed.example/`](../os/image/seed.example/README.md) |
| CI installs the ISO in a VM and boots it | `os image` workflow: build, boot under KVM with a seed, check like a user | [`.github/workflows/os-image.yml`](../.github/workflows/os-image.yml) |
| Hyprland desktop | a kiosk: `cage` (Wayland) running `foot` on the shared tmux session; the plain Linux console when there is no GPU | [`os/bin/bashos-console`](../os/bin/bashos-console) |

The base choice is recorded in [ADR 0002](adr/0002-bashos-os-debian-mkosi.md), including why not Arch (Omarchy's base) and why not bootc (the [reference architecture](ARCHITECTURE.md)'s L0).

## What a bashOS machine is

```
 power on ─▶ systemd-boot ─▶ UKI (Debian 13 kernel) ─▶ systemd
                                                         │
   first boot only: bashos-provision ◀── BASHOS-SEED ────┤  user · hostname · keys · harness.env
                                                         │
   tty1 (the monitor) ─ autologin ─▶ bashos-console ─────┤  kiosk: cage ▸ foot ▸ tmux attach
                                                         │  or the Linux console ▸ tmux attach
   ssh login ──────────────────────▶ bashos-console --attach (the same session; NOTMUX=1 skips)
                                                         │
   tmux session "console":  [bashos] the desktop · [ai] remote mirror · [dash] … · your windows
                                                         │
   user manager (linger):   bashos-harness.service ─▶ the hub's tools/console/run.sh  :4001
                            bashos-heal.timer      ─▶ bashos-console --heal  (every 10 min)
```

| Piece | What it is | Owned by |
| --- | --- | --- |
| `/opt/bashos` | The bashOS checkout, root-owned: the platform is not writable by the user's processes or the agents they run | `bashos os update` (sudo) |
| `/opt/bashos/.venv` | The runtime (`pip install -e`, always-latest) | the runtime phase |
| `/usr/local/bin/{bashos,os-health,bashos-os,bashos-console,bashos-harness}` | Absolute paths for tmux panes and systemd units (forge rule: a pane's PATH is bare) | the runtime phase |
| `/etc/bashos/os.conf` | The machine's settings, copied once from [`os/config/os.conf`](../os/config/os.conf) and never overwritten; `~/.config/bashos/os.conf` overrides per user; an exported `BASHOS_*` wins over both | the machine |
| `/usr/local/lib/systemd/{system,user}/bashos-*` | The units, in the vendor path so updates replace them and `systemctl edit` drop-ins survive | the system phase |
| `getty@tty1 … bashos-autologin.conf` | The monitor logs the user in (skipped when a drop-in already does) | the system phase |
| `~/.config/bashos/harness.env` | The Harness Console's secrets (`DASH_CONSOLE_TOKEN`, `GH_TOKEN`), mode 0600, created once | the user |
| `~/dev/bamr87` | The hub checkout the harness serves (`BASHOS_HUB_DIR`); cloned if absent, never touched if present | the user |

## Onto a machine

**The bashOS ISO** — Amrchy with bashOS as its layer, installed by the framework's own installer, interactively or unattended from a `cidata` drive. This is the path for a new machine, the X870E desktop first. [AMRCHY.md](AMRCHY.md) covers building it, seeding it and what happens at first boot. On Debian there are two more ways:


**In place** — the Omarchy one-liner, for a Debian 13 box that already has a life (forge today). Additive and reversible: `bashos os uninstall` removes every file, link, unit and managed block it added (`--purge` also removes `/opt/bashos` and `/etc/bashos`); the hub checkout, linger and sleep masks are left as they are.

```bash
bin/bashos os install --dry-run      # every change it would make, on any machine (macOS too)
bin/bashos os install                # as the machine's user; sudo asks once for the system phases
bashos os status                     # [ OK ]/[WARN]/[CRIT] per piece; exit = the worst verdict
```

**As an image** — the Omarchy ISO, for a fresh machine or a disk to replace. [`os/image/README.md`](../os/image/README.md) is the full procedure; in short:

```bash
bashos os image build --docker --arch x86-64      # mkosi in debian:trixie → os/image/mkosi.output/bashos_<v>.raw
bashos os image test --docker --arch x86-64       # QEMU + a seed drive: provisions, ssh, status, harness
sudo dd if=bashos_<v>.raw of=/dev/sdX bs=4M conv=fsync status=progress   # a USB stick or the target disk
```

The first boot grows the root partition and filesystem to fill the disk, then `bashos-provision` reads the `BASHOS-SEED` drive (or asks on the monitor), creates the user, names the machine, installs the ssh keys, enables tty1 autologin and linger, and runs the user phases as that user — which clone the hub and start the harness.

## The console

`BASHOS_CONSOLE` picks what the monitor shows. `auto` (the default) starts the kiosk — `cage -s -- bashos-console --kiosk`, which runs `foot … bashos-console --attach` — when `cage`, `foot` and a DRM device exist, because the bare Linux console has 16 colours and a 512-glyph font and the Textual desktop deserves truecolor. A kiosk that dies falls back to the Linux console and is not retried for a minute; `vt` skips the kiosk; `off` leaves tty1 alone.

Either way the monitor is one client of the tmux session `console`, so everything FORGE.md built on that still works: `bashos remote ask forge …` pops its overlay on whichever client sits on the console, the `ai` window keeps its transcript, and `window-size latest` (in [`os/config/tmux.conf`](../os/config/tmux.conf)) keeps a long-gone client from pinning the size. `bashos-heal.timer` re-adds a closed `bashos` window every 10 minutes and never starts a server, attaches, prints or changes focus.

**Orientation.** `BASHOS_CONSOLE_ROTATE` takes xrandr's words: `normal`, `left` (the picture turned 90° counter-clockwise, for a monitor stood on its right edge), `right` or `inverted`. Inside the kiosk, `bashos-console --kiosk` turns every output with `wlr-randr` (cage implements output management) before it starts the terminal. For the plain Linux console, the system phase writes a udev rule that sets fbcon's `rotate_all` when a framebuffer appears. forge's Dell U2415 stands in portrait: `left`.

**Remote keyboard and mouse.** With `BASHOS_CONSOLE_VNC=yes`, the kiosk also starts `wayvnc` on the monitor. cage provides the screen capture and the virtual keyboard and pointer it needs. `wayvnc` always binds `127.0.0.1` (port `BASHOS_CONSOLE_VNC_PORT`, 5900), whatever its config says, so ssh is the only way in. From a Mac: `ssh -N -L 5901:127.0.0.1:5900 HOST`, then open `vnc://localhost:5901` in Screen Sharing (Finder ▸ Go ▸ Connect to Server). Local port 5901 avoids the Mac's own Screen Sharing server on 5900. The account is in `~/.config/bashos/wayvnc.conf` (mode 0600, created once by the console phase with a generated password, never printed): the user name, and the password Screen Sharing asks for. It uses Apple Diffie-Hellman (`relax_encryption=true`), the password scheme Screen Sharing speaks; the ssh tunnel encrypts the session. The plain Linux console has no VNC, but ssh logins join the same tmux session anyway.

An existing hand-made hook is adopted, never duplicated: if `~/.zprofile` already sends tty1 into tmux (forge's `console-mirror:tty1`), or a getty drop-in already auto-logs the user in, the installer says so and leaves it; the heal timer still adds the `bashos` window to that session.

## The harness

`bashos-harness.service` (a user unit, started at boot by linger) serves the bamr87 hub's **Harness Console** — the FastAPI + React front end of [`tools/console/`](https://github.com/bamr87/bamr87/tree/main/tools/console) — from `BASHOS_HUB_DIR`:

| `BASHOS_HARNESS` | Runs |
| --- | --- |
| `native` (default) | `tools/console/run.sh` as the user: its own venv, always-latest requirements, the page built with npm |
| `compose` | the hub's `console` compose service in the foreground, so systemd supervises it; a LAN bind adds the hub's `compose/forge.yml` overlay |
| `off` | nothing |

It binds `127.0.0.1:4001` by default; reach it from another machine with `ssh -L 4001:127.0.0.1:4001 forge`. A LAN address (`BASHOS_HARNESS_HOST=0.0.0.0`) is refused unless `DASH_CONSOLE_TOKEN` is set in `harness.env`; it then answers to `HOST`, `HOST.local` and loopback (`DASH_CONSOLE_ALLOWED_HOSTS`), and with `BASHOS_LAN_CIDR` set the installer opens the port in ufw for that subnet only. The console keeps its own rules — allowlisted operations, confirm-gated GitHub writes, never commits or merges — bashOS only supervises the process.

## The engine

OpenCode is the dependency every bashOS command runs on, so a bashOS machine owns its own copy and keeps it on OpenCode's latest release ([`os/install/engine.sh`](../os/install/engine.sh)). `latest` means what npm's `latest` tag names for `opencode-ai`.

- **Fetched, not npm-installed.** bashOS downloads OpenCode's own platform binary straight from the registry and checks it against the registry's sha512, so no Node is needed. It lives root-owned in `/usr/local/lib/bashos/opencode/<version>`, so nothing running as the user can swap the binary that enforces the policy. On x86-64 it always takes the `-baseline` build: one disk boots on any CPU, and forge's i7-3820 has no AVX2.
- **Verified before it's trusted.** A new release is promoted (one atomic rename of `current`) only after `bashos opencode verify` passes against it. That command boots the engine and judges the permission rules *it* resolved from `opencode.jsonc` against `opencode/policy.py`: denied tools refused, bash refusing every known way out, probes and reads still running, the sealed agent with no tools at all. A release that fails is never installed, and the machine stays on the last one that passed. If `latest` is a new major the contract rejects (OpenCode 2 today, [#71](https://github.com/bamr87/bashos/issues/71)), the machine moves to the newest release of the major it runs instead. The previous release is kept for a rollback.
- **Daily.** `bashos-engine-update.timer` runs `bashos os engine update` once a day (`BASHOS_ENGINE_UPDATE=daily`; `off` leaves it to `bashos os update`). `bashos os status` shows the version, the last verdict and how old it is. `bashos os engine status` shows the build, the kept releases, and any other `opencode` on PATH.
- **Preferred over PATH.** `/etc/bashos/opencode` names the managed binary, and bashOS runs it ahead of whatever `opencode` is first on PATH (`BASHOS_OPENCODE_BIN` still overrides). `/usr/local/bin/opencode` points at it unless that name belongs to something else.
- **Watched upstream.** The `engine canary` workflow fetches npm's latest OpenCode every day the way a machine does and runs the contract, so an incompatible release shows up the day it ships.

## Updates

`bashos os update` is Omarchy's update: fetch the channel (`BASHOS_CHANNEL`, default `main`) into `/opt/bashos` with a fast-forward merge (an image's staged copy becomes a checkout on its first update), re-run the idempotent installer from the new code, run pending migrations, restart the harness. `--system` adds `apt-get full-upgrade`; Debian's unattended-upgrades already applies security fixes daily. `-n` previews all of it.

## Security model

- **No loop gains anything.** The OS layer adds no tool to `opencode/policy.py`, no network or write capability to any loop, and no credential to `opencode.jsonc`. The engine still gets the Claude Code credential through its environment only.
- **The platform is root-owned.** `/opt/bashos`, its venv and the units change only through sudo (`bashos os update`), so a process running as the user — including anything an agent is talked into — cannot rewrite the layer it runs on. This is the [reference architecture](ARCHITECTURE.md)'s "immutable by policy" goal in its first, mutable-root form; a read-only `/usr` with A/B updates is the roadmap below.
- **The seed is data.** `bashos-provision` reads only known `KEY=value` lines from `seed.env` and never sources it; keys and secrets land 0600 in the user's home. Baking a seed into an image (`--seed`) is possible and warned about — the image file then carries it.
- **VNC is loopback-only and password-protected.** `wayvnc` binds `127.0.0.1` from the command line, so it can't be widened by editing its config. The only way in is an ssh login, and a VNC password is still required on top.
- **The harness is loopback unless tokened.** No LAN listener without `DASH_CONSOLE_TOKEN`; no firewall rule without an explicit `BASHOS_LAN_CIDR`.
- **Physical access is the trust boundary on the console.** Autologin on tty1 is forge's existing trade; with `BASHOS_SUDO_NOPASSWD=yes` whoever holds the keyboard is root. The seed's default is `no`.

## forge, step by step

Each step is a deploy that changes forge, so each is run only after an explicit go-ahead (hub constitution § 10). The order goes from most reversible to least:

1. **In place, harness only.** `bin/bashos os install --dry-run` on forge, review, then install. forge's console mirror and getty drop-in are adopted, so the monitor keeps working exactly as now; what changes is `/opt/bashos`, the units, a `bashos` window in the console session and the Harness Console as a supervised service on `127.0.0.1:4001` (nothing listens there today). Undo: `bashos os uninstall`.
2. **The image, from USB, once.** Write the x86-64 image to a USB stick, plug it into one of forge's **black USB 2.0 ports**, add an entry with `sudo efibootmgr --create-only` (the boot order stays Debian's), `sudo efibootmgr --bootnext <entry>` and reboot: forge boots bashOS once and returns to Debian on the next reboot. forge's DX79SI firmware (2014) can't boot from its blue USB 3.0 ports, which are on NEC uPD720200 add-on controllers. It silently falls back to Debian, and after the warm reboot that controller didn't come back in Linux either. Secure Boot needs to be off; forge's firmware has none.
3. **The image, for good.** Only after an off-box backup (forge's restic repository lives on the same disk): either a second disk, or the image written over `sda`. forge's volume group has ~464 GB unallocated, so a side-by-side install is possible, but systemd-boot finds a root by GPT partition type, not inside LVM, so it needs a partition of its own.

## Roadmap

- **Immutable `/usr` + A/B updates** with `systemd-sysupdate` and dm-verity — the reference architecture's L0 without leaving Debian or mkosi.
- **Secure Boot**: mkosi signs the UKI and systemd-boot with an enrolled key.
- **Snapshots before an update** (Omarchy's `omarchy-snapshot`), on a btrfs root.
- **An installer image** that writes the root image to a chosen disk (Omarchy's configurator), rather than `dd` of the whole disk image.
