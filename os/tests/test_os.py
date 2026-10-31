"""The bashOS OS layer (os/) — offline tests. Every script runs against a fake root
(BASHOS_OS_ROOT) and a throwaway $HOME, so nothing reaches the real machine: no sudo, no apt,
no systemctl, no network. The image itself is built and booted by os/image/test/boot-smoke.sh
(the `os image` workflow), not here.

Stdlib + pytest only. The layer targets Debian's bash 5; any bash >= 4.4 on PATH runs it.
"""

from __future__ import annotations

import configparser
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

OS = Path(__file__).resolve().parents[1]
REPO = OS.parent

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shell environment")


def _bash_ok() -> bool:
    out = subprocess.run(["bash", "-c", "echo ${BASH_VERSINFO[0]}${BASH_VERSINFO[1]}"],
                         capture_output=True, text=True, check=False).stdout.strip()
    return out.isdigit() and int(out) >= 44


needs_bash = pytest.mark.skipif(not _bash_ok(), reason="the OS layer needs bash >= 4.4")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "root"
    (r / "etc").mkdir(parents=True)
    (r / "etc" / "os-release").write_text(
        'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\nVERSION_CODENAME=trixie\n'
    )
    return r


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def env(root: Path, home: Path, tmp_path: Path) -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("BASHOS_", "CLAUDE_", "SUDO_"))}
    e.update(
        HOME=str(home),
        BASHOS_OS_ROOT=str(root),
        BASHOS_USER="amr",
        SHELL="/bin/zsh",
        NO_COLOR="1",
        # The hub checkout the harness phase looks for (never cloned in a fake root).
        BASHOS_HUB_DIR=str(tmp_path / "hub"),
    )
    return e


def run(*args: str, env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["bash", *args], env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, check=False)
    if check:
        assert p.returncode == 0, p.stdout + p.stderr
    return p


def install(env: dict[str, str], *flags: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(str(OS / "install.sh"), *flags, env=env, check=check)


def tree(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------- the install


@needs_bash
def test_dry_run_changes_nothing(env, root, home):
    before_root, before_home = tree(root), tree(home)
    p = install(env, "--dry-run")
    assert "dry run: nothing was changed" in p.stdout
    for phase in ("preflight", "packages", "runtime", "system", "console", "harness", "finish"):
        assert f"== {phase} ==" in p.stdout
    assert tree(root) == before_root and tree(home) == before_home


@needs_bash
def test_install_lays_down_the_machine(env, root, home):
    p = install(env)
    # The layer, root-owned on a real machine, with the commands on /usr/local/bin.
    assert (root / "opt/bashos/os/os.sh").is_file()
    assert not (root / "opt/bashos/.venv").exists()  # pip is skipped in a fake root
    links = {
        "usr/local/bin/bashos": "/opt/bashos/bin/bashos",
        "usr/local/bin/os-health": "/opt/bashos/bin/os-health",
        "usr/local/bin/bashos-os": "/opt/bashos/os/os.sh",
        "usr/local/bin/bashos-console": "/opt/bashos/os/bin/bashos-console",
        "usr/local/bin/bashos-harness": "/opt/bashos/os/bin/bashos-harness",
        "usr/local/sbin/bashos-provision": "/opt/bashos/os/bin/bashos-provision",
    }
    for link, target in links.items():
        assert os.readlink(root / link) == target, link
        assert (root / target.lstrip("/")).is_file(), target
    # The machine's settings, the units, never-sleep, tty1 autologin and linger.
    assert (root / "etc/bashos/os.conf").read_text() == (OS / "config/os.conf").read_text()
    assert "commit=" in (root / "etc/bashos/build-info").read_text()
    for unit in ("system/bashos-provision.service", "user/bashos-harness.service",
                 "user/bashos-heal.service", "user/bashos-heal.timer"):
        assert (root / "usr/local/lib/systemd" / unit).is_file(), unit
    assert "IdleAction=ignore" in (root / "etc/systemd/logind.conf.d/bashos-no-sleep.conf").read_text()
    autologin = (root / "etc/systemd/system/getty@tty1.service.d/bashos-autologin.conf").read_text()
    assert "--autologin amr --noclear" in autologin
    assert (root / "var/lib/systemd/linger/amr").exists()
    # The user's side: managed blocks, the secrets file, the migration baseline.
    assert "exec /usr/local/bin/bashos-console" in (home / ".zprofile").read_text()
    assert "bashos-console --attach" in (home / ".zshrc").read_text()
    assert (home / ".tmux.conf").read_text().splitlines()[1] == \
        "source-file -q /opt/bashos/os/config/tmux.conf"
    harness_env = home / ".config/bashos/harness.env"
    assert stat.S_IMODE(harness_env.stat().st_mode) == 0o600
    assert (home / ".local/state/bashos/migrations").is_dir()
    assert "bashOS is installed." in p.stdout


@needs_bash
def test_install_is_idempotent(env, root, home):
    install(env)
    first_root, first_home = tree(root), tree(home)
    p = install(env)
    assert tree(root) == first_root and tree(home) == first_home
    assert "unchanged" in p.stdout
    for f in (".zprofile", ".zshrc", ".tmux.conf"):
        assert (home / f).read_text().count(">>> bashos os managed") == 1, f


@needs_bash
def test_user_lines_are_kept_and_tmux_defaults_come_first(env, home):
    (home / ".tmux.conf").write_text("set -g prefix C-a\n")
    (home / ".zprofile").write_text("export EDITOR=nvim\n")
    install(env, "--user-only")
    tmux = (home / ".tmux.conf").read_text().splitlines()
    assert tmux[0].startswith("# >>> bashos os managed") and tmux[-1] == "set -g prefix C-a"
    assert (home / ".zprofile").read_text().startswith("export EDITOR=nvim\n")


@needs_bash
def test_machine_settings_survive_a_reinstall(env, root):
    install(env)
    conf = root / "etc/bashos/os.conf"
    conf.write_text(conf.read_text() + "BASHOS_HARNESS=compose\n")
    p = install(env)
    assert conf.read_text().endswith("BASHOS_HARNESS=compose\n")
    assert "kept /etc/bashos/os.conf" in p.stdout


@needs_bash
def test_bash_users_get_profile_not_a_new_bash_profile(env, home):
    env["SHELL"] = "/bin/bash"
    (home / ".profile").write_text("# debian skeleton\n")
    install(env, "--user-only")
    assert "bashos-console" in (home / ".profile").read_text()
    assert not (home / ".bash_profile").exists()  # it would shadow ~/.profile
    assert "bashos-console --attach" in (home / ".bashrc").read_text()


@needs_bash
def test_forge_console_mirror_is_adopted_not_duplicated(env, root, home):
    """forge's 03-console-mirror.sh predates the layer: its hooks and getty drop-in stay."""
    (home / ".zprofile").write_text(
        '# console-mirror:tty1\nif [[ "$(tty)" == "/dev/tty1" && -z "${TMUX:-}" ]]; then\n'
        "  exec tmux new-session -A -s console\nfi\n"
    )
    (home / ".zshrc").write_text(
        '# console-mirror:ssh\nif [[ -n "${SSH_CONNECTION:-}" && -z "${TMUX:-}" ]]; then\n'
        "  exec tmux new-session -A -s console\nfi\n"
    )
    dropin = root / "etc/systemd/system/getty@tty1.service.d"
    dropin.mkdir(parents=True)
    (dropin / "autologin.conf").write_text(
        "[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin amr --noclear %I $TERM\n"
    )
    p = install(env)
    assert "bashos-console" not in (home / ".zprofile").read_text()
    assert "bashos-console" not in (home / ".zshrc").read_text()
    assert not (dropin / "bashos-autologin.conf").exists()
    assert "existing tty1 console mirror" in p.stdout
    assert "tty1 already logs amr in" in p.stdout


@needs_bash
def test_console_off_leaves_tty1_alone(env, root, home):
    (home / ".config/bashos").mkdir(parents=True)
    (home / ".config/bashos/os.conf").write_text("BASHOS_CONSOLE=off\n")
    install(env)
    assert not (root / "etc/systemd/system/getty@tty1.service.d/bashos-autologin.conf").exists()
    assert not (home / ".zprofile").exists() or "bashos-console" not in (home / ".zprofile").read_text()


@needs_bash
def test_the_user_phases_are_never_roots(env):
    env.pop("BASHOS_OS_ROOT")
    env["BASHOS_USER"] = "root"
    p = run(str(OS / "install.sh"), "--user-only", env=env, check=False)
    if os.geteuid() == 0:
        assert p.returncode == 1 and "never root's" in p.stderr
    else:
        assert p.returncode != 0 or "never root's" not in p.stderr


@needs_bash
def test_unknown_phase_is_refused(env):
    p = install(env, "--only", "nope", check=False)
    assert p.returncode == 1 and "unknown phase 'nope'" in p.stderr


@needs_bash
def test_uninstall_removes_what_install_added(env, root, home):
    (home / ".tmux.conf").write_text("set -g prefix C-a\n")
    install(env)
    run(str(OS / "os.sh"), "uninstall", env=env)
    assert (home / ".tmux.conf").read_text() == "set -g prefix C-a\n"
    assert ">>> bashos" not in (home / ".zprofile").read_text()
    assert not (root / "usr/local/bin/bashos").exists()
    assert not list((root / "usr/local/lib/systemd/user").glob("bashos-*"))
    assert not (root / "etc/systemd/system/getty@tty1.service.d/bashos-autologin.conf").exists()
    assert (root / "opt/bashos").is_dir() and (root / "etc/bashos/os.conf").is_file()  # kept without --purge
    run(str(OS / "os.sh"), "uninstall", "--purge", env=env)
    assert not (root / "opt/bashos").exists() and not (root / "etc/bashos").exists()


# ---------------------------------------------------------------- packages


def _packages(env: dict[str, str], *args: str) -> list[str]:
    script = f'source "{OS}/lib.sh"; source "{OS}/install/packages.sh"; os_packages "$@"'
    return run("-c", script, "_", *args, env=env).stdout.split()


@needs_bash
def test_package_guards_skip_what_is_already_provided(env, tmp_path):
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "docker").write_text("#!/bin/sh\n")
    (shims / "docker").chmod(0o755)
    clean = dict(env, PATH=f"{shims}:{env['PATH']}")
    assert "docker.io" not in _packages(clean, "services")  # forge's docker-ce stays
    assert {"docker.io", "docker-compose"} <= set(_packages(clean, "--all", "services"))
    base = _packages(clean, "--all", "base")
    assert {"python3", "python3-venv", "tmux", "shellcheck", "nodejs", "openssh-server"} <= set(base)
    assert not any(p.startswith(("cmd:", "#")) for p in base)


def test_package_lists_are_plain_debian_names():
    for lst in (OS / "packages").glob("*.list"):
        for line in lst.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            for word in line.split():
                assert re.fullmatch(r"(cmd:)?[a-z0-9][a-z0-9.+-]*", word), f"{lst.name}: {word}"


# ---------------------------------------------------------------- migrations


@needs_bash
def test_migrations_run_once_in_order_and_stop_on_failure(env, home, tmp_path):
    mig = tmp_path / "migrations"
    mig.mkdir()
    log = tmp_path / "ran.log"
    (mig / "1800000000.sh").write_text(f"echo first >> {log}\n")
    (mig / "1800000001.sh").write_text(f"echo second >> {log}\n")
    e = dict(env, BASHOS_OS_MIGRATIONS=str(mig))
    assert run(str(OS / "os.sh"), "migrate", "--pending", env=e).stdout.split() == \
        ["1800000000.sh", "1800000001.sh"]
    run(str(OS / "os.sh"), "migrate", env=e)
    assert log.read_text().split() == ["first", "second"]
    assert run(str(OS / "os.sh"), "migrate", "--pending", env=e, check=False).returncode == 1
    run(str(OS / "os.sh"), "migrate", env=e)
    assert log.read_text().split() == ["first", "second"]  # nothing ran twice
    (mig / "1800000002.sh").write_text("exit 3\n")
    p = run(str(OS / "os.sh"), "migrate", env=e, check=False)
    assert p.returncode == 1 and "1800000002.sh failed" in p.stderr
    assert not (home / ".local/state/bashos/migrations/1800000002.sh").exists()


@needs_bash
def test_a_fresh_install_marks_shipped_migrations_applied(env, home, tmp_path):
    mig = tmp_path / "migrations"
    mig.mkdir()
    (mig / "1800000000.sh").write_text("exit 1\n")  # would fail if it ever ran
    install(dict(env, BASHOS_OS_MIGRATIONS=str(mig)), "--user-only")
    assert (home / ".local/state/bashos/migrations/1800000000.sh").exists()


# ---------------------------------------------------------------- the harness


@pytest.fixture
def hub(env) -> Path:
    h = Path(env["BASHOS_HUB_DIR"])
    (h / "tools/console").mkdir(parents=True)
    (h / "compose").mkdir()
    (h / "compose/forge.yml").write_text("services: {}\n")
    return h


def harness(env: dict[str, str], conf: str = "", secret: str = "") -> subprocess.CompletedProcess:
    cfg = Path(env["HOME"]) / ".config/bashos"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "os.conf").write_text(conf)
    if secret:
        (cfg / "harness.env").write_text(secret)
    return run(str(OS / "bin/bashos-harness"), "--print", env=env, check=False)


@needs_bash
def test_harness_native_runs_the_hub_console(env, hub):
    p = harness(env)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == f"{hub}/tools/console/run.sh"


@needs_bash
def test_harness_refuses_a_lan_bind_without_a_token(env, hub):
    p = harness(env, "BASHOS_HARNESS_HOST=0.0.0.0\n")
    assert p.returncode == 78 and "without DASH_CONSOLE_TOKEN" in p.stderr
    p = harness(env, "BASHOS_HARNESS_HOST=0.0.0.0\n", "DASH_CONSOLE_TOKEN=s3cret\n")
    assert p.returncode == 0, p.stderr
    assert "s3cret" not in p.stdout + p.stderr


@needs_bash
def test_harness_compose_adds_the_forge_overlay_only_for_a_lan_bind(env, hub, tmp_path):
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "docker").write_text("#!/bin/sh\n")
    (shims / "docker").chmod(0o755)
    env = dict(env, PATH=f"{shims}:{env['PATH']}")
    loop = harness(env, "BASHOS_HARNESS=compose\n")
    assert loop.returncode == 0, loop.stderr
    assert "up --no-log-prefix console" in loop.stdout and "forge.yml" not in loop.stdout
    lan = harness(env, "BASHOS_HARNESS=compose\nBASHOS_HARNESS_HOST=0.0.0.0\n", "DASH_CONSOLE_TOKEN=t\n")
    assert f"-f {hub}/compose/forge.yml" in lan.stdout


@needs_bash
def test_harness_without_a_hub_says_how_to_get_one(env):
    p = harness(env)
    assert p.returncode == 78 and "no hub checkout" in p.stderr  # EX_CONFIG: no restart loop


@needs_bash
def test_harness_off_serves_nothing(env):
    p = harness(env, "BASHOS_HARNESS=off\n")
    assert p.returncode == 0 and "nothing to serve" in p.stdout


# ---------------------------------------------------------------- units, image, entry points


def _ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # systemd and mkosi keys are case-sensitive
    cp.read_string(path.read_text())
    return cp


def test_units_exec_the_commands_the_runtime_links():
    linked = set(re.findall(r'os_link "\$layer/[^"]+" (/usr/local/s?bin/[\w-]+)',
                            (OS / "install/runtime.sh").read_text()))
    for unit in sorted((OS / "systemd").rglob("bashos-*")):
        cp = _ini(unit)
        assert cp.has_section("Unit"), unit.name
        if unit.suffix == ".service":
            exe = cp["Service"]["ExecStart"].split()[0]
            assert exe in linked, f"{unit.name}: {exe} is not linked by os/install/runtime.sh"
        if unit.name != "bashos-heal.service":  # started by its timer, never enabled itself
            assert cp.has_section("Install"), unit.name


def test_provision_runs_once_and_before_the_monitor_login():
    unit = _ini(OS / "systemd/system/bashos-provision.service")["Unit"]
    assert unit["ConditionPathExists"] == "!/var/lib/bashos/provisioned"
    assert "getty@tty1.service" in unit["Before"]
    assert "/var/lib/bashos/provisioned" in (OS / "bin/bashos-provision").read_text()


def test_mkosi_builds_a_bootable_debian_13_disk():
    conf = _ini(OS / "image/mkosi.conf")
    assert conf["Distribution"]["Distribution"] == "debian"
    assert conf["Distribution"]["Release"] == "trixie"
    assert conf["Output"]["Format"] == "disk"
    assert conf["Content"]["Bootable"] == "yes"
    assert conf["Content"]["Bootloader"] == "systemd-boot"
    x86 = _ini(OS / "image/mkosi.conf.d/10-x86-64.conf")
    assert x86["Match"]["Architecture"] == "x86-64"
    assert "linux-image-amd64" in x86["Content"]["Packages"].split()
    root = _ini(OS / "image/mkosi.repart/10-root.conf")["Partition"]
    assert root["Type"] == "root" and root["GrowFileSystem"] == "yes"
    grow = _ini(OS / "image/mkosi.extra/usr/lib/repart.d/50-bashos-root.conf")["Partition"]
    assert grow["Type"] == "root" and "SizeMaxBytes" not in grow
    post = (OS / "image/mkosi.postinst.chroot").read_text()
    assert "/opt/bashos/os/install.sh --image" in post
    assert os.access(OS / "image/mkosi.postinst.chroot", os.X_OK)


def test_the_example_seed_only_uses_keys_provision_reads():
    keys = re.search(r'SEED_KEYS="([^"]+)"', (OS / "bin/bashos-provision").read_text()).group(1).split()
    for line in (OS / "image/seed.example/seed.env").read_text().splitlines():
        if m := re.match(r"([A-Z_]+)=", line):
            assert m.group(1) in keys, m.group(1)


def test_every_os_script_is_executable():
    for script in [*OS.glob("*.sh"), *(OS / "bin").iterdir(), OS / "image/build.sh",
                   OS / "image/test/boot-smoke.sh"]:
        if script.name != "lib.sh":
            assert os.access(script, os.X_OK), script


@needs_bash
def test_bin_bashos_reaches_the_os_layer_through_a_symlink(tmp_path, env):
    """The layer links bin/bashos onto /usr/local/bin: the launcher must find its tree."""
    link = tmp_path / "bashos"
    link.symlink_to(REPO / "bin/bashos")
    p = subprocess.run([str(link), "os", "help"], env=env, capture_output=True, text=True, check=False)
    assert p.returncode == 0, p.stderr
    assert "usage: bashos os" in p.stdout


@needs_bash
def test_os_dispatch_refuses_unknown_commands(env):
    p = run(str(OS / "os.sh"), "nope", env=env, check=False)
    assert p.returncode == 2 and "usage: bashos os" in p.stderr


@needs_bash
def test_settings_load_without_a_home(env):
    """A system service (bashos-provision) runs with no $HOME: loading settings must not trip set -u."""
    e = {k: v for k, v in env.items() if k not in ("HOME", "BASHOS_HUB_DIR")}
    p = run("-c", f'set -u; source "{OS}/lib.sh"; os_conf_load; printf %s "$BASHOS_HUB_DIR"', env=e)
    assert p.stdout == "~/dev/bamr87"
