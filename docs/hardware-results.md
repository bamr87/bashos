# Hardware results

One row per device × machine. "QEMU" rows boot the physical stick in a VM
(`make card-boot`), which proves the bytes on the device; real-machine rows
cover firmware, drivers, Wi-Fi and Secure Boot (docs/hardware-checklist.md).

## Devices flashed

| Date | Device | Flashed from | Method | Result |
|------|--------|--------------|--------|--------|
| 2026-11-07 | 128 GB SDXC card (SMED2S5) in a MacBook Pro built-in SD reader | macOS 27 (Apple Silicon) | `make card-image DISK=disk5` → `sudo make flash DISK=disk5` (card-sized sparse image, 5.57 GB of data extents written + read-back verified) | GPT: `Ventoy` exFAT 128.1 GB + `VTOYEFI` 33.6 MB — full capacity |

## Boots

| Date | Device | Machine | Firmware | Result | Notes |
|------|--------|---------|----------|--------|-------|
| 2026-11-07 | 128 GB SDXC | QEMU q35 (TCG, read-only snapshot of the card) | OVMF (UEFI) | ✅ `ONEUSB-READY` in ~78 s | Ventoy → home base with persistence; lightdm started |
| 2026-11-07 | 128 GB SDXC | QEMU q35 (TCG, read-only snapshot of the card) | SeaBIOS | ✅ `ONEUSB-READY` in ~75 s | same |
| — | 128 GB SDXC | modern UEFI laptop, Secure Boot on | UEFI + SB | pending | MOK enrollment, Wi-Fi, GPU |
| — | 128 GB SDXC | older BIOS/CSM machine | BIOS | pending | |
| — | 128 GB SDXC | desktop with wired Ethernet | UEFI | pending | netboot.xyz, `oneusb-install` |

The host Mac is Apple Silicon and cannot boot an x86 stick; real-machine rows need a PC
(with an SD slot or a USB SD reader).
