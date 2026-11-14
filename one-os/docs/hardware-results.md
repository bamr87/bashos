# Hardware results

One row per device × machine. "QEMU" rows boot the physical stick in a VM
(`make card-boot`), which proves the bytes on the device; real-machine rows
cover firmware, drivers, Wi-Fi and Secure Boot (docs/hardware-checklist.md).

## Devices flashed

| Date | Device | Flashed from | Method | Result |
|------|--------|--------------|--------|--------|
| 2026-11-07 | 128 GB SDXC card (SMED2S5) in a MacBook Pro built-in SD reader | macOS 27 (Apple Silicon) | `make card-image DISK=disk5` → `sudo make flash DISK=disk5` (card-sized sparse image, 5.57 GB of data extents written + read-back verified) | GPT: `Ventoy` exFAT 128.1 GB + `VTOYEFI` 33.6 MB — full capacity |
| 2026-11-12 | same 128 GB SDXC card | macOS 27 (Apple Silicon) | `make flash DISK=disk4` (34.59 GB of extents: 8 Linux ISOs + SteamOS recovery partitions 3–7, read-back verified) | Ventoy 111 GB + VTOYEFI + Valve's esp/efi-A/rootfs-A/var-A/home |
| 2026-11-12 | 32 GB SD card | macOS 27 (Apple Silicon) | plain `sudo dd if=build/steamos/recovery.img of=/dev/rdisk4 bs=4m` (Valve's recovery image only, no Ventoy) | 8,120,172,544 bytes in 251 s; boots Valve's recovery desktop |

## Boots

| Date | Device | Machine | Firmware | Result | Notes |
|------|--------|---------|----------|--------|-------|
| 2026-11-07 | 128 GB SDXC | QEMU q35 (TCG, read-only snapshot of the card) | OVMF (UEFI) | ✅ `ONEOS-READY` in ~78 s | Ventoy → home base with persistence; lightdm started |
| 2026-11-07 | 128 GB SDXC | QEMU q35 (TCG, read-only snapshot of the card) | SeaBIOS | ✅ `ONEOS-READY` in ~75 s | same |
| — | 128 GB SDXC | modern UEFI laptop, Secure Boot on | UEFI + SB | pending | MOK enrollment, Wi-Fi, GPU |
| — | 128 GB SDXC | older BIOS/CSM machine | BIOS | pending | |
| — | 128 GB SDXC | desktop with wired Ethernet | UEFI | pending | netboot.xyz, `oneos-install` |
| 2026-11-12 | network boot (no stick) | ASUS ROG Crosshair X870E Dark Hero, RX 9070 XT | UEFI, Secure Boot off | ✅ home base over PXE (5 GbE RTL8126 port) | 10 GbE RTL8127 port PXE-boots but had no driver in kernel 6.12 → backports kernel 7.2; 7.2 also drives the MediaTek MT7927 Wi-Fi (`mt7925e`) |
| 2026-11-12 | 32 GB SD (Valve recovery) | same X870E PC | UEFI | ✅ recovery desktop; *Wipe Device & Install* to the M.2 | the installed SteamOS 3.8.14 hit the first-boot network bug — see [field report](field-reports/2026-11-12-steamos-silent-network.md) |
| 2026-11-13 | M.2 (installed SteamOS 3.9.5) | same X870E PC | UEFI | ✅ root on `nvme0n1p4`, kernel 7.2.7-valve2, online over the 5 GbE port (`eno1`) | read over ssh: `wlan0` exists (the MT7927 has its driver on 7.2) but is not connected; the SATA SSD and the 8 TB disk carry no partition table, and the SSD is bashOS's target ([profile](../machines/x870e-dark-hero.yaml)) |

The host Mac is Apple Silicon and cannot boot an x86 stick; real-machine rows need a PC
(with an SD slot or a USB SD reader).
