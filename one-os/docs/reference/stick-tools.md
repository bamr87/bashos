# On-stick tools reference

Installed in the home base under `/usr/local/bin/`. `sudo oneos-install` and
`sudo oneos-restock` don't ask for a password.

## `oneos-install`

Install Debian, Ubuntu or Arch onto another drive. **Erases the target.**

```
sudo oneos-install [--target DISK] [--distro debian|ubuntu|arch] [options]
```

| Option | Default | |
|---|---|---|
| `--target DISK` | asked | whole disk, e.g. `/dev/nvme0n1` |
| `--distro` | `debian` | `debian`, `ubuntu`, `arch` |
| `--suite NAME` | `trixie` / `noble` | Debian/Ubuntu release |
| `--hostname NAME` | `oneos-<distro>` | |
| `--user NAME` | `oneos` | gets `sudo` |
| `--password-hash HASH` | asked (locked if `--unattended`) | `openssl passwd -6` output |
| `--mirror URL` | distro default | also `ONEOS_MIRROR` |
| `--efi` / `--bios` | both | only one boot loader |
| `--unattended` | off | never prompt |

Refuses the disk the home base booted from and disks with mounted partitions. Layout:
1 MB BIOS boot, 512 MB ESP (FAT32), ext4 root. Installs GRUB to the removable UEFI path
and to the MBR, `console=ttyS0` on the kernel command line, and `oneos-installed-marker.service`
(prints `ONEOS-INSTALLED-OK` on ttyS0 at boot; used by test T50). Guide: [install an OS](../user-guide/05-install-an-os.md).

## `oneos-restock`

Keep the stick's ISOs in line with `/oneos/manifest.yaml` on the stick.

| Command | Does |
|---|---|
| `sudo oneos-restock` | download missing/outdated ISOs, verify SHA-256, atomic rename |
| `--list` | status of every entry: `ok`, `outdated`, `missing`, `present` |
| `--include-large` | include entries marked `large: true` |
| `--add URL --sha256 SUM [--name N] [--alias TEXT]` | fetch an ISO into `/ISO` and record it in the stick's manifest |
| `--prune` | delete `/ISO` files the manifest doesn't list (try `--dry-run`) |
| `--backup-persistence` | copy `persistence/lightos.dat` → `.dat.bak` |
| `--p1 DIR` | use an already-mounted data partition |
| `--dry-run` | show what would happen |

## `oneos-mount-p1`

```
sudo oneos-mount-p1 MOUNTPOINT [rw|ro]
```

Mounts the stick's data partition (label `Ventoy`). While an ISO is booted, Ventoy's
device-mapper mapping holds the partition; if a plain mount fails it creates a linear
device-mapper view (`/dev/mapper/oneos-p1`) and mounts that. Exit `2` if no `Ventoy`
partition exists.

## `oneos-selftest`

Runs at boot (`oneos-selftest.service`). If `/oneos/selftest/run.sh` exists on the stick
it runs it as root, writes `/oneos/selftest/results/<name>.json`, prints
`ONEOS-SELFTEST <name> PASS|FAIL` on ttyS0 and powers off; otherwise prints
`ONEOS-READY` and exits. `run.sh` headers: `# name: <name>`, `# timeout: <seconds>`
(default 1800). Used by the test harness ([ADR-0003](../adr/0003-selftest-hook-mechanism.md)).
**Don't leave a `run.sh` on a stick you use** — the machine will power off after running it.

## Markers on the serial console

| Marker | Meaning |
|---|---|
| `ONEOS-READY` | home base booted; P1 mountable |
| `ONEOS-READY (no Ventoy partition)` | booted without Ventoy (ISO directly) |
| `ONEOS-READY (P1 not mountable: …)` | booted, but the data partition couldn't be mounted |
| `ONEOS-SELFTEST-START <name>` / `ONEOS-SELFTEST <name> PASS\|FAIL` | self-test hook |
| `ONEOS-INSTALL-DONE <distro> <disk>` | `oneos-install` finished |
| `ONEOS-INSTALLED-OK` | an installed system booted |
