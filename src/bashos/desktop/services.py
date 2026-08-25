"""App-scoped wiring: config, registry, models, kernel, engine lifecycle.

One `DesktopServices` lives for the whole desktop session. It is the only
place the desktop touches the kernel/engine layers, and the seam UI tests
inject through: a dry-run config means llm=None — no auth, no network, no
engine — and every loop short-circuits to its rendered-prompt report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from ..config import KernelConfig
from ..events import EventSink
from ..kernel import build_kernel
from ..registry import CommandSpec, load_registry
from ..runtime.llm import models_for, resolve_backend

HISTORY_FILE = Path.home() / ".bashos_history"


@dataclass
class DesktopServices:
    config: KernelConfig
    registry: dict[str, CommandSpec]
    llm: BaseChatModel | None = None
    classify_llm: BaseChatModel | None = None
    backend: str = field(default="")
    history_path: Path = HISTORY_FILE

    @classmethod
    def from_env(cls, model: str | None = None) -> DesktopServices:
        config = KernelConfig.from_env(model=model)
        registry = load_registry()
        llm = classify_llm = None
        if not config.dry_run:
            llm, classify_llm = models_for(config)
        return cls(
            config=config,
            registry=registry,
            llm=llm,
            classify_llm=classify_llm,
            backend=resolve_backend(config),
        )

    def models_for_window(
        self, sink: EventSink
    ) -> tuple[BaseChatModel | None, BaseChatModel | None]:
        """Per-window model handles.

        Engine-backed models are cheap pydantic objects, so each console
        window gets its own pair carrying that window's event sink — text
        deltas then stream to the right window with no routing ambiguity.
        Anything else (dry-run None, injected fakes, fallback backends) is
        shared as-is.
        """
        from ..opencode.model import OpencodeChatModel

        if isinstance(self.llm, OpencodeChatModel):
            return models_for(self.config, event_sink=sink)
        return self.llm, self.classify_llm

    def build_kernel(
        self,
        *,
        on_engine_event: EventSink | None = None,
        llm: BaseChatModel | None = None,
        classify_llm: BaseChatModel | None = None,
    ):
        """One compiled kernel per console window (cheap, stateless)."""
        return build_kernel(
            self.registry,
            llm if llm is not None else self.llm,
            self.config,
            classify_llm=classify_llm if classify_llm is not None else self.classify_llm,
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
