"""Desktop UI test fixtures — fully offline.

`dry_services` builds DesktopServices on a dry-run config: llm=None, no
auth, no network, no engine spawn — every kernel loop short-circuits to its
'[dry-run]'/'usage:' literal. `fake_services` swaps in the repo's FakeChat
for exact model-call-count assertions.

Standard pattern:

    async with app.run_test(size=(w, h)) as pilot:
        await pilot.press(...)
        await pilot.pause()
        await app.workers.wait_for_complete()
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable

import pytest
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

from bashos.config import KernelConfig
from bashos.desktop.app import BashOSApp
from bashos.desktop.services import DesktopServices

from ..conftest import FakeChat


@pytest.fixture
def dry_services(registry, tmp_path) -> DesktopServices:
    return DesktopServices(
        config=KernelConfig(dry_run=True),
        registry=registry,
        history_path=tmp_path / "history",
    )


@pytest.fixture
def fake_services(registry, tmp_path):
    def make(replies: list[str]) -> tuple[DesktopServices, FakeChat]:
        llm = FakeChat(replies=replies)
        services = DesktopServices(
            config=KernelConfig(),
            registry=registry,
            llm=llm,
            classify_llm=llm,
            history_path=tmp_path / "history",
        )
        return services, llm

    return make


@pytest.fixture
def desktop_app(dry_services) -> BashOSApp:
    return BashOSApp(services=dry_services)


# --- SVG snapshots ----------------------------------------------------------
#
# A local stand-in for pytest-textual-snapshot's `snap_compare`. That plugin
# (1.1.0, the latest release) hard-pins syrupy==4.8.0, and syrupy 4.x caps
# pytest below 9, so it cannot be installed beside pytest>=9.1.1. Upstream's
# fix (Textualize/pytest-textual-snapshot#24) is unreleased. This keeps the
# same baselines, file layout and `--snapshot-update` flow on syrupy>=5; the
# only thing dropped is the plugin's HTML diff report.


def _normalize_svg(svg: str) -> str:
    """Strip the per-export unique id rich.Console.export_svg() injects."""
    return re.sub(r"\bterminal-\d+-([\w-]+)", r"terminal-\1", svg)


class SVGImageExtension(SingleFileSnapshotExtension):
    file_extension = "svg"
    _write_mode = WriteMode.TEXT

    def read_snapshot_data_from_location(self, *args, **kwargs):
        data = super().read_snapshot_data_from_location(*args, **kwargs)
        return _normalize_svg(data) if data is not None else None

    def serialize(self, *args, **kwargs):
        return _normalize_svg(super().serialize(*args, **kwargs))


@pytest.fixture
def snap_compare(snapshot: SnapshotAssertion) -> Callable[..., bool]:
    snapshot = snapshot.use_extension(SVGImageExtension)

    def compare(
        app,
        press: Iterable[str] = (),
        terminal_size: tuple[int, int] = (80, 24),
        run_before: Callable[..., Awaitable[None] | None] | None = None,
    ) -> bool:
        from textual._doc import take_svg_screenshot

        actual = take_svg_screenshot(
            app=app, press=press, terminal_size=terminal_size, run_before=run_before
        )
        return snapshot == actual

    return compare
