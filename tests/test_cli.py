"""CLI wiring smoke tests — guard the terminal entry points offline."""

from typer.testing import CliRunner

from bashos.shell.cli import app

runner = CliRunner()


def test_help_runs():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "bashOS" in result.output


def test_list_renders_registry():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "/sh" in result.output
    assert "refine" in result.output  # loop column present


def test_run_dry_run_needs_no_auth():
    result = runner.invoke(app, ["run", "-n", "/sh", "find", "big", "files"])
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_run_help_mentions_exec():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--exec" in result.output


def test_exec_disabled_in_dry_run():
    result = runner.invoke(app, ["run", "-n", "-x", "/sh", "find", "big", "files"])
    assert result.exit_code == 1
    assert "disabled in dry-run" in result.output


def test_bare_invocation_without_a_tty_prints_desktop_guidance():
    """CliRunner is never a TTY, so bare `bashos` must guide, not hang."""
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "interactive terminal" in result.output


def test_desktop_command_is_listed_in_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "desktop" in result.output


def test_repl_alias_prints_deprecation_and_launches_the_desktop(monkeypatch):
    launched = {"count": 0}
    import bashos.desktop as desktop_pkg

    monkeypatch.setattr(desktop_pkg, "run_desktop", lambda model=None: launched.__setitem__("count", launched["count"] + 1))
    result = runner.invoke(app, ["repl"])
    assert result.exit_code == 0
    assert "deprecated" in result.output
    assert launched["count"] == 1


def test_bashos_desktop_env_zero_disables_autolaunch(monkeypatch):
    monkeypatch.setenv("BASHOS_DESKTOP", "0")
    result = runner.invoke(app, [])
    assert result.exit_code == 2
