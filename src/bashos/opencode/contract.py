"""Does an engine still enforce bashOS's policy? Asked of the engine, not of our file.

OpenCode is the dependency everything runs on, and bashOS tracks its latest
release. A release that read our config differently could widen what a loop
may touch without a single line of bashOS changing, so a new engine is trusted
only after this check passes.

OpenCode resolves `opencode.jsonc` into an ordered permission rule list per
agent (`GET /agent`). This module judges those *resolved* rules with OpenCode's
own semantics (`rules.py`) against what `policy.py` promises:

  readonly agent   every denied tool refused; bash refuses every way out we
                   know of; every allowlisted probe and read still runs
  sealed agent     no tool at all

Callers: `bashos opencode verify`, the OS layer before it promotes a new
OpenCode release (os/install/engine.sh), and the engine canary workflow.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import policy, project, rules


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
    "task": "general",
    "external_directory": "/etc/*",
    "question": "*",
}

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


def _agent(agents: Iterable[Mapping[str, object]], name: str) -> Mapping[str, object] | None:
    return next((a for a in agents if a.get("name") == name), None)


def _allowed(found: list[str]) -> str:
    return "allowed: " + ", ".join(found)


def check(agents: list[Mapping[str, object]]) -> list[Finding]:
    """Judge an engine's resolved agents (`GET /agent`) against policy.py."""
    findings: list[Finding] = []
    readonly = _agent(agents, project.READONLY_AGENT)
    sealed = _agent(agents, project.SEALED_AGENT)
    missing = [n for n, a in ((project.READONLY_AGENT, readonly), (project.SEALED_AGENT, sealed)) if a is None]
    findings.append(Finding("agents", not missing, "missing: " + ", ".join(missing) if missing else
                            f"{project.READONLY_AGENT}, {project.SEALED_AGENT}"))

    if readonly is not None:
        ro = rules.from_agent(readonly)
        # No rules at all means the engine reports them in a shape this module does not know:
        # nothing below could be judged, so that is a failure, not a pass.
        findings.append(Finding("readonly: rules", bool(ro), f"{len(ro)} resolved" if ro else
                                "none in a known shape (GET /agent → permission)"))
        if ro:
            open_tools = [t for t, v in DENIED_SAMPLES.items() if rules.evaluate(ro, t, v) == "allow"]
            findings.append(Finding("readonly: denied tools", not open_tools,
                                    _allowed(open_tools) if open_tools else ", ".join(DENIED_SAMPLES)))
            leaks = [c for c in BASH_ESCAPES if rules.evaluate(ro, "bash", c) == "allow"]
            findings.append(Finding("readonly: bash deny-by-default", not leaks,
                                    _allowed(leaks) if leaks else f"{len(BASH_ESCAPES)} ways out refused"))
            blocked = [p for p in policy.PROBE_COMMANDS
                       if rules.evaluate(ro, "bash", p) != "allow" or rules.evaluate(ro, "bash", f"{p} -x") != "allow"]
            findings.append(Finding("readonly: probes run", not blocked,
                                    "refused: " + ", ".join(blocked) if blocked else
                                    f"{len(policy.PROBE_COMMANDS)} probes"))
            unread = [t for t in policy.READ_TOOLS if rules.evaluate(ro, t, "src/bashos/__init__.py") != "allow"]
            findings.append(Finding("readonly: reads", not unread,
                                    "refused: " + ", ".join(unread) if unread else ", ".join(policy.READ_TOOLS)))

    if sealed is not None:
        se = rules.from_agent(sealed)
        open_tools = [t for t in (*policy.ALL_TOOLS, "external_directory")
                      if rules.evaluate(se, t, DENIED_SAMPLES.get(t, "anything")) == "allow"]
        findings.append(Finding("sealed: no tools", bool(se) and not open_tools,
                                _allowed(open_tools) if open_tools else
                                ("no rules in a known shape" if not se else f"{len(policy.ALL_TOOLS)} tools refused")))
    return findings


def passed(findings: Iterable[Finding]) -> bool:
    return all(f.ok for f in findings)
