#!/usr/bin/env python3
"""one-os flash wizard — a local web UI over the same scripts `make` uses.

    make wizard            (or: python3 ui/server.py [--port N] [--no-open])

Serves ui/index.html on 127.0.0.1 only. Every API call needs the per-run token that
is in the URL it prints, and a localhost Host header, so other web pages can't drive
it. It runs one job at a time from a fixed list; the disk write goes through
scripts/flash-macos.sh (all its guards) under the standard macOS admin prompt.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
WIZ = BUILD / "wizard"
CARD_IMG = BUILD / "one-os-card.img"
ISO = BUILD / "oneos-lightos.iso"
SUMS = BUILD / "payload.SHA256SUMS"
HISTORY = BUILD / "flash-history.jsonl"
TEST_VM = "flashtest"
ENV = {**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '/usr/bin:/bin')}"}
TOKEN = secrets.token_urlsafe(24)


# --------------------------------------------------------------------------- facts
def sh(*argv: str, timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=ENV)


def newest_mtime(*paths: Path) -> float:
    m = 0.0
    for p in paths:
        if p.is_file():
            m = max(m, p.stat().st_mtime)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    m = max(m, f.stat().st_mtime)
    return m


def artifact(path: Path, sources: float, stamp: Path | None = None) -> dict:
    """stamp: a file written when `path` was built, for files whose own mtime gets reset."""
    if not path.exists():
        return {"exists": False, "fresh": False}
    built = (stamp if stamp and stamp.exists() else path).stat().st_mtime
    return {"exists": True, "fresh": built >= sources, "mtime": built, "size": path.stat().st_size}


def host_app() -> str:
    """The .app this wizard was started from (macOS privacy checks disk access against it)."""
    pid = os.getppid()
    for _ in range(12):
        r = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=,comm="], capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            break
        ppid, comm = r.stdout.strip().split(None, 1)
        m = re.search(r"/([^/]+)\.app/Contents/MacOS/", comm)
        if m and m.group(1) != "Python" and "Helper" not in m.group(1):
            return m.group(1)
        pid = int(ppid)
        if pid <= 1:
            break
    return ""


HOST_APP = host_app() if sys.platform == "darwin" else ""


def prereqs() -> dict:
    out = {"host_app": HOST_APP}
    try:
        out["docker"] = sh("docker", "info", "--format", "{{.ServerVersion}}", timeout=8).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        out["docker"] = False
    out["builder"] = out["docker"] and sh("docker", "image", "inspect", "oneos-builder:latest").returncode == 0
    out["qemu"] = bool(shutil.which("qemu-system-x86_64", path=ENV["PATH"]))
    BUILD.mkdir(exist_ok=True)
    out["free_gb"] = round(shutil.disk_usage(BUILD).free / 1e9, 1)
    out["macos"] = sys.platform == "darwin"
    return out


def artifacts() -> dict:
    iso_src = newest_mtime(ROOT / "lightos", ROOT / "manifest.yaml", ROOT / "scripts/build-lightos.sh",
                           ROOT / "scripts/manifest.py")
    # stage-payload.sh hard-links the ISO into the payload and resets payload mtimes to
    # SOURCE_DATE_EPOCH, which resets the ISO's too; its .sha256 keeps the build time.
    iso = artifact(ISO, iso_src, stamp=ISO.with_name(ISO.name + ".sha256"))
    pay_src = max(newest_mtime(ROOT / "manifest.yaml", ROOT / "config", ROOT / "scripts/stage-payload.sh"),
                  iso.get("mtime", 0), newest_mtime(ROOT / "cache/SHA256SUMS"))
    payload = artifact(SUMS, pay_src)
    card = artifact(CARD_IMG, payload.get("mtime", float("inf")))
    return {"iso": iso, "payload": payload, "card_image": card}


def plist(disk: str) -> dict:
    import plistlib
    r = subprocess.run(["diskutil", "info", "-plist", disk], capture_output=True)
    return plistlib.loads(r.stdout) if r.returncode == 0 else {}


def devices() -> list[dict]:
    """Removable USB/SD whole disks, with what's on them now."""
    if sys.platform != "darwin":
        return []
    out = []
    listing = sh("diskutil", "list").stdout
    for disk in re.findall(r"^/dev/(disk\d+) \(", listing, re.M):
        info = plist(disk)
        if not info.get("RemovableMedia") or info.get("BusProtocol") not in ("USB", "Secure Digital"):
            continue
        import plistlib
        lst = plistlib.loads(subprocess.run(["diskutil", "list", "-plist", disk], capture_output=True).stdout or b"<plist/>")
        whole = next((d for d in lst.get("AllDisksAndPartitions", []) if d.get("DeviceIdentifier") == disk), {})
        guid = re.compile(r"[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}", re.I)
        parts = [{"name": p.get("VolumeName", ""),
                  "type": "partition" if guid.fullmatch(p.get("Content", "")) else p.get("Content", ""),
                  "size": _human(p.get("Size", 0))}
                 for p in whole.get("Partitions", [])]
        names = {p["name"] for p in parts}
        out.append({
            "disk": disk, "media": info.get("MediaName", ""), "bus": info.get("BusProtocol", ""),
            "size": info.get("TotalSize") or info.get("Size"), "partitions": parts,
            "is_oneos": {"Ventoy", "VTOYEFI"} <= names,
            "card_image_fits": CARD_IMG.exists() and CARD_IMG.stat().st_size == (info.get("TotalSize") or 0),
        })
    return out


def _human(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def history(n: int = 8) -> list[dict]:
    if not HISTORY.exists():
        return []
    return [json.loads(x) for x in HISTORY.read_text().splitlines()[-n:]][::-1]


# --------------------------------------------------------------------------- jobs
class Job:
    def __init__(self, step: str, title: str, log: Path):
        self.id = secrets.token_hex(4)
        self.step, self.title, self.log = step, title, log
        self.state = "running"
        self.started, self.ended = time.time(), None
        self.result: dict = {}
        self.proc: subprocess.Popen | None = None

    def view(self) -> dict:
        text = self.log.read_text(errors="replace") if self.log.exists() else ""
        progress = None
        m = re.findall(r"wrote\s+([\d.]+) / ([\d.]+) GB(?:\s+\(\s*([\d.]+) MB/s\))?", text)
        if m:
            done, total, rate = m[-1]
            progress = {"phase": "write", "done": float(done), "total": float(total), "rate": rate}
        v = re.findall(r"verified (\d+)/(\d+) extents", text)
        if v:
            progress = {"phase": "verify", "done": int(v[-1][0]), "total": int(v[-1][1])}
        lines = [ln.split("\r")[-1] for ln in text.splitlines()]
        return {"id": self.id, "step": self.step, "title": self.title, "state": self.state,
                "started": self.started, "ended": self.ended, "elapsed": (self.ended or time.time()) - self.started,
                "progress": progress, "log": "\n".join(lines[-200:]), "result": self.result}


JOB: Job | None = None
LOCK = threading.Lock()


def run_job(step: str, title: str, argv, after=None) -> Job:
    """argv: a list, or a function log_path -> list (for commands that write the log themselves)."""
    global JOB
    with LOCK:
        if JOB and JOB.state == "running":
            raise RuntimeError(f"'{JOB.title}' is still running")
        WIZ.mkdir(parents=True, exist_ok=True)
        log = WIZ / f"{time.strftime('%Y%m%d-%H%M%S')}-{step}.log"
        if callable(argv):
            argv = argv(log)
        log.write_text(f"$ {' '.join(shlex.quote(a) for a in argv)[:400]}\n")
        JOB = job = Job(step, title, log)

    def work():
        try:
            with open(log, "a") as f:
                job.proc = subprocess.Popen(argv, cwd=ROOT, env=ENV, stdout=f, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL)
                rc = job.proc.wait()
            job.result["rc"] = rc
            if after:
                after(job, rc)
            job.state = job.result.get("state") or ("ok" if rc == 0 else "failed")
        except Exception as e:  # report, never crash the server
            job.result["error"] = str(e)
            job.state = "failed"
        job.ended = time.time()

    threading.Thread(target=work, daemon=True).start()
    return job


def start_step(body: dict) -> Job:
    step = body.get("step")
    disk = body.get("disk", "")
    if disk and not re.fullmatch(r"disk\d+", disk):
        raise ValueError("bad disk id")
    make = ["make", "-C", str(ROOT)]
    if step == "builder":
        return run_job(step, "Build the builder container", make + ["builder"])
    if step == "fetch":
        return run_job(step, "Download + verify pinned artifacts", make + ["fetch"])
    if step == "lightos":
        return run_job(step, "Build the home-base ISO (~25 min)", make + ["lightos"])
    if step == "payload":
        return run_job(step, "Stage the stick's files", make + ["payload"])
    if step == "card-image":
        if not disk:
            raise ValueError("choose a device first")
        return run_job(step, f"Build the image sized for {disk}", make + ["card-image", f"DISK={disk}"])
    if step == "flash":
        return start_flash(disk, body.get("confirm", ""))
    if step == "test":
        return start_test()
    if step == "open-privacy":  # opens the pane; the person decides what to enable
        return run_job(step, "Open Privacy & Security → Full Disk Access",
                       ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])
    if step == "netboot":
        return run_job(step, "Extract the home base for network boot", make + ["netboot"])
    if step == "pxe-start":
        return run_job(step, "Start the network boot server", make + ["pxe-start"])
    if step == "pxe-stop":
        return run_job(step, "Stop the network boot server", make + ["pxe-stop"])
    if step == "steamos-fetch":
        return run_job(step, "Download SteamOS for the network boot server (~3.4 GB)", make + ["steamos-fetch"])
    if step == "stop-test":
        return run_job(step, "Stop the test VM", [str(ROOT / "scripts/oneos-vm"), "stop", TEST_VM])
    raise ValueError(f"unknown step {step!r}")


def start_flash(disk: str, confirm: str) -> Job:
    dev = next((d for d in devices() if d["disk"] == disk), None)
    if dev is None:
        raise ValueError(f"{disk} is not a removable USB/SD disk right now — refresh the device list")
    if confirm != dev["media"]:
        raise ValueError(f"type the media name exactly: {dev['media']}")
    a = artifacts()
    if not dev["card_image_fits"] or not a["card_image"]["fresh"]:
        raise ValueError("the card image is missing, stale, or sized for another device — prepare it first")
    # Runs as the person, not root: write-image.py asks macOS (authopen) for this one
    # device, which shows the system authorization dialog. No admin shell, no sudo.
    argv = [str(ROOT / "scripts/flash-macos.sh"), disk,
            f"--confirm={confirm}", f"--expect-size={dev['size']}"]

    def after(job: Job, rc: int):
        text = job.log.read_text(errors="replace")
        if rc != 0 and "authorization cancelled" in text:
            job.result["state"] = "cancelled"
            return
        ok = rc == 0 and "verified OK" in text
        job.result["state"] = "ok" if ok else "failed"
        if "Operation not permitted" in text or "blocked access" in text:
            job.result["hint"] = "full-disk-access"
        with open(HISTORY, "a") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "disk": disk, "media": dev["media"],
                                "size": dev["size"], "result": "verified" if ok else "failed",
                                "image_mtime": CARD_IMG.stat().st_mtime, "payload_sums": _sums_digest()}) + "\n")

    return run_job("flash", f"Flash {dev['media']} ({disk})", argv, after)


def _sums_digest() -> str:
    import hashlib
    return hashlib.sha256(SUMS.read_bytes()).hexdigest()[:16] if SUMS.exists() else ""


def start_test() -> Job:
    vm = str(ROOT / "scripts/oneos-vm")
    checks = r"""
fail=0
ok() { echo "PASS: $*"; }
bad() { echo "FAIL: $*"; fail=1; }
if id user >/dev/null 2>&1; then ok "live account 'user' exists"; else bad "no 'user' account"; fi
h=$(getent shadow user | cut -d: -f2)
if [ -n "$h" ] && [ "$(perl -e 'print crypt($ARGV[0],$ARGV[1])' live "$h")" = "$h" ]; then
  ok "password 'live' works"; else bad "password 'live' rejected"; fi
# The session process appears long before anything is drawn (minutes under TCG):
# wait for the panel and the desktop, then give them a moment to paint.
for i in $(seq 1 150); do pgrep -u user -x xfce4-panel >/dev/null && pgrep -u user -x xfdesktop >/dev/null && break; sleep 2; done
if pgrep -u user -x xfce4-panel >/dev/null && pgrep -u user -x xfdesktop >/dev/null; then
  ok "Xfce desktop logged in automatically (panel + desktop up)"; sleep 8; else bad "Xfce desktop did not come up"; fi
if ls -d /run/live/persistence/* >/dev/null 2>&1; then ok "persistence mounted"; else bad "persistence not mounted"; fi
if systemctl is-active --quiet qemu-guest-agent; then ok "guest agent running"; else bad "guest agent down"; fi
. /etc/oneos-release && ok "build $ONEOS_VERSION"
exit $fail
"""
    script = "\n".join([
        "set -e",
        f"{vm} stop {TEST_VM} --force >/dev/null 2>&1 || true",
        f"{vm} start {TEST_VM} --fresh --window --image {shlex.quote(str(CARD_IMG))}",
        f"{vm} wait {TEST_VM} --agent --timeout 900",
        f"{vm} exec {TEST_VM} --timeout 400 -- {shlex.quote(checks)}",
        # The desktop processes exist well before Xfce has painted (a black frame is ~3 KB, the desktop ~20 KB):
        # keep taking screenshots until the screen has real content.
        f"shot={shlex.quote(str(WIZ / 'test-screen.png'))}",
        "for i in $(seq 1 60); do",
        f"  {vm} screenshot {TEST_VM} \"$shot\" >/dev/null",
        "  [ \"$(stat -f %z \"$shot\")\" -gt 10000 ] && break; sleep 3",
        "done",
    ])

    def after(job: Job, rc: int):
        text = job.log.read_text(errors="replace")
        job.result["checks"] = [ln for ln in text.splitlines() if ln.startswith(("PASS: ", "FAIL: "))]
        job.result["screenshot"] = (WIZ / "test-screen.png").exists()

    return run_job("test", "Boot the flashed image and check it", ["bash", "-c", script], after)


# --------------------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "oneos-wizard"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _guard(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self.send_error(HTTPStatus.FORBIDDEN, "bad host")
            return False
        q = parse_qs(urlparse(self.path).query)
        token = self.headers.get("X-Token") or (q.get("t") or [""])[0]
        if not hmac.compare_digest(token, TOKEN):
            # ASCII only: send_error puts this in the HTTP status line.
            self.send_error(HTTPStatus.FORBIDDEN, "missing or wrong token - use the URL the wizard printed")
            return False
        return True

    def _json(self, obj, status=HTTPStatus.OK):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._guard():
            return
        path = urlparse(self.path).path
        if path == "/":
            data = (ROOT / "ui/index.html").read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; "
                             "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/state":
            self._json({"prereqs": prereqs(), "artifacts": artifacts(), "history": history(),
                        "job": JOB.view() if JOB else None, "test_vm_running": _vm_running(TEST_VM)})
        elif path == "/api/devices":
            self._json({"devices": devices()})
        elif path == "/api/netboot":
            self._json(netboot_view())
        elif path == "/api/job":
            self._json({"job": JOB.view() if JOB else None})
        elif path == "/test-screen.png":
            f = WIZ / "test-screen.png"
            if not f.exists():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = f.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if not self._guard():
            return
        if urlparse(self.path).path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            job = start_step(body)
            self._json({"job": job.view()})
        except (ValueError, RuntimeError) as e:
            self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)


PXE_PORT = 8780


def netboot_view() -> dict:
    """The local network boot server's state (netboot/server.py, read-only) plus each PC's
    latest status snapshot, for the wizard's Network boot panel."""
    import urllib.request
    out = {"running": False, "files": (BUILD / "netboot" / "live" / "filesystem.squashfs").exists()}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PXE_PORT}/api/status", timeout=2) as r:
            st = json.loads(r.read())
    except (OSError, ValueError):
        return out
    clients = BUILD / "netboot" / "clients"
    pcs = []
    for d in sorted(clients.iterdir() if clients.is_dir() else [], key=lambda d: -d.stat().st_mtime)[:6]:
        f = d / "status.txt"
        if f.is_file():
            text = f.read_text(errors="replace")
            pcs.append({"mac": d.name, "updated": f.stat().st_mtime, "summary": text.splitlines()[0] if text else "",
                        "detail": text[:6000]})
    reports = [e for e in st.get("events", []) if e.get("kind") == "report"][-12:]
    out.update(running=True, state=st.get("state"), steamos=st.get("steamos"), installs=st.get("installs"),
               events=st.get("events", [])[-25:], reports=reports, pcs=pcs)
    return out


def _vm_running(name: str) -> bool:
    meta = BUILD / "vms" / name / "instance.json"
    try:
        os.kill(json.loads(meta.read_text())["pid"], 0)
        return True
    except (OSError, KeyError, ValueError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    for port in range(a.port, a.port + 20):  # another wizard may already hold the default
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"no free port in {a.port}-{a.port + 19}")
    url = f"http://127.0.0.1:{srv.server_port}/?t={TOKEN}"
    print(f"one-os wizard: {url}\n(Ctrl-C to stop; the URL contains this session's access token)", flush=True)
    if not a.no_open and sys.platform == "darwin":
        subprocess.Popen(["open", url])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
