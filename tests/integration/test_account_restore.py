"""The paper account survives a restart — through the real store and the real engine.

Session A trades against ``PaperExecutionProvider`` and persists orders, fills and the
account journal into SQLite. The rebuild seeds a fresh engine and a fresh runtime, and
what the breakers, the budget and the position management see afterwards is what they
would have seen had the process never died. Where a scenario cannot be driven through
the strategy (a day that lost 2.5 %), the journal rows are written the way a session
writes them, with the matching ``fills`` rows the cross-check demands.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_live_runtime import FakeMarketData, _seed_every_bucket, live_settings
from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.core.ids import deterministic_id
from tia.core.rng import RngRegistry
from tia.domain.enums import Direction, MarketRegime, OrderState, OrderType, Side
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.orders import Fill, Order
from tia.domain.signals import SignalCandidate
from tia.events.envelope import EventEnvelope
from tia.execution.paper import PaperExecutionProvider
from tia.persistence import (
    AccountJournalRepository,
    Database,
    EventRepository,
    FillRepository,
    OrderRepository,
    RunRepository,
)
from tia.portfolio.account_journal import (
    EVENT_FILL,
    EVENT_MARK,
    EVENT_PLAN,
    AccountFillPayload,
    AccountMarkPayload,
    AccountPlanPayload,
    AccountRestore,
)
from tia.risk.engine import RiskEngine
from tia.risk.restore import RiskRestore
from tia.runtime.live import LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario

SYMBOL = "BTC-USD"
CAPITAL = 10_000.0


# ----------------------------------------------------------------------- plumbing


def _db(tmp_path: Path, name: str = "account.db") -> Database:
    return Database(f"sqlite+aiosqlite:///{tmp_path / name}")


def persister(db: Database, *, drop: set[str] | None = None, drop_fill_events: int = 0):  # type: ignore[no-untyped-def]
    """The slice of AppState._persist a session's account rests on. ``drop`` names kinds
    whose writes fail (a database outage during a write); ``drop_fill_events`` drops that
    many account fill events (a lost journal write)."""
    dropped = {"fill_events": 0}

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        if drop and kind in drop:
            raise RuntimeError(f"database unavailable during {kind}")
        async with db.session() as session:
            if kind == "order":
                await OrderRepository(session).upsert(payload["run_id"], payload["order"])
            elif kind == "fill":
                await FillRepository(session).append(payload["run_id"], payload["fill"])
            elif kind == "account_event":
                env = payload["envelope"]
                if env.event_type == EVENT_FILL and dropped["fill_events"] < drop_fill_events:
                    dropped["fill_events"] += 1
                    raise RuntimeError("database unavailable during account_event")
                await EventRepository(session).append(payload["run_id"], env)
            elif kind == "account_events":
                # One session for the batch, as AppState._persist does (Phase 1.8).
                for env in payload["envelopes"]:
                    await EventRepository(session).append(payload["run_id"], env)
            elif kind == "run_stop":
                await RunRepository(session).stop(payload["run_id"], payload["stopped_at"])

    return persist


async def register_run(db: Database, run_id: str, *, started_at: datetime | None = None) -> None:
    async with db.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime",
            started_at=started_at or datetime.now(UTC), initial_capital=CAPITAL, seed=1, symbols=(SYMBOL,),
        )


async def settle(runtime: LiveRuntime | None = None) -> None:
    """Let the sequenced persistence writes land. With a runtime, wait for exactly the
    writes it scheduled; without one, yield a few times (used where no runtime is in play)."""
    if runtime is not None:
        assert await runtime.flush_persistence(timeout_seconds=10.0), "persistence writes still in flight"
        return
    for _ in range(60):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


def engine_for(clock: SimulatedClock, settings) -> PaperExecutionProvider:  # type: ignore[no-untyped-def]
    return PaperExecutionProvider(
        settings.execution.model_copy(update={"reject_probability": 0.0, "partial_fill_probability": 0.0}),
        DEFAULT_UNIVERSE, clock, RngRegistry(1), initial_capital=CAPITAL,
    )


def build(  # type: ignore[no-untyped-def]
    *, persist=None, account: AccountRestore | None = None, risk: RiskRestore | None = None,
    engine: PaperExecutionProvider | None = None, clock: SimulatedClock | None = None,
    market: FakeMarketData | None = None, **live_overrides: Any,
):
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol=SYMBOL, timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = clock or SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = market or FakeMarketData(candles, clock)
    settings = live_settings(**live_overrides)
    execution = engine or engine_for(clock, settings)
    runtime = LiveRuntime(
        settings, activation=None, market_data=market, execution=execution, clock=clock,
        persist=persist, poll_interval_seconds=0.0, prior_account_state=account, prior_risk_state=risk,
    )
    return runtime, execution, market, clock


async def open_position(runtime: LiveRuntime, market: FakeMarketData) -> None:
    _seed_every_bucket(runtime)
    for _ in range(400):
        market.advance()
        await runtime._cycle_once()
        if runtime._open_trade is not None:
            runtime._planned_exit["target"] = None
            return
    raise AssertionError("no position was opened")


async def rebuild(db: Database, *, now: datetime | None = None) -> AccountRestore:
    async with db.session() as session:
        return await AccountJournalRepository(session).rebuild(
            now=now or datetime.now(UTC), initial_capital=CAPITAL, symbol=SYMBOL,
        )


# -------------------------------------------------- writing a day the way a session does


def _fill(fid: str, side: Side, qty: float, price: float, fee: float, at: datetime, order_id: str) -> Fill:
    return Fill(fill_id=fid, order_id=order_id, sequence=0, symbol=SYMBOL, side=side, quantity=qty,
                price=price, fee=fee, filled_at=at)


async def write_session_day(db: Database, run_id: str, fills: list[Fill], marks: list[tuple[float, datetime]],
                            *, plan: dict[str, Any] | None = None, skip_fill_rows: bool = False) -> None:
    """Rows exactly as a session persists them: the order row, the fill rows, the journal."""
    async with db.session() as session:
        for fill in fills:
            order = Order(
                order_id=fill.order_id, client_order_id=f"coid_{fill.order_id}", intent_id="int", signal_id="sig_x",
                symbol=SYMBOL, side=fill.side, order_type=OrderType.MARKET, quantity=fill.quantity,
                state=OrderState.FILLED, filled_quantity=fill.quantity, average_fill_price=fill.price,
                fees_paid=fill.fee, created_at=fill.filled_at, updated_at=fill.filled_at, fills=[fill],
            )
            await OrderRepository(session).upsert(run_id, order)
            if not skip_fill_rows:
                await FillRepository(session).append(run_id, fill)
            await EventRepository(session).append(run_id, EventEnvelope(
                event_id=deterministic_id("evt", EVENT_FILL, fill.fill_id), event_type=EVENT_FILL, source="live",
                occurred_at=fill.filled_at, ingestion_at=fill.filled_at, recorded_at=fill.filled_at,
                correlation_id=run_id, idempotency_key=f"{EVENT_FILL}:{fill.fill_id}",
                payload=AccountFillPayload(symbol=SYMBOL, fill_id=fill.fill_id, order_id=fill.order_id,
                                           side=fill.side.value, quantity=fill.quantity, price=fill.price,
                                           fee=fill.fee, filled_at=fill.filled_at),
            ))
        for price, at in marks:
            await EventRepository(session).append(run_id, EventEnvelope(
                event_id=deterministic_id("evt", EVENT_MARK, run_id, at.isoformat()), event_type=EVENT_MARK,
                source="live", occurred_at=at, ingestion_at=at, recorded_at=at, correlation_id=run_id,
                idempotency_key=f"{EVENT_MARK}:{run_id}:{at.isoformat()}",
                payload=AccountMarkPayload(symbol=SYMBOL, price=price, at=at),
            ))
        if plan:
            at = plan.pop("at")
            await EventRepository(session).append(run_id, EventEnvelope(
                event_id=deterministic_id("evt", EVENT_PLAN, run_id, at.isoformat()), event_type=EVENT_PLAN,
                source="live", occurred_at=at, ingestion_at=at, recorded_at=at, correlation_id=run_id,
                idempotency_key=f"{EVENT_PLAN}:{run_id}:{at.isoformat()}",
                payload=AccountPlanPayload(symbol=SYMBOL, at=at, **plan),
            ))


def _signal(at: datetime) -> SignalCandidate:
    return SignalCandidate(
        signal_id=f"sig_{at.timestamp():.0f}", symbol=SYMBOL, direction=Direction.LONG, confidence=0.8,
        base_confidence=0.8, created_at=at, expires_at=at + timedelta(minutes=5), market_snapshot_id="snap",
        entry_reference=50_000.0, stop_reference=49_000.0, target_reference=52_000.0, strategy_id="trend_following",
        strategy_version="1.0.0", regime=MarketRegime.TRENDING_UP, data_quality_score=1.0, data_freshness_score=1.0,
    )


# ------------------------------------------------------------------- the breakers


async def test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart(tmp_path: Path) -> None:
    """Before 1.2 a restart gave the engine a fresh day at the carried balance and the
    daily loss limit measured from there. Now the rebuilt account carries the day's
    opening equity, and the engine's breaker reads it."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        now = datetime.now(UTC)
        t0 = now - timedelta(hours=2)
        assert t0.date() == now.date() or True
        await register_run(db, "run_a", started_at=t0)
        # Buy 0.2 at 50,000; sell at 48,700: -260 and fees, -2.65 % of 10,000 in one UTC day.
        fills = [
            _fill("f1", Side.BUY, 0.2, 50_000.0, 2.5, t0, "ord_1"),
            _fill("f2", Side.SELL, 0.2, 48_700.0, 2.4, t0 + timedelta(minutes=30), "ord_2"),
        ]
        await write_session_day(db, "run_a", fills, [(50_000.0, t0 - timedelta(minutes=1)), (48_700.0, t0 + timedelta(minutes=31))])
        restore = await rebuild(db, now=now)
        assert restore.complete, restore.error
        # The rebuild says the same thing on a second read.
        assert (await rebuild(db, now=now)).as_dict() == restore.as_dict()
        if restore.current_day != t0.date().isoformat():
            pytest.skip("the UTC day rolled during the test; the day scenario is covered by the unit tests")
        assert restore.day_start_equity == pytest.approx(CAPITAL)
        assert restore.equity == pytest.approx(CAPITAL - 260.0 - 4.9)

        # The engine seeded from it reads a day down 2.65 %: the breaker refuses. The
        # runtime's clock sits on the candle series (bar time), so the feed is fresh.
        runtime, engine, market, clock = build(account=restore)
        if clock.now().date().isoformat() != restore.current_day:
            pytest.skip("the UTC day rolled during the test; the day scenario is covered by the unit tests")
        engine.restore_portfolio(restore.portfolio_state())
        portfolio = await engine.get_portfolio()
        assert portfolio.day_pnl_pct < -2.0
        risk = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, clock)
        decision = risk.evaluate(signal=_signal(clock.now()), portfolio=portfolio, now=clock.now())
        assert not decision.allows_execution
        assert any("daily loss" in r for r in decision.reasons), decision.reasons

        # And through the runtime itself: seeded engine, restored account, no entries.
        await runtime.start()
        try:
            assert runtime.entry_blocks == {}
            _seed_every_bucket(runtime)
            for _ in range(120):
                market.advance()
                await runtime._cycle_once()
            assert runtime.counters["orders"] == 0
            reasons = [r["reason"] for r in runtime.recent_refusals if r["stage"] == "risk"]
            assert any("daily loss" in r for r in reasons), (reasons[:3], dict(runtime.funnel))
        finally:
            await runtime.stop()
    finally:
        await db.close()


async def test_a_drawdown_past_the_breaker_survives_a_restart(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        now = datetime.now(UTC)
        t0 = now - timedelta(days=3)
        await register_run(db, "run_a", started_at=t0)
        # Peak at +1,200 (0.2 at 56,000), then out at 44,000: -1,200 from base, -17 % from peak.
        fills = [
            _fill("f1", Side.BUY, 0.2, 50_000.0, 2.5, t0, "ord_1"),
            _fill("f2", Side.SELL, 0.2, 44_000.0, 2.2, t0 + timedelta(days=1), "ord_2"),
        ]
        await write_session_day(db, "run_a", fills, [(56_000.0, t0 + timedelta(hours=1))])
        restore = await rebuild(db, now=now)
        assert restore.complete and restore.peak_equity == pytest.approx(CAPITAL - 2.5 + 1_200.0)
        clock = SimulatedClock(now)
        engine = engine_for(clock, live_settings())
        engine.restore_portfolio(restore.portfolio_state())
        portfolio = await engine.get_portfolio()
        assert portfolio.drawdown_pct > 10.0
        assert portfolio.day_pnl_pct == pytest.approx(0.0), "a new UTC day opened at the carried equity"
        risk = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, clock)
        decision = risk.evaluate(signal=_signal(now), portfolio=portfolio, now=now)
        assert not decision.allows_execution and any("drawdown" in r for r in decision.reasons)
    finally:
        await db.close()


async def test_restarting_before_and_after_midnight_utc_keeps_the_peak_and_rolls_the_day_correctly(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        day = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
        await register_run(db, "run_a", started_at=day)
        fills = [
            _fill("f1", Side.BUY, 0.2, 50_000.0, 2.5, day, "ord_1"),
            _fill("f2", Side.SELL, 0.2, 48_700.0, 2.4, day + timedelta(minutes=30), "ord_2"),
        ]
        await write_session_day(db, "run_a", fills, [(55_000.0, day + timedelta(minutes=5))])
        before = await rebuild(db, now=day + timedelta(hours=3, minutes=59))
        after = await rebuild(db, now=day + timedelta(hours=4, minutes=1))
        assert before.current_day == "2026-10-09" and after.current_day == "2026-10-10"
        assert before.day_start_equity == pytest.approx(CAPITAL)
        assert before.portfolio_state().day_pnl_pct < -2.0
        assert after.day_start_equity == pytest.approx(after.equity)
        assert after.portfolio_state().day_pnl_pct == pytest.approx(0.0)
        assert before.peak_equity == after.peak_equity == pytest.approx(CAPITAL - 2.5 + 1_000.0)
        assert before.equity == after.equity
    finally:
        await db.close()


# ------------------------------------------------------------ positions across restart


async def test_an_open_position_is_restored_protected_scorable_and_closable_after_a_restart(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, engine_a, market_a, clock_a = build(persist=persister(db))
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market_a)
        market_a.advance()
        await runtime_a._cycle_once()
        held_a = (await engine_a.get_positions())[SYMBOL]
        await settle(runtime_a)
        await runtime_a.stop()
        await settle(runtime_a)

        restore = await rebuild(db)
        assert restore.complete, restore.error
        assert restore.position_quantity == pytest.approx(held_a.quantity)
        assert restore.position_average_price == pytest.approx(held_a.average_price)
        assert restore.plan and restore.plan["stop"] is not None
        assert restore.beliefs and restore.beliefs.get("signal_id")

        # Session B: a fresh engine seeded from the journal, a fresh runtime adopting the leg.
        clock_b = SimulatedClock(clock_a.now())
        market_b = FakeMarketData(market_a._candles, clock_b)
        market_b.cursor = market_a.cursor
        engine_b = engine_for(clock_b, live_settings())
        engine_b.restore_portfolio(restore.portfolio_state())
        runtime_b, _, _, _ = build(persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b)
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            assert runtime_b.entry_blocks == {}
            assert runtime_b._open_trade is not None and runtime_b._open_trade["restored"] is True
            assert runtime_b._open_trade["quantity"] == pytest.approx(abs(held_a.quantity))
            assert runtime_b._planned_exit["stop"] == pytest.approx(restore.plan["stop"])
            assert runtime_b._entry_beliefs is not None
            market_b.advance()
            await runtime_b._cycle_once()
            stops = [o for o in await engine_b.get_orders(open_only=True) if o.order_type is OrderType.STOP]
            assert len(stops) == 1, "the restored leg is protected again"
            assert (await engine_b.get_portfolio()).peak_equity == pytest.approx(restore.peak_equity)
            # Retry of the close after the restart: through the guarded path, scored as evidence.
            assert await runtime_b._close_position("time stop") is True
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b._open_trade is None and runtime_b.counters["round_trips"] == 1
            assert (await engine_b.get_positions()) == {}
            await settle(runtime_b)
            final = await rebuild(db)
            assert final.complete and not final.has_position
            assert final.fills_seen == restore.fills_seen + 1
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_a_resting_entry_left_by_a_dead_session_is_orphaned_not_resurrected(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, _engine, market, _clock = build(persist=persister(db), entry_order_type="limit", entry_limit_timeout_bars=60)
        await register_run(db, runtime.run_id)
        await runtime.start()
        _seed_every_bucket(runtime)
        runtime._limit_price_for = lambda side, reference: reference * (0.5 if side.value == "buy" else 2.0)  # type: ignore[assignment]
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime._resting is not None:
                break
        assert runtime._resting is not None
        resting_id = runtime._resting["order_id"]
        await settle(runtime)
        runtime._stop_requested = True  # the process dies: no stamp, no cancel
        await runtime._finalize_stop()
        await settle(runtime)

        async with db.session() as session:
            row = await OrderRepository(session).get(resting_id)
            assert row is not None and row.state == "acknowledged"
            orphaned = await AccountJournalRepository(session).orphan_open_orders(exclude_run_id="run_next", at=datetime.now(UTC))
            assert orphaned == 1
            row = await OrderRepository(session).get(resting_id)
            assert row.state == "cancelled" and "orphaned" in row.reject_reason
        restore = await rebuild(db)
        assert restore.complete and not restore.has_position
    finally:
        await db.close()


async def test_a_pending_exit_at_restart_leaves_the_position_open_and_the_new_session_closes_it(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, _engine_a, market_a, clock_a = build(persist=persister(db))
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market_a)
        market_a.advance()
        await runtime_a._cycle_once()
        assert await runtime_a._close_position("time stop") is True
        pending_id = runtime_a._pending_exit["order_id"]
        await settle(runtime_a)
        runtime_a._stop_requested = True
        await runtime_a._finalize_stop()  # dies with the exit unfilled
        await settle(runtime_a)

        async with db.session() as session:
            assert await AccountJournalRepository(session).orphan_open_orders(exclude_run_id="run_b", at=datetime.now(UTC)) >= 1
            assert (await OrderRepository(session).get(pending_id)).state == "cancelled"
        restore = await rebuild(db)
        assert restore.complete and restore.has_position, "the exit never filled: the leg is still open"
        clock_b = SimulatedClock(clock_a.now())
        market_b = FakeMarketData(market_a._candles, clock_b)
        market_b.cursor = market_a.cursor
        engine_b = engine_for(clock_b, live_settings())
        engine_b.restore_portfolio(restore.portfolio_state())
        runtime_b, _, _, _ = build(persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b)
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            assert runtime_b._pending_exit is None and runtime_b._open_trade is not None
            assert await runtime_b._close_position("time stop") is True
            market_b.advance()
            await runtime_b._cycle_once()
            assert (await engine_b.get_positions()) == {}
            exits = [o for o in await engine_b.get_orders() if o.signal_id.startswith("exit:")]
            assert len(exits) == 1
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_partial_fills_and_fees_rebuild_identically_however_often(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, engine, market, _clock = build(persist=persister(db))
        await register_run(db, runtime.run_id)
        await runtime.start()
        _seed_every_bucket(runtime)
        # Cap the engine so entries fill over several bars.
        volume = market._candles[market.cursor].volume
        engine._config = engine._config.model_copy(update={"max_participation_rate": 0.02 / max(volume, 1e-9)})
        for _ in range(400):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is not None and runtime.counters["fills"] >= 2:
                break
        assert runtime.counters["fills"] >= 2, "more than one fill for the leg"
        await settle(runtime)
        portfolio = await engine.get_portfolio()
        await runtime.stop()
        await settle(runtime)
        first = await rebuild(db)
        second = await rebuild(db)
        assert first.complete, first.error
        assert first.as_dict() == second.as_dict()
        assert first.position_quantity == pytest.approx(portfolio.positions[SYMBOL].quantity)
        assert first.position_average_price == pytest.approx(portfolio.positions[SYMBOL].average_price)
        assert first.fees_paid == pytest.approx(portfolio.fees_paid)
        assert first.cash == pytest.approx(portfolio.cash)
        assert first.fills_seen == runtime.counters["fills"]
    finally:
        await db.close()


# ---------------------------------------------------------------- failures and blocks


async def test_an_unreadable_store_at_start_blocks_entries_and_never_substitutes_base_capital() -> None:
    restore = AccountRestore.failed("database unavailable at startup", initial_capital=CAPITAL)
    runtime, _engine, market, clock = build(account=restore)
    await runtime.start()
    try:
        assert "account_state" in runtime.entry_blocks
        _seed_every_bucket(runtime)
        for _ in range(60):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["orders"] == 0
        assert runtime.snapshot()["account_state"]["verified"] is False
        # Counters alone do not lift it.
        runtime.restore_risk_state(RiskRestore.empty(day=clock.now().date().isoformat()))
        assert "account_state" in runtime.entry_blocks
        # A still-failed account rebuild keeps it.
        runtime.restore_account_state(AccountRestore.failed("still down", initial_capital=CAPITAL), venue_position=0.0)
        assert "account_state" in runtime.entry_blocks
        # A complete rebuild that agrees with the engine lifts it.
        runtime.restore_account_state(AccountRestore.empty(initial_capital=CAPITAL), venue_position=0.0)
        assert "account_state" not in runtime.entry_blocks
    finally:
        await runtime.stop()


async def test_a_lost_journal_write_makes_the_rebuild_incomplete_and_the_next_session_blocked(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, _engine, market, _clock = build(persist=persister(db, drop_fill_events=1))
        await register_run(db, runtime.run_id)
        await runtime.start()
        await open_position(runtime, market)
        await settle(runtime)
        await runtime.stop()
        await settle(runtime)
        restore = await rebuild(db)
        assert restore.complete is False and "inconsistent" in restore.error
        assert restore.checks["fills_in_table"] == restore.checks["fills_in_journal"] + 1
        runtime_b, _, market_b, _ = build(account=restore)
        await runtime_b.start()
        try:
            assert "account_state" in runtime_b.entry_blocks
            _seed_every_bucket(runtime_b)
            for _ in range(40):
                market_b.advance()
                await runtime_b._cycle_once()
            assert runtime_b.counters["orders"] == 0
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_a_database_outage_during_a_write_does_not_pretend_the_state_was_saved(tmp_path: Path) -> None:
    """Writes that fail are logged, never believed. The rebuild afterwards shows the gap
    (fills table and journal both missing the fill) by disagreeing with the engine."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, engine, market, clock = build(persist=persister(db, drop={"fill", "account_event"}))
        await register_run(db, runtime.run_id)
        await runtime.start()
        await open_position(runtime, market)
        held = (await engine.get_positions())[SYMBOL].quantity
        await settle(runtime)
        await runtime.stop()
        await settle(runtime)
        restore = await rebuild(db)
        assert restore.complete and not restore.has_position, "the store never saw the fill"
        # Reconciliation against the engine that still holds the position refuses it.
        runtime_b, _, _, _ = build(account=restore, engine=engine, clock=clock)
        report = runtime_b.restore_account_state(restore, venue_position=held)
        assert report["verified"] is False
        assert "account_state" in runtime_b.entry_blocks
    finally:
        await db.close()


async def test_fill_rows_without_journal_events_are_an_inconsistent_account(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        t0 = datetime.now(UTC) - timedelta(hours=1)
        await register_run(db, "run_a", started_at=t0)
        async with db.session() as session:
            fill = _fill("f1", Side.BUY, 0.1, 50_000.0, 2.5, t0, "ord_1")
            order = Order(order_id="ord_1", client_order_id="coid_1", intent_id="int", signal_id="sig_x", symbol=SYMBOL,
                          side=Side.BUY, order_type=OrderType.MARKET, quantity=0.1, state=OrderState.FILLED,
                          filled_quantity=0.1, average_fill_price=50_000.0, fees_paid=2.5, created_at=t0, updated_at=t0, fills=[fill])
            await OrderRepository(session).upsert("run_a", order)
            await FillRepository(session).append("run_a", fill)
        restore = await rebuild(db)
        assert restore.complete is False and "fills table" in restore.error
    finally:
        await db.close()


async def test_a_restored_position_whose_side_disagrees_with_the_engine_blocks_entries(tmp_path: Path) -> None:
    restore_long = AccountRestore(**{**AccountRestore.empty(initial_capital=CAPITAL).__dict__,
                                      "consulted": True, "position_quantity": 0.01, "position_average_price": 50_000.0,
                                      "plan": {"symbol": SYMBOL, "stop": 49_000.0, "direction": "long"},
                                      "beliefs": {"regime": "trending_up", "direction": "long", "confidence": 0.8, "signal_id": "s"},
                                      "checks": {"symbol": SYMBOL}})
    runtime, _engine, _market, _clock = build(account=restore_long)
    # The engine was NOT seeded (flat): the journal and the venue disagree.
    report = runtime.restore_account_state(restore_long, venue_position=0.0)
    assert report["verified"] is False and "venue holds" in runtime.entry_blocks["account_state"]
