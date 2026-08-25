"""App-scoped wiring: config, registry, models, kernel, engine lifecycle.

One `DesktopServices` lives for the whole desktop session. It is the only
place the desktop touches the kernel/engine layers, and the seam UI tests
inject through: a dry-run config means llm=None — no auth, no network, no
engine — and every loop short-circuits to its rendered-prompt report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.language_models.chat_models import BaseChatModel

from ..config import KernelConfig
from ..events import EventSink
from ..kernel import build_kernel
from ..registry import CommandSpec, load_registry
from ..runtime.llm import models_for, resolve_backend


@dataclass
class DesktopServices:
    config: KernelConfig
    registry: dict[str, CommandSpec]
    llm: BaseChatModel | None = None
    classify_llm: BaseChatModel | None = None
    backend: str = field(default="")

    @classmethod
    def from_env(
        cls, model: str | None = None, *, event_sink: EventSink | None = None
    ) -> DesktopServices:
        config = KernelConfig.from_env(model=model)
        registry = load_registry()
        llm = classify_llm = None
        if not config.dry_run:
            llm, classify_llm = models_for(config, event_sink=event_sink)
        return cls(
            config=config,
            registry=registry,
            llm=llm,
            classify_llm=classify_llm,
            backend=resolve_backend(config),
        )

    def build_kernel(self, *, on_engine_event: EventSink | None = None):
        """One compiled kernel per console window (cheap, stateless)."""
        return build_kernel(
            self.registry,
            self.llm,
            self.config,
            classify_llm=self.classify_llm,
            on_engine_event=on_engine_event,
        )

    async def engine_status(self) -> list[tuple[str, str]]:
        """The six status rows — boots the engine if it is not up."""
        from ..opencode.engine import get_engine
        from ..opencode.status import engine_rows

        return await engine_rows(await get_engine(self.config))

    async def shutdown(self) -> None:
        """Stop the app-scoped engine. Idempotent; called once on unmount."""
        from ..opencode.engine import shutdown_engine

        await shutdown_engine()
