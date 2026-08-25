"""One source for engine status rows — every surface renders the same data.

The REPL's `engine` builtin, `bashos opencode status`, and the desktop's
engine panel all describe the same six facts about a started engine. This is
the single projection; renderers decide the table.
"""

from __future__ import annotations

from .engine import OpencodeEngine


async def engine_rows(engine: OpencodeEngine) -> list[tuple[str, str]]:
    """Six (label, detail) rows describing a started engine."""
    agents = [a.get("name", "?") for a in await engine.client.agents()]
    providers = await engine.client.connected_providers()
    return [
        ("url", f"{engine.url} ({'supervised' if engine.supervised else 'attached'})"),
        ("version", engine.version),
        ("auth", engine.auth_status),
        ("providers", ", ".join(providers) or "none"),
        ("config", engine.sync_status),
        ("agents", ", ".join(sorted(agents))),
    ]
