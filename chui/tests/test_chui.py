"""chui — the macOS terminal environment. Offline tests: every script runs against a throwaway
$HOME, with `defaults` and `osascript` shimmed so nothing reaches the real machine.

Stdlib + pytest only, so a bare macOS runner (bash 3.2, BSD tools) can run them too.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHUI = Path(__file__).resolve().parents[1]
REPO = CHUI.parent

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="shell environment")

# Run under the first bash on PATH, and also under macOS's stock /bin/bash 3.2 when present.
BASHES = ["bash"] + (["/bin/bash"] if sys.platform == "darwin" else [])
# An offline install: no brew, no snapshot, and no Apple Terminal / VS Code preferences.
QUIET = ("--skip-brew", "--no-backup", "--no-terminal")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture
def env(home: Path, tmp_path: Path) -> dict[str, str]:
    """A $HOME sandbox. macOS preference tools are no-op shims: they are not HOME-scoped."""
    shims = tmp_path / "shims"
    shims.mkdir()
    for tool in ("defaults", "osascript"):
        shim = shims / tool
        shim.write_text("#!/bin/sh\nexit 0\n")
        shim.chmod(0o755)
    e = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CHUI_", "ZSH", "GIT_")) and k not in ("ZELLIJ", "BAT_THEME")
    }
    e.update(
        HOME=str(home),
        PATH=f"{shims}{os.pathsep}{os.environ['PATH']}",
        CHUI_BACKUP_ROOT=str(tmp_path / "backups"),
        GIT_CONFIG_NOSYSTEM="1",
        NO_COLOR="1",
        COLUMNS="80",
    )
    e.pop("CI", None)
    return e


def sh(*args: str, env: dict[str, str], bash: str = "bash", **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        [bash, *args], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, **kw
    )


def fake_oh_my_zsh(home: Path) -> None:
    """Pre-create oh-my-zsh and its plugins so install.sh needs no network."""
    custom = home / ".oh-my-zsh" / "custom"
    for line in (CHUI / "custom" / "plugins.txt").read_text().splitlines():
        if line.strip():
            (custom / line.split()[1] / ".git").mkdir(parents=True)


# ---------------------------------------------------------------- one CLI


def _usage_commands() -> set[str]:
    out = subprocess.run(
        ["bash", str(CHUI / "tui.sh"), "help"], capture_output=True, text=True, check=True
    ).stdout
    return {m.group(1) for m in re.finditer(r"^chui (\w+)", out, re.M)}


def _dispatch_commands() -> set[str]:
    src = (CHUI / "tui.sh").read_text().split('cmd=${1:-menu}', 1)[1]
    labels = re.findall(r"^  ([\w|-]+)\)", src, re.M)
    return {name for label in labels for name in label.split("|") if not name.startswith("-")}


def _completion_commands() -> set[str]:
    src = (CHUI / "config" / "completions.zsh").read_text()
    block = src.split("_chui()", 1)[1].split("compdef", 1)[0]
    return set(re.findall(r"^\s+'(\w+):", block, re.M))


def test_every_documented_command_dispatches():
    """`chui check|backup|restore|keys|…` used to exist only in the zsh function, so they failed
    from bash, scripts and make. Help, dispatch and completion must now agree."""
    usage, dispatch, completion = _usage_commands(), _dispatch_commands(), _completion_commands()
    assert usage <= dispatch, f"documented but not dispatched: {usage - dispatch}"
    assert completion <= dispatch, f"completed but not dispatched: {completion - dispatch}"
    assert usage - {"help"} <= completion, f"not tab-completed: {usage - completion}"


@pytest.mark.parametrize("bash", BASHES)
def test_menu_without_a_tty_prints_help(env, bash):
    r = sh(str(CHUI / "tui.sh"), env=env, bash=bash)
    assert r.returncode == 0
    assert "chui install" in r.stdout


def test_unknown_command_fails(env):
    r = sh(str(CHUI / "tui.sh"), "nope", env=env)
    assert r.returncode == 2
    assert "unknown: nope" in r.stderr


def test_bashos_launcher_reaches_chui_without_a_venv(env):
    r = sh(str(REPO / "bin" / "bashos"), "chui", "help", env=env)
    assert r.returncode == 0, r.stderr
    assert "first run" not in r.stderr  # never bootstraps the Python venv for chui
    assert "chui install" in r.stdout


def test_zsh_wrapper_delegates_to_tui():
    src = (CHUI / "config" / "functions.zsh").read_text()
    body = src.split("chui() {", 1)[1]
    assert '"${CHUI_ROOT}/tui.sh" "$@"' in body
    assert "check.sh" not in body  # no second copy of the dispatch table


# ---------------------------------------------------------------- install / restore


@pytest.mark.parametrize("bash", BASHES)
def test_dry_run_changes_nothing(env, home, bash):
    (home / ".zshrc").write_text("# mine\n")
    r = sh(str(CHUI / "install.sh"), "--dry-run", "--skip-brew", env=env, bash=bash)
    assert r.returncode == 0, r.stderr
    assert f"plan: move {home}/.zshrc -> {home}/.zshrc.chui-" in r.stdout
    assert f"plan: link {home}/.local/bin/chui -> {CHUI}/tui.sh" in r.stdout
    assert sorted(p.name for p in home.iterdir()) == [".zshrc"]
    assert (home / ".zshrc").read_text() == "# mine\n"


@pytest.mark.parametrize("bash", BASHES)
def test_install_keeps_real_files_and_restore_rolls_back(env, home, bash, tmp_path):
    fake_oh_my_zsh(home)
    (home / ".zshrc").write_text("# mine\n")

    assert sh(str(CHUI / "backup.sh"), env=env, bash=bash).returncode == 0
    r = sh(str(CHUI / "install.sh"), *QUIET, env=env, bash=bash)
    assert r.returncode == 0, r.stdout + r.stderr

    zshrc = home / ".zshrc"
    assert zshrc.is_symlink() and zshrc.resolve() == (CHUI / "config" / "zshrc").resolve()
    # --no-backup used to `rm -rf` a real dotfile; now it is kept beside the link.
    kept = list(home.glob(".zshrc.chui-*"))
    assert len(kept) == 1 and kept[0].read_text() == "# mine\n"
    assert (home / ".local" / "bin" / "chui").resolve() == (CHUI / "tui.sh").resolve()

    # Re-running is a no-op.
    again = sh(str(CHUI / "install.sh"), *QUIET, env=env, bash=bash)
    assert "relink" not in again.stdout and "moved" not in again.stdout

    check = sh(str(CHUI / "check.sh"), env=env, bash=bash)
    assert "[ok] ~/.zshrc" in check.stdout
    assert "[ok] ~/.local/bin/chui" in check.stdout
    assert "links another checkout" not in check.stdout

    r = sh(str(CHUI / "uninstall.sh"), env=env, bash=bash)
    assert r.returncode == 0, r.stderr
    assert not zshrc.is_symlink() and zshrc.read_text() == "# mine\n"
    # Links the snapshot had no file for are removed, not left dangling.
    assert not (home / ".local" / "bin" / "chui").exists()
    assert not (home / ".p10k.zsh").is_symlink()


def test_check_flags_links_into_another_checkout(env, home, tmp_path):
    """Migrating from the standalone bamr87/chui clone: links still work, but track the old tree."""
    old = tmp_path / "github" / "chui" / "config"
    old.mkdir(parents=True)
    (old / "zshrc").write_text("")
    (home / ".zshrc").symlink_to(old / "zshrc")
    r = sh(str(CHUI / "check.sh"), env=env)
    assert r.returncode == 1
    assert "~/.zshrc links another checkout" in r.stdout


def test_install_relinks_from_another_checkout(env, home, tmp_path):
    fake_oh_my_zsh(home)
    old = tmp_path / "github" / "chui" / "config"
    old.mkdir(parents=True)
    (old / "zshrc").write_text("")
    (home / ".zshrc").symlink_to(old / "zshrc")
    r = sh(str(CHUI / "install.sh"), *QUIET, env=env)
    assert r.returncode == 0, r.stderr
    assert f"(was {old / 'zshrc'})" in r.stdout
    assert (home / ".zshrc").resolve() == (CHUI / "config" / "zshrc").resolve()


# ---------------------------------------------------------------- local.zsh


@pytest.mark.parametrize("bash", BASHES)
def test_settings_keep_foreign_lines_in_local_zsh(env, home, bash):
    """`chui configure` used to rewrite all of local.zsh, deleting lines other tools put there."""
    local = home / ".config" / "chui" / "local.zsh"
    local.parent.mkdir(parents=True)
    local.write_text(
        "# managed by chui TUI — not in git\n"
        "export CHUI_ICONS=never\n"
        'source "$HOME/bamr87/tools/devtools-env.sh"\n'
        "export PYTHONPATH=/x\n"
    )
    script = (
        f'source "{CHUI}/lib.sh"; '
        'CHUI_ICONS=$(chui_local_get CHUI_ICONS); BAT_THEME="Catppuccin Mocha"; '
        "chui_local_write; chui_local_write; "
        'printf "%s|%s" "$CHUI_ICONS" "$(chui_local_get BAT_THEME)"'
    )
    r = sh("-c", script, env=env, bash=bash)
    assert r.returncode == 0, r.stderr
    assert r.stdout == "never|Catppuccin Mocha"
    text = local.read_text()
    assert 'source "$HOME/bamr87/tools/devtools-env.sh"' in text
    assert "export PYTHONPATH=/x" in text
    assert "# managed by chui TUI" not in text
    assert text.count(">>> chui managed") == 1
    assert text.count("export CHUI_ICONS=") == 1


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_local_zsh_block_is_valid_zsh(env, home):
    script = f'source "{CHUI}/lib.sh"; BAT_THEME="Catppuccin Mocha"; chui_local_write'
    assert sh("-c", script, env=env).returncode == 0
    local = home / ".config" / "chui" / "local.zsh"
    r = subprocess.run(
        ["zsh", "-fc", f'source "{local}"; print -r -- "$BAT_THEME"'],
        capture_output=True,
        text=True,
    )
    assert r.stdout.strip() == "Catppuccin Mocha"


# ---------------------------------------------------------------- configs


def _after_keybinds(text: str) -> str:
    start = text.index("keybinds")
    depth, i = 0, text.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            return text[i:].strip()


def test_zellij_key_modes_share_everything_but_keys():
    classic = (CHUI / "config" / "zellij" / "config.kdl").read_text()
    unlock = (CHUI / "config" / "zellij" / "config.unlock-first.kdl").read_text()
    assert _after_keybinds(classic) == _after_keybinds(unlock)
    assert 'default_mode "locked"' in unlock
    assert '"Ctrl q"' not in unlock  # keys v1: no ctrl chord is claimed while locked


@pytest.mark.parametrize("mode,file", [("", "config.kdl"), ("unlock-first", "config.unlock-first.kdl")])
def test_zellij_mode_selects_config(env, home, mode, file):
    env = {**env, "CHUI_ZELLIJ_KEYS": mode}
    r = sh("-c", f'source "{CHUI}/lib.sh"; chui_zellij_config', env=env)
    assert r.stdout == file


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_zsh_files_parse():
    files = [CHUI / "config" / "zshrc", *sorted((CHUI / "config").glob("*.zsh"))]
    files.append(CHUI / "custom" / "forge.zsh")
    for f in files:
        r = subprocess.run(["zsh", "-n", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{f.name}: {r.stderr}"


def _vscode_keys():
    spec = importlib.util.spec_from_file_location(
        "vscode_keys", CHUI / "config" / "terminal" / "vscode-keys.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vscode_merge_is_idempotent_and_keeps_user_bindings(tmp_path):
    import json

    mod = _vscode_keys()
    bindings = json.loads((CHUI / "config" / "vscode" / "keybindings.json").read_text())
    dest = tmp_path / "keybindings.json"
    mine = {"key": "cmd+k", "command": "workbench.action.terminal.clear"}
    dest.write_text(json.dumps([mine, bindings[0]]))
    mod.merge(dest, bindings)
    mod.merge(dest, bindings)
    result = json.loads(dest.read_text())
    assert result[0] == mine
    assert len(result) == 1 + len(bindings)
    assert {(b["key"], b["when"]) for b in bindings} == mod.CHUI_KEYS


def test_home_map_tags_strays(env, home):
    (home / "Documents").mkdir()
    (home / "loose-notes.txt").write_text("x")
    r = sh(str(CHUI / "config" / "home.sh"), "map", "stray", env=env)
    assert r.returncode == 0, r.stderr
    plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
    assert re.search(r"^loose-notes\.txt .* stray$", plain, re.M)
    assert not re.search(r"^Documents/", plain, re.M)  # a macOS folder is never a stray
