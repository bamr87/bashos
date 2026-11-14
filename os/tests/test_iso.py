"""bashOS on Amrchy (os/iso, os/amrchy/layer, bashos-firstboot) — offline tests. Nothing is built,
booted or downloaded: the ISO tree is staged into a temporary directory, the layer's system
setup runs against a fake root with systemctl shimmed, and first boot is held at its two waits
(a user, the network). The ISO itself is built by `bashos os iso build` and installed in QEMU
(docs/OS.md); amrchy's own side of the contract is amrchy/test/shell.d/layers-test.sh.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

OS = Path(__file__).resolve().parents[1]
REPO = OS.parent
GIB = 1024**3

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shell environment")


def _bash_ok() -> bool:
    out = subprocess.run(["bash", "-c", "echo ${BASH_VERSINFO[0]}${BASH_VERSINFO[1]}"],
                         capture_output=True, text=True, check=False).stdout.strip()
    return out.isdigit() and int(out) >= 44


needs_bash = pytest.mark.skipif(not _bash_ok(), reason="the OS layer needs bash >= 4.4")


def _env(**extra: str) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("BASHOS_", "OMARCHY_"))}
    e.update(NO_COLOR="1", **extra)
    return e


def sh(*args: str, env: dict[str, str], check: bool = True, **kw) -> subprocess.CompletedProcess:
    p = subprocess.run(["bash", *args], env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, check=False, **kw)
    if check:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> Path:
    build = tmp_path_factory.mktemp("iso")
    sh(str(OS / "iso/build.sh"), "--stage-only", env=_env(BASHOS_ISO_BUILD=str(build)))
    return build / "stage/amrchy"


# ---------------------------------------------------------------- the ISO tree


def test_pins_are_full_commits():
    conf = dict(line.split("=", 1) for line in (OS / "iso/iso.conf").read_text().splitlines()
                if line and not line.startswith("#"))
    for key in ("OMARCHY_ISO_COMMIT", "OMARCHY_PKGS_COMMIT"):
        assert len(conf[key]) == 40 and int(conf[key], 16) >= 0, key
    assert conf["BASHOS_ISO_ARCH"] == "x86_64"


@needs_bash
def test_stage_is_amrchy_with_the_bashos_layer(staged):
    # The framework, whole, with its layer runners: what omarchy-iso-make --local-source builds.
    assert (staged / "install/post-install/layers.sh").is_file()
    assert (staged / "install/omarchy-base.packages").is_file()
    layer = staged / "install/layers/bashos"
    assert (layer / "system.sh").read_text() == (OS / "amrchy/layer/system.sh").read_text()
    # The payload is the bashOS tree the machine runs, without the framework or one-os.
    payload = layer / "payload"
    for path in ("os/bin/bashos-firstboot", "os/install.sh", "pyproject.toml", "src/bashos",
                 ".claude/commands", "opencode.jsonc"):
        assert (payload / path).exists(), path
    for path in ("amrchy", "one-os", "chui", "os/image"):
        assert not (payload / path).exists(), path
    stamp = dict(line.split("=", 1) for line in (layer / "build-info").read_text().splitlines())
    assert len(stamp["commit"]) == 40 and len(stamp["amrchy"]) == 40
    assert stamp["layer"] == "/opt/bashos" and stamp["source"] == "bashos-iso"


# ---------------------------------------------------------------- the layer, in the installer


def _shim_systemctl(bindir: Path, log: Path) -> None:
    bindir.mkdir(exist_ok=True)
    f = bindir / "systemctl"
    f.write_text(f'#!/bin/sh\necho "systemctl $*" >>{log}\n')
    f.chmod(0o755)


@needs_bash
def test_layer_puts_bashos_on_the_target_and_arms_first_boot(staged, tmp_path):
    target, calls = tmp_path / "target", tmp_path / "calls"
    _shim_systemctl(tmp_path / "bin", calls)
    env = _env(PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}", BASHOS_LAYER_ROOT=str(target),
               LAYER_DIR=str(staged / "install/layers/bashos"), OMARCHY_INSTALL_USER="amr")
    run = ["-eE", "-c", 'source "$LAYER_DIR/system.sh"']
    p = sh(*run, env=env)
    assert "bashos-firstboot finishes it online" in p.stdout
    assert (target / "opt/bashos/os/install.sh").is_file()
    assert (target / "etc/bashos/os.conf").read_text() == (OS / "config/os.conf").read_text()
    assert (target / "etc/bashos/firstboot.env").read_text() == "BASHOS_USER=amr\n"
    assert (target / "var/lib/bashos/firstboot-pending").exists()
    assert os.readlink(target / "usr/local/sbin/bashos-firstboot") == "/opt/bashos/os/bin/bashos-firstboot"
    assert (target / "usr/local/lib/systemd/system/bashos-firstboot.service").is_file()
    assert calls.read_text() == f"systemctl --root={target} enable bashos-firstboot.service\n"
    # The machine's own settings survive a framework upgrade's re-run; a finished machine is left be.
    (target / "etc/bashos/os.conf").write_text("BASHOS_HARNESS=off\n")
    sh(*run, env=env)
    assert (target / "etc/bashos/os.conf").read_text() == "BASHOS_HARNESS=off\n"
    (target / "var/lib/bashos/provisioned").write_text("done\n")
    (target / "opt/bashos/marker").write_text("kept")
    assert "bashos os update keeps it current" in sh(*run, env=env).stdout
    assert (target / "opt/bashos/marker").exists()


@needs_bash
def test_a_deferred_install_names_no_person(staged, tmp_path):
    target = tmp_path / "target"
    _shim_systemctl(tmp_path / "bin", tmp_path / "calls")
    env = _env(PATH=f"{tmp_path / 'bin'}:{os.environ['PATH']}", BASHOS_LAYER_ROOT=str(target),
               LAYER_DIR=str(staged / "install/layers/bashos"))
    sh("-eE", "-c", 'source "$LAYER_DIR/system.sh"', env=env)
    assert not (target / "etc/bashos/firstboot.env").exists()
    assert (target / "var/lib/bashos/firstboot-pending").exists()


# ---------------------------------------------------------------- first boot


@pytest.fixture
def fake_root(tmp_path) -> Path:
    root = tmp_path / "root"
    (root / "etc/bashos").mkdir(parents=True)
    (root / "var/lib/bashos").mkdir(parents=True)
    (root / "var/lib/bashos/firstboot-pending").touch()
    return root


def _firstboot(root: Path, **extra: str) -> subprocess.CompletedProcess:
    env = _env(BASHOS_OS_ROOT=str(root), HOME=str(root), **extra)
    return sh(str(OS / "bin/bashos-firstboot"), env=env, check=False)


@needs_bash
def test_first_boot_waits_for_its_person(fake_root):
    (fake_root / "etc/bashos/firstboot.env").write_text("BASHOS_USER=nobody-here-yet\n")
    p = _firstboot(fake_root)
    assert p.returncode == 75, p.stdout + p.stderr  # the unit starts it again a minute later
    assert "no user yet" in p.stdout
    assert (fake_root / "var/lib/bashos/firstboot-pending").exists()


@needs_bash
def test_first_boot_waits_for_the_network(fake_root):
    (fake_root / "etc/bashos/firstboot.env").write_text(f"BASHOS_USER={os.environ.get('USER') or 'root'}\n")
    p = _firstboot(fake_root, BASHOS_FIRSTBOOT_PROBES="http://127.0.0.1:9/")
    assert p.returncode == 75, p.stdout + p.stderr
    assert "offline" in p.stdout


@needs_bash
def test_first_boot_runs_once(fake_root):
    (fake_root / "var/lib/bashos/provisioned").write_text("2026-11-13\n")
    p = _firstboot(fake_root)
    assert p.returncode == 0 and "already done" in p.stdout
    assert not (fake_root / "var/lib/bashos/firstboot-pending").exists()


def test_first_boot_unit_retries_only_through_its_exit_code():
    unit = (OS / "systemd/system/bashos-firstboot.service").read_text()
    assert "ConditionPathExists=/var/lib/bashos/firstboot-pending" in unit
    assert "Restart=on-failure" in unit and "StartLimitIntervalSec=0" in unit
    script = (OS / "bin/bashos-firstboot").read_text()
    # Every real failure records itself and exits 0, so only the two waits (75) loop.
    assert "exit 0" in script.split("fail() {", 1)[1].split("}", 1)[0]


# ---------------------------------------------------------------- the cidata seed


def _seed(tmp_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    keys = tmp_path / "keys.pub"
    keys.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample amr@mac\n# a comment\n")
    base = ["--user", "amr", "--disk", "/dev/nvme0n1", "--disk-bytes", str(2000398934016),
            "--hostname", "x870e", "--keys", str(keys), "--password-hash", "$6$salt$hash",
            "--out", str(tmp_path / "cidata")]
    return sh(str(OS / "iso/seed.sh"), *base, *args, env=_env(HOME=str(tmp_path)), check=check)


@needs_bash
@pytest.mark.skipif(subprocess.run(["sh", "-c", "command -v jq"], capture_output=True).returncode,
                    reason="jq writes the answer files")
def test_seed_writes_the_configurators_answer_files(tmp_path):
    _seed(tmp_path)
    out = tmp_path / "cidata"
    conf = json.loads((out / "user_configuration.json").read_text())
    disk = conf["disk_config"]["device_modifications"][0]
    assert disk["device"] == "/dev/nvme0n1" and disk["wipe"] is True
    esp, main = disk["partitions"]
    assert esp["mountpoint"] == "/boot" and esp["size"]["value"] == 2 * GIB
    # The layout fills the disk exactly, less a 1 MiB gap in front and the GPT backup behind.
    assert main["start"]["value"] + main["size"]["value"] + 1024**2 == 2000398934016
    assert conf["hostname"] == "x870e" and conf["kernels"] == ["linux-omarchy"]
    assert "disk_encryption" not in conf["disk_config"]
    creds = json.loads((out / "user_credentials.json").read_text())
    assert creds["users"] == [{"enc_password": "$6$salt$hash", "groups": [], "sudo": True, "username": "amr"}]
    assert oct((out / "user_credentials.json").stat().st_mode & 0o777) == "0o600"
    assert (out / "user_encrypt_installation.txt").read_text() == "false\n"
    assert (out / "authorized_keys").read_text() == "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample amr@mac\n"


@needs_bash
@pytest.mark.parametrize(("args", "message"), [
    (["--user", "root"], "--user"),
    (["--disk-bytes", "12345"], "--disk-bytes"),
    (["--disk", "nvme0n1"], "--disk"),
    (["--password-hash", "hunter2"], "never the password"),
])
def test_seed_refuses_what_would_install_the_wrong_machine(tmp_path, args, message):
    p = _seed(tmp_path, *args, check=False)
    assert p.returncode == 2 and message in p.stderr
    assert not (tmp_path / "cidata").exists()
