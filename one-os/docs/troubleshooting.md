# Troubleshooting

**`make` on macOS says it needs Docker.** Everything except `flash` runs in the builder
container (`make builder` builds it). Docker Desktop must allow privileged containers.

**`make lightos` is slow on Apple Silicon.** It runs an amd64 container under emulation.
Expect 20–60 min the first time. CI (amd64, native) caches the ISO by `lightos/**` hash.

**VM tests time out on macOS.** No KVM there: QEMU uses TCG and timeouts are scaled ×8
(`ONEOS_TIMEOUT_SCALE` overrides). The definitive runs are on Linux CI with KVM.

**Overlay errors (`no free /dev/nbdN`).** Set `ONEOS_OVERLAY=fuse` or `raw` to pick another
backend (see `harness/oneos_harness/overlay.py`).

**Home base can't mount the Ventoy partition.** `ventoy.json` must keep
`VTOY_LINUX_REMOUNT: 1`; without it the ISO's device-mapper mapping holds P1 exclusively.

**Ventoy shows a second "Boot in normal mode" menu.** Keep `VTOY_SECONDARY_BOOT_MENU: 0`.

**Persistence lost after a crash.** Run `sudo e2fsck -f /path/to/persistence/lightos.dat` from
another Linux, or restore `lightos.dat.bak` (`sudo oneos-restock --backup-persistence` makes one).

**Secure Boot "Verification failed".** Expected on first boot — enroll Ventoy's key once
(docs/hardware-checklist.md).

**macOS flash: "image is N bytes but diskN is M".** The image must match the device
exactly (the backup GPT lives at the device's last sectors). Rebuild with
`make card-image DISK=diskN` for that device.

**macOS flash: "could not unmount".** Close Finder windows and apps using the card, then retry.

## Flashing and the wizard

**Wizard: "macOS blocked the write" / `Operation not permitted`.** A root process (sudo)
opening the raw disk is checked against the app it was started from. Use the normal
(no-sudo) path — `make wizard` or `make flash DISK=…` — which asks macOS for the one device
through the authorization dialog. Fallback: give that app Full Disk Access.

**Wizard: "missing or wrong token".** Open the exact URL the wizard printed; it changes per run.

**Wizard: Address already in use.** Another wizard is running; the new one takes the next
port automatically (check the printed URL).

**A card got a new disk number.** macOS renumbers on re-insertion. Commands that get a
missing disk list the removable disks present now.

## Booting real PCs

**SD card not offered in the boot menu.** Many PCs can't boot from built-in SD readers.
Use a USB SD-card adapter.

**Black desktop for a while after boot.** On slow machines (and in emulation) Xfce takes a
minute or two to draw after login; wait before assuming it failed.

**Login screen asks for a password.** User `user`, password `live`. If it never accepts it,
the image predates the `user-setup` fix — rebuild (`make lightos payload`) and re-flash.
