"""T100 — network boot; T110 — SteamOS onto the M.2 over the network (nightly).

A VM with no stick and an empty NVMe drive (/dev/nvme0n1, like an M.2 slot) boots from
the network: UEFI via HTTP boot (/uefi/boot.efi → iPXE → menu), BIOS via QEMU's iPXE ROM
(TFTP boot.ipxe → menu). netboot/server.py runs on the host side (10.0.2.2 in the VM).
"""
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.vm
PORT = 8780


@pytest.fixture(scope="module")
def netboot_server(cfg):
    if not (cfg.build / "netboot" / "live" / "filesystem.squashfs").exists():
        pytest.skip("build/netboot/ missing — run 'make netboot'")
    cfg.runs.mkdir(parents=True, exist_ok=True)
    log = open(cfg.runs / "netboot-server.log", "ab")
    proc = subprocess.Popen([sys.executable, str(cfg.repo / "netboot" / "server.py"), "--port", str(PORT)],
                            stdout=log, stderr=subprocess.STDOUT)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=1).read()
            break
        except OSError:
            time.sleep(0.2)
    yield f"http://127.0.0.1:{PORT}"
    proc.terminate()
    proc.wait(10)


def _status(base: str) -> dict:
    import json
    return json.loads(urllib.request.urlopen(f"{base}/api/status", timeout=5).read())


@pytest.mark.parametrize("profile", ["uefi", "bios"])
def test_network_boot_home_base(profile, netboot_server, make_vm, run_dir):
    target = run_dir / "m2.qcow2"
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", str(target), "64G"], check=True)
    vm = make_vm(profile=profile, pxe=True, net=True, target_disk=target, target_bus="nvme",
                 memory_mb=6144, name=f"pxe-{profile}").start()
    vm.wait_serial(r"ONEOS-READY[^\r\n]*", timeout=300)
    vm.wait_agent(timeout=180)
    r = vm.exec("cat /proc/cmdline; lsblk -dno NAME,SIZE /dev/nvme0n1", check=True)
    assert f"fetch=http://10.0.2.2:{PORT}/live/filesystem.squashfs" in r.stdout
    assert "oneos.server=" in r.stdout and "nvme0n1" in r.stdout
    seen = " ".join(e["msg"] for e in _status(netboot_server)["events"])
    for what in ("menu for", "/live/vmlinuz", "/live/initrd.img", "/live/oneos-net.cpio", "/live/filesystem.squashfs"):
        assert what in seen, f"server never saw {what!r}: {seen[-800:]}"
    # netboot/initrd/ replaced live-boot's link detection (it gives up too soon on 2.5 GbE cards)
    assert "one-os: link up on" in vm.serial_log.read_text(errors="replace"), "overlay's link detection never ran"
    vm.kill()


@pytest.mark.nightly
def test_steamos_network_install(netboot_server, make_vm, run_dir, cfg):
    status = _status(netboot_server)
    if not status["steamos"]:
        pytest.skip("no SteamOS image cached — run 'make steamos-fetch' or 'make steamos-capture'")
    version = status["steamos"]["version"]
    target = run_dir / "m2.qcow2"
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", str(target), "64G"], check=True)
    vm = make_vm(profile="uefi", pxe=True, net=True, target_disk=target, target_bus="nvme",
                 memory_mb=8192, smp=4, name="steamos").start()
    vm.wait_agent(timeout=300)
    r = vm.exec("oneos-steamos --unattended --yes", timeout=7200)
    (run_dir / "oneos-steamos.out").write_text(r.stdout + r.stderr)
    assert r.rc == 0, r.stdout[-3000:] + r.stderr[-2000:]
    labels = vm.exec("lsblk -nro PARTLABEL /dev/nvme0n1", check=True).stdout.split()
    assert set(labels) >= {"esp", "efi-A", "efi-B", "rootfs-A", "rootfs-B", "var-A", "var-B", "home"}, labels
    events = " ".join(e["msg"] for e in _status(netboot_server)["events"] if e["kind"] == "report")
    assert f"SteamOS {version} installed" in events, events[-800:]
    vm.exec("sync; systemctl poweroff", timeout=30)
    vm.wait_shutdown(300)

    # Boot the M.2 alone, network unplugged: SteamOS's boot loader is in the ESP's fallback path.
    sos = make_vm(profile="uefi", target_disk=target, target_bus="nvme", net=False, agent=False,
                  memory_mb=8192, smp=4, name="steamos-boot").start()
    deadline = time.monotonic() + cfg.t(240)
    biggest = 0
    while time.monotonic() < deadline and biggest < 20_000:
        biggest = max(biggest, sos.screendump(run_dir / "steamos-boot.png").stat().st_size)
        time.sleep(5)
    sos.kill()
    assert biggest >= 20_000, "the M.2 didn't show anything on screen (see steamos-boot.png and the serial log)"
