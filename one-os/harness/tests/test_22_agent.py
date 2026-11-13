"""T22 — the control channel (qemu-guest-agent) works: exec, exit codes, files.

Everything scripts/oneos-vm and newer tests rely on goes through this channel.
"""
import hashlib

import pytest

pytestmark = pytest.mark.vm


def test_guest_agent_exec_and_files(overlay, make_vm):
    overlay.set_default_image("/ISO/oneos-lightos.iso", timeout=1)
    with make_vm(profile="uefi", usb_image=overlay.path, name="agent", net=False) as vm:
        vm.wait_agent(timeout=180)

        r = vm.exec("id -un; cat /etc/oneos-release", check=True)
        assert r.stdout.startswith("root\n") and "ONEOS_VERSION=" in r.stdout

        assert vm.exec("exit 7").rc == 7
        assert "boom" in vm.exec("echo boom >&2; false").stderr

        payload = bytes(range(256)) * 512  # binary, > one 48 KiB transfer chunk
        vm.write_file("/tmp/blob", payload)
        assert vm.read_file("/tmp/blob") == payload
        assert vm.exec("sha256sum /tmp/blob | cut -c1-64", check=True).stdout.strip() == hashlib.sha256(payload).hexdigest()

        # The live user is real (T21 covers the desktop); the agent sees the same system.
        assert vm.exec("getent passwd user", check=True).stdout.startswith("user:")
