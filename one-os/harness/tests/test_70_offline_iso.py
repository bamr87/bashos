"""T70 — offline fallback ISO boots to its installer (nightly)."""
import pytest

from oneos_harness import screen

pytestmark = [pytest.mark.vm, pytest.mark.nightly]
ISO = "/ISO/ubuntu-server.iso"


def test_ubuntu_server_installer(overlay, make_vm):
    if overlay.sha256(ISO.lstrip("/")) is None:
        pytest.skip(f"{ISO} not on the stick (fetch with FETCH_LARGE=1)")
    if not screen.ocr_available():
        pytest.skip("needs tesseract")
    overlay.set_default_image(ISO, timeout=1)
    with make_vm(profile="uefi", usb_image=overlay.path, name="ubuntu-server", net=False) as vm:
        screen.wait_text(vm, "Ubuntu", timeout=180)
