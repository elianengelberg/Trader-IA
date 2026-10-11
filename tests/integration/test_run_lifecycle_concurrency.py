"""Start, stop and reset of a scenario run exclude one another (Phase 1.5).

Barriers, not sleeps: the start is held inside the write of its run row, the competing
operation arrives meanwhile, and the outcome is read after both complete. Two starts and a
failing start are covered in ``test_run_lifecycle.py``; here: a stop during a start, a
reset during a start, a start cancelled while held, and a stop whose loop will not yield.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _settings
from tia.api.state import AppState
from tia.persistence import RunRepository

RUN = {"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 5,
       "bar_interval_seconds": 0.0, "llm_enabled": False, "news_enabled": False}


async def _state(tmp_path: Path) -> AppState:
    state = AppState(_settings(tmp_path))
    await state.database.ensure_schema()
    return state


async def _runs(state: AppState) -> list[tuple[str, Any]]:
    async with state.database.session() as session:
        rows = (await session.execute(text("SELECT run_id, stopped_at FROM runs ORDER BY started_at"))).all()
    return [(str(r[0]), r[1]) for r in rows]


def _gate(monkeypatch: pytest.MonkeyPatch) -> tuple[asyncio.Event, asyncio.Event]:
    """Hold ``RunRepository.create`` until released; signal when it is entered."""
    entered = asyncio.Event()
    release = asyncio.Event()
    real_create = RunRepository.create

    async def gated(self: Any, **kwargs: Any) -> None:
        entered.set()
        await release.wait()
        await real_create(self, **kwargs)

    monkeypatch.setattr(RunRepository, "create", gated)
    return entered, release


async def test_a_stop_during_a_start_waits_and_then_stops_the_run_it_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    entered, release = _gate(monkeypatch)
    try:
        start = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        stop = asyncio.create_task(state.stop_run())
        await asyncio.sleep(0.05)
        assert not stop.done(), "the stop waits for the start it cannot see yet"
        release.set()
        await start
        stopped = await asyncio.wait_for(stop, timeout=30.0)
        assert stopped["state"] == "stopped"
        assert state.runtime is not None and not state.runtime.is_running
        rows = await _runs(state)
        assert len(rows) == 1 and rows[0][1] is not None, "one run, stamped by the stop"
    finally:
        await state.shutdown()


async def test_a_reset_during_a_start_waits_and_then_resets_the_run_it_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    entered, release = _gate(monkeypatch)
    try:
        start = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        reset = asyncio.create_task(state.reset_account(10_000.0, by="operator"))
        await asyncio.sleep(0.05)
        assert not reset.done(), "the reset waits for the start"
        release.set()
        await start
        result = await asyncio.wait_for(reset, timeout=30.0)
        assert result["state"] == "stopped"
        assert state.runtime is None, "the run the start installed is gone"
        assert await _runs(state) == [], "and so is its row"
    finally:
        await state.shutdown()


async def test_a_start_cancelled_while_held_installs_nothing_and_releases_the_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    entered, _release = _gate(monkeypatch)
    try:
        start = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        start.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start
        assert state.runtime is None
        assert await _runs(state) == [], "the row write never completed"
        assert not state._session_lock.locked(), "the lock was released by the cancellation"
        # The account is usable: a second start (with the gate removed) succeeds.
        monkeypatch.undo()
        await state.start_run(dict(RUN))
        assert state.runtime is not None and state.runtime.is_running
        await state.stop_run()
        rows = await _runs(state)
        assert len(rows) == 1 and rows[0][1] is not None
    finally:
        await state.shutdown()


async def test_a_second_start_waiting_on_the_lock_can_be_cancelled_without_touching_the_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    entered, release = _gate(monkeypatch)
    try:
        first = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.wait_for(entered.wait(), timeout=10.0)
        second = asyncio.create_task(state.start_run(dict(RUN)))
        await asyncio.sleep(0.05)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        release.set()
        await first
        assert state.runtime is not None and state.runtime.is_running
        assert len(await _runs(state)) == 1
    finally:
        await state.shutdown()


async def test_a_stop_whose_loop_will_not_yield_still_stops_and_stamps_the_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = await _state(tmp_path)
    try:
        await state.start_run(dict(RUN))
        engine = state.runtime
        assert engine is not None
        ticking = asyncio.Event()

        async def stuck() -> None:
            ticking.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(engine, "_tick", stuck)
        engine._stop_timeout_seconds = 0.1
        await asyncio.wait_for(ticking.wait(), timeout=10.0)
        stopped = await asyncio.wait_for(state.stop_run(), timeout=10.0)
        assert stopped["state"] == "stopped"
        assert "did not stop" in engine.last_error
        rows = await _runs(state)
        assert len(rows) == 1 and rows[0][1] is not None
        assert not state._session_lock.locked()
    finally:
        await state.shutdown()


async def test_stop_and_reset_hold_the_lock_only_for_the_bounded_stop(tmp_path: Path) -> None:
    """Neither operation awaits anything unbounded while holding the lock: with no run,
    both return at once and leave it free."""
    state = await _state(tmp_path)
    try:
        assert (await state.stop_run())["state"] == "stopped"
        assert (await state.reset_account(10_000.0, by="operator"))["state"] == "stopped"
        assert not state._session_lock.locked()
    finally:
        await state.shutdown()
