"""The 24/7 session's frequency limits survive a restart — through the real store.

A session persists its orders and fills as it goes; the next session rebuilds today's
entries from them before it accepts a single decision. What is tested here is that whole
path: runtime → SQLite → repository rebuild → runtime, with the same fakes for feed and
venue the rest of the live-runtime tests use, and a real database in between.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_live_runtime import (
    FakeExecution,
    FakeMarketData,
    _open_a_position,
    _seed_every_bucket,
    live_settings,
)
from tia.core.clock import SimulatedClock
from tia.persistence import (
    Database,
    FillRepository,
    OrderRepository,
    RiskStateRepository,
    RunRepository,
)
from tia.risk.restore import RiskRestore
from tia.runtime.live import LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario
from tia.runtime.states import LiveState


def build_runtime_paper_with(  # type: ignore[no-untyped-def]
    *, persist=None, prior_risk_state: RiskRestore | None = None, **live_overrides: Any
):
    """The paper-realtime runtime of the live-runtime tests, plus the restore argument."""
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = FakeMarketData(candles, clock)
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(**live_overrides),
        activation=None,
        market_data=market,
        execution=execution,
        clock=clock,
        persist=persist,
        poll_interval_seconds=0.0,
        prior_risk_state=prior_risk_state,
    )
    return runtime, execution, market


async def _settle() -> None:
    """Let the runtime's fire-and-forget persistence tasks finish."""
    for _ in range(50):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


def _db(tmp_path: Path) -> Database:
    return Database(f"sqlite+aiosqlite:///{tmp_path / 'risk.db'}")


def _persister(db: Database):  # type: ignore[no-untyped-def]
    """The subset of AppState._persist the frequency state is rebuilt from."""

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        async with db.session() as session:
            if kind == "order":
                await OrderRepository(session).upsert(payload["run_id"], payload["order"])
            elif kind == "fill":
                await FillRepository(session).append(payload["run_id"], payload["fill"])

    return persist


async def _register_run(db: Database, run_id: str, *, mode: str = "paper-live") -> None:
    async with db.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode=mode, scenario="realtime", started_at=datetime.now(UTC),
            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
        )


async def _refusals(runtime, stage: str) -> list[str]:  # type: ignore[no-untyped-def]
    return [r["reason"] for r in runtime.recent_refusals if r["stage"] == stage]


# --------------------------------------------------------------------- the whole path


async def test_a_restart_rebuilds_todays_entries_from_the_store_and_the_cap_still_binds(
    tmp_path: Path,
) -> None:
    """Session A opens one position and persists it. The rebuild says one entry today for
    BTC-USD with its fill time as the cooldown anchor; session B starts with exactly those
    counters, and a rebuild run twice says the same thing."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, execution, market = build_runtime_paper_with(persist=_persister(db))
        await _register_run(db, runtime_a.run_id)
        await runtime_a.start()
        try:
            await _open_a_position(runtime_a, execution, market)
            await _settle()
            now = datetime.now(UTC)  # fills are stamped by the venue fake's wall clock
        finally:
            await runtime_a.stop()
        await _settle()

        async with db.session() as session:
            first = await RiskStateRepository(session).rebuild(now=now)
        async with db.session() as session:
            second = await RiskStateRepository(session).rebuild(now=now)
        assert first.complete is True
        assert first.entries_today == 1
        assert first.entries_today_by_symbol == {"BTC-USD": 1}
        assert "BTC-USD" in first.last_entry_at
        assert first.entry_orders_today >= 1
        assert first.as_dict() == second.as_dict(), "rebuilding twice is the same rebuild"

        # Session B: seeded from the store, the engine holds the same counters the
        # restart would otherwise have zeroed.
        runtime_b, _, _ = build_runtime_paper_with(prior_risk_state=first)
        report = runtime_b.risk_state_report()
        assert report["verified"] is True
        assert report["engine"]["trades_today"] == 1
        assert report["engine"]["trades_today_by_symbol"] == {"BTC-USD": 1}
        assert report["engine"]["last_trade_at"]["BTC-USD"] == first.last_entry_at["BTC-USD"].isoformat()
        assert report["budget_orders_today"] == first.entry_orders_today
        assert runtime_b.snapshot()["risk_state"]["verified"] is True
    finally:
        await db.close()


async def test_a_replayed_fill_and_a_replayed_order_do_not_double_count(tmp_path: Path) -> None:
    """The store itself de-duplicates by id (fill_id, order_id are keys); the rebuild then
    cannot see a replay even if the writer sent it twice."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        persist = _persister(db)
        saved: list[tuple[str, dict[str, Any]]] = []

        async def recording(kind: str, payload: dict[str, Any]) -> None:
            saved.append((kind, payload))
            await persist(kind, payload)

        runtime, execution, market = build_runtime_paper_with(persist=recording)
        await _register_run(db, runtime.run_id)
        await runtime.start()
        try:
            await _open_a_position(runtime, execution, market)
            await _settle()
            now = datetime.now(UTC)  # fills are stamped by the venue fake's wall clock
        finally:
            await runtime.stop()
        await _settle()
        # Replay every persisted order and fill a second time, as a redelivery would.
        for kind, payload in list(saved):
            await persist(kind, payload)

        async with db.session() as session:
            restore = await RiskStateRepository(session).rebuild(now=now)
        assert restore.entries_today == 1
        assert restore.entries_today_by_symbol == {"BTC-USD": 1}
    finally:
        await db.close()


async def test_the_rebuild_sees_yesterday_as_zero_entries_but_keeps_the_cooldown_anchor(
    tmp_path: Path,
) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, execution, market = build_runtime_paper_with(persist=_persister(db))
        await _register_run(db, runtime.run_id)
        await runtime.start()
        try:
            await _open_a_position(runtime, execution, market)
            await _settle()
            now = datetime.now(UTC)  # fills are stamped by the venue fake's wall clock
        finally:
            await runtime.stop()
        await _settle()
        next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        async with db.session() as session:
            after = await RiskStateRepository(session).rebuild(now=next_midnight + timedelta(seconds=30))
        assert after.entries_today == 0
        assert after.entry_orders_today == 0
        assert "BTC-USD" in after.last_entry_at, "a cooldown anchor does not care what day it is"
    finally:
        await db.close()


async def test_sessions_of_other_accounts_do_not_count(tmp_path: Path) -> None:
    """The scenario engine's runs (mode ``paper``) are other accounts entirely."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, execution, market = build_runtime_paper_with(persist=_persister(db))
        await _register_run(db, runtime.run_id, mode="paper")  # a scenario run, not a session
        await runtime.start()
        try:
            await _open_a_position(runtime, execution, market)
            await _settle()
            now = datetime.now(UTC)  # fills are stamped by the venue fake's wall clock
        finally:
            await runtime.stop()
        await _settle()
        async with db.session() as session:
            restore = await RiskStateRepository(session).rebuild(now=now)
        assert restore.entries_today == 0 and restore.orders_seen == 0
    finally:
        await db.close()


# ------------------------------------------------------------------------ fail-safe


async def test_an_unreadable_store_refuses_new_entries_until_a_rebuild_succeeds() -> None:
    """The fail-safe: counters that could not be rebuilt are not trusted at zero. Every
    actionable signal is refused at the risk stage, nothing is sent, and the refusal names
    the cause. A complete rebuild lifts it and the session trades again."""
    runtime, execution, market = build_runtime_paper_with(
        prior_risk_state=RiskRestore.failed("database unavailable at startup")
    )
    assert runtime.risk_state_verified is False
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(60):
            market.advance()
            await runtime._cycle_once()
        assert execution.submissions == 0, "nothing may be sent on unverified counters"
        refused = await _refusals(runtime, "risk")
        assert refused and all("unverified" in r and "database unavailable" in r for r in refused)
        assert runtime.funnel["risk"] == len(refused)
        assert runtime.snapshot()["risk_state"]["verified"] is False
        assert runtime.state is LiveState.RUNNING, "a refusal, not a halt: exits still work"

        report = runtime.restore_risk_state(RiskRestore.empty(day=runtime._clock.now().date().isoformat()))
        assert report["verified"] is True
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is not None:
                break
        assert runtime._open_trade is not None, "once verified, the session trades"
    finally:
        await runtime.stop()


async def test_a_still_incomplete_rebuild_keeps_entries_refused() -> None:
    runtime, _execution, _market = build_runtime_paper_with(
        prior_risk_state=RiskRestore.failed("database unavailable at startup")
    )
    report = runtime.restore_risk_state(RiskRestore.failed("database still unavailable"))
    assert report["verified"] is False
    assert "still unavailable" in report["restore"]["error"]


async def test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart() -> None:
    now = datetime.now(UTC)
    runtime, execution, market = build_runtime_paper_with(
        prior_risk_state=RiskRestore(
            complete=True, day=now.date().isoformat(), entries_today=5,
            entries_today_by_symbol={"BTC-USD": 5},
            last_entry_at={"BTC-USD": now - timedelta(hours=2)},
            entry_orders_today=5,
        )
    )
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        # The engine's checks run in a fixed order and market conditions may refuse a
        # bar before the frequency check is reached; drive until the cap itself speaks.
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            assert execution.submissions == 0
            if any("per-symbol daily trade limit" in r for r in await _refusals(runtime, "risk")):
                break
        assert any("per-symbol daily trade limit" in r for r in await _refusals(runtime, "risk"))
        assert execution.submissions == 0
    finally:
        await runtime.stop()


async def test_a_cooldown_restored_from_the_store_is_still_active() -> None:
    runtime, execution, market = build_runtime_paper_with(
        prior_risk_state=RiskRestore(
            complete=True, day=datetime.now(UTC).date().isoformat(), entries_today=1,
            entries_today_by_symbol={"BTC-USD": 1},
            # The fake feed advances the clock one bar per cycle from its own series; an
            # anchor far in the future relative to that clock keeps the cooldown binding
            # for the whole drive below.
            last_entry_at={"BTC-USD": datetime.now(UTC) + timedelta(days=1)},
        )
    )
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            assert execution.submissions == 0
            if any("cooldown active" in r for r in await _refusals(runtime, "risk")):
                break
        assert any("cooldown active" in r for r in await _refusals(runtime, "risk"))
        assert execution.submissions == 0
    finally:
        await runtime.stop()


@pytest.mark.parametrize("persist", [None])
async def test_a_runtime_without_a_store_has_nothing_to_restore_and_is_complete(persist) -> None:  # type: ignore[no-untyped-def]
    runtime, _, _ = build_runtime_paper_with(persist=persist)
    report = runtime.risk_state_report()
    assert report["verified"] is True
    assert report["restore"]["consulted"] is False
