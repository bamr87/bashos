# Field report: SteamOS on an X870E desktop — "No networks found"

**Date:** 2026-11-12 · **Machine:** ASUS ROG Crosshair X870E Dark Hero, AMD RX 9070 XT,
64 GB, WD_BLACK SN8100 2 TB (`nvme0n1`) · **Goal:** install SteamOS on the M.2, then get
Wi-Fi working · **Outcome:** SteamOS installed and online over Ethernet; Wi-Fi waits on
the SteamOS 3.9 update (kernel 7.2).

This report is the record of one long debugging session: what broke, how each cause was
found, what was fixed where, and what to do differently. The SteamOS user guide has the
short version ([Install SteamOS → Troubleshooting](../user-guide/07-steamos.md#troubleshooting)).

> **Naming:** when this happened the project was called *one-usb*. On the machine described here
> the guard unit is `oneusb-nm-guard.service` and the SSH files are `oneusb_*`; media built today use `oneos-*`.

## The board's network hardware

| Port | Chip | Linux driver | Kernel 6.12 (home base before) | Kernel 6.16 (SteamOS 3.8) | Kernel 7.2 (home base now, SteamOS 3.9) |
|---|---|---|---|---|---|
| 5 GbE | Realtek RTL8126 | `r8169` (since 6.9) | ✅ | ✅ | ✅ |
| 10 GbE | Realtek RTL8127 | `r8169` (since 6.16) | ❌ | ✅ (warns: no `rtl8127a-1.fw`) | ✅ |
| Wi-Fi 7 | MediaTek MT7927 (`14c3:7927`) | `mt7925e` (mainline 7.2) | ❌ | ❌ | ✅ |

Firmware can network-boot from a port that the OS kernel can't drive yet. That was the
first trap (the PC PXE-booted from the 10 GbE port, then Linux waited for a link forever).

## Six problems, in the order they were met

| # | Symptom | Real cause | Found by | Fix | Where |
|---|---|---|---|---|---|
| 1 | Netboot stops at *waiting for a link* | Booted from the 10 GbE port; no driver in kernel 6.12 | Overlay message naming the PXE MAC vs the NICs Linux saw | Cable to the 5 GbE port; backports kernel 7.2 in the home base | one-os `netboot/initrd/`, `manifest.yaml` |
| 2 | Network SteamOS installer fails 3× | No efivarfs / no udev data in the chroot; writes to `/dev/ttyS0` block on a real UART | Installer log over the status channel | Mount efivarfs, bind `/run/udev`, never block on serial | `oneos-steamos` |
| 3 | SteamOS "installed" but *No networks found*; `update` fails with *`/dev/disk/by-partsets/B/rootfs` not found* | The PC was running the **recovery card**, not the M.2 (firmware picked the card's entry) | `findmnt -no SOURCE /` = `/dev/sdc3`; `efibootmgr` `BootCurrent: 0005` (USB); rauc log | Remove the card; know which system you're on before changing it | — |
| 4 | PC waits *for the PXE server* forever | The Mac's ProxyDHCP thread had died hours earlier on one `OSError: No route to host`; HTTP and TFTP kept running, so status looked fine | `lsof` showed UDP 4011 and 69 but no 67; traceback in `server.out` | Catch send errors, log them, keep listening | `netboot/server.py` |
| 5 | Installed SteamOS: *No networks found*, no update possible | Steam's first-boot `SetWifiBackend` → `steamos-wifi-set-backend-privileged restart_units` stops NetworkManager, fails at `iw phy phy0 interface add wlan0` (no Wi-Fi driver ⇒ no `phy0`), exits under `set -e` before restarting NetworkManager | The install's own journal, read offline from the netbooted home base: link up 2.5 Gb/s → DHCP starts → `Stopping Network Manager` 3 s later → `Error setting wifi backend: Exited 254` | A guard unit in the install's `/etc` overlay restarts NetworkManager ([recipe](../user-guide/07-steamos.md#setup-says-no-networks-found-and-never-continues-ethernet-plugged-in)); upstream: [SteamOS#2514](https://github.com/ValveSoftware/SteamOS/issues/2514), fix merged by Valve, not yet in a recovery image | M.2 install |
| 6 | No Wi-Fi at all on SteamOS 3.8 | MT7927 driver only in kernel 7.2; SteamOS 3.8 = 6.16; the DKMS backport needs ≥ 6.17 | `lspci -k` (no driver in use); home base on 7.2 showed `wlp9s0` with `mt7925e` | Update channel **Beta** → SteamOS 3.9.6 (kernel 7.2) | pending verification |

## Wrong turns worth remembering

- **"It's a physical link problem."** Concluded from *no traffic from the PC reaches the
  server*. The server was deaf (problem 4). Check your own instruments first: a status
  page that says *running* proves only that the process exists.
- **Setting `wifi.backend=wpa_supplicant`** in the install's `99-valve-wifi-backend.conf`
  so the switch would be a no-op. Steam calls the privileged helper directly (skipping the
  "already set" check) and rewrote the file 9 s into the next boot. Read the call path,
  not just the script that looks relevant.
- **"Restarted from the M.2 multiple times."** Four boots, all from the card. The
  firmware's `BootCurrent` and the kernel's `steamos.efi=PARTUUID=…` answer *which disk*
  without arguing.
- **Reading an offline disk while someone reinstalls it.** Superblocks went from valid to
  zeros between two commands: Valve's *Wipe Device & Install* had started on the PC's
  screen. Before reading a disk image as evidence, check `ps` and the journal for writers.

## Techniques that worked

- **A rescue system with the operator's SSH key** (the netbooted home base, or the recovery
  card with key-only `sshd` and a temporary `NOPASSWD` sudoers entry) turns "send me a
  photo of the screen" into direct inspection.
- **Read an installed system's journal offline:** mount its `home` partition read-only,
  `journalctl -D <home>/.steamos/offload/var/log/journal/<machine-id> --list-boots`.
  Mount times from `dumpe2fs -h` show boots the journal hasn't flushed yet.
- **Change an installed SteamOS before its first boot:** files under
  `var-A`/`var-B` → `lib/overlays/etc/upper/` appear in its `/etc`; the boot hook creates
  the overlay only when missing, so pre-seeding is safe.
- **Prove a fix by its log line,** not by the UI: `NetworkManager was stopped; starting it`
  once, then `connected:full` over SSH.

## Shared upstream and as a quest

- **SteamOS#2514:** [comment with this variant and the guard-unit workaround](https://github.com/ValveSoftware/SteamOS/issues/2514#issuecomment-6858076989)
  (posted 2026-11-13). No new issue was filed: #2514 already covers the bug, and Valve says the fix is merged and waiting on a new recovery image.
- **IT-Journey epic quest *The Silent Network*:** five chapters built from this session,
  [bamr87/it-journey#933](https://github.com/bamr87/it-journey/pull/933). Once it's merged it will be live at
  `https://it-journey.dev/quests/codex/silent-network/`.
