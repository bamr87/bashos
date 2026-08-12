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
