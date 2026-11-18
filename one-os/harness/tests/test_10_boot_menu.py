"""T10 — Ventoy menu renders with our aliases (OCR), in UEFI and BIOS."""
import pytest

from oneos_harness import screen

pytestmark = pytest.mark.vm


@pytest.mark.parametrize("profile", ["uefi", "bios"])
def test_menu_shows_home_base(profile, overlay, make_vm):
    if not screen.ocr_available():
        pytest.skip("tesseract not installed; T20 covers auto-boot of the default entry")
    overlay.set_menu_timeout(600)  # hold the menu while we look at it
    with make_vm(profile=profile, usb_image=overlay.path, name=f"menu-{profile}", net=False) as vm:
        text = screen.wait_text(vm, "Home base", timeout=90)
        assert "network install" in text.lower(), text  # OCR often misreads "xyz"
