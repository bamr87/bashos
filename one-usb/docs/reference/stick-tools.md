# On-stick tools reference

Installed in the home base under `/usr/local/bin/`. `sudo oneusb-install` and
`sudo oneusb-restock` don't ask for a password.

## `oneusb-install`

Install Debian, Ubuntu or Arch onto another drive. **Erases the target.**

```
sudo oneusb-install [--target DISK] [--distro debian|ubuntu|arch] [options]
```

| Option | Default | |
|---|---|---|
| `--target DISK` | asked | whole disk, e.g. `/dev/nvme0n1` |
| `--distro` | `debian` | `debian`, `ubuntu`, `arch` |
| `--suite NAME` | `trixie` / `noble` | Debian/Ubuntu release |
| `--hostname NAME` | `oneusb-<distro>` | |
| `--user NAME` | `oneusb` | gets `sudo` |
| `--password-hash HASH` | asked (locked if `--unattended`) | `openssl passwd -6` output |
| `--mirror URL` | distro default | also `ONEUSB_MIRROR` |
| `--efi` / `--bios` | both | only one boot loader |
| `--unattended` | off | never prompt |

Refuses the disk the home base booted from and disks with mounted partitions. Layout:
1 MB BIOS boot, 512 MB ESP (FAT32), ext4 root. Installs GRUB to the removable UEFI path
and to the MBR, `console=ttyS0` on the kernel command line, and `oneusb-installed-marker.service`
(prints `ONEUSB-INSTALLED-OK` on ttyS0 at boot; used by test T50). Guide: [install an OS](../user-guide/05-install-an-os.md).

## `oneusb-restock`

Keep the stick's ISOs in line with `/oneusb/manifest.yaml` on the stick.

| Command | Does |
|---|---|
| `sudo oneusb-restock` | download missing/outdated ISOs, verify SHA-256, atomic rename |
| `--list` | status of every entry: `ok`, `outdated`, `missing`, `present` |
| `--include-large` | include entries marked `large: true` |
| `--add URL --sha256 SUM [--name N] [--alias TEXT]` | fetch an ISO into `/ISO` and record it in the stick's manifest |
| `--prune` | delete `/ISO` files the manifest doesn't list (try `--dry-run`) |
| `--backup-persistence` | copy `persistence/lightos.dat` → `.dat.bak` |
| `--p1 DIR` | use an already-mounted data partition |
| `--dry-run` | show what would happen |

## `oneusb-mount-p1`

```
sudo oneusb-mount-p1 MOUNTPOINT [rw|ro]
```

Mounts the stick's data partition (label `Ventoy`). While an ISO is booted, Ventoy's
device-mapper mapping holds the partition; if a plain mount fails it creates a linear
device-mapper view (`/dev/mapper/oneusb-p1`) and mounts that. Exit `2` if no `Ventoy`
partition exists.

## `oneusb-selftest`

Runs at boot (`oneusb-selftest.service`). If `/oneusb/selftest/run.sh` exists on the stick
it runs it as root, writes `/oneusb/selftest/results/<name>.json`, prints
`ONEUSB-SELFTEST <name> PASS|FAIL` on ttyS0 and powers off; otherwise prints
`ONEUSB-READY` and exits. `run.sh` headers: `# name: <name>`, `# timeout: <seconds>`
(default 1800). Used by the test harness ([ADR-0003](../adr/0003-selftest-hook-mechanism.md)).
**Don't leave a `run.sh` on a stick you use** — the machine will power off after running it.

## Markers on the serial console

| Marker | Meaning |
|---|---|
| `ONEUSB-READY` | home base booted; P1 mountable |
| `ONEUSB-READY (no Ventoy partition)` | booted without Ventoy (ISO directly) |
| `ONEUSB-READY (P1 not mountable: …)` | booted, but the data partition couldn't be mounted |
| `ONEUSB-SELFTEST-START <name>` / `ONEUSB-SELFTEST <name> PASS\|FAIL` | self-test hook |
| `ONEUSB-INSTALL-DONE <distro> <disk>` | `oneusb-install` finished |
| `ONEUSB-INSTALLED-OK` | an installed system booted |
