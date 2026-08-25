"""Engine lifetime hazards a long-lived, multi-window app would trip.

All offline: no opencode binary, no network — the engine start path is
monkeypatched and the stdout drain is driven by an in-memory stream.
"""

from __future__ import annotations

import asyncio

import pytest

from bashos.config import KernelConfig
from bashos.opencode import engine as engine_mod
from bashos.opencode import server as server_mod
from bashos.opencode.status import engine_rows


@pytest.fixture(autouse=True)
def _reset_engine_singleton():
    engine_mod._ENGINE = None
    yield
    engine_mod._ENGINE = None


async def test_get_engine_is_single_flight(monkeypatch):
    """Two concurrent first calls must share one engine, not spawn two."""
    starts = 0

    async def fake_start(self):
        nonlocal starts
        starts += 1
        await asyncio.sleep(0.01)  # widen the race window
        self._handle = object()  # anything non-None flips .started
        return self

    monkeypatch.setattr(engine_mod.OpencodeEngine, "start", fake_start)
    config = KernelConfig()
    first, second = await asyncio.gather(
        engine_mod.get_engine(config), engine_mod.get_engine(config)
    )
    assert starts == 1
    assert first is second


async def test_shutdown_engine_is_idempotent(monkeypatch):
    stops = 0

    async def fake_start(self):
        self._handle = object()
        return self

    async def fake_stop(self):
        nonlocal stops
        stops += 1
        self._handle = None

    monkeypatch.setattr(engine_mod.OpencodeEngine, "start", fake_start)
    monkeypatch.setattr(engine_mod.OpencodeEngine, "stop", fake_stop)
    await engine_mod.get_engine(KernelConfig())
    await asyncio.gather(engine_mod.shutdown_engine(), engine_mod.shutdown_engine())
    assert stops == 1
    assert engine_mod._ENGINE is None


async def test_drain_appends_child_stdout_to_the_log(tmp_path):
    log = tmp_path / "opencode.log"
    stream = asyncio.StreamReader()
    stream.feed_data(b"INFO one\nINFO two\n")
    stream.feed_eof()
    await server_mod._drain_stdout(stream, log)
    assert log.read_bytes() == b"INFO one\nINFO two\n"


async def test_drain_without_a_log_path_just_consumes(tmp_path):
    stream = asyncio.StreamReader()
    stream.feed_data(b"x\n" * 1000)
    stream.feed_eof()
    await server_mod._drain_stdout(stream, None)  # must not raise or block


async def test_handle_stop_cancels_the_drain_task():
    stream = asyncio.StreamReader()  # never fed: the drain blocks forever

    class _Client:
        async def aclose(self):
            pass

    handle = server_mod.EngineHandle(
        url="http://127.0.0.1:1",
        client=_Client(),  # type: ignore[arg-type]
        drain_task=asyncio.create_task(server_mod._drain_stdout(stream, None)),
    )
    await handle.stop()
    assert handle.drain_task is None


async def test_status_rows_shape_is_shared():
    """engine_rows is the one projection every surface renders."""

    class _Client:
        async def agents(self):
            return [{"name": "bashos"}, {"name": "bashos-sealed"}]

        async def connected_providers(self):
            return []

    class _Engine:
        url = "http://127.0.0.1:4096"
        supervised = True
        version = "1.2.3"
        auth_status = "claude code oauth (keychain)"
        sync_status = "up to date"
        client = _Client()

    rows = await engine_rows(_Engine())  # type: ignore[arg-type]
    assert [label for label, _ in rows] == [
        "url", "version", "auth", "providers", "config", "agents",
    ]
    assert dict(rows)["providers"] == "none"
    assert dict(rows)["agents"] == "bashos, bashos-sealed"
    assert "supervised" in dict(rows)["url"]
