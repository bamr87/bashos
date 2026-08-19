"""The bashOS tool policy, expressed as an OpenCode permission ruleset.

This is layer L4 of the architecture — the gate every side effect passes
through — and it now lives in one place instead of being a per-loop hardcode.
The engine (OpenCode) owns the tool loop; bashOS owns what that loop is allowed
to touch.

Two profiles ship:

  readonly   the machine-inspection profile. Reads and searches are allowed,
             `bash` is deny-by-default with a narrow allowlist of diagnostic
             probes, and every mutating or outbound tool is denied outright.
             Used by /sys, /debug, /health.

  sealed     no tools at all. Used for single-completion calls, where a tool
             loop is not a feature but a bug.

OpenCode resolves bash patterns with "last matching rule wins", so `"*": "deny"`
is emitted first and the allowlist follows. Dicts preserve insertion order and
`json.dumps` keeps it, so the emitted `opencode.json` carries the precedence.

Widening this file is the only way to widen bashOS's blast radius — which is
the point. Never add a tool here that writes, connects out, or escalates.
"""

from __future__ import annotations

# Read-only diagnostic probes the agent may run through `bash`. Anything not
# matching one of these patterns is refused by the engine before it executes.
PROBE_COMMANDS = (
    "uname", "uptime", "df", "du", "ps", "top", "vm_stat", "free",
    "sw_vers", "sysctl", "ls", "which", "whoami", "id", "date",
    "netstat", "head", "wc", "file", "stat", "env", "git status", "git log",
    # the deterministic health floor (docs/FORGE.md) — read-only by contract
    "bin/os-health", "./bin/os-health",
    # read-only tmux verbs, so /health can inspect a dashboard session;
    # deliberately narrow — never bare "tmux" (that would allow kill-server)
    "tmux list-", "tmux capture-pane", "tmux has-session", "tmux display-message",
)

# OpenCode tool ids (GET /experimental/tool/ids), sorted into what bashOS
# permits and what it refuses.
READ_TOOLS = ("read", "glob", "grep", "list")
MUTATING_TOOLS = ("edit", "write", "apply_patch")
OUTBOUND_TOOLS = ("webfetch", "websearch")
DELEGATING_TOOLS = ("task",)

# Denied for the same reason in every profile: they either mutate the machine,
# reach the network, or spawn an agent that is not bound by this policy.
DENIED_TOOLS = (*MUTATING_TOOLS, *OUTBOUND_TOOLS, *DELEGATING_TOOLS)

# Every tool the engine can offer — the sealed profile switches them all off by
# name, because an empty allowlist still leaves tools visible to the model.
ALL_TOOLS = ("bash", *READ_TOOLS, *DENIED_TOOLS, "todowrite", "question", "skill")


def bash_rules() -> dict[str, str]:
    """Deny-by-default bash patterns: the catch-all first, probes after."""
    rules: dict[str, str] = {"*": "deny"}
    for probe in PROBE_COMMANDS:
        rules[probe] = "allow"
        rules[f"{probe} *"] = "allow"
    return rules


def readonly_permission() -> dict[str, object]:
    """The permission block for machine-inspection runs."""
    block: dict[str, object] = {"bash": bash_rules()}
    for tool in READ_TOOLS:
        block[tool] = "allow"
    for tool in DENIED_TOOLS:
        block[tool] = "deny"
    # the agent may not reach outside the project root, and may not stop to ask
    # a question the non-interactive terminal cannot answer
    block["external_directory"] = "deny"
    block["question"] = "deny"
    return block


def readonly_tools() -> dict[str, bool]:
    """Tool visibility for machine-inspection runs — denied tools stay hidden."""
    tools = {tool: True for tool in ("bash", *READ_TOOLS)}
    tools.update({tool: False for tool in DENIED_TOOLS})
    return tools


def sealed_tools() -> dict[str, bool]:
    """No tools at all — the profile for single-completion calls."""
    return {tool: False for tool in ALL_TOOLS}


def sealed_permission() -> dict[str, object]:
    return {"*": "deny"}


def readonly_policy() -> list[str]:
    """The readonly profile as flat `key=action` atoms.

    One greppable line per rule: what `bashos run -n` prints, what the tests
    assert invariants against, and what `docs/HARNESS.md` documents.
    """
    atoms = [f"{tool}=allow" for tool in READ_TOOLS]
    atoms += [f"{tool}=deny" for tool in DENIED_TOOLS]
    atoms += [f"bash:{pattern}={action}" for pattern, action in bash_rules().items()]
    return atoms


def describe_policy() -> str:
    """One-line-per-rule rendering for the dry-run report."""
    return "tool policy (opencode, deny-by-default):\n  " + "\n  ".join(readonly_policy())
