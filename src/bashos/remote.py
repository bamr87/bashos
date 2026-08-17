"""Remote dev-box integration — ssh probe surface + physical-monitor mirror.

The forge pattern (docs/FORGE.md) taken to its remote conclusion: bashOS runs
wherever the Claude Code OAuth lives; a dev box on the LAN is a *probe
surface* and a *display*. This module — not the model — performs every ssh:
a fixed, read-only probe script gathered in one round trip, the portable
health floor (bin/os-health) streamed over stdin, and the finished
interaction mirrored into an `ai` window of the box's shared tmux console,
where the physical monitor shows it live.

The loop policies are untouched: no loop gains ssh or any network tool. The
model only ever sees gathered text and answers over it (`remote ask`), so
deny-by-default holds end to end.

Hosts are ssh aliases (~/.ssh/config) — bashOS keeps no host registry.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import getpass
import platform
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
MARKER = "===bashos:{name}==="
AI_LOG = "~/monitoring/ai/session.log"
AI_WINDOW = "ai"
CONSOLE_SESSION = "console"

# Read-only probes gathered on the box, in one round trip. Fixed by code —
# the model cannot add to or alter this list.
PROBES: list[tuple[str, str]] = [
    ("os", "uname -srm"),
    ("uptime", "uptime"),
    ("disk", "df -Ph /"),
    ("memory", "free -m 2>/dev/null || vm_stat"),
    ("load", "cat /proc/loadavg 2>/dev/null || sysctl -n vm.loadavg"),
    ("docker", "docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null"),
    ("tmux", "tmux ls 2>/dev/null"),
    ("failed-units", "systemctl --failed --no-legend --no-pager 2>/dev/null"),
]


@dataclass(frozen=True)
class RemoteResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


Runner = Callable[..., Awaitable[RemoteResult]]


async def ssh_exec(host: str, command: str, *, stdin: str | None = None) -> RemoteResult:
    """Run one command on `host` over ssh. NOTMUX=1 keeps console-mirror
    shells from swallowing the session on boxes that run the mirror hook."""
    proc = await asyncio.create_subprocess_exec(
        "ssh", *SSH_OPTS, host, f"export NOTMUX=1; {command}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(stdin.encode() if stdin is not None else None)
    return RemoteResult(proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace"))


def health_script() -> str:
    """The portable verdict floor, read fresh from this checkout."""
    path = Path(__file__).resolve().parents[2] / "bin" / "os-health"
    return path.read_text(encoding="utf-8")


def _gather_script() -> str:
    """One shell script: health floor first, then every probe, marker-delimited."""
    lines = [
        "cat > /tmp/.bashos-health.$$ <<'BASHOS_HEALTH_EOF'",
        health_script().rstrip(),
        "BASHOS_HEALTH_EOF",
        f"echo '{MARKER.format(name='health')}'",
        "bash /tmp/.bashos-health.$$ 2>&1 || true",
        "rm -f /tmp/.bashos-health.$$",
    ]
    for name, cmd in PROBES:
        lines.append(f"echo '{MARKER.format(name=name)}'")
        lines.append(f"{cmd} 2>&1 || true")
    return "\n".join(lines) + "\n"


def _parse_sections(stdout: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    pattern = re.compile(r"^===bashos:([a-z-]+)===$")
    for line in stdout.splitlines():
        if match := pattern.match(line.strip()):
            current = match.group(1)
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return {k: v.strip() for k, v in sections.items()}


async def gather(host: str, *, runner: Runner = ssh_exec) -> dict[str, str]:
    """Health floor + fixed probes from `host`, one ssh round trip."""
    result = await runner(host, "bash -s", stdin=_gather_script())
    if not result.ok and not result.stdout:
        raise RuntimeError(f"ssh to {host} failed: {result.stderr.strip() or 'unreachable'}")
    return _parse_sections(result.stdout)


def context_text(host: str, sections: dict[str, str]) -> str:
    """Render gathered sections into the context block the model reasons over."""
    parts = [f"[remote host: {host} — every reading below was probed by bashOS over ssh]"]
    for name, body in sections.items():
        if body:
            parts.append(f"--- {name} ---\n{body}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# the monitor mirror


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


AI_LATEST = "~/monitoring/ai/latest.txt"
POPUP_SECONDS = 45

_ENSURE_SURFACE = f"""\
mkdir -p ~/monitoring/ai
touch {AI_LOG}
if tmux has-session -t {CONSOLE_SESSION} 2>/dev/null; then
  tmux list-windows -t {CONSOLE_SESSION} -F '#W' | grep -qx {AI_WINDOW} || \
    tmux new-window -d -t {CONSOLE_SESSION} -n {AI_WINDOW} 'tail -n 300 -F {AI_LOG}'
fi
"""


async def ensure_surface(host: str, *, runner: Runner = ssh_exec) -> bool:
    """AI log + console `ai` window exist; no content, no focus change."""
    return (await runner(host, "bash -s", stdin=_ENSURE_SURFACE)).ok


async def mirror(host: str, text: str, *, runner: Runner = ssh_exec) -> bool:
    """Display `text` on the box: append to the AI session log (the `ai`
    pane/window tail picks it up) AND announce it — a transient popup overlay
    on whichever client is on the console (the physical monitor), dismissed by
    any key or after {POPUP_SECONDS}s. Windows are never switched and focus is
    never stolen; without a tmux console the log still lands."""
    if not text:
        return await ensure_surface(host, runner=runner)
    payload = _b64(text if text.endswith("\n") else text + "\n")
    script = f"""\
{_ENSURE_SURFACE}
printf '%s' '{payload}' | base64 -d > {AI_LATEST}
cat {AI_LATEST} >> {AI_LOG}
if tmux has-session -t {CONSOLE_SESSION} 2>/dev/null; then
  client=$(tmux list-clients -t {CONSOLE_SESSION} -F '#{{client_tty}}' 2>/dev/null | head -1)
  if [ -n "$client" ]; then
    # -E blocks until the popup closes; background it so the ssh returns now
    ( tmux display-popup -c "$client" -w 96% -h 75% -T ' bashos ' -E \
      'bash -c "cat {AI_LATEST}; printf \\"\\n  [any key or {POPUP_SECONDS}s to dismiss]\\"; read -t {POPUP_SECONDS} -n 1 || true"' \
      >/dev/null 2>&1 & )
  fi
fi
"""
    return (await runner(host, "bash -s", stdin=script)).ok


def interaction_entry(question: str, answer: str) -> str:
    """One mirrored interaction, formatted for a portrait monitor."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    origin = f"{getpass.getuser()}@{platform.node().split('.')[0]}"
    bar = "─" * 72
    return f"{bar}\nbashos · {stamp} · from {origin}\nQ: {question}\n\n{answer}\n"


# ---------------------------------------------------------------------------
# doctor / setup


ASK_SYSTEM = """\
You are answering about a REMOTE dev box. Everything you know about it is in
the [remote host] context block — deterministic probes bashOS just ran over
ssh, including the [ OK ]/[WARN]/[CRIT] health floor. Never contradict a
verdict line; never state a number that is not in the context. Structure:
**VERDICT** (the floor lines, verbatim) · **CAUSES** (one line per non-OK,
with its number) · **ACTIONS** (commands for the box, only if needed).
Your answer will be displayed on the box's physical monitor — keep lines
under 100 characters."""


async def ask(
    host: str,
    question: str,
    config,
    *,
    runner: Runner = ssh_exec,
    do_mirror: bool = True,
) -> str:
    """The AI path: probe the box (code), reason locally (Claude Code OAuth),
    mirror the finished interaction onto the box's monitor."""
    question = question.strip() or "How healthy is this machine? Anything needing attention?"
    sections = await gather(host, runner=runner)
    prompt = f"{question}\n\n{context_text(host, sections)}"
    if config.dry_run:
        return f"[dry-run] remote ask → {host} (no model call, no mirror)\n\n--- rendered prompt ---\n\n{prompt}"

    from langchain_core.messages import HumanMessage, SystemMessage

    from .kernel.context import system_prompt
    from .runtime.llm import get_chat_model, message_text

    llm = get_chat_model(config)
    reply = await llm.ainvoke(
        [SystemMessage(content=system_prompt(ASK_SYSTEM)), HumanMessage(content=prompt)]
    )
    answer = message_text(reply).strip()
    if do_mirror:
        await mirror(host, interaction_entry(question, answer), runner=runner)
    return answer


async def doctor(host: str, *, runner: Runner = ssh_exec) -> list[tuple[str, bool, str]]:
    """Named connection/integration checks. Returns (check, ok, detail)."""
    checks: list[tuple[str, bool, str]] = []
    hello = await runner(host, "hostname && uname -s")
    if not hello.ok:
        return [("ssh", False, hello.stderr.strip() or "unreachable")]
    hostname, *rest = hello.stdout.split()
    checks.append(("ssh", True, f"{hostname} ({rest[0] if rest else '?'})"))

    probes = {
        "tmux-console": f"tmux has-session -t {CONSOLE_SESSION} 2>/dev/null && echo yes",
        "monitor-attached": f"tmux list-clients -t {CONSOLE_SESSION} 2>/dev/null | head -1",
        "ai-window": f"tmux list-windows -t {CONSOLE_SESSION} -F '#W' 2>/dev/null | grep -x {AI_WINDOW}",
        "health-floor": "command -v bashos-health || command -v forge-health",
        "docker": "docker ps -q 2>/dev/null | wc -l",
        "sudo-n": "sudo -n true 2>/dev/null && echo yes",
    }
    results = await asyncio.gather(*(runner(host, cmd) for cmd in probes.values()))
    for (name, _), result in zip(probes.items(), results, strict=True):
        detail = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        checks.append((name, result.ok and bool(detail), detail or "not found"))
    return checks


async def setup(host: str, *, runner: Runner = ssh_exec) -> list[str]:
    """User-level install of the monitoring kit on `host`:
    ~/.local/bin/bashos-health (the current floor), the AI log, and the
    console `ai` window. Root-level niceties (a /usr/local/bin symlink) are
    attempted with `sudo -n` and skipped silently without it."""
    actions: list[str] = []
    payload = _b64(health_script())
    install = (
        f"mkdir -p ~/.local/bin ~/monitoring/ai && "
        f"printf '%s' '{payload}' | base64 -d > ~/.local/bin/bashos-health && "
        f"chmod +x ~/.local/bin/bashos-health && "
        f"touch {AI_LOG} && echo installed"
    )
    result = await runner(host, install)
    if not result.ok:
        raise RuntimeError(f"setup on {host} failed: {result.stderr.strip()}")
    actions.append("~/.local/bin/bashos-health installed (current floor)")

    if (await runner(host, "sudo -n ln -sf ~/.local/bin/bashos-health /usr/local/bin/bashos-health 2>/dev/null && echo yes")).stdout.strip():
        actions.append("/usr/local/bin/bashos-health symlinked (sudo -n available)")
    else:
        actions.append("/usr/local/bin symlink skipped (no passwordless sudo)")

    if await ensure_surface(host, runner=runner):
        actions.append(f"AI log + console '{AI_WINDOW}' window ready ({AI_LOG})")
    return actions
