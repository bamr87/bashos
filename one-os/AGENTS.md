# one-os — working notes for coding agents

> How to work in one-os: the ground rules (never write a real disk), the build and test loop, the live-VM tool and the map. The repo-wide rules are in the [root AGENTS.md](../AGENTS.md).

one-os builds, boots, manages and deploys machines. Today that is one stick (Ventoy menu →
persistent Debian "home base" + netboot.xyz + offline ISOs), a PXE server and a SteamOS
deployer, all built from `manifest.yaml` and tested in QEMU. Paths below are relative to
`one-os/`; run commands from there (or `bin/bashos one-os <target>` from the repo root). Read `PLAN.md` and `docs/adr/` before
changing design; `docs/spike.md` records what was proven and the traps found.

## Ground rules

- **Never write a real disk.** No `make flash`, `scripts/flash*.sh`, `write-image.py`,
  `dd`, `diskutil erase*`, or `oneos-install` against hardware. Those are the human's
  steps (they need the admin password in macOS's authorization dialog + a typed confirmation). Physical sticks may be *booted*
  read-only: `sudo scripts/oneos-vm start NAME --disk diskN` — ask the human to run it.
- Disk numbers on macOS change on re-insert; check `diskutil list` every time.
- `--apt-recommends false` has bitten twice (no X server; no `user-setup` → no login).
  When adding desktop/live features, list Recommends explicitly and add a test.
- "Process exists" ≠ "works": under TCG the Xfce session starts minutes before anything
  is drawn. Wait for the concrete thing (panel + desktop), then screenshot.
- Prove features with tests, not by eye: the harness is the definition of done.

## Build → test loop

```bash
make lint                       # shellcheck, ruff, manifest schema (fast, run often)
make lightos                    # home-base ISO, ~25 min on Apple Silicon (amd64 emulated)
make payload image              # stage P1 tree + 16 GB sparse test image (~3 min)
make test ARGS="-k t21 -v"      # one test; `make test` = fast suite (~30 min under TCG)
```

On macOS every Linux-only step runs in the Docker builder (`docker/builder.Dockerfile`);
VMs for tests run inside it too. Test artifacts: `build/test-runs/<test>/` (serial log,
pcap, screenshots, QEMU log, selftest JSON).

## Live VMs: `scripts/oneos-vm` (runs on the host, no Docker)

Named instances in `build/vms/NAME/`, persistent across stop/start. Every VM has three
control sockets: QMP (screen/keys/power), ttyS0 serial (interactive + logged), and
**qemu-guest-agent** (root exec + file copy, no network or password — ADR-0004).

```bash
scripts/oneos-vm start dev                 # headless, card/test image via overlay (--window to watch)
scripts/oneos-vm wait dev --agent          # ~90 s under TCG
scripts/oneos-vm exec dev -- systemctl --failed
scripts/oneos-vm exec dev -- 'journalctl -b -u lightdm --no-pager | tail -50'
scripts/oneos-vm cp dev vm:/var/log/Xorg.0.log build/
scripts/oneos-vm screenshot dev            # prints a PNG path → Read it to see the screen
scripts/oneos-vm keys dev ctrl-alt-f2      # QMP qcodes; `type dev 'text\n'` for strings
scripts/oneos-vm console dev --send '\n'   # ttyS0 (getty: user/live)
scripts/oneos-vm status dev                # state, READY marker, agent, last serial lines
scripts/oneos-vm stop dev                  # clean poweroff (keeps persistence consistent)
```

Other shapes: `--profile bios`, `--fresh` (new overlay/NVRAM), `--iso build/oneos-lightos.iso`
(no Ventoy), `--target 20G` (install disk /dev/vda) then `--no-usb` to boot only that disk.
The human sees the same instance with `make run` (instance `run`, windowed).

Debugging order of preference: `exec` (journal, systemctl, files) → `serial` (early boot,
kernel, Ventoy hand-off) → `screenshot` + Read (menus, desktop) → `console` (agent down).
If the agent never comes up: `serial` shows how far boot got; the Ventoy menu and GRUB
are screen-only (screenshot), the kernel and systemd log to ttyS0.

## Flash wizard

`make wizard` (ui/server.py + ui/index.html) is the human's repeatable flash flow; its
jobs call the same make targets / scripts. You may start it and drive its read-only
API (`/api/state`, `/api/devices`) or build steps, but the `flash` step is the human's
(admin password + typed confirmation). Logs: `build/wizard/*.log`.

## Documentation

`docs/README.md` is the index (user / operator / developer guides + reference). When you
change behaviour, update the page that describes it. `make docs-screenshots` regenerates
`docs/images/` from real VMs and the wizard — look at every image before keeping it.
Mermaid diagrams must parse (no `;` or `{}` in sequence messages).

## Map

- `manifest.yaml` — pins; `scripts/manifest.py lint` enforces schema/no `<PIN>`
- `machines/` — machine profiles (parts, firmware, chips and their first kernels) and the systems'
  kernels; `scripts/oneos-machine check NAME --system SYS` before any deploy (docs/reference/machines.md)
- `lightos/` — live-build tree; tools in `config/includes.chroot/usr/local/bin/`
- `scripts/` — fetch, build, stage, install-to-device, flash (Linux/macOS), lint, bump
- `ui/` — flash wizard (stdlib HTTP server + single page)
- `remote/agent/` + `scripts/oneos-remote` — drive an installed machine over SSH: screenshots, uinput keyboard and
  pointer, recorded Claude Code sessions in tmux, connection log and screen recording (operator guide 06)
- `harness/oneos_harness/` — `qemu.py` (VM), `qga.py` (agent), `overlay.py` (P1 edits via nbd),
  `cli.py` (oneos-vm), `netcap.py`, `screen.py`; tests in `harness/tests/` (IDs in README)
