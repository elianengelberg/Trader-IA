"""The application's run lifecycle against the real store (Phase 1.4).

Scenario runs: the row is written before the engine is installed as "the run", a start
that fails installs nothing and stamps its row, two concurrent starts yield one run, and a
stop is idempotent. Persistence failures the dispatcher absorbs are counted and reach the
health endpoint. The realtime stop waits for a start in progress instead of answering
"disarmed" while the session it did not see goes on. Concurrency is driven by barriers.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _FakePublicFeed, _settings
from tia.api.state import AppState
from tia.core.config import LiveConfig
from tia.persistence import RunRepository
from tia.runtime.engine import RuntimeEngine

RUN = {"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 3,
       "bar_interval_seconds": 0.0, "llm_enabled": False, "news_enabled": False}


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def _state(tmp_path: Path) -> AppState:
    # No market stream: the fake public feed stands in for the venue, and nothing here
    # may try the network (egress is blocked in this environment).
    state = AppState(_settings(tmp_path, live=LiveConfig(market_stream=False)))
    await state.database.ensure_schema()
    return state


async def _runs(state: AppState) -> list[tuple[str, Any, str]]:
    async with state.database.session() as session:
        rows = (await session.execute(text("SELECT run_id, stopped_at, notes FROM runs ORDER BY started_at"))).all()
    return [(str(r[0]), r[1], str(r[2] or "")) for r in rows]


# ----------------------------------------------------------------- scenario runs


async def test_a_run_whose_row_cannot_be_written_is_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    try:
        async def refuse(self: Any, **kwargs: Any) -> None:
            raise RuntimeError("store refused the row")

        monkeypatch.setattr(RunRepository, "create", refuse)
        with pytest.raises(RuntimeError, match="refused"):
            await state.start_run(dict(RUN))
        assert state.runtime is None, "an engine without a row is not the run"
        snapshot = state.runtime_snapshot()
        assert snapshot["state"] == "stopped" and snapshot["run_id"] is None
        assert await _runs(state) == []
    finally:
        await state.shutdown()


async def test_a_start_that_fails_stamps_its_row_and_installs_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    try:
        async def broken_start(self: Any) -> None:
            raise RuntimeError("feed unavailable at start")

        monkeypatch.setattr(RuntimeEngine, "start", broken_start)
        with pytest.raises(RuntimeError, match="feed unavailable"):
            await state.start_run(dict(RUN))
        assert state.runtime is None
        rows = await _runs(state)
        assert len(rows) == 1
        _run_id, stopped_at, notes = rows[0]
        assert stopped_at is not None, "the row is stamped as over"
        assert "start_failed" in notes and "feed unavailable" in notes
    finally:
        await state.shutdown()


async def test_two_concurrent_starts_yield_exactly_one_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first start is held inside the row write; the second arrives meanwhile. With
    the lock the second waits and is refused; without it both passed the "already
    active" check (the engine is not running until ``start()``), wrote two rows and ran
    two engines over one account."""
    state = await _state(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    real_create = RunRepository.create
    starts = 0
    real_start = RuntimeEngine.start

    async def gated_create(self: Any, **kwargs: Any) -> None:
        entered.set()
        await release.wait()
        await real_create(self, **kwargs)

    async def counted_start(self: Any) -> None:
        nonlocal starts
        starts += 1
        await real_start(self)

    monkeypatch.setattr(RunRepository, "create", gated_create)
    monkeypatch.setattr(RuntimeEngine, "start", counted_start)
    try:
        first = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        second = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.sleep(0.05)
        assert not second.done(), "the second start waits for the first"
        release.set()
        await first
        with pytest.raises(ValueError, match="already active"):
            await second
        assert starts == 1
        assert len(await _runs(state)) == 1
        assert state.runtime is not None and state.runtime.is_running
    finally:
        with contextlib.suppress(Exception):
            await state.stop_run()
        await state.shutdown()


async def test_stop_is_idempotent_and_stamps_the_row_once(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    try:
        assert state.runtime is None
        assert (await state.stop_run())["state"] == "stopped"
        await state.start_run(dict(RUN))
        assert state.runtime is not None and state.runtime.is_running
        first = await state.stop_run()
        second = await state.stop_run()
        assert first["state"] == "stopped" and second["state"] == "stopped"
        assert state.runtime.persistence_flushed is True
        rows = await _runs(state)
        assert len(rows) == 1 and rows[0][1] is not None
    finally:
        await state.shutdown()


# ---------------------------------------------- persistence failures reach health


async def test_a_write_the_store_refuses_is_counted_and_degrades_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    try:
        before = await state.health()
        assert before["components"]["persistence"] == "online"

        @contextlib.asynccontextmanager
        async def broken_session():  # type: ignore[no-untyped-def]
            raise RuntimeError("database is locked")
            yield  # pragma: no cover

        monkeypatch.setattr(state.database, "session", broken_session)
        await state._persist("log", {"run_id": "r", "level": "INFO", "at": datetime.now(UTC)})
        status = state.persistence_status()
        assert status["failures"] == 1 and status["writes"] == 0
        assert status["last_error"] is not None and "log" in status["last_error"]
        assert "locked" in status["last_error"]
        monkeypatch.undo()

        health = await state.health()
        assert health["components"]["persistence"] == "degraded"
        assert health["status"] == "degraded" and "persistence" in health["degraded"]
        assert (await state.system_status())["persistence"]["failures"] == 1
        assert "tia_persist_failures_total 1" in state.prometheus_metrics()

        state._persist_last_failed_at = datetime.now(UTC) - timedelta(minutes=11)
        assert (await state.health())["components"]["persistence"] == "online", "an old failure is history"
    finally:
        await state.shutdown()


# ------------------------------------------------- the realtime stop and a start


async def test_a_stop_that_arrives_during_a_start_waits_and_then_stops_the_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Before Phase 1.4 the stop did not take the session lock: it saw no session yet,
    answered "disarmed", and the session the start was building ran on."""
    state = await _state(tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()
    real_lease = state._foreign_session_lease

    async def gated_lease(*, mode: str) -> Any:
        entered.set()
        await release.wait()
        return await real_lease(mode=mode)

    monkeypatch.setattr(state, "_foreign_session_lease", gated_lease)
    try:
        start = asyncio.create_task(state.start_paper_realtime(actor="operator"))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        stop = asyncio.create_task(state.stop_realtime_session(reason="operator"))
        await asyncio.sleep(0.05)
        assert not stop.done(), "the stop waits for the start it cannot see yet"
        release.set()
        started = await start
        assert started.get("run_id"), "the start completed and built the session"
        stopped = await asyncio.wait_for(stop, timeout=30.0)
        assert stopped.get("state") == "stopped", stopped
        assert state.live_runtime is not None and not state.live_runtime.is_running
        rows = await _runs(state)
        assert len(rows) == 1 and rows[0][1] is not None, "the operator's stop stamped the row"
    finally:
        await state.shutdown()
