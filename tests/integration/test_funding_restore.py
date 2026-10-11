"""The funding a leg paid, and the period it was paid through, survive a restart
(Phases 1.6 and 1.7).

Session A opens a position, watches one settlement and pays it; its journal carries the
settlement as a cash adjustment and, in the leg's plan, the running tally and the period
pointer. Session B adopts the leg from the rebuild after the *next* settlement has passed
with nobody watching: it settles that period from the venue's realised rate for it and
the mark printed then — never from today's reading — and never touches the period A paid.
The closed trade's carry is both settlements; the account's cash, replayed from both
journals, moved by exactly the trade's reported net: once in the account, once in the
attribution, never twice in either.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_account_restore import (
    CAPITAL,
    SYMBOL,
    _db,
    build,
    engine_for,
    open_position,
    persister,
    rebuild,
    register_run,
    settle,
)
from tests.integration.test_live_runtime import (
    FakeMarketData,
    _previous_funding_block,
    live_settings,
)
from tia.core.clock import SimulatedClock
from tia.portfolio.account_journal import AccountRestore
from tia.runtime.live import (
    funding_period_from_index,
    funding_period_index,
    funding_period_key,
    funding_period_of,
    funding_period_start,
)

RATE_A = 0.0001
RATE_B = 0.0002
TODAYS_READING = 0.0009  # what the monitor says *now*: never the price of yesterday's settlement


def _events(runtime, kind: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []
    previous = runtime._on_event

    def capture(event: dict[str, Any]) -> None:
        if event.get("type") == kind:
            seen.append(event.get("data", {}))
        previous(event)

    runtime._on_event = capture
    return seen


async def _settle_once(runtime, market) -> float:  # type: ignore[no-untyped-def]
    """The next check sees one boundary crossed since the last one, as at a settlement
    watched as it happens; returns what it charged."""
    before = runtime.funding["paid_usd"]
    market.advance()  # first: the bar may itself enter a new period
    runtime._funding_period = _previous_funding_block(runtime._clock.now())
    await runtime._cycle_once()
    assert runtime.funding["payments"] >= 1
    return runtime.funding["paid_usd"] - before


def _next_settlement_after(now: datetime) -> datetime:
    return funding_period_start(funding_period_from_index(funding_period_index(funding_period_of(now)) + 1))


def _resumed_market(market_a, clock_a, *, at: datetime) -> tuple[FakeMarketData, SimulatedClock]:  # type: ignore[no-untyped-def]
    """Session B's feed: the same series, continued so that B's clock reads ``at``."""
    shift = at - clock_a.now()
    candles = [
        c.model_copy(update={"open_time": c.open_time + shift, "close_time": c.close_time + shift})
        for c in market_a._candles
    ]
    clock_b = SimulatedClock(at)
    market_b = FakeMarketData(candles, clock_b)
    market_b.cursor = market_a.cursor
    return market_b, clock_b


async def _funding_rows(db) -> list[str]:  # type: ignore[no-untyped-def]
    """The journal's funding adjustments, as their period keys, in order."""
    async with db.session() as session:
        rows = (
            await session.execute(
                text("SELECT idempotency_key FROM events WHERE event_type = 'account.adjustment' ORDER BY occurred_at, event_id")
            )
        ).all()
    return [str(r[0]).split("funding:", 1)[1] for r in rows if "funding:" in str(r[0])]


async def test_a_restart_past_a_settlement_settles_it_from_its_own_data_and_never_the_one_already_paid(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, engine_a, market_a, clock_a = build(
            persist=persister(db), charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0,
        )
        runtime_a._funding_rate = lambda: RATE_A
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market_a)
        held = (await engine_a.get_positions())[SYMBOL]
        entry_notional = abs(held.quantity) * runtime_a._open_trade["price"]
        long = held.quantity > 0
        runtime_a._planned_exit["stop"] = runtime_a._open_trade["price"] * (0.5 if long else 1.5)

        paid_a = await _settle_once(runtime_a, market_a)
        period_a = runtime_a.funding["period"]
        assert paid_a == pytest.approx(RATE_A * held.notional * (1.0 if long else -1.0), rel=0.05)
        assert paid_a != 0.0 and period_a == funding_period_key(funding_period_of(clock_a.now()))
        assert runtime_a._open_trade["funding_paid"] == pytest.approx(paid_a)
        await settle(runtime_a)
        await runtime_a.stop()
        await settle(runtime_a)

        restore = await rebuild(db)
        assert restore.complete, restore.error
        assert restore.has_position and restore.plan is not None
        assert restore.plan["funding_paid"] == pytest.approx(paid_a), "the tally travelled with the plan"
        assert restore.plan["funding_period"] == period_a, "and so did the period pointer"
        assert restore.plan["funding_unreconciled_periods"] == 0
        assert await _funding_rows(db) == [period_a]

        # Session B: 61 s after the next settlement, which nobody watched. The series
        # continues, so the mark printed at the settlement is on record.
        boundary = _next_settlement_after(clock_a.now())
        market_b, clock_b = _resumed_market(market_a, clock_a, at=boundary + timedelta(seconds=61))
        mark_b = [c for c in market_b._candles[: market_b.cursor] if c.close_time <= boundary][-1].close
        period_b = funding_period_key(funding_period_of(boundary))
        engine_b = engine_for(clock_b, live_settings(charge_funding=True))
        engine_b.restore_portfolio(restore.portfolio_state())
        runtime_b, _, _, _ = build(
            persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b,
            charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0,
        )
        runtime_b._funding_rate = lambda: TODAYS_READING
        runtime_b._funding_rate_at = lambda at: RATE_B if at == boundary else None
        closed = _events(runtime_b, "trade.closed")
        payments = _events(runtime_b, "live.funding")
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            assert runtime_b._open_trade is not None and runtime_b._open_trade["restored"] is True
            assert runtime_b._open_trade["funding_paid"] == pytest.approx(paid_a), "adopted with its carry so far"
            assert runtime_b.funding["period"] == period_a, "and from the period A settled"
            runtime_b._planned_exit["stop"] = runtime_b._open_trade["price"] * (0.5 if long else 1.5)

            market_b.advance()
            await runtime_b._cycle_once()
            expected_b = RATE_B * abs(held.quantity) * mark_b * (1.0 if long else -1.0)
            assert runtime_b.funding["payments"] == 1 and runtime_b.funding["reconstructed_payments"] == 1
            assert runtime_b.funding["paid_usd"] == pytest.approx(expected_b, rel=1e-6)
            assert payments[-1]["source"] == "reconstructed" and payments[-1]["period"] == period_b
            assert payments[-1]["rate"] == RATE_B, "that settlement's realised rate, not today's reading"
            assert runtime_b.funding["unreconciled_periods"] == 0 and runtime_b.funding["period"] == period_b
            assert runtime_b._open_trade["funding_paid"] == pytest.approx(paid_a + expected_b), "the leg was open at the settlement"
            assert runtime_b.funding["unattributed_payments"] == 0

            assert await runtime_b._close_position("time stop") is True
            for _ in range(3):
                market_b.advance()
                await runtime_b._cycle_once()
                if runtime_b._open_trade is None:
                    break
            assert runtime_b._open_trade is None and closed, "the round trip closed and was announced"
            trade = closed[-1]
            assert trade["funding_bps"] == pytest.approx((paid_a + expected_b) / entry_notional * 10_000.0, abs=1e-4)
            assert trade["net_bps"] == pytest.approx(trade["gross_bps"] - trade["fees_bps"] - trade["funding_bps"], abs=2e-4)
            await settle(runtime_b)
        finally:
            await runtime_b.stop()
        await settle(runtime_b)

        assert await _funding_rows(db) == [period_a, period_b], "one row per period, A's untouched"
        final = await rebuild(db, now=clock_b.now() + timedelta(minutes=1))
        assert final.complete and not final.has_position
        assert final.cash == pytest.approx((await engine_b.get_portfolio()).cash)
        assert final.cash - CAPITAL == pytest.approx(trade["net_usd"], abs=0.02)
        assert final.cash - CAPITAL == pytest.approx(
            entry_notional * (trade["gross_bps"] - trade["fees_bps"]) / 10_000.0 - paid_a - expected_b, abs=0.01
        )
    finally:
        await db.close()


async def test_a_restart_inside_the_period_already_paid_charges_nothing_again(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, _engine_a, market_a, clock_a = build(persist=persister(db), charge_funding=True)
        runtime_a._funding_rate = lambda: RATE_A
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market_a)
        await _settle_once(runtime_a, market_a)
        period_a = runtime_a.funding["period"]
        await settle(runtime_a)
        await runtime_a.stop()
        await settle(runtime_a)
        restore = await rebuild(db)
        assert restore.plan["funding_period"] == period_a

        resume_at = clock_a.now() + timedelta(seconds=1)
        assert funding_period_key(funding_period_of(resume_at)) == period_a, "still the same period"
        market_b, clock_b = _resumed_market(market_a, clock_a, at=resume_at)
        engine_b = engine_for(clock_b, live_settings(charge_funding=True))
        engine_b.restore_portfolio(restore.portfolio_state())
        runtime_b, _, _, _ = build(
            persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b, charge_funding=True,
        )
        runtime_b._funding_rate = lambda: RATE_A
        runtime_b._funding_rate_at = lambda at: RATE_A
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            for _ in range(3):
                market_b.advance()
                await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0 and runtime_b.funding["unreconciled_periods"] == 0
            assert runtime_b.funding["period"] == period_a
            await settle(runtime_b)
        finally:
            await runtime_b.stop()
        await settle(runtime_b)
        assert await _funding_rows(db) == [period_a]
    finally:
        await db.close()


async def test_a_plan_without_a_pointer_joins_the_current_period_late(tmp_path: Path) -> None:
    """Journals written before Phase 1.7 carry no pointer: the adopting session cannot
    know what was settled, so it settles nothing for the past and guesses nothing."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, _engine_a, market_a, clock_a = build(persist=persister(db))
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market_a)
        await settle(runtime_a)
        await runtime_a.stop()
        await settle(runtime_a)
        restore = await rebuild(db)
        assert restore.plan is not None and restore.plan["funding_paid"] == 0.0
        old_plan = {k: v for k, v in restore.plan.items() if not k.startswith("funding_period")}
        old_plan["funding_period"] = None
        old = AccountRestore(**{**restore.__dict__, "plan": old_plan})

        boundary = _next_settlement_after(clock_a.now())
        market_b, clock_b = _resumed_market(market_a, clock_a, at=boundary + timedelta(seconds=61))
        engine_b = engine_for(clock_b, live_settings(charge_funding=True))
        engine_b.restore_portfolio(old.portfolio_state())
        runtime_b, _, _, _ = build(
            persist=persister(db), account=old, engine=engine_b, clock=clock_b, market=market_b, charge_funding=True,
        )
        runtime_b._funding_rate = lambda: RATE_A
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            assert runtime_b._funding_period is None and runtime_b._open_trade["funding_paid"] == 0.0
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0 and runtime_b.funding["unreconciled_periods"] == 0
            assert runtime_b.funding["period"] == funding_period_key(funding_period_of(clock_b.now()))
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_a_redelivered_settlement_is_one_row_and_one_charge_in_the_rebuild(tmp_path: Path) -> None:
    """The journal keys a settlement by its period: the same period written twice — a
    retry, two sessions claiming it — is one row, folded once."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, _engine, _market, _clock = build(persist=persister(db), charge_funding=True)
        await register_run(db, runtime.run_id)
        for _ in range(2):
            runtime._journal_adjustment(-1.25, "funding +0.000100 (observed, period 2026-01-01:1)", key="funding:2026-01-01:1")
        runtime._journal_adjustment(-0.75, "funding +0.000100 (observed, period 2026-01-01:2)", key="funding:2026-01-01:2")
        await settle(runtime)
        assert await _funding_rows(db) == ["2026-01-01:1", "2026-01-01:2"]
        restore = await rebuild(db)
        assert restore.complete
        assert restore.cash == pytest.approx(CAPITAL - 1.25 - 0.75)
    finally:
        await db.close()
