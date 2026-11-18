"""Does an engine still enforce bashOS's policy? Asked of the engine, not of our file.

OpenCode is the dependency everything runs on, and bashOS tracks its latest
release. A release that read our config differently could widen what a loop
may touch without a single line of bashOS changing, so a new engine is trusted
only after this check passes.

OpenCode resolves `opencode.jsonc` into an ordered permission rule list per
agent (`GET /agent`; on OpenCode 2, `GET /api/agent`). This module judges those
*resolved* rules with OpenCode's own semantics (`rules.py`) against what
`policy.py` promises:

  readonly agent   every denied tool refused; a tool policy.py never named
                   refused; bash refuses every way out we know of; every
                   allowlisted probe and read still runs
  sealed agent     no tool at all

OpenCode 2 can also evaluate a permission on request, so there `ask_engine`
puts the same samples to the engine itself and requires its own answers to
agree: a mirror of the semantics is a model of the engine, the engine's answer
is the engine. And `session_routes` drives, without running a turn, the 2.x
routes a turn needs (two of them experimental), so a release that moved one
fails verify instead of every later turn.

Callers: `bashos opencode verify`, the OS layer before it promotes a new
OpenCode release (os/install/engine.sh), the engine canary workflow, and the
engine's start on any OpenCode 2 binary (engine.py), which runs `check` before
a loop may use it.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from . import policy, project, rules
from .client import OpencodeError


@dataclass(frozen=True)
class Finding:
    name: str
    ok: bool
    detail: str


# A representative input for each tool the readonly agent must refuse.
DENIED_SAMPLES = {
    "edit": "src/bashos/__init__.py",
    "write": "src/bashos/new.py",
    "apply_patch": "src/bashos/__init__.py",
    "webfetch": "https://example.com",
    "websearch": "bashos",
    "execute": "await fetch('https://example.com')",
    "task": "general",
    "external_directory": "/etc/*",
    "question": "*",
}

# A tool no release has shipped yet: the readonly agent must refuse what policy.py never named.
UNKNOWN_TOOL = "bashos-contract-unnamed-tool"

# Commands the readonly agent's bash must refuse: mutation, the network, a shell, privilege,
# and the escapes that once got through (policy.BASH_ESCAPES).
BASH_ESCAPES = (
    "rm -rf /",
    "curl https://example.com",
    "wget https://example.com",
    "ssh forge",
    "sh -c id",
    "bash -c id",
    "python3 -c 'print(1)'",
    "sudo id",
    "git push",
    "dd if=/dev/zero of=/tmp/x",
    "env",
    "env curl https://example.com",
    "tmux display-message -p '#(curl https://example.com)'",
    "git log --output=/tmp/x",
)

READ_SAMPLE = "src/bashos/__init__.py"


def _agent(agents: Iterable[Mapping[str, object]], name: str) -> Mapping[str, object] | None:
    # OpenCode 1 names an agent by `name`; OpenCode 2 by `id` (its `name` is a display label)
    return next((a for a in agents if a.get("id") == name or a.get("name") == name), None)


def _allowed(found: list[str]) -> str:
    return "allowed: " + ", ".join(found)


def samples(major: int = 1) -> dict[str, list[tuple[str, str, bool]]]:
    """Every (action, input, must-be-allowed) the contract judges, per bashOS agent,
    named the way an engine of `major` names its tools."""
    def a(tool: str) -> str:
        return rules.action(tool, major)

    readonly = [(a(t), v, False) for t, v in DENIED_SAMPLES.items()]
    readonly.append((UNKNOWN_TOOL, "*", False))
    readonly += [(a("bash"), c, False) for c in BASH_ESCAPES]
    readonly += [(a("bash"), cmd, True) for p in policy.PROBE_COMMANDS for cmd in (p, f"{p} -x")]
    readonly += [(a(t), READ_SAMPLE, True) for t in policy.READ_TOOLS]
    sealed = [(a(t), DENIED_SAMPLES.get(t, "anything"), False)
              for t in (*policy.ALL_TOOLS, "external_directory", UNKNOWN_TOOL)]
    return {project.READONLY_AGENT: readonly, project.SEALED_AGENT: sealed}


def check(agents: list[Mapping[str, object]], major: int = 1) -> list[Finding]:
    """Judge an engine's resolved agents (`GET /agent`) against policy.py."""
    findings: list[Finding] = []
    readonly = _agent(agents, project.READONLY_AGENT)
    sealed = _agent(agents, project.SEALED_AGENT)
    missing = [n for n, a in ((project.READONLY_AGENT, readonly), (project.SEALED_AGENT, sealed)) if a is None]
    findings.append(Finding("agents", not missing, "missing: " + ", ".join(missing) if missing else
                            f"{project.READONLY_AGENT}, {project.SEALED_AGENT}"))

    def act(tool: str) -> str:
        return rules.action(tool, major)

    if readonly is not None:
        ro = rules.from_agent(readonly)
        # No rules at all means the engine reports them in a shape this module does not know:
        # nothing below could be judged, so that is a failure, not a pass.
        findings.append(Finding("readonly: rules", bool(ro), f"{len(ro)} resolved" if ro else
                                "none in a known shape (GET /agent → permission)"))
        if ro:
            open_tools = [t for t, v in DENIED_SAMPLES.items() if rules.evaluate(ro, act(t), v) == "allow"]
            findings.append(Finding("readonly: denied tools", not open_tools,
                                    _allowed(open_tools) if open_tools else ", ".join(DENIED_SAMPLES)))
            unnamed = rules.evaluate(ro, UNKNOWN_TOOL, "*")
            findings.append(Finding("readonly: tools deny-by-default", unnamed != "allow",
                                    f"a tool policy.py never named is {unnamed}"))
            leaks = [c for c in BASH_ESCAPES if rules.evaluate(ro, act("bash"), c) == "allow"]
            findings.append(Finding("readonly: bash deny-by-default", not leaks,
                                    _allowed(leaks) if leaks else f"{len(BASH_ESCAPES)} ways out refused"))
            blocked = [p for p in policy.PROBE_COMMANDS
                       if rules.evaluate(ro, act("bash"), p) != "allow"
                       or rules.evaluate(ro, act("bash"), f"{p} -x") != "allow"]
            findings.append(Finding("readonly: probes run", not blocked,
                                    "refused: " + ", ".join(blocked) if blocked else
                                    f"{len(policy.PROBE_COMMANDS)} probes"))
            unread = [t for t in policy.READ_TOOLS if rules.evaluate(ro, act(t), READ_SAMPLE) != "allow"]
            findings.append(Finding("readonly: reads", not unread,
                                    "refused: " + ", ".join(unread) if unread else ", ".join(policy.READ_TOOLS)))

    if sealed is not None:
        se = rules.from_agent(sealed)
        open_tools = [t for t in (*policy.ALL_TOOLS, "external_directory", UNKNOWN_TOOL)
                      if rules.evaluate(se, act(t), DENIED_SAMPLES.get(t, "anything")) == "allow"]
        findings.append(Finding("sealed: no tools", bool(se) and not open_tools,
                                _allowed(open_tools) if open_tools else
                                ("no rules in a known shape" if not se else f"{len(policy.ALL_TOOLS)} tools refused")))
    return findings


async def ask_engine(client: Any) -> list[Finding]:
    """Put every sample to an OpenCode 2 engine's own permission evaluation.

    One throwaway session per bashOS agent; the engine answers allow, deny or ask, and a
    sample passes when the engine allows exactly what policy.py allows. An "ask" counts
    as not allowed (bashOS refuses every approval request), and the session that holds
    it is deleted. OpenCode 1 has no such route: there the mirrored `check` is the contract.
    """
    if getattr(client, "major", 1) < 2:
        return []
    findings: list[Finding] = []
    for agent, cases in samples(client.major).items():
        session = await client.create_session(title="bashos opencode verify", agent=agent)
        wrong: list[str] = []
        try:
            for action, value, allow in cases:
                effect = await client.evaluate_permission(session, agent=agent, action=action, resource=value)
                if (effect == "allow") != allow:
                    wrong.append(f"{action}({value})={effect}")
        finally:
            await client.delete_session(session)
        findings.append(Finding(f"{agent}: the engine's own answers", not wrong,
                                "disagree: " + ", ".join(wrong[:8]) if wrong else f"{len(cases)} samples agree"))
    return findings


# How long one route of `session_routes` may take on an idle throwaway session, in seconds.
ROUTE_TIMEOUT = 10.0
ROUTES_FINDING = "OpenCode 2 session routes"


async def session_routes(client: Any, model: str) -> list[Finding]:
    """Drive every OpenCode 2 route a turn uses besides the permission ones, without a turn.

    `check` and `ask_engine` prove the policy, not that bashOS can still run a turn: a release
    that moved one of these routes (two sit under 2.x's `/api/experimental`) would pass both,
    and every `act()` and `complete()` would then fail. So on one throwaway session this
    switches the agent and the model, puts and deletes the `bashos.system` instruction entry,
    waits on the idle session, reads its timeline, proves the prompt route is served with a
    body it must refuse, and reads the first frame of the event stream. No turn runs: verify
    passes no credential. OpenCode 1 takes the agent, model and system prompt on the prompt
    itself; there this returns nothing.
    """
    if getattr(client, "major", 1) < 2:
        return []
    session = await client.create_session(title="bashos opencode verify", agent=project.SEALED_AGENT)
    steps = {
        "agent": lambda: client.set_session_agent(session, project.READONLY_AGENT),
        "model": lambda: client.set_session_model(session, model),
        "system prompt put": lambda: client.set_session_system(session, "bashos opencode verify"),
        "system prompt delete": lambda: client.set_session_system(session, None),
        "wait": lambda: client.wait_idle(session),
        "messages": lambda: client.timeline(session),
        "prompt": lambda: client.probe_prompt(session),
        "events": lambda: _first_event(client),
    }
    failed: list[str] = []
    try:
        for name, step in steps.items():
            try:
                await asyncio.wait_for(step(), timeout=ROUTE_TIMEOUT)
            except (OpencodeError, TimeoutError) as exc:
                failed.append(f"{name} ({str(exc)[:160] or 'timed out'})")
    finally:
        await client.delete_session(session)
    return [Finding(ROUTES_FINDING, not failed,
                    "failed: " + "; ".join(failed) if failed else ", ".join(steps))]


async def _first_event(client: Any) -> None:
    """The event stream opens with a frame (`server.connected`); a moved route yields none."""
    async with contextlib.aclosing(client.events()) as stream:
        async for _ in stream:
            return
    raise OpencodeError("the event stream ended before its first frame")


async def resolved_agents(client: Any, *, timeout: float = 15.0) -> list[Mapping[str, object]]:
    """The engine's resolved agents, once it has read bashOS's.

    OpenCode 2 boots a project lazily and lists its built-in agents a moment before the ones
    from `opencode.jsonc` (measured on 2.0.20: `[]`, then the built-ins, then all of them).
    Judging the first answer would report bashOS's agents missing, so this waits for them,
    and returns whatever the engine has when the time runs out — the contract then says so.
    """
    deadline = time.monotonic() + timeout
    wanted = (project.READONLY_AGENT, project.SEALED_AGENT)
    while True:
        agents = list(await client.agents())
        if all(_agent(agents, name) is not None for name in wanted) or time.monotonic() > deadline:
            return agents
        await asyncio.sleep(0.25)


def passed(findings: Iterable[Finding]) -> bool:
    return all(f.ok for f in findings)
