from bashos.registry import VALID_LOOPS

EXPECTED_COMMANDS = {
    "sh", "explain", "script", "debug", "pipe",
    "regex", "cron", "sys", "port", "audit",
    "health", "dash",
}


def test_all_commands_load(registry):
    assert EXPECTED_COMMANDS <= set(registry)


def test_specs_are_wellformed(registry):
    for spec in registry.values():
        assert spec.description, f"/{spec.name} has no description"
        assert spec.loop in VALID_LOOPS
        assert "$ARGUMENTS" in spec.body, f"/{spec.name} body lacks $ARGUMENTS"


def test_loop_assignments(registry):
    assert registry["sh"].loop == "prompt"
    assert registry["script"].loop == "refine"
    assert registry["sys"].loop == "react"
    assert registry["debug"].loop == "react"
    assert registry["health"].loop == "react"
    assert registry["dash"].loop == "refine"


def test_sys_allows_bare_invocation(registry):
    assert registry["sys"].requires_args is False
    assert registry["sh"].requires_args is True
    assert registry["health"].requires_args is False
    assert registry["dash"].requires_args is False


def test_react_policy_stays_readonly(registry):
    """The forge merge widened the probe list — but never with write/network."""
    from bashos.loops.react import PROBE_COMMANDS, readonly_policy

    assert "bin/os-health" in PROBE_COMMANDS
    joined = " ".join(readonly_policy())
    for forbidden in ("ssh", "curl", "wget", "rm", "Bash(tmux:", "tmux kill"):
        assert forbidden not in joined, f"react policy must not allow {forbidden!r}"


def test_render_substitutes_arguments(registry):
    rendered = registry["sh"].render("find big files")
    assert "find big files" in rendered
    assert "$ARGUMENTS" not in rendered
