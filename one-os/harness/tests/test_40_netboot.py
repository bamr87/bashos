"""T40 — netboot.xyz reaches the internet; T45 — full netboot install start (nightly)."""
import time

import pytest

from oneos_harness import netcap, screen

pytestmark = [pytest.mark.vm, pytest.mark.network]
HOST = "boot.netboot.xyz"
# UEFI boots the standalone .efi, BIOS the .iso (see manifest.yaml / docs/spike.md).
NETBOOT = {"uefi": "/ISO/netboot.xyz-snp.efi", "bios": "/ISO/netboot.xyz.iso"}


def _require(overlay, iso):
    if overlay.sha256(iso.lstrip("/")) is None:
        pytest.skip(f"{iso} not on the stick")


@pytest.mark.parametrize("profile", ["uefi", "bios"])
def test_netboot_reaches_internet(profile, overlay, make_vm, cfg):
    _require(overlay, NETBOOT[profile])
    overlay.set_default_image(NETBOOT[profile], timeout=1)
    with make_vm(profile=profile, usb_image=overlay.path, name=f"netboot-{profile}") as vm:
        deadline = time.monotonic() + cfg.t(120)
        cap = netcap.Capture()
        while time.monotonic() < deadline:
            time.sleep(5)
            cap = netcap.read(vm.pcap)
            if HOST in cap.dns_queries and cap.connected_to(HOST):
                break
        assert HOST in cap.dns_queries, f"no DNS query for {HOST}; saw {sorted(set(cap.dns_queries))}"
        assert cap.connected_to(HOST), f"no TCP connection to {HOST} {cap.resolved(HOST)}; SYNs: {cap.tcp_syns}"
        _soft_menu_check(vm)


def _soft_menu_check(vm) -> None:
    """Soft assertion (PLAN §7.3): the netboot.xyz menu is showing.

    In UEFI, iPXE's console is mirrored to serial by OVMF (and screendumps of it come
    out blank), so check serial first; in BIOS it's VGA-only, so fall back to OCR.
    """
    import warnings
    try:
        vm.wait_serial(r"netboot\.xyz", timeout=15)
        return
    except AssertionError:
        pass
    if not screen.ocr_available():
        return
    try:
        screen.wait_text(vm, "netboot.xyz", timeout=30)
    except AssertionError as e:
        warnings.warn(f"netboot.xyz menu not recognised on serial or by OCR: {e}", stacklevel=2)


@pytest.mark.nightly
@pytest.mark.xfail(reason="drives netboot.xyz's live menu by keystrokes; upstream layout changes break it", strict=False)
def test_netboot_debian_installer_starts(overlay, make_vm):
    if not screen.ocr_available():
        pytest.skip("needs tesseract")
    _require(overlay, NETBOOT["uefi"])
    overlay.set_default_image(NETBOOT["uefi"], timeout=1)
    with make_vm(profile="uefi", usb_image=overlay.path, name="netboot-install") as vm:
        screen.wait_text(vm, "Linux Network Installs", timeout=180)
        # Main menu → "Linux Network Installs" → "Debian" → newest release → "Text Based Install".
        _select(vm, "Linux Network Installs")
        screen.wait_text(vm, "Debian", timeout=60)
        _select(vm, "Debian")
        screen.wait_text(vm, "Install", timeout=60)
        vm.send_keys("ret")            # default: current stable
        screen.wait_text(vm, "Install", timeout=60)
        vm.send_keys("ret")            # default: text install
        screen.wait_text(vm, "Debian", timeout=600)


def _select(vm, label: str) -> None:
    """Best effort: jump to the item by its first letter (iPXE menu hotkeys), then Enter.

    netboot.xyz doesn't guarantee hotkeys for every entry, hence the xfail above.
    """
    vm.type_text(label[0].lower())
    vm.send_keys("ret")
