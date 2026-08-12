import bashos.loops.refine as refine_mod
from bashos.config import KernelConfig
from bashos.kernel import build_kernel
from bashos.loops.refine import extract_script

from .conftest import FakeChat

SCRIPT_REPLY = "```bash\n#!/usr/bin/env bash\nset -Eeuo pipefail\necho ok\n```"
FIXED_REPLY = "```bash\n#!/usr/bin/env bash\nset -Eeuo pipefail\necho \"fixed\"\n```"


def test_extract_script_from_fence():
    assert extract_script(SCRIPT_REPLY).startswith("#!/usr/bin/env bash")
    assert extract_script("no fence at all") == "no fence at all"


async def test_refine_without_shellcheck_marks_unverified(registry, monkeypatch):
    monkeypatch.setattr(refine_mod, "find_shellcheck", lambda: None)
    llm = FakeChat(replies=[SCRIPT_REPLY])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "/script say ok", "trace": []})
    assert "echo ok" in result["output"]
    assert "unverified" in result["output"]
    assert llm.calls == 1  # no repair pass without a critique


async def test_refine_repairs_until_clean(registry, monkeypatch):
    verdicts = iter([("issues", "stdin:3: warning: SC2086"), ("clean", "")])

    async def fake_shellcheck(script: str):
        return next(verdicts)

    monkeypatch.setattr(refine_mod, "run_shellcheck", fake_shellcheck)
    llm = FakeChat(replies=[SCRIPT_REPLY, FIXED_REPLY])
    kernel = build_kernel(registry, llm, KernelConfig())
    result = await kernel.ainvoke({"input": "/script say ok", "trace": []})
    assert "fixed" in result["output"]
    assert "shellcheck clean" in result["output"]
    assert llm.calls == 2  # draft + one repair pass


async def test_refine_bounded_by_max_iters(registry, monkeypatch):
    async def always_issues(script: str):
        return "issues", "stdin:1: warning: SC0000"

    monkeypatch.setattr(refine_mod, "run_shellcheck", always_issues)
    llm = FakeChat(replies=[SCRIPT_REPLY])
    kernel = build_kernel(registry, llm, KernelConfig(refine_max_iters=2))
    result = await kernel.ainvoke({"input": "/script say ok", "trace": []})
    assert "still reports issues" in result["output"]
    assert llm.calls == 3  # draft + exactly two bounded repair passes
