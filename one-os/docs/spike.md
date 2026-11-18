# Phase 0 spike report

Date: 2026-11-07 · Host: macOS 27 on Apple Silicon, Docker Desktop (linux/arm64 VM),
QEMU TCG (no KVM). Ventoy 1.1.18. All runs inside `docker/builder.Dockerfile`.

## Questions from PLAN §10 and answers

| Question | Answer | Evidence |
|----------|--------|----------|
| Does `Ventoy2Disk.sh` work on a loop device? | **Yes.** `-I -g -s` on `/dev/loopN` in a privileged container; it asks for confirmation twice, answered by piping `y\ny`. Ventoy's aarch64 tools run fine on arm64 hosts. | `make image`, T00 green |
| Are loop partitions visible without udev? | **Yes** on Docker Desktop with `-v /dev:/dev`; `lib.sh` still falls back to `mknod` from sysfs. | `loop1p1/p2` appeared |
| Can tests edit P1 in a qcow2 overlay? | **Yes** — `qemu-nbd` works in Docker Desktop's VM (nbd module present); FUSE export also available. | `Overlay.set_default_image()` round-trip |
| Does netboot.xyz boot under Ventoy in OVMF? | **Not the ISO.** `netboot.xyz.iso` (and `-sb`, `-multiarch`, `-legacy`) keep the EFI loader only inside the El Torito FAT image; Ventoy says "No bootfile found for UEFI". `auto_memdisk` mode fails too ("cannot load image"). **Decision:** ship `netboot.xyz.efi` for UEFI (Ventoy boots `.efi` files) and `netboot.xyz.iso` for BIOS, each hidden in the other mode with `image_blacklist_uefi` / `image_blacklist_legacy`. | T40 green: UEFI (`.efi`) and BIOS (`.iso`) both resolve and connect to `boot.netboot.xyz` |
| Separate Secure Boot netboot image? | **Dropped.** With Ventoy's MOK-enrolled key, Ventoy boots the plain `.efi` under Secure Boot; the `-sb` ISO has the same El Torito problem anyway. To verify on hardware (checklist). | — |
| Where does netboot live (§5.2 note)? | `/ISO/…`, so `VTOY_DEFAULT_SEARCH_ROOT=/ISO` keeps working. | menu screendump |
| Menu aliases render? | **Yes, but no emoji** — Ventoy's font draws them as `?` boxes. Aliases are ASCII; `make lint` enforces it. | menu screendump |
| Is `/dev/kvm` on GitHub-hosted runners? | Expected yes on `ubuntu-24.04` with the udev rule in `ci.yml`. **Not verified here** — the first CI run confirms (`ls -l /dev/kvm` step); fallback is a self-hosted runner. | — |
| Does the home base boot under Ventoy? | **Yes**, UEFI and BIOS (T20, ~1 min each even under TCG) — once the persistence entry has `"autosel": 1, "timeout": 3`. Without them Ventoy waits on its "boot with/without persistence" picker forever. | T20 green |
| Does the ISO boot without Ventoy? | **Yes**, UEFI and BIOS, `ONEOS-READY` after ~45 s under TCG (Phase 2 acceptance). | `test_lightos_iso_direct` green |
| Can the booted home base mount P1? | **BIOS yes; UEFI no** with a plain mount, despite `VTOY_LINUX_REMOUNT`. Fix: `oneos-mount-p1` falls back to a linear device-mapper view of P1. T20 now requires a bare `ONEOS-READY` so this can't regress silently. | T20 (strict) green in both modes |
| Debian live persistence under Ventoy? | **Yes.** A canary written in boot 1 is read back in boot 2 (`.dat` labelled `persistence`, `/ union`). | T30 green |
| Does `oneos-install` refuse the stick? | **Yes**, and the stick's first MiB is unchanged. | T51 green |

## Later findings (control channel, wizard)

- **No login at all**: `user-setup` (a `live-config` Recommends) was missing, so the live
  `user` account was never created; getty showed "user (automatic login) → Authentication
  failure" and LightDM looped. Fixed in the package list; T21 asserts account, password
  and the Xfce session.
- **qemu-guest-agent protocol**: only the agent sends the `0xFF` sync sentinel; a client
  that sends one gets "JSON parse error, stray '\uFFFD'" and loses its sync request.
- **Agent polling wedge**: reconnecting to the agent socket every few seconds while the
  guest hadn't opened its port left Debian's QEMU 10.0 channel silent until polling
  stopped (Homebrew QEMU was fine). `wait_agent` now holds one connection and re-sends.
- **ISO mtime is not the build time**: the payload hard-links the ISO and resets payload
  mtimes to `SOURCE_DATE_EPOCH`, which resets the ISO's. Freshness uses `oneos-lightos.iso.sha256`.
- **Windowed QEMU text looked scrambled**: `zoom-to-fit=on` nearest-neighbour scales the
  framebuffer into the first window size. Windows now open 1:1.
- macOS raw disks report size 0 to `lseek(SEEK_END)`; use `DKIOCGETBLOCKCOUNT × DKIOCGETBLOCKSIZE`.
- **Root is not enough on macOS**: a root process (sudo or `do shell script … with administrator
  privileges`) opening `/dev/rdiskN` gets `EPERM` unless the app it was launched from (e.g. VS Code)
  has Full Disk Access. The flasher now runs unprivileged and opens just the one device through
  `/usr/libexec/authopen` (system authorization dialog, `sys.openfile.readwrite.<path>`, fd passed
  back via SCM_RIGHTS) — no sudo, no root shell, no standing permission for any app.

## Other findings

- With `--apt-recommends false`, `xfce4` + `lightdm` don't pull in an X server or greeter;
  `lightdm` fails to start. `manifest.py` now lists Xorg + `lightdm-gtk-greeter` explicitly.
- `netboot.xyz` menus auto-select "Boot from local disk" after 300 s; under TCG OCR can
  miss the menu, so T40's menu check is serial-first and soft.
- After the dm fallback, two devices carry the label `Ventoy` (`sda1` and
  `/dev/mapper/oneos-p1`); `blkid -L` may return either. Anything that needs the
  physical disk must walk down with `lsblk -lsp` (as `oneos-install` does).
- In UEFI, screendumps of iPXE's EFI text console come out blank; OVMF mirrors it to
  serial, which is the better oracle.
- OVMF connects only the devices in QEMU's boot order. A NIC without a `bootindex` gets no
  driver, so `netboot.xyz-snp.efi` prints "Available interfaces..." with none listed and
  exits to Ventoy ("cannot load image"); from the UEFI shell it works, because the firmware
  connects everything before starting the shell. The harness puts the NIC last in the order.

- `live-build` templates on trixie have `timeout 0` (wait forever) for isolinux and no
  timeout for GRUB; `build-lightos.sh` sets 5 s so Ventoy-booted ISOs don't stall.
- `VTOY_LINUX_REMOUNT: 1` is needed so the home base can mount P1 for the self-test
  hook and `oneos-restock`.
- The persistence file is written in full (exFAT has no sparse files), so a 4 GB
  `persistence_mb` makes every test image at least 4 GB of real I/O.
- `VTOY_SECONDARY_BOOT_MENU: 0` keeps Ventoy 1.1's "Boot in normal mode" sub-menu from
  blocking auto-boot.
- On Apple Silicon, `make lightos` runs the amd64 builder under emulation; QEMU runs x86
  guests under TCG. Timeouts scale ×8 (`ONEOS_TIMEOUT_SCALE`).
