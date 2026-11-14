#!/usr/bin/env python3
"""capture-steamos.py diskN — capture a bootable SteamOS stick as a deployable image.

    make steamos-capture DISK=disk6

Reads the stick READ-ONLY (macOS authorization dialog via authopen; nothing is written
to it), checks its partition table is a SteamOS recovery layout (esp, efi-A, rootfs-A,
var-A, home), copies just its partitions — sparsely — to
cache/steamos/steamos-stick-<build>-<version>.img, and records the SHA-256 and metadata.
The network boot server and oneos-steamos then deploy it like Valve's own image.
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "cache" / "steamos"
CHUNK = 4 << 20
STEAMOS_PARTS = {"esp", "efi-A", "rootfs-A", "var-A", "home"}


def die(msg: str) -> None:
    raise SystemExit(f"capture-steamos: {msg}")


def disk_info(disk: str) -> dict:
    r = subprocess.run(["diskutil", "info", "-plist", disk], capture_output=True)
    if r.returncode != 0 or subprocess.run(["diskutil", "list", disk], capture_output=True).returncode != 0:
        die(f"no such disk: {disk} (check 'diskutil list')")
    return plistlib.loads(r.stdout)


def open_readonly(dev: str) -> int:
    """Open the raw device read-only: directly as root, else through authopen."""
    if os.geteuid() == 0:
        return os.open(dev, os.O_RDONLY)
    import socket
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    print(f"capture-steamos: asking macOS for read-only access to {dev} (authorization dialog)…", flush=True)
    proc = subprocess.Popen(["/usr/libexec/authopen", "-stdoutpipe", "-o", str(os.O_RDONLY), dev],
                            stdin=subprocess.DEVNULL, stdout=child)
    child.close()
    _, fds, _, _ = socket.recv_fds(parent, 1024, 1)
    proc.wait()
    parent.close()
    if not fds:
        die("authorization cancelled or denied — nothing was read")
    return fds[0]


def gpt_partitions(fd: int) -> list[dict]:
    hdr = os.pread(fd, 512, 512)
    if hdr[:8] != b"EFI PART":
        die("no GPT partition table on this disk — not a SteamOS stick")
    entries_lba, count, esize = struct.unpack_from("<QII", hdr, 72)
    table = os.pread(fd, count * esize, entries_lba * 512)
    parts = []
    for i in range(count):
        e = table[i * esize:(i + 1) * esize]
        if e[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        name = e[56:128].decode("utf-16-le").rstrip("\0")
        parts.append({"name": name, "first": first, "last": last})
    return parts


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"disk\d+", sys.argv[1]):
        print(__doc__, file=sys.stderr)
        return 2
    disk = sys.argv[1]
    info = disk_info(disk)
    if not info.get("RemovableMedia") or info.get("BusProtocol") not in ("USB", "Secure Digital"):
        die(f"{disk} is not a removable USB/SD disk")
    media = info.get("MediaName", "?")
    fd = open_readonly(f"/dev/r{disk}")
    parts = gpt_partitions(fd)
    names = {p["name"] for p in parts}
    if not STEAMOS_PARTS <= names:
        die(f"{disk} doesn't look like a SteamOS image (partitions: {sorted(names)}; need {sorted(STEAMOS_PARTS)})")
    end = (max(p["last"] for p in parts) + 1 + 33) * 512   # + room for the backup GPT
    OUT.mkdir(parents=True, exist_ok=True)
    part = OUT / f"capture-{disk}.img.part"
    print(f"capture-steamos: {media} ({disk}): SteamOS layout {sorted(names)}; copying {end / 1e9:.2f} GB")
    h = hashlib.sha256()
    out = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.ftruncate(out, end)
    t0, off = time.monotonic(), 0
    while off < end:
        n = min(CHUNK, end - off)
        buf = os.pread(fd, n, off)
        if len(buf) != n:
            die(f"short read at {off}")
        h.update(buf)
        if buf.count(0) != n:          # leave all-zero chunks as holes (sparse)
            os.pwrite(out, buf, off)
        off += n
        rate = off / max(time.monotonic() - t0, 1e-3)
        print(f"\r  read {off / 1e9:5.2f} / {end / 1e9:.2f} GB  ({rate / 1e6:5.1f} MB/s)", end="", flush=True)
    print()
    os.fsync(out)
    os.close(out)
    os.close(fd)

    # In the builder: move the backup GPT to the image's end, read the SteamOS version,
    # and check Valve's installer is inside (oneos-steamos runs it).
    rel = part.relative_to(ROOT)
    probe = subprocess.run(["docker", "run", "--rm", "--privileged", "-v", "/dev:/dev", "-v", f"{ROOT}:/work", "-w", "/work",
                            "oneos-builder:latest", "bash", "-c", f"""
set -e
sgdisk -e {rel} >/dev/null
dev=$(losetup -fP --show -r {rel}); trap 'umount /mnt/r 2>/dev/null; losetup -d $dev' EXIT
mkdir -p /mnt/r; mount -o ro ${{dev}}p3 /mnt/r
grep -E '^(VERSION_ID|BUILD_ID|VARIANT_ID)=' /mnt/r/etc/os-release
debugfs -R 'stat /deck/tools/repair_device.sh' ${{dev}}p5 2>/dev/null | grep -q 'Inode:' && echo HAS_INSTALLER=1 || echo HAS_INSTALLER=0
"""], capture_output=True, text=True)
    if probe.returncode != 0:
        die(f"could not read the captured image in the builder:\n{probe.stderr[-800:]}")
    meta = dict(line.split("=", 1) for line in probe.stdout.split() if "=" in line)
    meta = {k: v.strip('"') for k, v in meta.items()}
    if meta.get("HAS_INSTALLER") != "1":
        die("this stick has no Valve installer (home/deck/tools/repair_device.sh) — it can't be deployed by oneos-steamos")
    version, build = meta.get("VERSION_ID", "unknown"), meta.get("BUILD_ID", "unknown")
    final = OUT / f"steamos-stick-{build}-{version}.img"
    os.replace(part, final)
    # sgdisk rewrote the backup GPT, so hash the final file for what gets served.
    fh = hashlib.sha256()
    with open(final, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            fh.update(chunk)
    final.with_name(final.name + ".sha256").write_text(f"{fh.hexdigest()}  {final.name}\n")
    final.with_name(final.name + ".json").write_text(json.dumps({
        "captured_from": f"{media} ({disk})", "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": version, "build": build, "variant": meta.get("VARIANT_ID"),
        "device_sha256_of_copied_range": h.hexdigest()}, indent=2) + "\n")
    print(f"capture-steamos: SteamOS {version} (build {build}, {meta.get('VARIANT_ID')}) → {final.relative_to(ROOT)}")
    print("capture-steamos: the stick was only read; you can remove it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
