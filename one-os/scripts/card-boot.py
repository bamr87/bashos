#!/usr/bin/env python3
"""card-boot.py <diskN> — boot a flashed device in QEMU, UEFI then BIOS, read-only.

The device is attached as USB storage with snapshot=on: the guest's writes go to a
temporary overlay, so the card itself is never modified. Passes when each boot
prints a bare ONEOS-READY (home base up, P1 mountable). Needs root on macOS to
open /dev/diskN. Logs land in build/card-boot/.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))

from oneos_harness import VM, Config  # noqa: E402


def removable_disks() -> str:
    """Removable whole disks with their media name/size — disk numbers change on re-insert."""
    out = []
    for line in subprocess.run(["diskutil", "list"], capture_output=True, text=True).stdout.splitlines():
        if not line.startswith("/dev/disk"):
            continue
        d = line.split()[0].removeprefix("/dev/")
        info = subprocess.run(["diskutil", "info", d], capture_output=True, text=True).stdout
        fields = dict(ln.strip().split(":", 1) for ln in info.splitlines() if ":" in ln)
        if fields.get("Removable Media", "").strip() == "Removable":
            size = " ".join(fields.get("Disk Size", "").split()[:2])
            out.append(f"  {d} ({fields.get('Device / Media Name', '?').strip()}, {size})")
    return "\n".join(out) or "  (none)"


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("disk"):
        print(__doc__, file=sys.stderr)
        return 2
    dev = Path(f"/dev/{sys.argv[1]}")
    listing = subprocess.run(["diskutil", "list", sys.argv[1]], capture_output=True, text=True).stdout
    if "Ventoy" not in listing or "VTOYEFI" not in listing:
        print(f"[card-boot] {dev} has no Ventoy/VTOYEFI partitions — flash it first "
              f"(sudo make flash DISK=…).\n{listing}", file=sys.stderr)
        print(f"[card-boot] removable disks right now:\n{removable_disks()}", file=sys.stderr)
        return 1
    cfg = Config()
    out = ROOT / "build" / "card-boot"
    shutil.rmtree(out, ignore_errors=True)  # QEMU logs append; don't mix in earlier runs
    failures = 0
    for profile in ("uefi", "bios"):
        vm = VM(cfg, out, profile=profile, usb_image=dev, usb_snapshot=True, net=False, name=f"card-{profile}")
        print(f"[card-boot] {profile}: booting {dev} (accel={cfg.accel}, read-only)…", flush=True)
        try:
            vm.start()
            marker = vm.wait_serial(r"ONEOS-READY[^\r\n]*", timeout=180).strip()
            ok = marker == "ONEOS-READY"
            print(f"[card-boot] {profile}: {'PASS' if ok else 'FAIL'} — {marker}", flush=True)
            failures += not ok
        except AssertionError as e:
            print(f"[card-boot] {profile}: FAIL — {str(e).splitlines()[0]}", flush=True)
            failures += 1
        finally:
            try:
                vm.screendump(out / f"card-{profile}.final.png")
            except Exception:
                pass
            vm.kill()
    print(f"[card-boot] logs: {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
