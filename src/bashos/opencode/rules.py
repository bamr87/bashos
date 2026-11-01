"""OpenCode's permission semantics, mirrored so bashOS can judge a ruleset without a model.

OpenCode resolves an agent's permission into an ordered list of rules —
(permission, pattern, action) — and a request gets the action of the LAST rule
whose permission and pattern both match. Matching is `Wildcard.match` from
OpenCode's `packages/core/src/util/wildcard.ts`: `*` is any run of characters
(spaces and `/` included), `?` is one character, everything else is literal,
the match is anchored at both ends, and a pattern ending in " *" also matches
the bare command ("ls *" matches "ls").

Two callers: the policy tests (does `policy.py` deny what it claims to?) and
`contract.py` (does a given engine still resolve our config that way?).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

Rule = tuple[str, str, str]  # (permission, pattern, action)

_SPECIAL = re.compile(r"[.+^${}()|\[\]\\]")


def wildcard(text: str, pattern: str) -> bool:
    """OpenCode's Wildcard.match(text, pattern), line for line."""
    escaped = _SPECIAL.sub(lambda m: "\\" + m.group(0), pattern.replace("\\", "/"))
    escaped = escaped.replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    return re.fullmatch(escaped, text.replace("\\", "/"), re.S) is not None


def evaluate(rules: Iterable[Rule], permission: str, value: str, default: str = "ask") -> str:
    """The action OpenCode takes for `permission` on `value`: the last matching rule's."""
    action = default
    for perm, pattern, act in rules:
        if wildcard(permission, perm) and wildcard(value, pattern):
            action = act
    return action


def from_config(block: Mapping[str, object]) -> list[Rule]:
    """A config permission block (`{"bash": {"*": "deny", ...}, "edit": "deny"}`) as rules."""
    rules: list[Rule] = []
    for perm, spec in block.items():
        if isinstance(spec, str):
            rules.append((perm, "*", spec))
        elif isinstance(spec, Mapping):
            rules.extend((perm, str(pattern), str(action)) for pattern, action in spec.items())
    return rules


def from_agent(agent: Mapping[str, object]) -> list[Rule]:
    """A resolved agent's rules, as an engine reports them (`GET /agent` → `permission`)."""
    raw = agent.get("permission")
    if not isinstance(raw, list):
        return []
    return [
        (str(r.get("permission", "")), str(r.get("pattern", "")), str(r.get("action", "")))
        for r in raw
        if isinstance(r, Mapping)
    ]
