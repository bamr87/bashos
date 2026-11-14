"""T80 — Secure Boot path: MOK enrollment then home base (nightly)."""
import pytest

from oneos_harness import screen

pytestmark = [pytest.mark.vm, pytest.mark.nightly]


@pytest.mark.xfail(reason="MokManager is keystroke-driven; sequence verified manually per docs/hardware-checklist.md", strict=False)
def test_secure_boot_enroll_then_boot(overlay, make_vm, cfg):
    if not screen.ocr_available():
        pytest.skip("needs tesseract")
    try:
        cfg.firmware("code_sb"), cfg.firmware("vars_ms")
    except FileNotFoundError as e:
        pytest.skip(str(e))
    overlay.set_default_image("/ISO/oneos-lightos.iso", timeout=1)
    vm = make_vm(profile="uefi-sb", usb_image=overlay.path, name="sb").start()
    # First boot: shim can't verify Ventoy's grub → "Verification failed" → MokManager.
    screen.wait_text(vm, "Verification failed", timeout=120)
    vm.send_keys("ret")
    screen.wait_text(vm, "Perform MOK management", timeout=60)
    # "Enroll key from disk" is the 3rd item; then VTOYEFI volume → the .cer file.
    vm.send_keys("down", "down", "ret")
    screen.wait_text(vm, "VTOYEFI", timeout=30)
    vm.send_keys("ret")
    screen.wait_text(vm, "ENROLL_THIS_KEY", timeout=30)
    vm.send_keys("down", "ret")          # skip "../" → the cert
    screen.wait_text(vm, "Continue", timeout=30)
    vm.send_keys("down", "ret")          # Continue
    screen.wait_text(vm, "Enroll the key", timeout=30)
    vm.send_keys("down", "ret")          # Yes
    screen.wait_text(vm, "Reboot", timeout=30)
    vm.send_keys("ret")
    # -no-reboot makes QEMU exit on reboot; boot again with the same NVRAM.
    vm.wait_shutdown(60)
    vm2 = make_vm(profile="uefi-sb", usb_image=overlay.path, name="sb").start()
    vm2.wait_serial(r"ONEOS-READY", timeout=180)
