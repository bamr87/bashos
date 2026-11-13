"""Per-test copy-on-write view of the stick, with P1 editing (PLAN §7.2).

The base image is never modified. Editing P1 needs the overlay as a block
device; three backends, tried in order:

  nbd   qcow2 overlay + qemu-nbd (needs the nbd kernel module — CI runners)
  fuse  qcow2 overlay + qemu-storage-daemon FUSE export + losetup
  raw   sparse/reflink copy of the raw image + losetup (works everywhere, uses more I/O)

Edits only happen while no VM is using the overlay.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path


def run(*argv: str, check: bool = True, **kw) -> subprocess.CompletedProcess:
    if os.geteuid() != 0 and argv[0] in {"losetup", "mount", "umount", "qemu-nbd", "modprobe", "blkid", "partprobe", "mknod"}:
        argv = ("sudo", *argv)
    return subprocess.run(argv, check=check, text=True, capture_output=True, **kw)


def _wait_block(dev: str, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while not os.path.exists(dev):
        if time.monotonic() > deadline:
            # No udev (container): create the node from sysfs.
            name = os.path.basename(dev)
            sysdev = Path(f"/sys/class/block/{name}/dev")
            if sysdev.exists():
                maj, mi = sysdev.read_text().strip().split(":")
                run("mknod", dev, "b", maj, mi)
                return
            raise FileNotFoundError(dev)
        time.sleep(0.1)


def _nbd_available() -> bool:
    if shutil.which("qemu-nbd") is None:
        return False
    if not os.path.exists("/sys/module/nbd"):
        run("modprobe", "nbd", "max_part=16", check=False)
    return os.path.exists("/dev/nbd0") or os.path.exists("/sys/block/nbd0")


def _fuse_available() -> bool:
    return shutil.which("qemu-storage-daemon") is not None and os.path.exists("/dev/fuse")


class Overlay:
    def __init__(self, base: Path, workdir: Path, backend: str | None = None):
        self.base = base.resolve()
        self.dir = workdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend or os.environ.get("ONEOS_OVERLAY") or self._pick_backend()
        if self.backend == "raw":
            self.path = self.dir / "usb.raw"
            subprocess.run(["cp", "--reflink=auto", "--sparse=always", str(self.base), str(self.path)], check=True)
        else:
            self.path = self.dir / "usb.qcow2"
            subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", "raw", "-b", str(self.base),
                            str(self.path)], check=True)

    @staticmethod
    def _pick_backend() -> str:
        if _nbd_available():
            return "nbd"
        if _fuse_available():
            return "fuse"
        return "raw"

    # ------------------------------------------------------------------ block access
    @contextlib.contextmanager
    def block_device(self) -> Iterator[str]:
        if self.backend == "nbd":
            dev = self._free_nbd()
            run("qemu-nbd", "--connect", dev, "--format", "qcow2", "--cache=unsafe", str(self.path))
            try:
                run("partprobe", dev, check=False)
                yield dev
            finally:
                run("qemu-nbd", "--disconnect", dev, check=False)
        elif self.backend == "fuse":
            export = self.dir / "usb.fuse"
            export.touch()
            pidfile = self.dir / "qsd.pid"
            run("qemu-storage-daemon",
                "--blockdev", f"driver=file,node-name=file0,filename={self.path}",
                "--blockdev", "driver=qcow2,node-name=disk0,file=file0",
                "--export", f"type=fuse,id=exp0,node-name=disk0,mountpoint={export},writable=on",
                "--pidfile", str(pidfile), "--daemonize")
            try:
                with self._loop(export) as dev:
                    yield dev
            finally:
                run("umount", str(export), check=False)
                if pidfile.exists():
                    with contextlib.suppress(ProcessLookupError, ValueError):
                        os.kill(int(pidfile.read_text()), 15)
        else:
            with self._loop(self.path) as dev:
                yield dev

    @contextlib.contextmanager
    def _loop(self, file: Path) -> Iterator[str]:
        dev = run("losetup", "-fP", "--show", str(file)).stdout.strip()
        try:
            run("partprobe", dev, check=False)
            yield dev
        finally:
            run("losetup", "-d", dev, check=False)

    @staticmethod
    def _free_nbd() -> str:
        for i in range(16):
            if Path(f"/sys/block/nbd{i}/size").read_text().strip() == "0":
                return f"/dev/nbd{i}"
        raise RuntimeError("no free /dev/nbdN")

    @contextlib.contextmanager
    def p1(self, readonly: bool = False) -> Iterator[Path]:
        """Mount the Ventoy data partition of the overlay."""
        with self.block_device() as dev:
            part = f"{dev}p1"
            _wait_block(part)
            mnt = Path(tempfile.mkdtemp(prefix="oneos-p1-"))
            run("mount", "-t", "exfat", "-o", f"{'ro' if readonly else 'rw'},uid={os.getuid()},gid={os.getgid()}",
                part, str(mnt))
            try:
                yield mnt
            finally:
                os.sync()
                run("umount", str(mnt), check=False)
                mnt.rmdir()

    # ------------------------------------------------------------------ edits
    def edit_ventoy_json(self, fn) -> dict:
        with self.p1() as p1:
            f = p1 / "ventoy" / "ventoy.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            fn(data)
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return data

    def set_default_image(self, iso_path: str, timeout: int = 1) -> None:
        """Make Ventoy auto-boot `iso_path` (e.g. "/ISO/netboot.xyz.iso") after `timeout` seconds."""
        if not iso_path.startswith("/"):
            iso_path = "/" + iso_path

        def fn(d):
            ctrl = [c for c in d.get("control", []) if not ({"VTOY_DEFAULT_IMAGE", "VTOY_MENU_TIMEOUT"} & c.keys())]
            ctrl += [{"VTOY_DEFAULT_IMAGE": iso_path}, {"VTOY_MENU_TIMEOUT": str(timeout)}]
            d["control"] = ctrl
        self.edit_ventoy_json(fn)

    def set_menu_timeout(self, timeout: int) -> None:
        def fn(d):
            d["control"] = [c for c in d.get("control", []) if "VTOY_MENU_TIMEOUT" not in c]
            d["control"].append({"VTOY_MENU_TIMEOUT": str(timeout)})
        self.edit_ventoy_json(fn)

    def put_selftest(self, name: str, script: str, timeout: int = 1800) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError(f"bad test name {name!r}")
        body = f"#!/bin/bash\n# name: {name}\n# timeout: {timeout}\nset -euo pipefail\n{script}\n"
        with self.p1() as p1:
            d = p1 / "oneos" / "selftest"
            (d / "results").mkdir(parents=True, exist_ok=True)
            (d / "results" / f"{name}.json").unlink(missing_ok=True)
            (d / "run.sh").write_text(body, encoding="utf-8")

    def clear_selftest(self) -> None:
        with self.p1() as p1:
            (p1 / "oneos" / "selftest" / "run.sh").unlink(missing_ok=True)

    def read_result(self, name: str) -> dict:
        with self.p1(readonly=True) as p1:
            f = p1 / "oneos" / "selftest" / "results" / f"{name}.json"
            if not f.exists():
                raise AssertionError(f"selftest {name}: no result file on P1")
            data = json.loads(f.read_text(encoding="utf-8"))
        (self.dir / f"{name}.result.json").write_text(json.dumps(data, indent=2))
        return data

    def remove(self, rel: str) -> None:
        with self.p1() as p1:
            (p1 / rel).unlink()

    def sha256(self, rel: str) -> str | None:
        import hashlib
        with self.p1(readonly=True) as p1:
            f = p1 / rel
            if not f.exists():
                return None
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)
