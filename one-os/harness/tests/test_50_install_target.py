"""T50 — install Debian to a second disk, then boot it with the USB removed. T51 — refuse own disk."""
import os
import subprocess

import pytest
from conftest import selftest

from oneos_harness import VM

pytestmark = pytest.mark.vm


def test_install_to_target_then_boot_without_usb(overlay, make_vm, run_dir, cfg):
    target = run_dir / "target.qcow2"
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", str(target), "20G"], check=True)
    mirror = os.environ.get("ONEOS_MIRROR", "")
    script = (f"export ONEOS_MIRROR={mirror!r}\n" if mirror else "") + (
        "oneos-install --unattended --distro debian --target /dev/vda --hostname t50 --user tester")
    r = selftest(make_vm, overlay, "t50-install", script, timeout=1800, target_disk=target)
    assert r["status"] == "PASS", r["output"][-4000:]

    # Second boot: only the target disk. No USB attached at all.
    vm: VM = make_vm(profile="uefi", target_disk=target, name="t50-target", net=False).start()
    vm.wait_serial(r"ONEOS-INSTALLED-OK", timeout=180)
    vm.kill()


def test_install_refuses_own_disk(overlay, make_vm):
    script = r"""
set -x
# P1 may be visible twice (sda1 and our dm view); walk down to the real disk.
usb=$(lsblk -lspno NAME,TYPE "$(blkid -L Ventoy)" | awk '$2=="disk"{print $1}' | head -1)
[ -n "$usb" ]
before=$(dd if="$usb" bs=1M count=1 status=none | sha256sum)
if oneos-install --unattended --distro debian --target "$usb"; then
  echo "oneos-install accepted the boot disk!"; exit 1
fi
after=$(dd if="$usb" bs=1M count=1 status=none | sha256sum)
[ "$before" = "$after" ]
echo refused-and-untouched
"""
    r = selftest(make_vm, overlay, "t51-refuse", script, net=False)
    assert r["status"] == "PASS", r["output"]
    assert "refused-and-untouched" in r["output"]
    # P1 still intact from the host's point of view.
    assert overlay.sha256("ventoy/ventoy.json") is not None
