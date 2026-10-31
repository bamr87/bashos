# os — bashOS as the operating system

> The Linux OS layer of bashOS: install it onto a Debian 13 machine, or build it into a bootable image, so the monitor boots into the bashOS console and the machine serves the bamr87 Harness Console.

The design, the Omarchy mapping, the security model and the forge runbook are in [docs/OS.md](../docs/OS.md); the base decision is [ADR 0002](../docs/adr/0002-bashos-os-debian-mkosi.md). This file is the reference for the directory.

## Use

```bash
bin/bashos os install --dry-run      # the plan for this machine; changes nothing (works on macOS)
bin/bashos os install                # Debian 13: the layer, the console, the harness (sudo asks once)
bashos os status                     # verdicts; exit 0 OK · 1 WARN · 2 CRIT
bashos os harness url                # where the Harness Console answers (and the ssh -L line)
bashos os update [--system]          # pull, re-apply, migrate (and apt full-upgrade)
bashos os uninstall [--purge]        # remove what install added
bashos os image build --docker       # the bootable disk image (image/README.md)
```

On a fresh Debian 13 box with nothing checked out, the one-liner clones into `/opt/bashos` and runs the same installer: `curl -fsSL https://raw.githubusercontent.com/bamr87/bashos/main/os/boot.sh | bash` (read it first).

## Layout

| Path | What it is |
| --- | --- |
| `os.sh` | The dispatch table: `install`, `update`, `migrate`, `status`, `harness`, `console`, `heal`, `uninstall`, `image`, `version` |
| `install.sh` | The phase runner; `--dry-run`, `--image`, `--user-only`, `--system-only`, `--only`/`--skip PHASE`, `--root DIR` |
| `install/*.sh` | One phase each: `preflight`, `packages`, `runtime`, `system` (root) · `console`, `harness`, `finish` (the user) |
| `lib.sh` | Every helper that changes the machine — and the three switches they all obey: `BASHOS_OS_DRY_RUN`, `BASHOS_OS_ROOT` (a fake root), `BASHOS_OS_IMAGE` |
| `packages/*.list` | Debian package names per concern; a trailing `cmd:NAME` skips the line when `NAME` is already on PATH |
| `config/os.conf` | The shipped defaults, copied once to `/etc/bashos/os.conf` |
| `config/tmux.conf` | tmux defaults, sourced first from `~/.tmux.conf` |
| `bin/bashos-console` | tty1 → kiosk or Linux console → the shared tmux session; `--attach` (ssh), `--heal` (the timer) |
| `bin/bashos-harness` | Runs the hub's Harness Console (`native` / `compose` / `off`); `--print` shows the command |
| `bin/bashos-provision` | An image's first boot: the user, hostname, keys and user phases, from a `BASHOS-SEED` drive or tty1 |
| `systemd/` | `bashos-provision.service` (system) · `bashos-harness.service`, `bashos-heal.{service,timer}` (user) |
| `migrations/` | One-shot `<timestamp>.sh` scripts for existing installs ([README](migrations/README.md)) |
| `image/` | The mkosi image definition, its build wrapper and boot test ([README](image/README.md)) |
| `tests/` | The offline suite: fake root, throwaway `$HOME`, no sudo/apt/systemctl/network |
| `boot.sh` | The curl one-liner |

## Rules for changing it

- **Every change to a machine goes through `lib.sh`** (`os_root`, `os_install_file`, `os_write_file`, `os_link`, `os_block_put`, `os_systemctl`), so `--dry-run` and `--root` stay truthful. A phase never calls `sudo` or writes a system path directly.
- **Idempotent or it is a migration.** A second `bashos os install` must change nothing (`test_install_is_idempotent`). Something a re-run cannot express — a rename, a removal — is a migration.
- **The user's files are theirs.** Only the managed block between the `>>> bashos os managed` markers is ever written; `/etc/bashos/os.conf` and `harness.env` are created once and never rewritten; an existing hand-made hook or getty drop-in is adopted, not duplicated.
- **No loop gains a tool.** Nothing here touches `src/bashos/opencode/policy.py` or the engine's credential path.
- Shell: `set -Eeuo pipefail`, quoted expansions, shellcheck-clean (`make lint`), bash ≥ 4.4 (Debian 13 ships 5.2). Tests: `python -m pytest os/tests -q`.
