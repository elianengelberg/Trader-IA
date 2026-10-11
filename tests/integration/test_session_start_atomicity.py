"""Starting a paper session is one guarded step (Phase 1.2, F5 and F8).

Before 1.2 two concurrent start requests could both pass the "already active" check and
build two runtimes over one account (F5), and the run row was written only after the
loop had started, so a fill in the first cycle referenced a run the store did not know
(F8). The tests here drive ``AppState`` itself over a temporary SQLite store with the
synthetic public feed; the execution provider is the real paper engine.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.test_live_api import _FakePublicFeed, _settings
from tia.api.state import AppState
from tia.core.errors import LiveActivationError
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order
from tia.persistence import FillRepository, RunRepository
from tia.persistence import repositories as repositories_module
from tia.runtime.live import LiveRuntime


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def _state(tmp_path: Path) -> AppState:
    state = AppState(_settings(tmp_path))
    await state.startup()
    return state


async def _rows(state: AppState) -> list[tuple[str, str | None, object]]:
    async with state.database.session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT run_id, notes, stopped_at FROM runs "
                    "WHERE mode = 'paper-live' ORDER BY started_at, run_id"
                )
            )
        ).all()
    return [(str(r[0]), r[1], r[2]) for r in rows]


def _track_starts(monkeypatch: pytest.MonkeyPatch) -> list[LiveRuntime]:
    """Record every runtime whose loop was started, so none is left running."""
    started: list[LiveRuntime] = []
    real_start = LiveRuntime.start

    async def start(self: LiveRuntime) -> None:
        started.append(self)
        await real_start(self)

    monkeypatch.setattr(LiveRuntime, "start", start)
    return started


async def _stop_all(state: AppState, runtimes: list[LiveRuntime]) -> None:
    for runtime in runtimes:
        if runtime.is_running:
            await runtime.stop(reason="test teardown")
    await state.shutdown()


# ------------------------------------------------------------------ F5: one at a time


async def test_two_simultaneous_start_requests_yield_one_session_and_one_run_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _track_starts(monkeypatch)
    state = await _state(tmp_path)
    try:
        results = await asyncio.gather(
            state.start_paper_realtime(actor="operator-a"),
            state.start_paper_realtime(actor="operator-b"),
            return_exceptions=True,
        )
        accepted = [r for r in results if isinstance(r, dict)]
        refused = [r for r in results if isinstance(r, LiveActivationError)]
        assert len(accepted) == 1 and len(refused) == 1, results
        assert "already active" in str(refused[0])
        assert len(started) == 1, "exactly one loop was started"
        assert state.live_runtime is started[0] and state.live_runtime.is_running
        rows = await _rows(state)
        assert len(rows) == 1
        assert rows[0][0] == state.live_runtime.run_id
        assert rows[0][2] is None, "the one row is the live one: not stamped"
    finally:
        await _stop_all(state, started)


async def test_without_the_lock_two_concurrent_starts_build_two_runtimes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect the lock closes, reproduced on the unlocked path: both requests pass
    the "already active" check while the other is still building, two loops run over
    one account, and the application remembers only the last. This is what F5 named."""
    started = _track_starts(monkeypatch)
    state = await _state(tmp_path)
    try:
        results = await asyncio.gather(
            state._start_paper_realtime_locked(actor="operator-a"),
            state._start_paper_realtime_locked(actor="operator-b"),
            return_exceptions=True,
        )
        assert all(isinstance(r, dict) for r in results), results
        assert len(started) == 2, "both loops started: the race is real without the lock"
        assert all(r.is_running for r in started)
        assert len(await _rows(state)) == 2
        assert sum(1 for r in started if r is state.live_runtime) == 1, "one is orphaned"
    finally:
        await _stop_all(state, started)


async def test_a_second_sequential_start_is_refused_while_one_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _track_starts(monkeypatch)
    state = await _state(tmp_path)
    try:
        first = await state.start_paper_realtime(actor="operator")
        with pytest.raises(LiveActivationError, match="already active"):
            await state.start_paper_realtime(actor="operator")
        assert len(started) == 1
        assert len(await _rows(state)) == 1, "a refused start writes nothing"
        assert state.live_runtime.run_id == first["run_id"]

        # Stopped, the slot is free: the next start is a new run, the old one stamped.
        await state.stop_realtime_session(reason="operator stop")
        second = await state.start_paper_realtime(actor="operator")
        assert second["run_id"] != first["run_id"]
        rows = await _rows(state)
        assert [r[0] for r in rows] == [first["run_id"], second["run_id"]]
        assert rows[0][2] is not None and rows[1][2] is None
        assert len(started) == 2
    finally:
        await _stop_all(state, started)


# ----------------------------------------------------------- F8: the row before the loop


async def test_a_failed_run_row_write_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = _track_starts(monkeypatch)
    state = await _state(tmp_path)
    outage = {"on": True}
    real_create = RunRepository.create

    async def create(self: RunRepository, **kwargs: Any) -> None:
        if outage["on"]:
            raise RuntimeError("database is locked")
        await real_create(self, **kwargs)

    monkeypatch.setattr(repositories_module.RunRepository, "create", create)
    try:
        with pytest.raises(LiveActivationError, match="run row could not be persisted"):
            await state.start_paper_realtime(actor="operator")
        assert state.live_runtime is None
        assert started == [], "no loop was started"
        assert await _rows(state) == []

        # The store comes back: the same request now succeeds, with a row of its own.
        outage["on"] = False
        snapshot = await state.start_paper_realtime(actor="operator")
        assert state.live_runtime is not None and state.live_runtime.is_running
        rows = await _rows(state)
        assert [r[0] for r in rows] == [snapshot["run_id"]]
        assert rows[0][2] is None
    finally:
        await _stop_all(state, started)


async def test_a_runtime_that_fails_to_start_leaves_a_stamped_row_and_no_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = await _state(tmp_path)
    attempts: list[LiveRuntime] = []
    real_start = LiveRuntime.start

    async def start(self: LiveRuntime) -> None:
        attempts.append(self)
        if len(attempts) == 1:
            raise LiveActivationError("clock skew 2400 ms exceeds the signing window")
        await real_start(self)

    monkeypatch.setattr(LiveRuntime, "start", start)
    try:
        with pytest.raises(LiveActivationError, match="clock skew"):
            await state.start_paper_realtime(actor="operator")
        assert state.live_runtime is None
        rows = await _rows(state)
        assert len(rows) == 1
        failed_id, notes, stopped_at = rows[0]
        assert failed_id == attempts[0].run_id
        assert stopped_at is not None, "a run that never ran is not left looking live"
        assert notes and "start_failed" in notes and "clock skew" in notes

        # Retry after the error: a fresh row, the failed one untouched.
        snapshot = await state.start_paper_realtime(actor="operator")
        assert snapshot["run_id"] != failed_id
        assert state.live_runtime is not None and state.live_runtime.is_running
        rows = await _rows(state)
        assert [r[0] for r in rows] == [failed_id, snapshot["run_id"]]
        assert rows[0][2] is not None and rows[1][2] is None
    finally:
        await _stop_all(state, [r for r in attempts if r.is_running])


async def test_the_run_row_exists_before_the_loop_starts_so_a_first_cycle_fill_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fill the loop produces in its very first cycle is written against the run row.
    The store enforces the foreign key, so the only way that write can land is for the
    row to exist before ``start`` — which is what this pins, from inside ``start``."""
    state = await _state(tmp_path)
    seen: dict[str, Any] = {}
    real_start = LiveRuntime.start

    async def start(self: LiveRuntime) -> None:
        async with state.database.session() as session:
            row = await RunRepository(session).get(self.run_id)
        seen["row_at_start"] = row is not None
        seen["stamped_at_start"] = row.stopped_at if row is not None else "no row"
        # The first thing a loop can do is fill: persist one through the runtime's own
        # path, before the loop takes a single decision.
        now = datetime.now(UTC)
        fill = Fill(
            fill_id="fill_first_cycle", order_id="ord_first_cycle", sequence=1,
            symbol="BTC-USD", side=Side.BUY, quantity=0.01, price=50_000.0, fee=0.5,
            filled_at=now,
        )
        order = Order(
            order_id="ord_first_cycle", client_order_id="coid_first_cycle", intent_id="int_1",
            signal_id="sig_1", symbol="BTC-USD", side=Side.BUY, order_type=OrderType.MARKET,
            quantity=0.01, state=OrderState.FILLED, filled_quantity=0.01,
            average_fill_price=50_000.0, fees_paid=0.5, created_at=now, updated_at=now,
            fills=[fill],
        )
        self._save("order", {"run_id": self.run_id, "order": order})
        self._save("fill", {"run_id": self.run_id, "fill": fill})
        await real_start(self)

    monkeypatch.setattr(LiveRuntime, "start", start)
    try:
        snapshot = await state.start_paper_realtime(actor="operator")
        assert seen["row_at_start"] is True, "the row was there when the loop started"
        assert seen["stamped_at_start"] is None
        assert await state.live_runtime.flush_persistence(), "writes still in flight"
        async with state.database.session() as session:
            fills = (
                await session.execute(
                    text("SELECT run_id, fill_id FROM fills WHERE fill_id = 'fill_first_cycle'")
                )
            ).all()
        assert [(str(r[0]), str(r[1])) for r in fills] == [(snapshot["run_id"], "fill_first_cycle")]

        # And the store would have refused that same fill for a run it did not know.
        orphan = Fill(
            fill_id="fill_orphan", order_id="ord_first_cycle", sequence=2, symbol="BTC-USD",
            side=Side.BUY, quantity=0.01, price=50_000.0, fee=0.5, filled_at=datetime.now(UTC),
        )
        with pytest.raises(IntegrityError):
            async with state.database.session() as session:
                await FillRepository(session).append("run_that_was_never_written", orphan)
    finally:
        await state.shutdown()
