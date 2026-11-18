"""oneos-vm — start, drive, inspect and debug one-os VMs by name.

Built for an agent (Claude Code) and a human to share the same instance: every
command is non-interactive, prints plain text, and exits non-zero on failure; a
human can add --window to watch, or `console` for an interactive serial login.

  oneos-vm start NAME [--window] [--profile uefi|bios|uefi-sb] [--fresh]
                       [--image IMG | --iso ISO | --disk diskN [--write] | --pxe]
                       [--target SIZE [--target-bus nvme|virtio]] [--no-usb] [--no-net]
                       [--mem MB] [--smp N]
  oneos-vm list
  oneos-vm status NAME
  oneos-vm wait NAME [--agent | --ready | --serial REGEX | --screen TEXT] [--timeout S]
  oneos-vm exec NAME [--timeout S] -- CMD...      (root, via qemu-guest-agent)
  oneos-vm cp NAME SRC DST                         (vm:/path on one side)
  oneos-vm screenshot NAME [OUT.png]
  oneos-vm keys NAME KEY...                        (qcodes: ret, esc, down, ctrl-alt-f2…)
  oneos-vm type NAME TEXT
  oneos-vm serial NAME [-n LINES] [-f]
  oneos-vm console NAME [--send TEXT] [--read S]   (interactive on a tty)
  oneos-vm logs NAME
  oneos-vm stop NAME [--force]
  oneos-vm rm NAME

Instances live in build/vms/NAME/. Overlays persist across stop/start; --fresh
discards them. Timeouts are in real seconds (no TCG scaling) unless noted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import serial as serial_mod
from .config import Config
from .qemu import QMP, VM
from .qga import QGA, AgentUnavailable, wait_agent

READY_RE = r"ONEOS-READY[^\r\n]*"


class Instance:
    def __init__(self, cfg: Config, name: str):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,23}", name):
            raise SystemExit("instance names: lowercase letters, digits, dashes; max 24 chars")
        self.cfg, self.name = cfg, name
        self.dir = cfg.build / "vms" / name
        self.meta_path = self.dir / "instance.json"

    # paths match qemu.VM's naming
    def p(self, suffix: str) -> Path:
        return self.dir / f"{self.name}{suffix}"

    @property
    def meta(self) -> dict:
        try:
            return json.loads(self.meta_path.read_text())
        except FileNotFoundError:
            raise SystemExit(f"no instance '{self.name}' (oneos-vm list)") from None

    def pid(self) -> int | None:
        try:
            pid = self.meta.get("pid")
        except SystemExit:
            return None
        if not pid:
            return None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        except PermissionError:  # started with sudo (physical disk); still alive
            pass
        return pid

    def running(self) -> bool:
        return self.pid() is not None

    def require_running(self) -> None:
        if not self.running():
            raise SystemExit(f"instance '{self.name}' is not running (oneos-vm start {self.name})")

    def qmp(self) -> QMP:
        self.require_running()
        return QMP(self.p(".qmp"), timeout=10)

    def qga(self, timeout: float = 10) -> QGA:
        self.require_running()
        return QGA(self.p(".qga"), timeout=timeout)


# --------------------------------------------------------------------------- commands
def cmd_start(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    if inst.running():
        print(f"'{a.name}' is already running (pid {inst.pid()})")
        return 0
    if a.fresh and inst.dir.exists():
        shutil.rmtree(inst.dir)
    inst.dir.mkdir(parents=True, exist_ok=True)
    if len(str(inst.p(".serial"))) > 100:
        raise SystemExit(f"socket path too long for macOS ({inst.p('.serial')}); use a shorter name or path")

    usb = cdrom = None
    snapshot = False
    source: str
    if a.disk:
        if os.geteuid() != 0:
            raise SystemExit(f"booting a physical disk needs root: sudo scripts/oneos-vm start {a.name} --disk {a.disk}")
        listing = subprocess.run(["diskutil", "list", a.disk], capture_output=True, text=True).stdout
        if "VTOYEFI" not in listing:
            raise SystemExit(f"{a.disk} has no Ventoy layout — flash it first")
        subprocess.run(["diskutil", "unmountDisk", f"/dev/{a.disk}"], capture_output=True)
        usb, snapshot = Path(f"/dev/{a.disk}"), not a.write
        source = f"/dev/{a.disk} ({'WRITABLE' if a.write else 'read-only snapshot'})"
    elif a.iso:
        cdrom = Path(a.iso).resolve()
        source = f"{cdrom.name} as CD-ROM (no Ventoy)"
    elif a.pxe:
        source = "network boot (PXE → netboot/server.py)"
        ensure_netboot_server(cfg)
    elif not a.no_usb:
        base = Path(a.image).resolve() if a.image else next(
            (p for p in (cfg.build / "one-os-card.img", cfg.image) if p.exists()), None)
        if base is None or not base.exists():
            raise SystemExit("no stick image — run 'make image' or 'make card-image DISK=…', or pass --image")
        usb = inst.dir / "usb.qcow2"
        stamp = f"{base} {int(base.stat().st_mtime)} {base.stat().st_size}"
        stamp_file = inst.dir / "usb.base"
        if not usb.exists() or (stamp_file.read_text() if stamp_file.exists() else "") != stamp:
            if usb.exists():
                print("stick image changed since this overlay was made — starting a fresh overlay")
            usb.unlink(missing_ok=True)
            subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "raw", "-b", str(base), str(usb)],
                           check=True)
            stamp_file.write_text(stamp)
        source = f"{base.name} via overlay {usb.relative_to(cfg.repo)}"
    else:
        source = "no stick"

    target = None
    if a.target or a.no_usb:
        target = inst.dir / "target.qcow2"
        if not target.exists():
            if not a.target:
                raise SystemExit("--no-usb boots the target disk, but this instance has none; add --target 20G")
            subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", str(target), a.target], check=True)

    vm = VM(cfg, inst.dir, profile=a.profile, usb_image=usb, cdrom=cdrom, target_disk=target,
            net=not a.no_net, memory_mb=a.mem, smp=a.smp, name=a.name, usb_snapshot=snapshot,
            display="window" if a.window else "none", agent=True, reboot=True, detach=True,
            pxe=a.pxe, target_bus=a.target_bus)
    vm.start()
    vm._close_qmp()  # free the single QMP slot for later commands
    inst.meta_path.write_text(json.dumps({
        "name": a.name, "pid": vm.proc.pid, "profile": a.profile, "source": source,
        "target": str(target) if target else None, "window": a.window, "net": not a.no_net,
        "started": time.time(), "accel": cfg.accel,
    }, indent=2))
    tdev = "/dev/nvme0n1" if a.target_bus == "nvme" else "/dev/vda"
    print(f"started '{a.name}' (pid {vm.proc.pid}): {a.profile}, {cfg.accel}, {source}"
          + (f", target disk {tdev}" if target else "") + (", window" if a.window else ", headless"))
    print(f"next: oneos-vm wait {a.name} --agent   then   oneos-vm exec {a.name} -- <cmd>")
    return 0


def ensure_netboot_server(cfg: Config, port: int = 8780) -> None:
    """PXE VMs fetch the menu and the home base from netboot/server.py on the host."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2).read()
        return
    except OSError:
        pass
    if not (cfg.build / "netboot" / "live" / "filesystem.squashfs").exists():
        raise SystemExit("no network-boot files — run 'make netboot' first")
    log = open(cfg.build / "netboot" / "server.out", "ab")
    subprocess.Popen([sys.executable, str(cfg.repo / "netboot" / "server.py"), "--port", str(port)],
                     stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1).read()
            print(f"started the network boot server on :{port} (log: build/netboot/server.out)")
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit("the network boot server didn't start; see build/netboot/server.out")


def cmd_list(cfg: Config, a: argparse.Namespace) -> int:
    root = cfg.build / "vms"
    names = sorted(p.name for p in root.iterdir() if (p / "instance.json").exists()) if root.exists() else []
    if not names:
        print("no instances (oneos-vm start NAME)")
        return 0
    print(f"{'NAME':16} {'STATE':8} {'PROFILE':8} SOURCE")
    for n in names:
        inst = Instance(cfg, n)
        m = inst.meta
        print(f"{n:16} {'running' if inst.running() else 'stopped':8} {m['profile']:8} {m['source']}")
    return 0


def cmd_status(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    m = inst.meta
    up = inst.running()
    state = f"running (pid {inst.pid()}, up {time.time() - m['started']:.0f}s)" if up else "stopped"
    print(f"name     {a.name}\nstate    {state}")
    print(f"profile  {m['profile']} ({m.get('accel')})\nsource   {m['source']}")
    log = serial_mod.read_text(inst.p(".serial.log"))
    ready = re.findall(READY_RE, log)
    print(f"ready    {ready[-1].strip() if ready else 'not yet'}")
    if up:
        try:
            with inst.qga(timeout=10) as q:
                q.ping()
            print("agent    up")
        except AgentUnavailable:
            print("agent    not answering (still booting, or not in this image)")
    lines = [ln for ln in re.sub(r"\x1b\[[0-9;?=]*[A-Za-z]", "", log).splitlines() if ln.strip()]
    print("serial   " + ("\n         ".join(lines[-5:]) if lines else "(empty)"))
    return 0


def cmd_wait(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    inst.require_running()
    t0 = time.monotonic()
    if a.serial or a.ready:
        pattern = a.serial or READY_RE
        start = 0 if a.ready else len(serial_mod.read_text(inst.p(".serial.log")))
        m, _ = serial_mod.wait_for(inst.p(".serial.log"), pattern, a.timeout, start=start, alive=inst.running)
        print(m.group(0).strip())
    elif a.screen:
        from . import screen
        deadline = time.monotonic() + a.timeout
        while True:
            png = inst.p(".wait.png")
            with inst.qmp() as q:
                q.execute("screendump", filename=str(png), format="png")
            if a.screen.lower() in screen.ocr(png).lower():
                break
            if time.monotonic() > deadline:
                raise SystemExit(f"'{a.screen}' not on screen after {a.timeout:.0f}s ({png})")
            time.sleep(3)
        print(f"'{a.screen}' on screen")
    else:
        wait_agent(inst.p(".qga"), a.timeout, alive=inst.running)
        print("agent up")
    print(f"({time.monotonic() - t0:.0f}s)")
    return 0


def cmd_exec(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    if not a.command:
        raise SystemExit("usage: oneos-vm exec NAME -- CMD...")
    cmd = a.command[0] if len(a.command) == 1 else " ".join(_shquote(c) for c in a.command)
    with inst.qga(timeout=30) as q:
        r = q.exec(cmd, timeout=a.timeout)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.rc


def cmd_cp(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    with inst.qga(timeout=60) as q:
        if a.src.startswith("vm:") and not a.dst.startswith("vm:"):
            data = q.read_file(a.src[3:])
            dst = Path(a.dst)
            if dst.is_dir():
                dst = dst / Path(a.src[3:]).name
            dst.write_bytes(data)
            print(f"{a.src} → {dst} ({len(data)} bytes)")
        elif a.dst.startswith("vm:") and not a.src.startswith("vm:"):
            data = Path(a.src).read_bytes()
            q.write_file(a.dst[3:], data)
            print(f"{a.src} → {a.dst} ({len(data)} bytes)")
        else:
            raise SystemExit("exactly one of SRC/DST must start with vm:")
    return 0


def cmd_screenshot(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    out = Path(a.out).resolve() if a.out else inst.p(".screen.png")
    with inst.qmp() as q:
        q.execute("screendump", filename=str(out), format="png")
    print(out)
    return 0


def cmd_keys(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    with inst.qmp() as q:
        for k in a.keys:
            q.execute("send-key", keys=[{"type": "qcode", "data": part} for part in k.split("-")])
            time.sleep(0.15)
    return 0


def cmd_type(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    names = {" ": "spc", "\n": "ret", "-": "minus", ".": "dot", "/": "slash", ",": "comma", "=": "equal",
             ";": "semicolon", "'": "apostrophe", "\t": "tab", "\\": "backslash"}
    shifted = {"_": "minus", ":": "semicolon", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
               "&": "7", "*": "8", "(": "9", ")": "0", "+": "equal", '"': "apostrophe", "?": "slash",
               "<": "comma", ">": "dot", "|": "backslash", "~": "grave_accent"}
    with inst.qmp() as q:
        for ch in a.text.encode().decode("unicode_escape"):
            if ch in shifted:
                keys = ["shift", shifted[ch]]
            elif ch.isupper():
                keys = ["shift", ch.lower()]
            else:
                keys = [names.get(ch, ch)]
            q.execute("send-key", keys=[{"type": "qcode", "data": k} for k in keys])
            time.sleep(0.08)
    return 0


def cmd_serial(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    log = inst.p(".serial.log")
    clean = lambda s: re.sub(r"\x1b\[[0-9;?=]*[A-Za-z]|\r", "", s)  # noqa: E731
    text = clean(serial_mod.read_text(log))
    print("\n".join(text.splitlines()[-a.lines:]))
    if a.follow:
        pos = len(serial_mod.read_text(log))
        try:
            while inst.running():
                cur = serial_mod.read_text(log)
                if len(cur) > pos:
                    sys.stdout.write(clean(cur[pos:]))
                    sys.stdout.flush()
                    pos = len(cur)
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


def cmd_console(cfg: Config, a: argparse.Namespace) -> int:
    """Talk to ttyS0. Interactive on a terminal (Ctrl-] to leave); scripted with --send."""
    inst = Instance(cfg, a.name)
    inst.require_running()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(inst.p(".serial")))
    if a.send is not None or not sys.stdin.isatty():
        payload = (a.send if a.send is not None else sys.stdin.read()).encode().decode("unicode_escape")
        s.sendall(payload.encode())
        out, deadline = b"", time.monotonic() + a.read
        while time.monotonic() < deadline:
            r, _, _ = select.select([s], [], [], 0.2)
            if r:
                chunk = s.recv(65536)
                if not chunk:
                    break
                out += chunk
        sys.stdout.write(re.sub(r"\x1b\[[0-9;?=]*[A-Za-z]|\r", "", out.decode("utf-8", "replace")))
        return 0
    import termios
    import tty
    print(f"[console {a.name}: ttyS0 — press Enter for a login prompt, Ctrl-] to leave]")
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin)
        while True:
            r, _, _ = select.select([s, sys.stdin], [], [])
            if s in r:
                data = s.recv(65536)
                if not data:
                    break
                os.write(sys.stdout.fileno(), data)
            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                if b"\x1d" in data:
                    break
                s.sendall(data)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        print()
    return 0


def cmd_logs(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    for suffix, what in ((".serial.log", "serial console (ttyS0)"), (".qemu.log", "QEMU stderr"),
                         (".pcap", "network capture"), (".cmdline", "QEMU command line"),
                         (".screen.png", "last screenshot")):
        p = inst.p(suffix)
        if p.exists():
            print(f"{what:24} {p}  ({p.stat().st_size} bytes)")
    print(f"{'instance metadata':24} {inst.meta_path}")
    return 0


def cmd_stop(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    pid = inst.pid()
    if pid is None:
        print(f"'{a.name}' is not running")
        return 0
    if not a.force:
        try:  # clean shutdown keeps the persistence file consistent
            with inst.qga(timeout=3) as q:
                q.shutdown()
        except AgentUnavailable:
            with inst.qmp() as q:
                q.execute("system_powerdown")
        deadline = time.monotonic() + a.timeout
        while time.monotonic() < deadline and inst.running():
            time.sleep(1)
    if inst.running():
        try:
            with inst.qmp() as q:
                q.execute("quit")
        except Exception:
            os.kill(pid, signal.SIGKILL)
        time.sleep(1)
    print(f"stopped '{a.name}'" + (" (forced)" if a.force else ""))
    return 0


def cmd_rm(cfg: Config, a: argparse.Namespace) -> int:
    inst = Instance(cfg, a.name)
    if inst.running():
        raise SystemExit(f"'{a.name}' is running; oneos-vm stop {a.name} first")
    shutil.rmtree(inst.dir, ignore_errors=True)
    print(f"removed '{a.name}'")
    return 0


def _shquote(s: str) -> str:
    return s if re.fullmatch(r"[\w@%+=:,./-]+", s) else "'" + s.replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------- argparse
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="oneos-vm", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("start")
    s.add_argument("name")
    s.add_argument("--window", action="store_true", help="show the screen in a window")
    s.add_argument("--profile", default="uefi", choices=["uefi", "bios", "uefi-sb"])
    s.add_argument("--fresh", action="store_true", help="discard this instance's overlay/NVRAM/target first")
    src = s.add_mutually_exclusive_group()
    src.add_argument("--image", help="raw stick image (default: build/one-os-card.img, else one-os-test.img)")
    src.add_argument("--iso", help="boot an ISO as CD-ROM instead of the stick")
    src.add_argument("--disk", help="physical stick, e.g. disk5 (macOS, sudo)")
    src.add_argument("--pxe", action="store_true", help="no stick: boot from the network (starts netboot/server.py)")
    s.add_argument("--write", action="store_true", help="with --disk: write through to the stick")
    s.add_argument("--target", metavar="SIZE", help="attach an empty install-target disk, e.g. 64G")
    s.add_argument("--target-bus", choices=["nvme", "virtio"], default="nvme",
                   help="nvme (default; /dev/nvme0n1 like an M.2 drive) or virtio (/dev/vda)")
    s.add_argument("--no-usb", action="store_true", help="boot the target disk only (after an install)")
    s.add_argument("--no-net", action="store_true")
    s.add_argument("--mem", type=int, default=4096)
    s.add_argument("--smp", type=int, default=4)

    for name in ("list",):
        sp.add_parser(name)
    for name in ("status", "logs", "rm"):
        sp.add_parser(name).add_argument("name")

    w = sp.add_parser("wait")
    w.add_argument("name")
    g = w.add_mutually_exclusive_group()
    g.add_argument("--agent", action="store_true", help="guest agent answers (default)")
    g.add_argument("--ready", action="store_true", help="ONEOS-READY on serial")
    g.add_argument("--serial", metavar="REGEX", help="new serial output matching REGEX")
    g.add_argument("--screen", metavar="TEXT", help="TEXT visible on screen (OCR)")
    w.add_argument("--timeout", type=float, default=600)

    e = sp.add_parser("exec")
    e.add_argument("name")
    e.add_argument("--timeout", type=float, default=600)
    e.add_argument("command", nargs="*", help="after --; one argument is run by /bin/sh -c")

    c = sp.add_parser("cp")
    c.add_argument("name")
    c.add_argument("src")
    c.add_argument("dst")

    sc = sp.add_parser("screenshot")
    sc.add_argument("name")
    sc.add_argument("out", nargs="?")

    k = sp.add_parser("keys")
    k.add_argument("name")
    k.add_argument("keys", nargs="+")

    t = sp.add_parser("type")
    t.add_argument("name")
    t.add_argument("text")

    se = sp.add_parser("serial")
    se.add_argument("name")
    se.add_argument("-n", "--lines", type=int, default=40)
    se.add_argument("-f", "--follow", action="store_true")

    co = sp.add_parser("console")
    co.add_argument("name")
    co.add_argument("--send", help=r"send TEXT (escapes like \n allowed), print the reply, exit")
    co.add_argument("--read", type=float, default=3, help="seconds to collect output after --send")

    st = sp.add_parser("stop")
    st.add_argument("name")
    st.add_argument("--force", action="store_true")
    st.add_argument("--timeout", type=float, default=120)

    # Everything after the first "--" is the guest command, verbatim (argparse would
    # otherwise take options like --timeout that follow the instance name).
    argv = list(sys.argv[1:] if argv is None else argv)
    tail: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, tail = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    if a.cmd == "exec" and tail:
        a.command = tail
    cfg = Config()
    try:
        return globals()[f"cmd_{a.cmd}"](cfg, a)
    except AgentUnavailable as e:
        print(f"oneos-vm: {e}", file=sys.stderr)
        return 3
    except (serial_mod.SerialTimeout, TimeoutError) as e:
        print(f"oneos-vm: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
