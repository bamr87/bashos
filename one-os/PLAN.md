# one-os — Implementation Plan

> One USB to rule them all: a single stick that boots a lightweight, persistent
> "home base" OS, installs heavier operating systems onto another drive over the
> network, and keeps offline installers as a fallback — built reproducibly from
> code and tested in CI before it ever touches hardware.

Status: **Draft v1** · Owner: the maintainer · Created: 2026-11-07

---

## 1. Goals and non-goals

### Goals

| # | Goal | Measured by |
|---|------|-------------|
| G1 | One boot menu on one stick (UEFI + legacy BIOS) | Harness boots the menu in both firmware modes |
| G2 | Lightweight Linux "home base" with persistent storage, Wi-Fi, and repair tools | Persistence round-trip test passes |
| G3 | Network install of many OSes via netboot.xyz (iPXE) | Netboot test sees DNS/HTTP traffic to `boot.netboot.xyz` and the menu renders |
| G4 | Install a full OS onto a *different* drive from the home base | Install-to-target test boots the target disk with the USB detached |
| G5 | Offline fallback installers (e.g., Windows 11, Ubuntu Server) | Fallback ISO boots to its installer screen |
| G6 | Fully reproducible: `make` rebuilds the stick from a pinned manifest | Two clean builds produce identical payload checksums (except timestamps where unavoidable) |
| G7 | Self-restocking: home base can download/verify new ISOs onto the stick | `oneos-restock` test passes |

### Non-goals (v1)

- Netbooting retail Windows (needs self-hosted WinPE + SMB; revisit later).
- macOS installers (not bootable on non-Apple hardware).
- Wi-Fi at the iPXE stage (unsupported in practice — Wi-Fi lives in the home base).
- Hosting our own PXE server on the LAN (iVentoy / self-hosted netboot.xyz are future options).

---

## 2. Architecture

### 2.1 Boot chain

```
Firmware (UEFI or BIOS)
   └─► Ventoy bootloader (GRUB2-based, on the small VTOYEFI partition)
         ├─► /ISO/oneos-lightos.iso  + /persistence/lightos.dat   (home base)
         ├─► /netboot.xyz.iso         → iPXE → internet → distro installers
         ├─► /ISO/<offline installers>.iso
         └─► (Phase 8) chainload native install on reserved partition
```

### 2.2 Disk layout

```
┌──────────────────────────────────────────────────────────────┐
│ P1  "Ventoy"  exFAT   (rest of drive)                         │
│     /ventoy/ventoy.json           config (persistence, aliases)│
│     /netboot.xyz.iso                                           │
│     /ISO/oneos-lightos.iso                                    │
│     /ISO/*.iso                    offline installers           │
│     /persistence/lightos.dat      ext4 persistence image       │
│     /oneos/manifest.yaml         copy of the build manifest   │
│     /oneos/selftest/             test hooks + results (CI)    │
├──────────────────────────────────────────────────────────────┤
│ P2  "VTOYEFI" FAT 32 MB           Ventoy bootloader            │
├──────────────────────────────────────────────────────────────┤
│ (Phase 8) reserved space, ext4    native home-base install     │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Key design decision: build a *payload*, not just a disk image

Writing a fixed-size `.img` to a stick with `dd` wastes the extra capacity (an
8 GB image on a 128 GB stick leaves 120 GB unusable). So the build produces:

1. **`build/payload/`** — the staged file tree for P1 (ISOs, `.dat`, `ventoy.json`).
2. **`build/one-os-test.img`** — Ventoy installed onto a *sparse loop file* with
   the payload copied in. Used only by the test harness and CI.
3. **`make flash DEV=/dev/sdX`** — runs the **same** `install_to_device()` routine
   against real hardware: Ventoy2Disk on the device, then copy the payload in.

One code path for both, so what CI tests is what goes onto the stick.

### 2.4 Components

| Component | Choice | Why |
|-----------|--------|-----|
| Boot manager | **Ventoy** (pinned version, checksum-verified) | Boots ISOs in place, works in UEFI + BIOS, supports persistence, ships CLI `Ventoy2Disk.sh` |
| Home base OS | **Debian stable live** built with `live-build` (Xfce or LXQt) | Reproducible, scriptable, has firmware for Wi-Fi, has Debian-live persistence |
| Network installer | **netboot.xyz** ISO (+ `-sb` variant for Secure Boot) | iPXE menu of many OSes, small, maintained |
| Offline installers | Declared in `manifest.yaml`; Windows ISO supplied by the user | Licensing/size: Windows is never downloaded by CI |
| Test harness | **pytest + QEMU/KVM + OVMF/SeaBIOS + QMP** | Headless, scriptable, runs on CI runners with KVM |
| CI | GitHub Actions | Already in use across the fleet |

---

## 3. Repository layout

```
one-os/
├── README.md
├── PLAN.md                      ← this file
├── Makefile                     ← entry point for everything
├── manifest.yaml                ← pinned versions, URLs, sha256s
├── config/
│   ├── ventoy.json.j2           ← templated Ventoy config
│   └── theme/                   ← optional Ventoy menu theme
├── lightos/                     ← live-build tree for the home base
│   ├── auto/config
│   ├── config/package-lists/oneos.list.chroot
│   └── config/includes.chroot/
│       ├── usr/local/bin/oneos-restock
│       ├── usr/local/bin/oneos-install
│       ├── usr/local/bin/oneos-selftest
│       └── etc/systemd/system/oneos-selftest.service
├── scripts/
│   ├── lib.sh                   ← logging, checksum, sudo/loop helpers
│   ├── fetch.sh                 ← download + verify everything in manifest
│   ├── build-lightos.sh         ← live-build wrapper (runs in container)
│   ├── stage-payload.sh         ← assemble build/payload/
│   ├── install-to-device.sh     ← Ventoy2Disk + copy payload (loop OR real)
│   ├── build-test-image.sh      ← sparse file → loop → install-to-device
│   └── flash.sh                 ← safety-guarded wrapper for real sticks
├── harness/
│   ├── pyproject.toml
│   ├── oneos_harness/
│   │   ├── qemu.py              ← VM launcher (firmware modes, disks, QMP, serial)
│   │   ├── overlay.py           ← qcow2 overlays + edit P1 via loop mount
│   │   ├── serial.py            ← wait_for(pattern, timeout)
│   │   ├── netcap.py            ← pcap assertions (DNS/HTTP)
│   │   └── screen.py            ← QMP screendump + OCR (optional assertions)
│   └── tests/
│       ├── test_00_image.py
│       ├── test_10_boot_menu.py
│       ├── test_20_lightos.py
│       ├── test_30_persistence.py
│       ├── test_40_netboot.py
│       ├── test_50_install_target.py
│       ├── test_60_restock.py
│       └── test_70_offline_iso.py
├── docker/
│   └── builder.Dockerfile       ← pinned Debian with live-build, qemu, ovmf, exfatprogs
├── docs/
│   ├── hardware-checklist.md
│   ├── troubleshooting.md
│   └── adr/
│       ├── 0001-ventoy-as-boot-manager.md
│       ├── 0002-payload-not-dd-image.md
│       └── 0003-selftest-hook-mechanism.md
└── .github/workflows/
    ├── ci.yml                   ← lint + build + fast tests on PR
    └── nightly.yml              ← full matrix incl. Secure Boot + netboot install
```

---

## 4. The manifest (single source of truth)

```yaml
# manifest.yaml — every external artifact is pinned and checksummed.
schema: 1

ventoy:
  version: "<PIN>"                       # e.g. latest 1.x at time of Phase 0
  url: "https://github.com/ventoy/Ventoy/releases/download/v<PIN>/ventoy-<PIN>-linux.tar.gz"
  sha256: "<PIN>"
  options:
    partition_style: gpt                 # Ventoy2Disk -g
    secure_boot: true                    # Ventoy2Disk -s
    reserve_mb: 0                        # Ventoy2Disk -r  (Phase 8 → 20480)

lightos:
  builder: live-build
  distribution: trixie                   # Debian 13
  desktop: xfce
  persistence_mb: 4096
  extra_packages: [gparted, network-manager, firmware-linux, debootstrap,
                   arch-install-scripts, curl, yq, smartmontools, testdisk]

netboot:
  - name: netboot.xyz
    file: netboot.xyz.iso
    url: "https://boot.netboot.xyz/ipxe/netboot.xyz.iso"
    sha256_from: "https://boot.netboot.xyz/ipxe/netboot.xyz-sha256-checksums.txt"
  - name: netboot.xyz-secureboot
    file: netboot.xyz-sb.iso
    url: "https://boot.netboot.xyz/ipxe/netboot.xyz-sb.iso"
    sha256_from: "https://boot.netboot.xyz/ipxe/netboot.xyz-sha256-checksums.txt"

isos:
  - name: ubuntu-server
    file: ISO/ubuntu-server.iso
    url: "<PIN>"
    sha256: "<PIN>"
    ci: true
  - name: windows11
    file: ISO/windows11.iso
    source: user-supplied                # placed in ./local-isos/ by the user
    optional: true
    ci: false                            # never downloaded or redistributed by CI
```

Rules:
- `fetch.sh` refuses any artifact whose checksum doesn't match. No `<PIN>` may
  remain at release time (`make lint` enforces this).
- A `make bump` target (Phase 6) proposes new pins via PR; humans approve.

---

## 5. Build pipeline

```
make fetch        → cache/   (downloads, verified)
make lightos      → build/oneos-lightos.iso   (live-build in Docker)
make payload      → build/payload/             (ISOs + .dat + ventoy.json)
make image        → build/one-os-test.img     (sparse 16 GB, Ventoy + payload)
make test         → harness (fast suite)
make test-full    → harness (full matrix)
make flash DEV=/dev/sdX  → real stick (guarded)
make clean / distclean
```

### 5.1 `build-lightos.sh` (home base)

- Runs inside `docker/builder.Dockerfile` (privileged, needed by live-build).
- `lb config --distribution trixie --archive-areas "main contrib non-free non-free-firmware" --binary-images iso-hybrid --bootappend-live "boot=live components persistence console=tty0 console=ttyS0,115200"`
- `console=ttyS0` is **always** on (harmless on hardware, essential for tests).
- Includes the three `oneos-*` tools and the self-test unit (see §6.3).
- Output: `build/oneos-lightos.iso` + `.sha256`.

### 5.2 `stage-payload.sh`

1. Copy ISOs from `cache/` into `build/payload/` per manifest paths.
2. Create `persistence/lightos.dat`: an ext4 image labelled `persistence`,
   containing `persistence.conf` with `/ union` (Debian-live convention).
   Use Ventoy's `CreatePersistentImg.sh` if it fits, otherwise
   `truncate` + `mkfs.ext4 -L persistence` + write the conf file.
3. Render `config/ventoy.json.j2` → `payload/ventoy/ventoy.json`:

```json
{
  "control": [
    { "VTOY_DEFAULT_SEARCH_ROOT": "/ISO" },
    { "VTOY_MENU_TIMEOUT": "10" },
    { "VTOY_DEFAULT_IMAGE": "/ISO/oneos-lightos.iso" }
  ],
  "persistence": [
    { "image": "/ISO/oneos-lightos.iso", "backend": "/persistence/lightos.dat" }
  ],
  "menu_alias": [
    { "image": "/ISO/oneos-lightos.iso", "alias": "🏠 Home base (persistent)" },
    { "image": "/netboot.xyz.iso",       "alias": "🌐 Network install (netboot.xyz)" }
  ]
}
```

> Note: `VTOY_DEFAULT_SEARCH_ROOT` would hide `/netboot.xyz.iso` at the root —
> Phase 0 decides whether netboot lives at `/ISO/netboot.xyz.iso` instead.

4. Copy `manifest.yaml` → `payload/oneos/manifest.yaml` (so `oneos-restock`
   knows what belongs on the stick).

### 5.3 `install-to-device.sh <device>`

```bash
# 1. Guard: device must be a whole block device (loop or removable disk).
# 2. Ventoy2Disk.sh -I [-g] [-s] [-r $RESERVE_MB] "$dev"   (non-interactive)
# 3. partprobe; wait for P1 (label "Ventoy").
# 4. mount P1 (exfat) → rsync -a build/payload/ → sync → umount.
# 5. (Phase 8) format + populate reserved partition.
```

### 5.4 `build-test-image.sh`

`truncate -s 16G` → `losetup -fP --show` → `install-to-device.sh /dev/loopN` →
`losetup -d`. Image stays sparse, so it uses only the disk space of its contents.

### 5.5 `flash.sh` safety guards (non-negotiable)

- Refuse unless `DEV` is set explicitly; never auto-detect.
- Refuse if the device is mounted as `/`, `/boot`, or holds any active mount.
- Refuse if `lsblk -o RM,TRAN` shows it is not removable / not `usb`, unless
  `--i-know-this-is-not-usb` is passed (external SSDs).
- Print model, serial, and size; require typing the model name to confirm.

---

## 6. Home-base tooling (inside the light OS)

### 6.1 `oneos-restock`

- Finds P1 by label `Ventoy`, mounts it read-write.
- Reads `/oneos/manifest.yaml`; downloads missing or outdated ISOs over
  Wi-Fi/Ethernet; verifies sha256 before moving into place (write to `*.part`,
  then atomic rename).
- `--add <url> --sha256 <sum>` for ad-hoc ISOs; `--list`; `--prune`.

### 6.2 `oneos-install`

The Wi-Fi-friendly path for G4 (iPXE needs wired Ethernet).

```
oneos-install --target /dev/nvme0n1 --distro debian|ubuntu|arch \
               [--hostname X] [--user Y] [--unattended] [--efi|--bios]
```

- **Refuses** to target the disk the live system booted from (compare against
  the device that holds P1 / `/run/live/medium`).
- Partitions (GPT: ESP + root), runs `debootstrap` / `pacstrap`, installs a
  kernel and GRUB, sets fstab/hostname/user, installs the
  `oneos-installed-marker` unit (prints `ONEOS-INSTALLED-OK` on serial at boot).
- Interactive mode prompts for anything missing; `--unattended` is for tests.

### 6.3 Self-test hook (how the harness drives the guest)

Problem: Ventoy boots ISOs unmodified, so we can't change the kernel command
line per test. Solution — a **file-based hook on P1**:

- `oneos-selftest.service` (in every build, enabled) runs at boot:
  if `P1:/oneos/selftest/run.sh` exists, execute it, write
  `P1:/oneos/selftest/results/<name>.json`, print
  `ONEOS-SELFTEST <name> PASS|FAIL` to `/dev/ttyS0`, then power off.
- If the file doesn't exist (every real-world boot), the service is a no-op and
  prints `ONEOS-READY` to the serial console.
- The harness injects `run.sh` into a **qcow2 overlay** of the test image, so the
  base image is never modified and tests are isolated.

Security note: the hook only executes from the stick's own P1, which is
already fully trusted (it holds the bootloader). Document this in ADR-0003.

---

## 7. Test harness

### 7.1 VM profiles

| Profile | Firmware | Machine | Use |
|---------|----------|---------|-----|
| `uefi` | OVMF (`OVMF_CODE_4M.fd`) | q35 | default for all tests |
| `bios` | SeaBIOS | q35 | menu + lightos + netboot smoke |
| `uefi-sb` | OVMF secboot + MS keys (`OVMF_VARS_4M.ms.fd`) | q35, SMM on | nightly only |

Common QEMU wiring (`qemu.py`):

```
qemu-system-x86_64 -enable-kvm -machine q35 -m 4096 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file=<per-test copy of OVMF_VARS> \
  -device qemu-xhci \
  -drive if=none,id=usb,format=qcow2,file=<overlay of one-os-test.img> \
  -device usb-storage,drive=usb,bootindex=0,removable=on \
  -drive if=virtio,format=qcow2,file=<target.qcow2>        # install tests only
  -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
  -object filter-dump,id=cap0,netdev=n0,file=<test>.pcap \
  -serial file:<test>.serial.log -qmp unix:<test>.qmp,server,nowait \
  -display none
```

The stick is attached as **USB storage on xHCI** (not virtio), so it shows up
the way it does on hardware, including as a "removable" device.

### 7.2 Harness primitives

```python
class VM:
    def __init__(self, profile, usb_image, target_disk=None, net=True): ...
    def start(self): ...
    def wait_serial(self, pattern, timeout): ...        # regex on serial log
    def screendump(self, path): ...                      # QMP
    def send_keys(self, *keys): ...                      # QMP send-key fallback
    def wait_shutdown(self, timeout): ...
    def kill(self): ...

class Overlay:  # qcow2 overlay + edit P1 via qemu-nbd/losetup and exfat mount
    def set_default_image(self, iso_path): ...           # rewrites ventoy.json
    def put_selftest(self, name, script): ...
    def read_result(self, name) -> dict: ...
```

`set_default_image()` + `VTOY_MENU_TIMEOUT=1` make Ventoy auto-boot the entry
under test — no keystroke choreography. Keep `send_keys` for the interactive
paths (netboot.xyz menu, MOK enrollment).

### 7.3 Test catalogue

| ID | Test | Profile(s) | Assertion | Suite |
|----|------|-----------|-----------|-------|
| T00 | Image structure | — (no VM) | P1 exfat label `Ventoy`, P2 present, payload checksums match manifest, `ventoy.json` valid JSON + schema | fast |
| T10 | Boot menu renders | uefi, bios | screendump OCR contains `Home base` alias (or: entry auto-boots → T20 marker) | fast |
| T20 | Home base boots | uefi, bios | serial `ONEOS-READY` within 120 s | fast |
| T30 | Persistence round-trip | uefi | run 1 writes `/root/canary` with a random token, powers off; run 2 reads it back → PASS | fast |
| T40 | Netboot reaches the internet | uefi, bios | pcap contains a DNS query for `boot.netboot.xyz` and a TCP connection to it; OCR shows `netboot.xyz` menu (soft assertion) | fast* |
| T45 | Netboot full install | uefi | key-driven: netboot.xyz → Debian → installer starts (OCR `Debian`) | nightly |
| T50 | Install to target disk | uefi | selftest runs `oneos-install --unattended --distro debian --target /dev/vda`; then reboot **with USB detached**, booting only `target.qcow2` → serial `ONEOS-INSTALLED-OK` | fast** |
| T51 | Install refuses own disk | uefi | `oneos-install --target <usb disk>` exits non-zero, disk untouched | fast |
| T60 | Restock | uefi | delete an ISO from the overlay; selftest runs `oneos-restock`; file returns with correct sha256 | nightly |
| T70 | Offline ISO boots | uefi | default image = ubuntu-server ISO → serial or OCR shows installer | nightly |
| T80 | Secure Boot path | uefi-sb | OCR shows Ventoy/MOK enrollment screen; after scripted enroll, `ONEOS-READY` | nightly |
| T90 | Reproducibility | — | two clean `make payload` runs → identical checksums for non-timestamped artifacts | nightly |

\* needs outbound internet from the runner. \** downloads Debian packages — use
a CI cache for the apt mirror (e.g., `apt-cacher-ng` service container) to keep
it fast and avoid hammering mirrors.

### 7.4 Artifacts on failure

Every test keeps: serial log, pcap, final screendump, QEMU stderr, and the
selftest result JSON. CI uploads them as a workflow artifact.

---

## 8. CI

### `ci.yml` (pull requests)

1. `make lint` — shellcheck, ruff, `yq` schema check, no `<PIN>`s on `main`.
2. Restore `cache/` (keyed on `manifest.yaml` hash) → `make fetch`.
3. `make lightos` (cached on `lightos/**` hash).
4. `make payload image`.
5. `make test` (T00–T51 except T45), with `/dev/kvm` enabled on the runner.
6. Upload failure artifacts.

### `nightly.yml`

Full matrix including `bios`, `uefi-sb`, T45, T60, T70, T80, T90. Publish
`build/payload.tar.zst` + `SHA256SUMS` as a release candidate.

### CI notes
- Check in Phase 0 that the chosen GitHub-hosted Linux runner exposes `/dev/kvm`
  (enable it with the usual udev rule step). If it doesn't, fall back to a
  self-hosted runner. TCG (no KVM) works but is ~10× slower — fast suite only.
- Loop devices and exFAT mounts need `sudo`. The hosted runners have it.
  Wrap every privileged step in `scripts/lib.sh` so it's easy to audit.

---

## 9. Hardware validation (manual, `docs/hardware-checklist.md`)

Run before tagging a release, on at least: one modern UEFI laptop (Secure Boot
on), one older BIOS/CSM machine, and one desktop with wired Ethernet.

- [ ] Menu appears; aliases and theme correct
- [ ] Home base boots; Wi-Fi connects; GPU/display OK
- [ ] Persistence survives reboot
- [ ] netboot.xyz loads over wired Ethernet; reaches a distro installer
- [ ] USB-Ethernet adapter at the iPXE stage (record: works / doesn't)
- [ ] `oneos-install` to internal disk over Wi-Fi; target boots without the stick
- [ ] Windows ISO boots to setup (if supplied)
- [ ] Secure Boot: MOK enrollment flow documented with photos
- [ ] Record results in `docs/hardware-results.md` (model, firmware, pass/fail)

---

## 10. Phased delivery

| Phase | Deliverable | Acceptance criteria |
|-------|-------------|---------------------|
| **0 — Spike** (½–1 day) | Throwaway notes in `docs/spike.md` | Proven by hand: `Ventoy2Disk.sh` works on a loop device; Debian live persistence works under Ventoy; netboot.xyz boots under Ventoy in OVMF + SeaBIOS; `/dev/kvm` available on the CI runner; decide netboot file location (§5.2 note) |
| **1 — Skeleton** | Repo layout, Makefile, manifest, `fetch.sh`, lint, ADR-0001/0002 | `make fetch` downloads + verifies everything; `make lint` green |
| **2 — Home base** | live-build tree, Docker builder, `oneos-selftest` service | `make lightos` produces a bootable ISO; boots in QEMU straight from the ISO with `ONEOS-READY` on serial |
| **3 — Image assembly** | `stage-payload.sh`, `install-to-device.sh`, `build-test-image.sh` | `make image` produces an image; T00 passes |
| **4 — Harness core** | `qemu.py`, `overlay.py`, `serial.py`, T10/T20 | T10 + T20 green in uefi and bios |
| **5 — Features** | persistence, `oneos-install`, `oneos-restock`, netcap; T30/T40/T50/T51/T60 | All green locally |
| **6 — CI** | `ci.yml`, `nightly.yml`, caching, artifacts, `make bump` | PR pipeline < 30 min; nightly publishes a payload RC |
| **7 — Hardware + flash** | `flash.sh` with guards, hardware checklist | Checklist complete on 3 machines; v1.0.0 tagged |
| **8 — Native home base** (optional) | Reserved partition + chainload via `ventoy_grub.cfg` | Same T20/T30 tests pass for the native variant; compare boot time and update ergonomics vs the live + persistence variant |

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Ventoy CLI behavior changes between versions | Build breaks | Pin version + sha256; Phase 0 spike documents exact flags; nightly catches drift on `make bump` PRs |
| Ventoy ships prebuilt binaries | Supply-chain trust | Verify release checksum; document in ADR-0001; option to build from source later |
| Persistence `.dat` gets corrupted by unclean shutdowns | Home base state lost | `oneos-restock --backup-persistence`; `e2fsck` on the image in the home base's shutdown hook |
| iPXE can't drive some NICs / no Wi-Fi | Netboot unusable on some machines | `oneos-install` from the home base is the primary install path; netboot is the bonus path |
| Secure Boot + MOK flow is interactive | Hard to automate | Nightly-only T80 with QMP keystrokes; clear docs |
| CI runner without KVM | Slow or impossible boot tests | Detect in workflow; self-hosted runner fallback |
| User flashes the wrong disk | Data loss | `flash.sh` guards (§5.5); `oneos-install` refuses the boot disk (T51) |
| Large ISOs blow the CI cache | Slow builds | Only `ci: true` ISOs in CI; small test ISOs where possible |

---

## 12. Definition of done (v1.0.0)

- `make flash DEV=/dev/sdX` on a clean machine builds a working stick from the
  pinned manifest with no manual steps besides supplying optional Windows ISOs.
- Fast suite runs on every PR, full matrix nightly, both green.
- Hardware checklist passed on 3 machines and recorded.
- README covers: what it is, quick start, flashing safely, adding ISOs,
  restocking, and installing to another drive over Wi-Fi vs Ethernet.

---

## 13. Working with AI on this repo

- Keep `PLAN.md` and the ADRs current. An agent that reads them first stays
  consistent with earlier decisions.
- Give agents the harness as their feedback loop: "make T30 pass" is a better
  task than "implement persistence".
- Never let an agent run `flash.sh` or `oneos-install` against real hardware.
  Agents work against loop devices and qcow2 overlays only.
- Ask for the Phase 0 spike as a *report*, not code, and review it before
  Phase 1 starts. Every later phase depends on its answers.
