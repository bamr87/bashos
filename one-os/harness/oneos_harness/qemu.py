"""VM launcher: firmware profiles, USB-on-xHCI stick, target disk, pcap, QMP, guest agent (PLAN §7.1).

Control channels of every VM, all unix sockets in its directory (or in a short one under /tmp
when that path is too long for a socket: a deep checkout, a long test name):
  <name>.qmp         QEMU monitor (screendump, send-key, quit)
  <name>.serial      ttyS0, interactive; everything is also logged to <name>.serial.log
  <name>.qga         qemu-guest-agent (exec, files) — see qga.py / ADR-0004
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import serial
from .config import Config
from .qga import QGA, ExecResult, wait_agent

PROFILES = ("uefi", "bios", "uefi-sb")
# A unix socket's path must fit in sun_path: 108 bytes on Linux, 104 on macOS.
SOCK_PATH_MAX = 100


class QMP:
    """Minimal QMP client — enough for screendump, send-key and quit."""

    def __init__(self, path: Path, timeout: float = 30):
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                self.sock.close()
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        self.sock.settimeout(timeout)
        self._buf = b""
        self._recv()  # greeting
        self.execute("qmp_capabilities")

    def _recv(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QMP socket closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line)

    def execute(self, cmd: str, **args) -> dict:
        self.sock.sendall(json.dumps({"execute": cmd, "arguments": args} if args else {"execute": cmd}).encode() + b"\n")
        while True:
            msg = self._recv()
            if "event" in msg:
                continue
            if "error" in msg:
                raise RuntimeError(f"QMP {cmd}: {msg['error']}")
            return msg.get("return", {})

    def close(self) -> None:
        self.sock.close()

    def __enter__(self) -> QMP:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class VM:
    def __init__(self, cfg: Config, workdir: Path, profile: str = "uefi", usb_image: Path | None = None,
                 target_disk: Path | None = None, net: bool = True, cdrom: Path | None = None,
                 memory_mb: int = 4096, smp: int = 2, name: str = "vm", usb_snapshot: bool = False,
                 display: str = "none", agent: bool = True, reboot: bool = False, detach: bool = False,
                 pxe: bool = False, target_bus: str = "virtio"):
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {PROFILES}")
        self.cfg, self.profile, self.name = cfg, profile, name
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.usb_image, self.target_disk, self.cdrom, self.net = usb_image, target_disk, cdrom, net
        self.memory_mb, self.smp = memory_mb, smp
        self.usb_snapshot = usb_snapshot  # writes go to a temp file, never to usb_image
        self.display, self.agent, self.reboot, self.detach = display, agent, reboot, detach
        # pxe: boot from the network first (QEMU's TFTP serves build/netboot/tftp/boot.ipxe, which
        # chains to netboot/server.py on the host); target_bus "nvme" makes the target /dev/nvme0n1.
        self.pxe, self.target_bus = pxe, target_bus
        self.sock_dir = self.dir
        if len(str(self.dir / f"{name}.serial")) > SOCK_PATH_MAX:
            self.sock_dir = Path(tempfile.mkdtemp(prefix="oneos-vm-", dir="/tmp"))
        self.serial_log = self.dir / f"{name}.serial.log"
        self.serial_sock = self.sock_dir / f"{name}.serial"
        self.qga_path = self.sock_dir / f"{name}.qga"
        self.pcap = self.dir / f"{name}.pcap"
        self.stderr_log = self.dir / f"{name}.qemu.log"
        self.qmp_path = self.sock_dir / f"{name}.qmp"
        self.proc: subprocess.Popen | None = None
        self.qmp: QMP | None = None
        self._serial_pos = 0

    # ------------------------------------------------------------------ wiring
    def _firmware_args(self) -> list[str]:
        if self.profile == "bios":
            return []  # QEMU's default firmware is SeaBIOS
        code = self.cfg.firmware("code_sb" if self.profile == "uefi-sb" else "code")
        vars_src = self.cfg.firmware("vars_ms" if self.profile == "uefi-sb" else "vars")
        # Per-VM-name copy: a second boot of the same VM name keeps NVRAM (MOK enrollment).
        vars_copy = self.dir / f"{self.name}.OVMF_VARS.fd"
        if not vars_copy.exists():
            shutil.copyfile(vars_src, vars_copy)
        return ["-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={code}",
                "-drive", f"if=pflash,format=raw,unit=1,file={vars_copy}"]

    def argv(self) -> list[str]:
        accel = self.cfg.accel
        machine = "q35"
        if self.profile == "uefi-sb":
            machine += ",smm=on"
        a = [self.cfg.qemu_binary(), "-name", self.name, "-machine", f"{machine},accel={accel}",
             "-cpu", "host" if accel == "kvm" else "max", "-m", str(self.memory_mb), "-smp", str(self.smp),
             "-nodefaults", "-vga", "std", *self._display_args(),
             # Serial: interactive socket, and every byte also lands in the log file.
             "-chardev", f"socket,id=ser0,path={self.serial_sock},server=on,wait=off,"
                         f"logfile={self.serial_log},logappend=on",
             "-serial", "chardev:ser0",
             "-qmp", f"unix:{self.qmp_path},server=on,wait=off"]
        if not self.reboot:
            a.append("-no-reboot")
        if self.agent:
            a += ["-device", "virtio-serial-pci,id=vser0",
                  "-chardev", f"socket,id=qga0,path={self.qga_path},server=on,wait=off",
                  "-device", "virtserialport,bus=vser0.0,chardev=qga0,name=org.qemu.guest_agent.0"]
        if self.profile == "uefi-sb":
            a += ["-global", "driver=cfi.pflash01,property=secure,value=on",
                  "-global", "ICH9-LPC.disable_s3=1"]
        a += self._firmware_args()
        a += ["-device", "qemu-xhci,id=xhci"]
        if self.display == "window":
            a += ["-device", "usb-tablet,bus=xhci.0", "-device", "usb-kbd,bus=xhci.0"]
        boot = 0
        if self.pxe:
            boot = 1  # the NIC takes bootindex 0 (see the network section below)
        if self.usb_image is not None:
            fmt = "qcow2" if self.usb_image.suffix == ".qcow2" else "raw"
            snap = ",snapshot=on" if self.usb_snapshot else ""
            a += ["-drive", f"if=none,id=usb,format={fmt},file={self.usb_image},cache=unsafe{snap}",
                  "-device", f"usb-storage,bus=xhci.0,drive=usb,removable=on,bootindex={boot}"]
            boot += 1
        if self.cdrom is not None:
            a += ["-drive", f"if=none,id=cd,media=cdrom,readonly=on,format=raw,file={self.cdrom}",
                  "-device", f"ide-cd,drive=cd,bootindex={boot}"]
            boot += 1
        if self.target_disk is not None:
            a += ["-drive", f"if=none,id=target,format=qcow2,file={self.target_disk},cache=unsafe"]
            if self.target_bus == "nvme":
                a += ["-device", f"nvme,serial=ONEOS-M2-0001,drive=target,bootindex={boot}"]
            else:
                a += ["-device", f"virtio-blk-pci,drive=target,bootindex={boot}"]
        if self.net or self.pxe:
            user = "user,id=n0"
            nic = "virtio-net-pci,netdev=n0"
            if self.pxe:
                # BIOS: QEMU's iPXE NIC ROM fetches boot.ipxe over TFTP and runs it.
                # UEFI: the firmware's own stack needs an EFI program; it HTTP-boots
                # /uefi/boot.efi from netboot/server.py on the host (10.0.2.2), which hands
                # iPXE and then, to iPXE, the menu.
                boot_file = "boot.ipxe" if self.profile == "bios" else "http://10.0.2.2:8780/uefi/boot.efi"
                user += f",tftp={self.cfg.build / 'netboot' / 'tftp'},bootfile={boot_file}"
                nic += ",bootindex=0"
            a += ["-netdev", user, "-device", nic,
                  "-object", f"filter-dump,id=cap0,netdev=n0,file={self.pcap}"]
        else:
            a += ["-nic", "none"]
        return a

    def _display_args(self) -> list[str]:
        if self.display == "none":
            return ["-display", "none"]
        if self.display == "window":
            # 1:1 pixels: zoom-to-fit squeezes the guest framebuffer into the initial window
            # with nearest-neighbour scaling, which turns console text into noise.
            ui = "cocoa" if sys.platform == "darwin" else "gtk"
            return ["-display", f"{ui},zoom-to-fit=off"]
        raise ValueError("display must be 'none' or 'window'")

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> VM:
        self.sock_dir.mkdir(exist_ok=True)  # kill() removes a short one; the VM may start again
        for p in (self.qmp_path, self.serial_sock, self.qga_path):
            p.unlink(missing_ok=True)
        argv = self.argv()
        (self.dir / f"{self.name}.cmdline").write_text(" ".join(argv) + "\n")
        self._serial_pos = len(serial.read_text(self.serial_log))
        with open(self.stderr_log, "ab") as log:  # the child keeps its own copy of the fd
            # detach: own session, so it outlives the CLI that started it (scripts/oneos-vm).
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=self.detach)
        try:
            self.qmp = QMP(self.qmp_path)
        except Exception:
            self.kill()
            raise RuntimeError(f"QEMU failed to start:\n{self.stderr_log.read_text(errors='replace')[-3000:]}") from None
        return self

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait_serial(self, pattern: str, timeout: float) -> str:
        """Wait (scaled timeout) for `pattern` in serial output produced by *this* boot."""
        m, self._serial_pos = serial.wait_for(self.serial_log, pattern, self.cfg.t(timeout),
                                              start=self._serial_pos, alive=self.alive)
        return m.group(0)

    def wait_agent(self, timeout: float = 180) -> None:
        """Wait (scaled timeout) until qemu-guest-agent answers inside the guest."""
        wait_agent(self.qga_path, self.cfg.t(timeout), alive=self.alive)

    def exec(self, command: str | list[str], timeout: float = 300, check: bool = False) -> ExecResult:
        """Run a command as root in the guest via the guest agent."""
        with QGA(self.qga_path) as q:
            r = q.exec(command, timeout=self.cfg.t(timeout))
        return r.check() if check else r

    def read_file(self, path: str) -> bytes:
        with QGA(self.qga_path) as q:
            return q.read_file(path)

    def write_file(self, path: str, data: bytes) -> None:
        with QGA(self.qga_path) as q:
            q.write_file(path, data)

    def screendump(self, path: Path | None = None) -> Path:
        path = path or self.dir / f"{self.name}.screen.png"
        assert self.qmp, "VM not started"
        self.qmp.execute("screendump", filename=str(path), format="png")
        return path

    def send_keys(self, *keys: str, delay: float = 0.15) -> None:
        """send_keys("down", "down", "ret") or chords like "ctrl-alt-delete"."""
        assert self.qmp, "VM not started"
        for k in keys:
            self.qmp.execute("send-key", keys=[{"type": "qcode", "data": part} for part in k.split("-")])
            time.sleep(delay)

    def type_text(self, text: str) -> None:
        names = {" ": "spc", "\n": "ret", "-": "minus", ".": "dot", "/": "slash", "_": "shift-minus", ":": "shift-semicolon"}
        for ch in text:
            if ch.isupper():
                self.send_keys(f"shift-{ch.lower()}")
            else:
                self.send_keys(names.get(ch, ch))

    def wait_shutdown(self, timeout: float) -> int:
        assert self.proc
        try:
            return self.proc.wait(self.cfg.t(timeout))
        except subprocess.TimeoutExpired:
            raise AssertionError(f"VM {self.name} did not power off within {self.cfg.t(timeout):.0f}s;\n"
                                 f"{serial.tail(self.serial_log)}") from None
        finally:
            self._close_qmp()

    def kill(self) -> None:
        if self.alive():
            try:
                if self.qmp:
                    self.qmp.execute("quit")
                self.proc.wait(5)
            except Exception:
                self.proc.kill()
                self.proc.wait(5)
        self._close_qmp()
        if self.sock_dir != self.dir:
            shutil.rmtree(self.sock_dir, ignore_errors=True)

    def _close_qmp(self) -> None:
        if self.qmp:
            try:
                self.qmp.close()
            except OSError:
                pass
            self.qmp = None

    def __enter__(self) -> VM:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.kill()
