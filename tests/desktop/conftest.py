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

import pytest

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
