"""QEMU guest agent client: run commands and move files inside a running VM (ADR-0004).

The guest runs qemu-guest-agent on a virtio-serial port; QEMU exposes the host end
as a unix socket. No network, no credentials, works from early userspace on.
"""
from __future__ import annotations

import base64
import json
import random
import socket
import time
from dataclasses import dataclass
from pathlib import Path


class AgentUnavailable(ConnectionError):
    pass


@dataclass
class ExecResult:
    rc: int
    stdout: str
    stderr: str

    def check(self) -> ExecResult:
        if self.rc != 0:
            raise RuntimeError(f"guest command failed (rc={self.rc}):\n{self.stderr or self.stdout}")
        return self


class QGA:
    def __init__(self, path: Path, timeout: float = 10, sync: bool = True):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(str(path))
        except OSError as e:
            self.sock.close()
            raise AgentUnavailable(f"cannot connect to {path}: {e}") from None
        self.sock.settimeout(timeout)
        self._buf = b""
        self._tokens: set[int] = set()
        if sync and not self.try_sync(timeout):
            self.close()
            raise AgentUnavailable(f"guest agent not answering within {timeout:.0f}s; is the VM booted?")

    # ------------------------------------------------------------------ protocol
    def try_sync(self, timeout: float) -> bool:
        """Send guest-sync-delimited and wait up to `timeout` for a reply to it (or to any
        earlier sync on this connection). Discards stale replies left by earlier clients."""
        token = random.randint(1, 2**31)
        self._tokens.add(token)
        # Only the agent sends the 0xFF sentinel (ahead of its reply); a client-sent 0xFF
        # is a JSON parse error for current agents and eats the sync request.
        self.sock.sendall(json.dumps({"execute": "guest-sync-delimited",
                                      "arguments": {"id": token}}).encode() + b"\n")
        self.sock.settimeout(timeout)
        try:
            while True:
                if self._recv().get("return") in self._tokens:
                    self._tokens.clear()
                    return True
        except TimeoutError:
            return False

    def _recv(self) -> dict:
        while True:
            while b"\n" not in self._buf:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise AgentUnavailable("guest agent closed the channel")
                self._buf += chunk
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.lstrip(b"\xff").strip()
            if line:
                return json.loads(line)

    def call(self, cmd: str, **args):
        self.sock.sendall(json.dumps({"execute": cmd, "arguments": args}).encode() + b"\n")
        msg = self._recv()
        if "error" in msg:
            raise RuntimeError(f"guest agent {cmd}: {msg['error'].get('desc', msg['error'])}")
        return msg.get("return")

    def close(self) -> None:
        self.sock.close()

    def __enter__(self) -> QGA:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ helpers
    def ping(self) -> None:
        self.call("guest-ping")

    def exec(self, command: str | list[str], timeout: float = 300, stdin: bytes | None = None) -> ExecResult:
        """Run as root in the guest. A string goes through /bin/sh -c; a list is exec'd directly."""
        argv = ["/bin/sh", "-c", command] if isinstance(command, str) else list(command)
        args = {"path": argv[0], "arg": argv[1:], "capture-output": True}
        if stdin is not None:
            args["input-data"] = base64.b64encode(stdin).decode()
        pid = self.call("guest-exec", **args)["pid"]
        deadline = time.monotonic() + timeout
        delay = 0.05
        while True:
            st = self.call("guest-exec-status", pid=pid)
            if st.get("exited"):
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"guest command still running after {timeout:.0f}s: {argv}")
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
        dec = lambda k: base64.b64decode(st.get(k, "")).decode("utf-8", "replace")  # noqa: E731
        rc = st.get("exitcode", 128 + st.get("signal", 0))
        return ExecResult(rc=rc, stdout=dec("out-data"), stderr=dec("err-data"))

    def read_file(self, path: str) -> bytes:
        h = self.call("guest-file-open", path=path, mode="rb")
        data = b""
        try:
            while True:
                r = self.call("guest-file-read", handle=h, count=48 * 1024)
                data += base64.b64decode(r.get("buf-b64", ""))
                if r.get("eof"):
                    return data
        finally:
            self.call("guest-file-close", handle=h)

    def write_file(self, path: str, data: bytes) -> None:
        h = self.call("guest-file-open", path=path, mode="wb")
        try:
            for i in range(0, len(data), 48 * 1024):
                self.call("guest-file-write", handle=h, **{"buf-b64": base64.b64encode(data[i:i + 48 * 1024]).decode()})
        finally:
            self.call("guest-file-close", handle=h)

    def shutdown(self, mode: str = "powerdown") -> None:
        """guest-shutdown never replies on success; don't wait for one."""
        self.sock.sendall(json.dumps({"execute": "guest-shutdown", "arguments": {"mode": mode}}).encode() + b"\n")


def wait_agent(path: Path, timeout: float, alive=lambda: True) -> None:
    """Block until the guest agent answers.

    Holds ONE connection and re-sends sync requests on it. Reconnecting in a loop while
    the guest hasn't opened its port yet wedges the channel on some QEMU versions (seen
    with Debian's 10.0: the agent was up, but no reply arrived until polling stopped).
    """
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        if not alive():
            raise AgentUnavailable("VM exited before its guest agent came up")
        try:
            q = QGA(path, timeout=5, sync=False)
        except AgentUnavailable as e:  # socket not there yet
            last = e
            time.sleep(1)
            continue
        try:
            while time.monotonic() < deadline and alive():
                if q.try_sync(5):
                    return
        except (OSError, AgentUnavailable) as e:
            last = e
        finally:
            q.close()
    raise AgentUnavailable(f"guest agent not up after {timeout:.0f}s ({last or 'no reply'})")
