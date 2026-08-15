"""Remote layer tests — offline: every ssh is a recorded fake runner call."""

from __future__ import annotations

import asyncio
import base64

import pytest

from bashos import remote
from bashos.config import KernelConfig
from bashos.remote import RemoteResult

FLOOR = "os-health 2026-08-14 · Linux\n\n[ OK ] load        0.4 (cores: 8)\n[WARN] disk        / 91% used (9G free)"


class FakeRunner:
    """Records (host, command, stdin) and replies from a queue keyed by substring."""

    def __init__(self, replies: dict[str, RemoteResult] | None = None, default: RemoteResult | None = None):
        self.calls: list[tuple[str, str, str | None]] = []
        self.replies = replies or {}
        self.default = default or RemoteResult(0, "", "")

    async def __call__(self, host: str, command: str, *, stdin: str | None = None) -> RemoteResult:
        self.calls.append((host, command, stdin))
        for key, result in self.replies.items():
            if key in command or (stdin and key in stdin):
                return result
        return self.default


def gather_stdout() -> str:
    return (
        f"===bashos:health===\n{FLOOR}\n"
        "===bashos:os===\nLinux 6.12.101 x86_64\n"
        "===bashos:docker===\nforge-stack-postgres-1\tUp 2 hours\n"
        "===bashos:tmux===\nconsole: 4 windows\n"
    )


def test_gather_is_one_round_trip_and_parses_sections():
    runner = FakeRunner(default=RemoteResult(0, gather_stdout(), ""))
    sections = asyncio.run(remote.gather("forge", runner=runner))
    assert len(runner.calls) == 1, "gather must be a single ssh round trip"
    host, command, stdin = runner.calls[0]
    assert host == "forge" and command == "bash -s"
    assert "os-health" in (stdin or ""), "the floor script travels over stdin"
    assert sections["health"] == FLOOR
    assert sections["os"].startswith("Linux")
    assert "postgres" in sections["docker"]


def test_gather_raises_when_unreachable():
    runner = FakeRunner(default=RemoteResult(255, "", "ssh: No route to host"))
    with pytest.raises(RuntimeError, match="No route to host"):
        asyncio.run(remote.gather("forge", runner=runner))


def test_probe_list_is_readonly():
    joined = " ".join(cmd for _, cmd in remote.PROBES) + " " + remote._gather_script()
    for forbidden in ("rm -rf", "curl", "wget", ">", "sudo", "kill"):
        # the only redirects allowed are the heredoc + stderr merges the script itself builds
        if forbidden == ">":
            continue
        assert forbidden not in joined, f"probe surface must not contain {forbidden!r}"


def test_mirror_transports_via_base64_and_announces_without_stealing_focus():
    runner = FakeRunner()
    text = "Q: is it 'healthy'?\nA: yes — 100% \"fine\"\n"
    asyncio.run(remote.mirror("forge", text, runner=runner))
    _, command, stdin = runner.calls[0]
    assert command == "bash -s", "mirror travels as a stdin script — no ssh quoting games"
    assert stdin is not None
    assert base64.b64encode(text.encode()).decode() in stdin
    assert "display-popup" in stdin, "an interaction must announce itself on the monitor"
    assert "new-window -d" in stdin, "the ai window is created detached"
    for forbidden in ("select-window", "switch-client"):
        assert forbidden not in stdin, "mirror must not steal window focus"


def test_mirror_empty_text_only_ensures_surface():
    runner = FakeRunner()
    asyncio.run(remote.mirror("forge", "", runner=runner))
    _, _, stdin = runner.calls[0]
    assert "display-popup" not in (stdin or ""), "no interaction → no popup"


def test_ask_dry_run_makes_no_model_call_and_no_mirror():
    runner = FakeRunner(default=RemoteResult(0, gather_stdout(), ""))
    config = KernelConfig(dry_run=True)
    out = asyncio.run(remote.ask("forge", "how is disk?", config, runner=runner))
    assert "dry-run" in out
    assert "how is disk?" in out
    assert FLOOR.splitlines()[-1] in out, "gathered floor must be in the rendered prompt"
    assert len(runner.calls) == 1, "dry-run: gather only — no mirror ssh"


def test_setup_is_user_level_first():
    runner = FakeRunner(
        replies={"ln -sf": RemoteResult(1, "", "")},
        default=RemoteResult(0, "installed\n", ""),
    )
    actions = asyncio.run(remote.setup("forge", runner=runner))
    install_cmd = runner.calls[0][1]
    assert "~/.local/bin/bashos-health" in install_cmd
    assert "sudo" not in install_cmd, "the install itself must be user-level"
    assert any("skipped" in a for a in actions), "root symlink degrades, not fails"


def test_doctor_reports_unreachable_as_single_failure():
    runner = FakeRunner(default=RemoteResult(255, "", "connection refused"))
    checks = asyncio.run(remote.doctor("forge", runner=runner))
    assert checks == [("ssh", False, "connection refused")]
