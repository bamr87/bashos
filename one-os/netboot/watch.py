#!/usr/bin/env python3
"""watch.py — follow network-boot clients on a running netboot/server.py.

    python3 netboot/watch.py                         # print client events as they happen
    python3 netboot/watch.py --until http --timeout 1500
    python3 netboot/watch.py --mac 02:00:00:c0:ff:ee --until squashfs

Reads the server's event list (/api/status), so it sees exactly what the server logged.
Events from the server itself (self-tests, this machine) are left out.
--until: dhcp (any boot request), http (a client fetched something over HTTP or TFTP),
squashfs (a client finished downloading the home base), installed (a SteamOS install
reported success). Exit code 0 when the condition was met, 1 on timeout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

SELF_TEST_MAC = "02:00:00:c0:ff:ee"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://127.0.0.1:8780")
    ap.add_argument("--until", choices=["dhcp", "http", "squashfs", "installed"])
    ap.add_argument("--timeout", type=float, default=0, help="seconds (0 = forever)")
    ap.add_argument("--mac", help="only this client (for DHCP events)")
    ap.add_argument("--since", type=float, default=0, help="seconds of history to include (default: none)")
    a = ap.parse_args()

    status = json.loads(urllib.request.urlopen(f"{a.server}/api/status", timeout=5).read())
    me = status["state"].get("server_ip") or ""
    seen_t = time.time() - a.since
    deadline = time.monotonic() + a.timeout if a.timeout else None
    met = False
    while True:
        try:
            status = json.loads(urllib.request.urlopen(f"{a.server}/api/status", timeout=5).read())
        except OSError as e:
            print(f"watch: server not reachable ({e})", file=sys.stderr)
            return 1
        for e in status["events"]:
            if e["t"] <= seen_t:
                continue
            seen_t = e["t"]
            client = e["client"]
            if e["kind"] in ("server",) or client.startswith(("127.0.0.1", f"{me}:")) or SELF_TEST_MAC in client:
                continue
            if a.mac and e["kind"] in ("dhcp", "seen") and a.mac.lower() not in client.lower():
                continue
            print(f"{time.strftime('%H:%M:%S', time.localtime(e['t']))} {e['kind']:6} {client:21} {e['msg']}",
                  flush=True)
            msg = e["msg"]
            if a.until == "dhcp" and e["kind"] == "dhcp":
                met = True
            elif a.until == "http" and e["kind"] in ("http", "tftp"):
                met = True
            elif a.until == "squashfs" and e["kind"] == "http" and msg.startswith("done /live/filesystem.squashfs"):
                met = True
            elif a.until == "installed" and e["kind"] == "report" and msg.startswith("complete"):
                met = True
        if met:
            return 0
        if deadline and time.monotonic() > deadline:
            print("watch: timed out", file=sys.stderr)
            return 1
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
