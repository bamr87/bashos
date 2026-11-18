#!/usr/bin/env python3
"""Capture documentation screenshots from real VMs (make docs-screenshots).

Boots the current stick image (build/one-os-card.img, else the test image) with
scripts/oneos-vm and saves PNGs into docs/images/:

  ventoy-menu-uefi.png   Ventoy menu, UEFI (countdown stopped with a keypress)
  home-base-desktop.png  Xfce desktop after autologin
  home-base-tools.png    terminal showing the oneos-* tools
  ventoy-menu-bios.png   Ventoy menu, legacy BIOS
  netboot-menu.png       netboot.xyz main menu (BIOS; needs internet)

Frames are picked by a simple rule (the busiest screen after the trigger); check the
results by eye before committing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
from oneos_harness.qemu import QMP  # noqa: E402

VM = str(ROOT / "scripts/oneos-vm")
OUT = ROOT / "docs/images"
TMP = ROOT / "build/docs-frames"


def vm(*args: str, check: bool = True) -> str:
    r = subprocess.run([VM, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"oneos-vm {' '.join(args)} failed:\n{r.stdout}{r.stderr}")
    return r.stdout


def shot(name: str, path: Path) -> int:
    with QMP(ROOT / f"build/vms/{name}/{name}.qmp", timeout=10) as q:
        q.execute("screendump", filename=str(path), format="png")
    return path.stat().st_size


def keys(name: str, *ks: str) -> None:
    with QMP(ROOT / f"build/vms/{name}/{name}.qmp", timeout=10) as q:
        for k in ks:
            q.execute("send-key", keys=[{"type": "qcode", "data": p} for p in k.split("-")])
            time.sleep(0.3)


def wait_for_menu(name: str, timeout: float = 120) -> None:
    """Ventoy's menu is a large, busy PNG; firmware/blank screens are tiny."""
    deadline = time.monotonic() + timeout
    f = TMP / f"{name}-probe.png"
    while time.monotonic() < deadline:
        if shot(name, f) > 60_000:
            keys(name, "up", "down")  # any key stops the countdown; back on the default entry
            time.sleep(1.5)
            return
        time.sleep(0.5)
    raise SystemExit(f"{name}: Ventoy menu not seen within {timeout:.0f}s")


def wait_painted(name: str, path: Path, min_bytes: int = 10_000, timeout: float = 240) -> None:
    """Desktop processes start long before Xfce paints; a black 1280x800 frame is ~3 KB,
    the painted desktop (black wallpaper) ~20 KB."""
    deadline = time.monotonic() + timeout
    while shot(name, path) < min_bytes:
        if time.monotonic() > deadline:
            raise SystemExit(f"{name}: screen still blank after {timeout:.0f}s ({path})")
        time.sleep(3)
    time.sleep(5)  # let icons/thumbnails settle
    shot(name, path)


def busiest_text_frame(name: str, seconds: float, every: float = 2.0) -> Path:
    """Busiest frame once the graphical Ventoy screen is gone. iPXE's text-mode menu
    compresses to a few KB, so Ventoy's (and its loading dialog's) ~100 KB frames must
    be skipped rather than compared."""
    best, best_size = None, 0
    for i in range(int(seconds / every)):
        f = TMP / f"{name}-{i:03d}.png"
        size = shot(name, f)
        if size < 60_000 and size >= best_size:
            best, best_size = f, size
        time.sleep(every)
    if best is None:
        raise SystemExit(f"{name}: never left the Ventoy screen")
    return best


def main() -> int:
    # The newest stick image: the card image is only rebuilt when a card is inserted.
    images = [p for p in (ROOT / "build/one-os-card.img", ROOT / "build/one-os-test.img") if p.exists()]
    if not images:
        raise SystemExit("no stick image — run 'make image'")
    image = max(images, key=lambda p: p.stat().st_mtime)
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)

    # UEFI: menu → home base → desktop → tools
    vm("start", "docs-uefi", "--fresh", "--no-net", "--image", str(image))
    try:
        wait_for_menu("docs-uefi")
        shot("docs-uefi", OUT / "ventoy-menu-uefi.png")
        keys("docs-uefi", "ret")
        vm("wait", "docs-uefi", "--agent", "--timeout", "900")
        vm("exec", "docs-uefi", "--timeout", "600", "--",
           "for i in $(seq 1 200); do pgrep -u user -x xfce4-panel >/dev/null && "
           "pgrep -u user -x xfdesktop >/dev/null && break; sleep 3; done")
        wait_painted("docs-uefi", OUT / "home-base-desktop.png")
        demo = ("clear; echo '$ oneos-install --help'; oneos-install --help; echo; "
                "echo '$ sudo oneos-restock --list'; sudo oneos-restock --list; exec bash")
        vm("exec", "docs-uefi", "--",
           "su - user -c \"DISPLAY=:0 setsid xfce4-terminal --geometry=110x32 "
           f"-T 'one-os tools' -x bash -c {_q(demo)} >/dev/null 2>&1 &\"")
        vm("exec", "docs-uefi", "--timeout", "300", "--",
           "for i in $(seq 1 100); do pgrep -u user -x xfce4-terminal >/dev/null && break; sleep 2; done; sleep 20")
        shot("docs-uefi", OUT / "home-base-tools.png")
    finally:
        vm("stop", "docs-uefi", "--force", check=False)

    # BIOS: menu → netboot.xyz (entries sort by file name: netboot first, home base second)
    vm("start", "docs-bios", "--fresh", "--profile", "bios", "--image", str(image))
    try:
        wait_for_menu("docs-bios")
        shot("docs-bios", OUT / "ventoy-menu-bios.png")
        keys("docs-bios", "up", "ret")
        best = busiest_text_frame("docs-bios", seconds=150)
        shutil.copyfile(best, OUT / "netboot-menu.png")
    finally:
        vm("stop", "docs-bios", "--force", check=False)

    for p in sorted(OUT.glob("*.png")):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KiB")
    return 0


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    sys.exit(main())
