#!/usr/bin/env python3
"""one-os network boot server: HTTP, plus ProxyDHCP + TFTP for real PXE.

    python3 netboot/server.py                       # HTTP only (QEMU tests, iPXE from the stick)
    python3 netboot/server.py --pxe --iface en5     # + ProxyDHCP/TFTP: PCs on that LAN can PXE-boot

HTTP (port 8780)
  /boot.ipxe                 hands over to /menu.ipxe?mac=<client MAC>
  /menu.ipxe                 iPXE menu (home base in RAM, Install SteamOS, netboot.xyz, local disk);
                             defaults to the local disk for PCs that already got SteamOS
  /live/{vmlinuz,initrd.img,filesystem.squashfs}   the home base, from build/netboot/
  /live/oneos-net.cpio      netboot/initrd/ as a second initrd (patient wired-link detection)
  /tftp/<loader>             iPXE loaders (also for UEFI HTTP boot clients)
  /uefi/boot.efi             UEFI HTTP boot entry point: firmware gets iPXE (snponly.efi); iPXE
                             asking for the same URL gets the menu script (no chain-load loop)
  /netboot/netboot.xyz.{efi,iso}                   from cache/ISO/
  /steamos/<file>            SteamOS images in cache/steamos/: Valve's .img.bz2 or a captured
                             stick's .img (make steamos-capture)
  /steamos/latest.json       the image to deploy (cache/steamos/SELECTED, else the newest):
                             version, size, sha256, url_path
  /docs/…, /src/one-os.bundle   rendered documentation and the repository (git bundle)
  /report?stage=&pct=&msg=   installers report progress here
  /tools/[oneos-*]          the home base's tools from the repo (the boot hook installs them, so
                             fixes reach network-booted PCs without rebuilding the ISO)
  /ssh/authorized_keys       public SSH keys for network-booted PCs (build/netboot/authorized_keys)
  /hooks/<file>              live-config hooks from netboot/hooks/ (the menu passes oneos-netboot.sh)
  /client-status?mac=        POST: a network-booted home base's status snapshot (every 30 s), kept
                             in build/netboot/clients/<mac>/; GET returns the latest one
  /api/status                events and clients, for the wizard
--pxe
  ProxyDHCP on udp/67 and udp/4011: answers only PXE/iPXE clients with boot info and
  never hands out addresses, so the LAN's own DHCP server stays in charge.
  TFTP on udp/69: serves build/netboot/tftp/ (read-only).

Everything is read-only and limited to those directories. Runs as a normal user on
macOS (which allows binding these ports); macOS may ask to allow incoming connections.
"""
from __future__ import annotations

import argparse
import collections
import ipaddress
import json
import re
import socket
import struct
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
NETBOOT = ROOT / "build" / "netboot"
TFTP_DIR = NETBOOT / "tftp"
CACHE = ROOT / "cache"
TEMPLATE = ROOT / "netboot" / "boot.ipxe"

EVENTS: collections.deque = collections.deque(maxlen=500)
CLIENTS: dict[str, dict] = {}
LOCK = threading.Lock()
LOG = None
STATE = {"started": time.time(), "http_port": 0, "pxe": False, "iface": None, "server_ip": None}


def event(kind: str, client: str, msg: str, **extra) -> None:
    e = {"t": time.time(), "kind": kind, "client": client, "msg": msg, **extra}
    with LOCK:
        EVENTS.append(e)
        # "ip:port" → ip; a MAC (aa:bb:…) stays whole
        key = client.rsplit(":", 1)[0] if re.fullmatch(r"[\d.]+:\d+", client) else client
        c = CLIENTS.setdefault(key, {"first": e["t"]})
        c.update(last=e["t"], last_kind=kind, last_msg=msg, **{k: v for k, v in extra.items() if v is not None})
    line = f"{time.strftime('%H:%M:%S')} {kind:6} {client:21} {msg}"
    print(line, flush=True)
    if LOG:
        LOG.write(line + "\n")
        LOG.flush()


# --------------------------------------------------------------------------- SteamOS cache
STEAMOS = CACHE / "steamos"
INSTALLS = NETBOOT / "installs.json"   # MAC → {version, at}: PCs that got SteamOS from this server
CLIENT_DIR = NETBOOT / "clients"       # <mac>/status.txt: latest snapshot from a network-booted home base
LAST_STATUS: dict[str, str] = {}


def steamos_images() -> list[dict]:
    """Deployable images: Valve's *.img.bz2 and captured sticks' *.img (newest last)."""
    out = []
    for img in sorted([*STEAMOS.glob("*.img.bz2"), *STEAMOS.glob("*.img")], key=lambda p: p.stat().st_mtime):
        m = re.search(r"-(\d{8}\.\d+)-(\d+\.\d+\.\d+)\.img(\.bz2)?$", img.name)
        sha = img.with_name(img.name + ".sha256")
        meta_f = img.with_name(img.name + ".json")
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
        kind = "stick" if img.suffix == ".img" else "valve"
        src = STEAMOS / "LATEST_URL"
        out.append({"filename": img.name, "path": str(img), "size": img.stat().st_size, "kind": kind,
                    "build": m.group(1) if m else meta.get("build"), "version": m.group(2) if m else meta.get("version"),
                    "sha256": sha.read_text().split()[0] if sha.exists() else None,
                    "source": meta.get("captured_from") if kind == "stick" else
                    (src.read_text().strip() if src.exists() else "Valve"),
                    "url_path": f"/steamos/{img.name}"})
    return out


def steamos_cached() -> dict | None:
    """The image to deploy: cache/steamos/SELECTED if it names a cached image, else the newest."""
    imgs = steamos_images()
    if not imgs:
        return None
    sel = STEAMOS / "SELECTED"
    want = sel.read_text().strip() if sel.exists() else ""
    return next((i for i in imgs if i["filename"] == want), imgs[-1])


TOOLS = ROOT / "lightos" / "config" / "includes.chroot" / "usr" / "local" / "bin"   # served as /tools/
OVERLAY = ROOT / "netboot" / "initrd"   # extra initramfs files, served as /live/oneos-net.cpio


def overlay_cpio() -> bytes:
    """netboot/initrd/ as an uncompressed newc cpio: the kernel unpacks it over the home base's
    initrd (iPXE loads both). Directories first so parents exist; owner root, modes from git."""
    def entry(name: str, mode: int, data: bytes = b"") -> bytes:
        hdr = "070701" + "".join(f"{v:08x}" for v in (0, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name) + 1, 0))
        out = hdr.encode() + name.encode() + b"\0"
        out += b"\0" * (-len(out) % 4) + data
        return out + b"\0" * (-len(out) % 4)
    parts = []
    for p in sorted(OVERLAY.rglob("*")):
        rel = p.relative_to(OVERLAY).as_posix()
        if p.is_dir():
            parts.append(entry(rel, 0o040755))
        elif p.is_file():
            parts.append(entry(rel, 0o100755 if p.suffix == ".sh" else 0o100644, p.read_bytes()))
    parts.append(entry("TRAILER!!!", 0))
    return b"".join(parts)


def installs() -> dict:
    try:
        return json.loads(INSTALLS.read_text())
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "oneos-netboot"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _client(self) -> str:
        return f"{self.client_address[0]}:{self.client_address[1]}"

    def _send(self, body: bytes, ctype: str, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path: Path, ctype: str = "application/octet-stream"):
        if not path.is_file():
            event("http", self._client(), f"404 {self.path}")
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = int(rng.group(2)) if rng.group(2) else size - 1
            else:
                start = size - int(rng.group(2))
            end = min(end, size - 1)
            if start > end:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(HTTPStatus.OK)
        length = end - start + 1
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if self.command == "HEAD":
            return
        t0 = time.monotonic()
        event("http", self._client(), f"GET {self.path} ({length / 1e6:.1f} MB)")
        sent = 0
        with open(path, "rb") as f:
            f.seek(start)
            while sent < length:
                chunk = f.read(min(1 << 20, length - sent))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    event("http", self._client(), f"aborted {self.path} after {sent / 1e6:.1f} MB")
                    return
                sent += len(chunk)
        if length > 50e6:
            dt = max(time.monotonic() - t0, 1e-3)
            event("http", self._client(), f"done {self.path} ({sent / 1e6:.0f} MB, {sent / 1e6 / dt:.0f} MB/s)")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        p = url.path
        host = self.headers.get("Host") or f"{STATE['server_ip']}:{STATE['http_port']}"
        if p == "/boot.ipxe":   # learn the client's MAC, then show its menu
            body = (f"#!ipxe\nchain http://{host}/menu.ipxe?mac=${{net0/mac:hexhyp}} || "
                    f"chain http://{host}/menu.ipxe\n")
            return self._send(body.encode(), "text/plain")
        if p == "/menu.ipxe":
            mac = parse_qs(url.query).get("mac", [""])[0].lower()
            s = steamos_cached()
            tag = f" {s['version']} (from this server)" if s and s["version"] else " (latest, from Valve)"
            done = installs().get(mac) if mac else None
            note = (f"item --gap --        SteamOS {done['version']} was installed on this PC at {done['at']}\n"
                    if done else "")
            body = TEMPLATE.read_text().format(srv=f"http://{host}", steamos=tag, default="local" if done else "homebase",
                                               note=note)
            event("http", self._client(), f"menu for {mac or '?'}" + (" (SteamOS installed → local disk)" if done else ""),
                  mac=mac or None)
            return self._send(body.encode(), "text/plain")
        if p == "/live/oneos-net.cpio":
            event("http", self._client(), "GET /live/oneos-net.cpio (network-card fix)")
            return self._send(overlay_cpio(), "application/octet-stream")
        if p.startswith("/live/") and p[6:] in ("vmlinuz", "initrd.img", "filesystem.squashfs"):
            return self._file(NETBOOT / "live" / p[6:])
        if p in ("/boot.efi", "/autoexec.ipxe"):
            p = "/uefi" + p   # forgiving short form of the HTTP boot address
        if p in ("/uefi/autoexec.ipxe", "/tftp/autoexec.ipxe"):
            # iPXE looks for autoexec.ipxe next to where it was loaded from. This makes a firmware
            # "HTTP boot URL" of http://<server>:<port>/uefi/boot.efi enough on its own (no ProxyDHCP).
            event("http", self._client(), f"iPXE autoexec → menu ({p})")
            # autoexec runs before iPXE configures the network itself: firmware HTTP boot leaves no
            # address behind for it, and the interface starts closed ("Network unreachable"):
            # open it, and run DHCP if it still has no address.
            body = (f"#!ipxe\nifopen net0 && isset ${{net0/ip}} || dhcp\nchain http://{host}/menu.ipxe?mac=${{net0/mac:hexhyp}} || "
                    f"chain http://{host}/menu.ipxe\n")
            return self._send(body.encode(), "text/plain")
        if p == "/uefi/boot.efi":
            # Firmware HTTP boot and iPXE both land here (e.g. QEMU's user network hands out one
            # boot URL to everybody). iPXE identifies itself in the User-Agent: give it the menu.
            if "iPXE" in (self.headers.get("User-Agent") or ""):
                event("http", self._client(), "iPXE → menu (via /uefi/boot.efi)")
                body = (f"#!ipxe\nchain http://{host}/menu.ipxe?mac=${{net0/mac:hexhyp}} || "
                        f"chain http://{host}/menu.ipxe\n")
                return self._send(body.encode(), "text/plain")
            return self._file(TFTP_DIR / "snponly.efi")
        if p.startswith("/tftp/") and re.fullmatch(r"[\w.-]+", p[6:]):
            return self._file(TFTP_DIR / p[6:])
        if p in ("/netboot/netboot.xyz.efi", "/netboot/netboot.xyz.iso"):
            return self._file(CACHE / "ISO" / Path(p).name)
        if p.startswith("/steamos/") and p != "/steamos/latest.json":
            img = next((i for i in steamos_images() if i["url_path"] == p), None)
            return self._file(Path(img["path"]) if img else Path("/nonexistent"))
        if p == "/steamos/latest.json":
            s = steamos_cached()
            if not s:
                return self._send(b'{"error": "no SteamOS image cached on this server"}', "application/json",
                                  HTTPStatus.NOT_FOUND)
            return self._send(json.dumps({k: v for k, v in s.items() if k != "path"}).encode(), "application/json")
        if p.startswith("/docs/"):
            docs = (ROOT / "build" / "docs-html").resolve()
            f = (docs / p[len("/docs/"):]).resolve()
            if docs in f.parents and f.is_file():
                ctype = {".html": "text/html; charset=utf-8", ".css": "text/css", ".png": "image/png",
                         ".js": "text/javascript", ".svg": "image/svg+xml"}.get(f.suffix, "application/octet-stream")
                return self._send(f.read_bytes(), ctype)
            return self.send_error(HTTPStatus.NOT_FOUND)
        if p == "/src/one-os.bundle":
            return self._file(ROOT / "build" / "one-os.bundle")
        if p in ("/tools/", "/tools"):   # the home base's one-os tools, as in the repo right now
            names = sorted(f.name for f in TOOLS.glob("oneos-*") if f.is_file())
            return self._send(("\n".join(names) + "\n").encode(), "text/plain")
        if p.startswith("/tools/") and re.fullmatch(r"oneos-[\w.-]+", p[7:]) and (TOOLS / p[7:]).is_file():
            event("http", self._client(), f"tool {p[7:]}")
            return self._send((TOOLS / p[7:]).read_bytes(), "text/plain")
        if p == "/ssh/authorized_keys":   # public keys only, put there by: scripts/pxe.sh ssh-key
            f = NETBOOT / "authorized_keys"
            if f.is_file():
                event("http", self._client(), "ssh keys")
                return self._send(f.read_bytes(), "text/plain")
            return self.send_error(HTTPStatus.NOT_FOUND)
        if p.startswith("/hooks/") and re.fullmatch(r"[\w.-]+", p[7:]):
            f = ROOT / "netboot" / "hooks" / p[7:]
            if f.is_file():
                event("http", self._client(), f"hook {p[7:]}")
                return self._send(f.read_bytes(), "text/plain")
        if p == "/client-status":
            mac = parse_qs(url.query).get("mac", [""])[0].lower()
            f = CLIENT_DIR / mac / "status.txt"
            if re.fullmatch(r"[0-9a-f-]{17}", mac) and f.is_file():
                return self._send(f.read_bytes(), "text/plain; charset=utf-8")
            return self.send_error(HTTPStatus.NOT_FOUND)
        if p == "/report":
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            pct = q.get("pct")
            mac = (q.get("mac") or "").lower() or None
            event("report", self._client(), f"{q.get('stage', '?')}: {q.get('msg', '')}"[:300],
                  stage=q.get("stage"), pct=float(pct) if pct and re.fullmatch(r"[\d.]+", pct) else None,
                  host=q.get("host"), mac=mac)
            if q.get("stage") == "complete" and mac and re.fullmatch(r"[0-9a-f-]{17}", mac):
                with LOCK:
                    data = installs()
                    data[mac] = {"version": q.get("version") or "?", "at": time.strftime("%Y-%m-%d %H:%M")}
                    INSTALLS.write_text(json.dumps(data, indent=2))
            return self._send(b"ok\n", "text/plain")
        if p == "/api/status":
            with LOCK:
                body = {"state": STATE, "events": list(EVENTS)[-200:], "clients": CLIENTS,
                        "steamos": {k: v for k, v in (steamos_cached() or {}).items() if k != "path"} or None,
                        "images": [{k: v for k, v in i.items() if k != "path"} for i in steamos_images()],
                        "installs": installs(),
                        "netboot_ready": (NETBOOT / "live" / "filesystem.squashfs").exists()}
            return self._send(json.dumps(body).encode(), "application/json")
        event("http", self._client(), f"404 {self.path}")
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        """Status snapshots from network-booted home bases (netboot/hooks/oneos-netboot.sh)."""
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        mac = parse_qs(url.query).get("mac", [""])[0].lower()
        if url.path != "/client-status" or not re.fullmatch(r"[0-9a-f-]{17}", mac) or not 0 < length <= 1 << 20:
            self.rfile.read(min(length, 1 << 20))
            return self.send_error(HTTPStatus.BAD_REQUEST)
        body = self.rfile.read(length)
        d = CLIENT_DIR / mac
        d.mkdir(parents=True, exist_ok=True)
        (d / "status.txt").write_bytes(body)
        summary = body.split(b"\n", 1)[0].decode("utf-8", "replace")[:300]
        # One event per change, ignoring the uptime counter (snapshots arrive every 30 s).
        key = re.sub(r"^up=\d+s ", "", summary)
        if LAST_STATUS.get(mac) != key:
            LAST_STATUS[mac] = key
            with open(d / "history.log", "a") as h:
                h.write(f"{time.strftime('%H:%M:%S')} {summary}\n")
            event("status", self._client(), summary, mac=mac)
        return self._send(b"ok\n", "text/plain")


# --------------------------------------------------------------------------- network facts
def iface_ipv4(name: str) -> tuple[str, str]:
    """(ip, broadcast) of an interface (macOS ifconfig / Linux ip)."""
    if sys.platform == "darwin":
        out = subprocess.run(["ifconfig", name], capture_output=True, text=True).stdout
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+) netmask (0x[0-9a-f]+)(?: broadcast (\S+))?", out)
        if not m:
            raise SystemExit(f"interface {name} has no IPv4 address")
        ip, mask = m.group(1), str(ipaddress.IPv4Address(int(m.group(2), 16)))
    else:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", name], capture_output=True, text=True).stdout
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", out)
        if not m:
            raise SystemExit(f"interface {name} has no IPv4 address")
        ip, mask = m.group(1), m.group(2)
    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    return ip, str(net.broadcast_address)


def interfaces() -> list[dict]:
    out = []
    if sys.platform == "darwin":
        names = subprocess.run(["ifconfig", "-l"], capture_output=True, text=True).stdout.split()
    else:
        names = [p.name for p in Path("/sys/class/net").iterdir()]
    for n in names:
        if n.startswith(("lo", "utun", "awdl", "llw", "bridge", "anpi", "gif", "stf", "ap")):
            continue
        try:
            ip, bcast = iface_ipv4(n)
        except SystemExit:
            continue
        out.append({"name": n, "ip": ip, "broadcast": bcast})
    return out


# --------------------------------------------------------------------------- ProxyDHCP
DHCP_MAGIC = b"\x63\x82\x53\x63"
SEEN_DHCP: set[str] = set()
ARCH_LOADER = {0: "undionly.kpxe", 6: "ipxe.efi", 7: "snponly.efi", 9: "snponly.efi"}


def parse_dhcp(data: bytes) -> dict | None:
    if len(data) < 240 or data[236:240] != DHCP_MAGIC:
        return None
    pkt = {"op": data[0], "xid": data[4:8], "flags": data[10:12], "giaddr": data[24:28],
           "chaddr": data[28:44], "mac": ":".join(f"{b:02x}" for b in data[28:34]), "opts": {}}
    i = 240
    while i < len(data):
        code = data[i]
        if code == 255:
            break
        if code == 0:
            i += 1
            continue
        ln = data[i + 1]
        pkt["opts"][code] = data[i + 2: i + 2 + ln]
        i += 2 + ln
    return pkt


def boot_choice(pkt: dict, http_base: str) -> tuple[str, str] | None:
    """(client class, boot file) for a PXE/iPXE/HTTP-boot client, else None."""
    vendor = pkt["opts"].get(60, b"")
    user_class = pkt["opts"].get(77, b"")
    arch = struct.unpack("!H", pkt["opts"][93][:2])[0] if len(pkt["opts"].get(93, b"")) >= 2 else 0
    if b"iPXE" in user_class or 175 in pkt["opts"]:
        return "iPXE", f"{http_base}/boot.ipxe"
    if vendor.startswith(b"HTTPClient"):
        return "HTTPClient", f"{http_base}/uefi/boot.efi"
    if vendor.startswith(b"PXEClient"):
        loader = ARCH_LOADER.get(arch)
        return ("PXEClient", loader) if loader else None
    return None


def build_reply(pkt: dict, msg_type: int, server_ip: str, klass: str, bootfile: str) -> bytes:
    sip = socket.inet_aton(server_ip)
    file_field = bootfile.encode()[:127].ljust(128, b"\0")
    sname = server_ip.encode().ljust(64, b"\0")
    head = struct.pack("!BBBB", 2, 1, 6, 0) + pkt["xid"] + b"\0\0" + b"\x80\0" + b"\0" * 8 + sip + pkt["giaddr"]
    head += pkt["chaddr"] + sname + file_field + DHCP_MAGIC
    opts = [(53, bytes([msg_type])), (54, sip), (60, klass.encode())]
    if 97 in pkt["opts"]:
        opts.append((97, pkt["opts"][97]))
    if klass == "PXEClient":
        opts.append((43, b"\x06\x01\x08\xff"))  # PXE_DISCOVERY_CONTROL = 8: just use the boot file
    opts += [(66, server_ip.encode()), (67, bootfile.encode())]
    body = b"".join(bytes([c, len(v)]) + v for c, v in opts) + b"\xff"
    return head + body


DHCP_TYPES = {1: "DISCOVER", 2: "OFFER", 3: "REQUEST", 4: "DECLINE", 5: "ACK", 6: "NAK", 7: "RELEASE", 8: "INFORM"}


def describe(pkt: dict) -> str:
    o = pkt["opts"]
    arch = struct.unpack("!H", o[93][:2])[0] if len(o.get(93, b"")) >= 2 else None
    bits = [DHCP_TYPES.get(o.get(53, b"\0")[0], "?")]
    if arch is not None:
        bits.append(f"arch {arch}")
    if 50 in o:
        bits.append(f"wants {socket.inet_ntoa(o[50])}")
    if 54 in o:
        bits.append(f"server {socket.inet_ntoa(o[54])}")
    if 77 in o:
        bits.append(f"user-class {o[77].decode(errors='replace')[:20]}")
    return ", ".join(bits)


def proxydhcp_loop(port: int, iface: str) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # Replies to clients without an address go to 255.255.255.255 (many PXE firmwares ignore
    # subnet-directed broadcasts); pin the socket to the LAN interface so they leave there.
    if sys.platform == "darwin":
        s.setsockopt(socket.IPPROTO_IP, 25, socket.if_nametoindex(iface))   # IP_BOUND_IF
    elif hasattr(socket, "SO_BINDTODEVICE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, iface.encode())
    s.bind(("0.0.0.0", port))
    while True:
        data, addr = s.recvfrom(4096)
        pkt = parse_dhcp(data)
        if not pkt or pkt["op"] != 1:
            continue
        mtype = pkt["opts"].get(53, b"\0")[0]
        # Read per packet: address_watch() follows the Mac to a new address (Wi-Fi roaming, DHCP).
        server_ip, broadcast = STATE["server_ip"], STATE["broadcast"]
        choice = boot_choice(pkt, f"http://{server_ip}:{STATE['http_port']}")
        if not choice:
            # Not a network-booting client: never answered. Noting the first broadcast per device
            # shows whether DHCP broadcasts from the rest of the LAN (e.g. behind an access point)
            # reach this machine at all — the precondition for PXE.
            if port == 67 and pkt["mac"] not in SEEN_DHCP:
                SEEN_DHCP.add(pkt["mac"])
                host = pkt["opts"].get(12, b"").decode(errors="replace")
                vendor = pkt["opts"].get(60, b"").decode(errors="replace")[:40]
                event("seen", pkt["mac"], f"DHCP broadcast heard (not answered){': ' + host if host else ''}"
                      f"{' [' + vendor + ']' if vendor else ''}", mac=pkt["mac"])
            continue
        klass, bootfile = choice
        event("dhcp", pkt["mac"], f"{klass} {describe(pkt)} (udp/{port} from {addr[0]})", mac=pkt["mac"])
        if port == 67 and mtype == 1:      # DISCOVER → OFFER, broadcast (client has no address yet)
            reply = build_reply(pkt, 2, server_ip, klass, bootfile)
            # Both broadcast forms: some access points forward one and not the other.
            # A send can fail while the Mac's network blips (EHOSTUNREACH, ENETDOWN): log it and
            # keep listening — one failed send must never end the loop (it did: PXE went silent).
            sent = []
            for dest in ("255.255.255.255", broadcast):
                try:
                    s.sendto(reply, (dest, 68))
                    sent.append(dest)
                except OSError as e:
                    event("dhcp", pkt["mac"], f"offer to {dest} failed: {e}", mac=pkt["mac"])
            if sent:
                event("dhcp", pkt["mac"], f"{klass} offer → {bootfile} (to {' and '.join(sent)})",
                      mac=pkt["mac"])
        elif port == 4011 and mtype == 3:  # REQUEST to the boot server → ACK, unicast
            try:
                s.sendto(build_reply(pkt, 5, server_ip, klass, bootfile), addr)
                event("dhcp", pkt["mac"], f"{klass} ack (4011) → {bootfile}", mac=pkt["mac"])
            except OSError as e:
                event("dhcp", pkt["mac"], f"ack to {addr[0]} failed: {e}", mac=pkt["mac"])


# --------------------------------------------------------------------------- TFTP (RFC 1350 + 2347/2348/2349)
def tftp_loop() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 69))
    while True:
        data, addr = s.recvfrom(2048)
        if len(data) > 4 and struct.unpack("!H", data[:2])[0] == 1:
            threading.Thread(target=tftp_send, args=(data, addr, STATE["server_ip"]), daemon=True).start()


def tftp_send(req: bytes, addr, server_ip: str) -> None:
    parts = req[2:].split(b"\0")
    name = parts[0].decode(errors="replace").lstrip("/")
    opts = {parts[i].decode().lower(): parts[i + 1].decode() for i in range(2, len(parts) - 1, 2) if parts[i]}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((server_ip if server_ip != "0.0.0.0" else "0.0.0.0", 0))
    s.settimeout(2)
    path = TFTP_DIR / name
    if not re.fullmatch(r"[\w.-]+", name) or not path.is_file():
        s.sendto(struct.pack("!HH", 5, 1) + b"file not found\0", addr)
        event("tftp", f"{addr[0]}:{addr[1]}", f"not found: {name}")
        return
    data = path.read_bytes()
    blksize = 512
    oack = {}
    if "blksize" in opts:
        blksize = max(8, min(int(opts["blksize"]), 1456))
        oack["blksize"] = str(blksize)
    if "tsize" in opts:
        oack["tsize"] = str(len(data))
    if oack:
        pkt = struct.pack("!H", 6) + b"".join(k.encode() + b"\0" + v.encode() + b"\0" for k, v in oack.items())
        if not _tftp_xfer(s, addr, pkt, 0):
            return  # client only wanted the size (tsize probe), or went away
    event("tftp", f"{addr[0]}:{addr[1]}", f"sending {name} ({len(data)} bytes, blksize {blksize})")
    block = 1
    for off in range(0, len(data) + 1, blksize):
        chunk = data[off: off + blksize]
        if not _tftp_xfer(s, addr, struct.pack("!HH", 3, block & 0xFFFF) + chunk, block & 0xFFFF):
            event("tftp", f"{addr[0]}:{addr[1]}", f"transfer of {name} failed at block {block}")
            return
        block += 1
        if len(chunk) < blksize:
            break
    event("tftp", f"{addr[0]}:{addr[1]}", f"sent {name}")


def _tftp_xfer(s: socket.socket, addr, pkt: bytes, expect_block: int, tries: int = 5) -> bool:
    for _ in range(tries):
        s.sendto(pkt, addr)
        try:
            while True:
                data, src = s.recvfrom(1024)
                if src != addr or len(data) < 4:
                    continue
                op, blk = struct.unpack("!HH", data[:4])
                if op == 5:
                    return False
                if op == 4 and blk == expect_block:
                    return True
        except TimeoutError:
            continue
    return False


# --------------------------------------------------------------------------- main
def default_iface() -> str | None:
    if sys.platform == "darwin":
        out = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True).stdout
        m = re.search(r"interface: (\S+)", out)
    else:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True).stdout
        m = re.search(r"dev (\S+)", out)
    return m.group(1) if m else None


def write_autoexec(port: int) -> None:
    """iPXE loaded over TFTP also looks for autoexec.ipxe there: point it at the menu, so the
    LAN path works even if its second DHCP round misses our ProxyDHCP reply."""
    base = f"http://{STATE['server_ip']}:{port}"
    (TFTP_DIR / "autoexec.ipxe").write_text(f"#!ipxe\nifopen net0 && isset ${{net0/ip}} || dhcp\nchain {base}/boot.ipxe\n")


def address_watch(iface: str, port: int) -> None:
    """The Mac's address can change under a running server (new network, DHCP renewal):
    PXE replies and the TFTP autoexec must name the current one, or PCs chain to nowhere."""
    while True:
        time.sleep(15)
        try:
            ip, bcast = iface_ipv4(iface)
        except Exception:   # interface down for a moment: keep the old address until it's back
            continue
        if ip != STATE["server_ip"]:
            old = STATE["server_ip"]
            STATE.update(server_ip=ip, broadcast=bcast)
            write_autoexec(port)
            event("server", ip, f"{iface} address changed {old} → {ip}: PXE now points at http://{ip}:{port}")


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--pxe", action="store_true", help="also run ProxyDHCP (67, 4011) and TFTP (69)")
    ap.add_argument("--iface", help="LAN interface for --pxe (default: the default route's)")
    ap.add_argument("--list-interfaces", action="store_true")
    a = ap.parse_args()
    if a.list_interfaces:
        print(json.dumps(interfaces(), indent=2))
        return 0
    if not (NETBOOT / "live" / "filesystem.squashfs").exists():
        print("note: build/netboot/ is empty — run 'make netboot' (the menu will load, booting won't)",
              file=sys.stderr)
    NETBOOT.mkdir(parents=True, exist_ok=True)
    LOG = open(NETBOOT / "server.log", "a")
    TFTP_DIR.mkdir(parents=True, exist_ok=True)
    # Hand-off for iPXE NIC ROMs (e.g. QEMU's) that load boot.ipxe over TFTP; 10.0.2.2 is the
    # host as seen from QEMU user networking.
    (TFTP_DIR / "boot.ipxe").write_text(f"#!ipxe\nchain http://10.0.2.2:{a.port}/boot.ipxe\n")

    http = ThreadingHTTPServer(("0.0.0.0", a.port), Handler)
    http.daemon_threads = True
    STATE["http_port"] = a.port
    threading.Thread(target=http.serve_forever, daemon=True).start()
    if a.pxe:
        iface = a.iface or default_iface()
        if not iface:
            raise SystemExit("no default interface; pass --iface")
        ip, bcast = iface_ipv4(iface)
        STATE.update(pxe=True, iface=iface, server_ip=ip, broadcast=bcast)
        write_autoexec(a.port)
        for port in (67, 4011):
            threading.Thread(target=proxydhcp_loop, args=(port, iface), daemon=True).start()
        threading.Thread(target=tftp_loop, daemon=True).start()
        threading.Thread(target=address_watch, args=(iface, a.port), daemon=True).start()
        event("server", ip, f"PXE on {iface} ({ip}, broadcast {bcast}); menu http://{ip}:{a.port}/boot.ipxe")
    else:
        STATE["server_ip"] = "127.0.0.1"
        event("server", "-", f"HTTP on :{a.port} (QEMU: http://10.0.2.2:{a.port}/boot.ipxe); PXE off")
    s = steamos_cached()
    event("server", "-", f"SteamOS cache: {s['filename'] if s else 'none (installers download from Valve)'}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
