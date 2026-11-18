#!/usr/bin/env python3
"""write-image.py <image> <raw-device> [--verify-only]

Copy a sparse disk image to a device, writing only the image's data extents
(SEEK_DATA/SEEK_HOLE). A card-sized image built by `make card-image` holds a
few GB of data in a 128 GB file, so this writes minutes of data instead of
hours of zeros.

Why skipping holes is safe here: every byte Ventoy2Disk, mkexfatfs and the
payload copy wrote (including zero-filled metadata) is allocated in the image;
holes are only space nothing ever wrote — free exFAT clusters and unused gaps —
whose old contents on the device are never read. The image must be exactly the
device's size so the backup GPT lands at the device's real end.

Then reads every written extent back and compares SHA-256. Called by
scripts/flash-macos.sh, which does the safety checks; don't run it directly.

Privileges: run as a normal user. On macOS the device is opened through
/usr/libexec/authopen, Apple's helper for exactly this: it shows the system
authorization dialog, opens just this one device path, and passes the open
descriptor back over a socket. Nothing else runs as root and no app needs Full
Disk Access. (Run as root, it opens the device directly.)
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import socket
import stat
import struct
import subprocess
import sys
import time

AUTHOPEN = "/usr/libexec/authopen"

CHUNK = 8 << 20


def extents(fd: int, size: int):
    off = 0
    while off < size:
        try:
            start = os.lseek(fd, off, os.SEEK_DATA)
        except OSError:  # ENXIO: no more data
            return
        end = os.lseek(fd, start, os.SEEK_HOLE)
        yield start, end
        off = end


# <sys/disk.h>: _IOR('d', 24, uint32_t) and _IOR('d', 25, uint64_t)
DKIOCGETBLOCKSIZE = 0x40046418
DKIOCGETBLOCKCOUNT = 0x40086419


def device_size(fd: int) -> int:
    """Size in bytes. macOS raw disks report 0 for SEEK_END, so ask the disk driver."""
    mode = os.fstat(fd).st_mode
    if sys.platform == "darwin" and (stat.S_ISCHR(mode) or stat.S_ISBLK(mode)):
        bs = struct.unpack("I", fcntl.ioctl(fd, DKIOCGETBLOCKSIZE, b"\0" * 4))[0]
        count = struct.unpack("Q", fcntl.ioctl(fd, DKIOCGETBLOCKCOUNT, b"\0" * 8))[0]
        return bs * count
    return os.lseek(fd, 0, os.SEEK_END)


def open_device(path: str, write: bool) -> int:
    flags = os.O_RDWR if write else os.O_RDONLY
    if os.geteuid() == 0 or sys.platform != "darwin":
        return os.open(path, flags)
    # authopen -stdoutpipe sends the descriptor back with SCM_RIGHTS on a unix socket.
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        print(f"write-image: asking macOS for permission to open {path} (authorization dialog)…",
              file=sys.stderr, flush=True)
        proc = subprocess.Popen([AUTHOPEN, "-stdoutpipe", "-o", str(flags), path],
                                stdin=subprocess.DEVNULL, stdout=child)
        child.close()
        _, fds, _, _ = socket.recv_fds(parent, 1024, 1)
        rc = proc.wait()
    finally:
        parent.close()
    if not fds:
        raise PermissionError(errno.EACCES, f"authorization cancelled or denied (authopen exit {rc})", path)
    return fds[0]


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    image, dev = sys.argv[1], sys.argv[2]
    verify_only = "--verify-only" in sys.argv
    src = os.open(image, os.O_RDONLY)
    isize = os.fstat(src).st_size
    try:
        dst = open_device(dev, write=not verify_only)
    except PermissionError as e:
        if e.errno == errno.EPERM and sys.platform == "darwin":
            # A root process opening the disk itself is checked by macOS privacy protection
            # against the app that started it; the authopen path (run without sudo) isn't.
            print(f"write-image: macOS blocked access to {dev} (privacy protection, not file permissions).\n"
                  f"  Run the flash WITHOUT sudo (make flash DISK=…) so it uses macOS's authorization\n"
                  f"  dialog, or give the app you ran it from Full Disk Access. Nothing was written.",
                  file=sys.stderr)
        else:
            print(f"write-image: could not open {dev}: {e.strerror}. Nothing was written.", file=sys.stderr)
        return 1
    dsize = device_size(dst)
    if isize != dsize:
        print(f"write-image: image is {isize} bytes but {dev} is {dsize}; build it with "
              f"'make card-image DISK=…'", file=sys.stderr)
        return 1
    ext = list(extents(src, isize))
    total = sum(e - s for s, e in ext)
    print(f"write-image: {len(ext)} extents, {total / 1e9:.2f} GB of data in a {isize / 1e9:.1f} GB image",
          file=sys.stderr)

    if not verify_only:
        done, t0 = 0, time.monotonic()
        for s, e in ext:
            off = s
            while off < e:
                n = min(CHUNK, e - off)
                buf = os.pread(src, n, off)
                os.pwrite(dst, buf, off)
                off += n
                done += n
                rate = done / max(time.monotonic() - t0, 1e-3)
                print(f"\r  wrote {done / 1e9:6.2f} / {total / 1e9:.2f} GB  ({rate / 1e6:5.1f} MB/s)",
                      end="", file=sys.stderr, flush=True)
        os.fsync(dst)
        print(file=sys.stderr)

    bad = 0
    for i, (s, e) in enumerate(ext):
        hs, hd = hashlib.sha256(), hashlib.sha256()
        off = s
        while off < e:
            n = min(CHUNK, e - off)
            hs.update(os.pread(src, n, off))
            hd.update(os.pread(dst, n, off))
            off += n
        if hs.digest() != hd.digest():
            bad += 1
            print(f"\nwrite-image: MISMATCH in extent {s}-{e}", file=sys.stderr)
        print(f"\r  verified {i + 1}/{len(ext)} extents", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    if bad:
        print(f"write-image: {bad} extents differ", file=sys.stderr)
        return 1
    print("write-image: verified OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
