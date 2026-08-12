from bashos.config import KernelConfig
from bashos.kernel import build_kernel, parse_line

from .conftest import FakeChat


def test_parse_line():
    assert parse_line("/sh do a thing") == ("sh", "do a thing")
    assert parse_line("  /AUDIT foo bar  ") == ("audit", "foo bar")
    assert parse_line("plain english request") == (None, "plain english request")
    assert parse_line("/sys") == ("sys", "")


async def test_slash_command_routes_to_prompt_loop(registry):
    llm = FakeChat(replies=["THE ANSWER"])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "/regex match an email", "trace": []})
    assert result["route"] == "slash"
    assert result["output"] == "THE ANSWER"
    assert llm.calls == 1


async def test_natural_language_is_classified_then_run(registry):
    llm = FakeChat(replies=["/pipe", "PIPELINE OUTPUT"])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "count unique ips in access.log", "trace": []})
    assert result["route"] == "classified"
    assert result["command"] == "pipe"
    assert result["output"] == "PIPELINE OUTPUT"
    assert llm.calls == 2


async def test_bad_classifier_reply_falls_back_to_sh(registry):
    llm = FakeChat(replies=["not-a-command", "FALLBACK OUTPUT"])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "do something odd", "trace": []})
    assert result["command"] == "sh"
    assert result["output"] == "FALLBACK OUTPUT"


async def test_unknown_command_suggests_alternative(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/shh list files", "trace": []})
    assert result["route"] == "error"
    assert "command not found" in result["output"]
    assert "/sh" in result["output"]


async def test_dry_run_renders_prompt_without_model(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sh find files over 100MB", "trace": []})
    assert "[dry-run]" in result["output"]
    assert "find files over 100MB" in result["output"]


async def test_missing_args_shows_usage(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sh", "trace": []})
    assert result["output"].startswith("usage: /sh")


async def test_react_dry_run_reports_tool_policy(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sys", "trace": []})
    assert "loop=react" in result["output"]
    assert "Bash(uname:*)" in result["output"]


async def test_trace_accumulates_across_nodes(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sh do it", "trace": []})
    assert any(line.startswith("parse:") for line in result["trace"])
    assert any(line.startswith("prompt:") for line in result["trace"])
