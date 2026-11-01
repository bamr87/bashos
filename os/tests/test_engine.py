"""The managed engine (os/install/engine.sh): OpenCode on npm's latest release, verified first.

A local stand-in for the npm registry serves `opencode-ai` and its platform package; a stand-in
verifier plays `bashos opencode verify`; a fake root keeps every path off the machine. The fetch
needs GNU coreutils (sha512sum, basenc) and jq, so those tests run on Linux (CI, a bashOS box).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

OS = Path(__file__).resolve().parents[1]
REPO = OS.parent
PKG = "opencode-linux-x64-baseline"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shell environment")
needs_gnu = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("sha512sum", "basenc", "jq", "curl")) or sys.platform == "darwin",
    reason="the engine fetch needs GNU coreutils, jq and curl (Linux)",
)


class Registry:
    """Just enough of registry.npmjs.org: packuments, version documents, tarballs."""

    def __init__(self) -> None:
        self.routes: dict[str, bytes] = {}
        self.versions: list[str] = []
        registry = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (http.server's name)
                body = registry.routes.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                self.wfile.write(body or b"not found")

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(self, version: str, *, tamper: bool = False) -> None:
        data = io.BytesIO()
        script = f"#!/bin/sh\necho {version}\n".encode()
        with tarfile.open(fileobj=data, mode="w:gz") as tar:
            info = tarfile.TarInfo("package/bin/opencode")
            info.size, info.mode = len(script), 0o755
            tar.addfile(info, io.BytesIO(script))
        tgz = data.getvalue()
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(tgz).digest()).decode()
        self.routes[f"/tgz/{version}.tgz"] = tgz + (b"x" if tamper else b"")
        self.routes[f"/{PKG}/{version}"] = json.dumps(
            {"dist": {"tarball": f"{self.url}/tgz/{version}.tgz", "integrity": integrity}}).encode()
        self.versions.append(version)
        self.routes["/opencode-ai"] = json.dumps({"versions": {v: {} for v in self.versions}}).encode()

    def latest(self, version: str) -> None:
        self.routes["/opencode-ai/latest"] = json.dumps({"version": version}).encode()


@pytest.fixture
def registry():
    r = Registry()
    yield r
    r.server.shutdown()


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, str]:
    """A fake root, an x86-64 glibc `uname`/`ldd`, and a verifier that rejects OpenCode 2."""
    root, shims = tmp_path / "root", tmp_path / "shims"
    (root / "etc").mkdir(parents=True)
    shims.mkdir()
    for name, body in {
        "uname": 'case "$1" in -m) echo x86_64 ;; *) echo Linux ;; esac',
        "ldd": "echo 'ldd (GNU libc) 2.41'",
        # stands in for `bashos opencode verify --binary BIN`
        "verify": f'echo "$1" >>{tmp_path}/verified; v=$("$1" --version); [ "${{v%%.*}}" = 1 ] && [ ! -e {tmp_path}/reject ]',
    }.items():
        (shims / name).write_text(f"#!/bin/sh\n{body}\n")
        (shims / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("BASHOS_")}
    env.update(BASHOS_OS_ROOT=str(root), BASHOS_ENGINE_VERIFIER=str(shims / "verify"),
               PATH=f"{shims}:{env['PATH']}", HOME=str(tmp_path), NO_COLOR="1", BASHOS_USER="amr")
    return env


def engine(env: dict[str, str], *args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["bash", str(OS / "os.sh"), "engine", *args], env=env, capture_output=True,
                       text=True, stdin=subprocess.DEVNULL, check=False)
    if check:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


def state(env: dict[str, str]) -> dict[str, str]:
    path = Path(env["BASHOS_OS_ROOT"]) / "var/lib/bashos/opencode.state"
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def home(env: dict[str, str]) -> Path:
    return Path(env["BASHOS_OS_ROOT"]) / "usr/local/lib/bashos/opencode"


# ---------------------------------------------------------------- which build


@pytest.mark.parametrize(("arch", "libc", "package"), [
    ("x86_64", "GNU libc", "opencode-linux-x64-baseline"),  # always baseline: forge has no AVX2
    ("aarch64", "GNU libc", "opencode-linux-arm64"),
    ("x86_64", "musl libc", "opencode-linux-x64-baseline-musl"),
])
def test_the_build_suits_any_cpu_the_disk_boots_on(tmp_path, arch, libc, package):
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "uname").write_text(f"#!/bin/sh\necho {arch}\n")
    (shims / "ldd").write_text(f"#!/bin/sh\necho '{libc}'\n")
    for f in shims.iterdir():
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{shims}:{os.environ['PATH']}")
    out = subprocess.run(["bash", "-c", f'source "{OS}/lib.sh"; source "{OS}/install/engine.sh"; os_engine_package'],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == package


# ---------------------------------------------------------------- the update


@needs_gnu
def test_latest_is_fetched_verified_and_promoted(registry, machine, tmp_path):
    registry.publish("1.2.3")
    registry.latest("1.2.3")
    env = dict(machine, BASHOS_ENGINE_REGISTRY=registry.url)
    engine(env, "update")
    current = home(env) / "current"
    assert os.readlink(current) == "1.2.3"
    assert (current / "bin/opencode").read_text().endswith("echo 1.2.3\n")
    assert "1.2.3" in (current / "PACKAGE").read_text() and PKG in (current / "PACKAGE").read_text()
    root = Path(env["BASHOS_OS_ROOT"])
    assert (root / "etc/bashos/opencode").read_text().strip() == "/usr/local/lib/bashos/opencode/current/bin/opencode"
    assert os.readlink(root / "usr/local/bin/opencode") == "/usr/local/lib/bashos/opencode/current/bin/opencode"
    assert state(env)["verdict"] == "ok"
    # the contract ran on the staged download, before anything was promoted
    verified = (tmp_path / "verified").read_text().split()
    assert len(verified) == 1 and not verified[0].startswith(str(home(env)))
    engine(env, "update")  # nothing new: nothing fetched, nothing verified
    assert len((tmp_path / "verified").read_text().split()) == 1


@needs_gnu
def test_a_release_that_fails_the_contract_is_never_promoted(registry, machine, tmp_path):
    env = dict(machine, BASHOS_ENGINE_REGISTRY=registry.url)
    registry.publish("1.2.3")
    registry.latest("1.2.3")
    engine(env, "update")
    registry.publish("1.2.4")
    registry.latest("1.2.4")
    (tmp_path / "reject").touch()
    engine(env, "update")
    assert os.readlink(home(env) / "current") == "1.2.3"
    assert not (home(env) / "1.2.4").exists()
    assert state(env)["verdict"] == "rejected" and state(env)["version"] == "1.2.4"


@needs_gnu
def test_a_new_major_the_contract_rejects_keeps_the_newest_release_that_runs(registry, machine):
    env = dict(machine, BASHOS_ENGINE_REGISTRY=registry.url)
    registry.publish("1.2.3")
    registry.latest("1.2.3")
    engine(env, "update")
    for v in ("1.2.5", "2.0.0"):
        registry.publish(v)
    registry.latest("2.0.0")  # OpenCode 2: the stand-in verifier refuses it, as bashOS does (#71)
    engine(env, "update")
    assert os.readlink(home(env) / "current") == "1.2.5"
    assert "bamr87/bashos#71" in state(env)["detail"]
    kept = sorted(p.name for p in home(env).iterdir() if p.name != "current")
    assert kept == ["1.2.3", "1.2.5"]  # this release and the one before it, for a rollback


@needs_gnu
def test_a_download_that_does_not_match_the_registry_is_refused(registry, machine, tmp_path):
    env = dict(machine, BASHOS_ENGINE_REGISTRY=registry.url)
    registry.publish("1.2.3", tamper=True)
    registry.latest("1.2.3")
    p = engine(env, "update")
    assert "sha512" in p.stderr
    assert not (home(env) / "current").exists()
    assert not (tmp_path / "verified").exists()  # never even run


@needs_gnu
def test_an_unreachable_registry_keeps_the_engine(machine):
    env = dict(machine, BASHOS_ENGINE_REGISTRY="http://127.0.0.1:9")
    p = engine(env, "update")
    assert "did not answer" in p.stderr
    assert state(env)["verdict"] == "unreachable"


def test_a_fake_root_never_reaches_the_real_registry(machine):
    p = engine(machine, "update")  # no BASHOS_ENGINE_REGISTRY
    assert "skip (fake root)" in p.stdout
    assert not (Path(machine["BASHOS_OS_ROOT"]) / "usr/local/lib/bashos").exists()


# ---------------------------------------------------------------- the npm copy older images installed


def _npm_copy(root: Path) -> Path:
    npm = root / "usr/local/lib/node_modules/opencode-ai/bin"
    npm.mkdir(parents=True)
    (npm / "opencode.exe").write_text("#!/bin/sh\necho 1.19.5\n")
    (root / "usr/local/bin").mkdir(parents=True, exist_ok=True)
    (root / "usr/local/bin/opencode").symlink_to("../lib/node_modules/opencode-ai/bin/opencode.exe")
    return npm.parent


def _migration() -> Path:
    return next(p for p in sorted((OS / "migrations").glob("*.sh")) if "node_modules/opencode-ai" in p.read_text())


def test_image_machines_drop_the_npm_copy_once_the_managed_engine_runs(machine):
    root = Path(machine["BASHOS_OS_ROOT"])
    env = dict(machine, OS_SRC=str(REPO))
    npm = _npm_copy(root)
    run = lambda: subprocess.run(["bash", str(_migration())], env=env, capture_output=True, text=True)  # noqa: E731
    assert run().returncode == 0 and npm.exists()  # an in-place install: the npm copy is the person's
    (root / "etc/systemd/network").mkdir(parents=True)
    (root / "etc/systemd/network/80-bashos-wired.network").write_text("[Match]\n")
    assert run().returncode == 1 and npm.exists()  # no managed engine yet: keep it, fail, retry later
    managed = root / "usr/local/lib/bashos/opencode/1.19.5/bin"
    managed.mkdir(parents=True)
    (managed / "opencode").write_text("#!/bin/sh\necho 1.19.5\n")
    (managed / "opencode").chmod(0o755)
    (root / "usr/local/lib/bashos/opencode/current").symlink_to("1.19.5")
    p = run()
    assert p.returncode == 0, p.stderr
    assert not npm.exists()
    assert os.readlink(root / "usr/local/bin/opencode") == "/usr/local/lib/bashos/opencode/current/bin/opencode"
