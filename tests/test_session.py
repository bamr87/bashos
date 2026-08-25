"""The conversation-memory contract every surface shares (shell/session.py)."""

from __future__ import annotations

from bashos.shell.session import EXCERPT, ConsoleSession, Turn, excerpt, format_history


def test_first_turn_payload_has_no_history_keys():
    session = ConsoleSession()
    payload = session.payload_for("/sh find big files")
    assert payload == {"input": "/sh find big files", "trace": []}


def test_payload_carries_last_turn_keys():
    session = ConsoleSession()
    session.record("/sh find big files", "sh", "```bash\nfind . -size +100M\n```")
    payload = session.payload_for("now exclude .venv")
    assert payload["last_command"] == "sh"
    assert payload["last_input"] == "/sh find big files"
    assert "via: /sh" in payload["history"]
    assert payload["trace"] == []


def test_history_is_bounded_to_three_turns():
    session = ConsoleSession()
    for i in range(5):
        session.record(f"input {i}", "sh", f"output {i}")
    history = format_history(session.turns)
    assert "input 0" not in history
    assert "input 1" not in history
    assert all(f"input {i}" in history for i in (2, 3, 4))


def test_excerpt_flattens_and_bounds():
    long = "word\nword\t " * 200
    flat = excerpt(long)
    assert len(flat) <= EXCERPT
    assert flat.endswith("...")
    assert "\n" not in flat
    assert excerpt("short answer") == "short answer"


def test_record_skips_unrouted_results():
    """A turn is only remembered when the kernel actually routed a command —
    this condition is what keeps follow-up routing honest."""
    session = ConsoleSession()
    session.record("gibberish", None, "some error text")
    assert session.turns == []
    assert session.last_output == "some error text"  # exec still sees it


def test_runnable_from_last_extracts_the_first_fence():
    session = ConsoleSession()
    session.record("/sh list", "sh", "Sure:\n```bash\nls -la\n```\ndone")
    assert session.runnable_from_last() == "ls -la"
    assert ConsoleSession().runnable_from_last() is None


def test_turn_is_immutable():
    turn = Turn("in", "sh", "out")
    try:
        turn.output = "changed"  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised
