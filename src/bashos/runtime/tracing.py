"""Optional observability: OpenInference tracing to Arize Phoenix.

Enabled when PHOENIX_COLLECTOR_ENDPOINT is set (or BASHOS_TRACE=1), and the
`trace` extras are installed (`pip install -e ".[trace]"`). Kernel nodes and
LangChain-backed model calls are exported as spans; on the claude-code backend
the model call itself runs inside the `claude` subprocess, so its span carries
timing but not token-level detail — use the `api` backend for full LLM
telemetry.

Everything degrades to a silent no-op when disabled or uninstalled: the
terminal never breaks over missing observability.
"""

from __future__ import annotations

import os

_initialized = False


def init_tracing() -> str | None:
    """Register the Phoenix OTel provider once. Returns the endpoint, or None."""
    global _initialized
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    if not endpoint and os.environ.get("BASHOS_TRACE") != "1":
        return None
    if _initialized:
        return endpoint or "default"
    try:
        from phoenix.otel import register
    except ImportError:
        return None  # trace extras not installed — no-op
    register(project_name="bashos", auto_instrument=True, batch=True)
    _initialized = True
    return endpoint or "default"
