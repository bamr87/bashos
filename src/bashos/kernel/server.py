"""Kernel graph entry for LangGraph Server.

`langgraph.json` points here; `langgraph dev` (the langgraph-dev compose
service) serves this exact kernel over HTTP — same registry, same loops, same
Claude Code OAuth runtime — Studio-compatible at :2024.

Invoke with: {"input": "/sh find big files", "trace": []}
"""

from __future__ import annotations

from ..config import KernelConfig
from ..registry import load_registry
from ..runtime.llm import models_for
from ..runtime.tracing import init_tracing
from .graph import build_kernel

init_tracing()

_config = KernelConfig.from_env()
_llm, _classify = models_for(_config)
graph = build_kernel(load_registry(), _llm, _config, classify_llm=_classify)
