"""T20 — home base boots to ONEOS-READY (and Phase 2 acceptance: straight from the ISO)."""
import pytest

pytestmark = pytest.mark.vm


@pytest.mark.parametrize("profile", ["uefi", "bios"])
def test_home_base_boots(profile, overlay, make_vm):
    overlay.set_default_image("/ISO/oneos-lightos.iso", timeout=1)
    with make_vm(profile=profile, usb_image=overlay.path, name=f"lightos-{profile}", net=False) as vm:
        marker = vm.wait_serial(r"ONEOS-READY[^\r\n]*", timeout=120)
        # Booted from the stick, the self-test hook must be able to reach P1.
        assert marker.strip() == "ONEOS-READY", marker


@pytest.mark.parametrize("profile", ["uefi", "bios"])
def test_lightos_iso_direct(profile, cfg, make_vm):
    """No Ventoy: the ISO itself must boot and report ready (PLAN §10 phase 2)."""
    if not cfg.lightos_iso.exists():
        pytest.skip("build/oneos-lightos.iso missing — run 'make lightos'")
    with make_vm(profile=profile, cdrom=cfg.lightos_iso, name=f"iso-{profile}", net=False) as vm:
        vm.wait_serial(r"ONEOS-READY", timeout=120)


def test_desktop_autologin(overlay, make_vm):
    """T21 — the live user exists, its password is "live", and Xfce starts via autologin.

    Regression guard: with --apt-recommends false, user-setup went missing and no
    account was created, so the desktop booted to a login nobody could pass.
    """
    from conftest import selftest
    script = r"""
id user
hash=$(getent shadow user | cut -d: -f2)
[ "$(perl -e 'print crypt($ARGV[0], $ARGV[1])' live "$hash")" = "$hash" ]
echo "password ok"
for i in $(seq 1 150); do pgrep -u user -x xfce4-session >/dev/null && break; sleep 2; done
pgrep -u user -a -x xfce4-session
"""
    r = selftest(make_vm, overlay, "t21-desktop", script, net=False)
    assert r["status"] == "PASS", r["output"]
    assert "password ok" in r["output"] and "xfce4-session" in r["output"]
