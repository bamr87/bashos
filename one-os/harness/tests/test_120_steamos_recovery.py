"""T120 — Valve's SteamOS recovery boots from the stick's reserved space (Ventoy F6 menu).

scripts/stick-add-steamos.sh copies Valve's recovery partitions after Ventoy's and writes
ventoy/ventoy_grub.cfg. This boots that entry and waits for Valve's own recovery desktop
("Wipe Device & Install SteamOS"): the normal way to install SteamOS, from the one-os stick.
"""
import json
import subprocess

import pytest

from oneos_harness import screen

pytestmark = pytest.mark.vm


def _has_recovery(image) -> bool:
    out = subprocess.run(["sfdisk", "-J", str(image)], capture_output=True, text=True)
    if out.returncode != 0:
        return False
    names = [p.get("name") for p in json.loads(out.stdout)["partitiontable"]["partitions"]]
    return "rootfs-A" in names and "esp" in names


def test_steamos_recovery_from_stick(image, overlay, make_vm):
    if not _has_recovery(image):
        pytest.skip("image has no SteamOS recovery partitions (steamos.recovery_on_stick false?)")
    if not screen.ocr_available():
        pytest.skip("needs tesseract")
    overlay.set_menu_timeout(60)        # time to read the menu and press F6
    vm = make_vm(profile="uefi", usb_image=overlay.path, memory_mb=4096, name="steamos-recovery").start()
    screen.wait_text(vm, "Home base", timeout=120)   # Ventoy menu up (its F-key footer is too small to OCR)
    vm.send_keys("f6")
    screen.wait_text(vm, "SteamOS recovery", timeout=30)
    vm.send_keys("ret")
    # Valve's loader (steamcl) logs to serial: it found the copied efi-A by its PARTUUID.
    vm.wait_serial(r"ChainedLoaderDevicePartUUID: [0-9A-Fa-f-]{36}", timeout=120)
    screen.wait_text(vm, "Wipe Device", timeout=900)
    vm.kill()
