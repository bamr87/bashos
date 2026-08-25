from bashos.config import KernelConfig
from bashos.kernel import build_kernel, guess_command, looks_like_followup, parse_line

from .conftest import FakeChat


def test_config_reads_refine_and_classify_env(monkeypatch):
    monkeypatch.setenv("BASHOS_REFINE_MAX_ITERS", "4")
    monkeypatch.setenv("BASHOS_CLASSIFY_MODEL", "claude-haiku-4")
    config = KernelConfig.from_env()
    assert config.refine_max_iters == 4
    assert config.classify_model == "claude-haiku-4"


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
    result = await kernel.ainvoke({"input": "do something with these records", "trace": []})
    assert result["route"] == "classified"
    assert result["command"] == "pipe"
    assert result["output"] == "PIPELINE OUTPUT"
    assert llm.calls == 2


async def test_heuristic_classifies_without_model(registry):
    llm = FakeChat(replies=["PIPELINE OUTPUT"])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "count unique ips in access.log", "trace": []})
    assert result["route"] == "classified"
    assert result["command"] == "pipe"
    assert result["output"] == "PIPELINE OUTPUT"
    assert llm.calls == 1
    assert any("heuristic" in line for line in result["trace"])


async def test_followup_reuses_last_command(registry):
    llm = FakeChat(replies=["REFINED"])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke(
        {
            "input": "now exclude .venv",
            "trace": [],
            "last_command": "sh",
            "last_input": "find the largest files",
        }
    )
    assert result["route"] == "followup"
    assert result["command"] == "sh"
    assert "Revision:" in result["args"]
    assert "exclude" in result["args"]
    assert llm.calls == 1


async def test_guess_command_and_followup_helpers(registry):
    assert guess_command("count unique ips in access.log", registry) == "pipe"
    assert guess_command("find files over 100MB", registry) is None
    assert looks_like_followup("now exclude .venv")
    assert not looks_like_followup("find files over 100MB")


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


async def test_react_dry_run_reports_engine_agent_and_policy(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sys", "trace": []})
    output = result["output"]
    assert "loop=react" in output
    assert "engine agent: bashos" in output
    # the policy the engine will enforce is printed before anything runs
    assert "bash:*=deny" in output
    assert "bash:uname *=allow" in output
    assert "write=deny" in output


async def test_trace_accumulates_across_nodes(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/sh do it", "trace": []})
    assert any(line.startswith("parse:") for line in result["trace"])
    assert any(line.startswith("prompt:") for line in result["trace"])


async def test_refine_dry_run_trace_not_doubled(registry):
    kernel = build_kernel(registry, None, KernelConfig(dry_run=True))
    result = await kernel.ainvoke({"input": "/script say ok", "trace": []})
    parse_lines = [line for line in result["trace"] if line.startswith("parse:")]
    assert len(parse_lines) == 1
    assert any(line.startswith("refine:") for line in result["trace"])
