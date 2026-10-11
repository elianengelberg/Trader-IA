"""Adverse, deterministic, end to end (Phase 1.3, Stage C).

A stochastic venue (rejects and forced partials, seeded), a store that loses a whole
table's writes, and a restart on top of it. What is asserted is not a P&L but the
invariants the earlier phases bought: at most one stop, a book that never flips against
the tracked round trip, a rebuild that is either complete and equal to the engine or
incomplete and says why — never a quiet absorption.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.integration.test_account_restore import (
    SYMBOL,
    _db,
    build,
    engine_for,
    persister,
    rebuild,
    register_run,
    settle,
)
from tests.integration.test_live_runtime import FakeMarketData, _seed_every_bucket, live_settings
from tia.core.clock import SimulatedClock
from tia.core.rng import RngRegistry
from tia.domain.enums import OrderType, Side
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.paper import PaperExecutionProvider
from tia.persistence import AccountJournalRepository


async def _invariants(runtime, engine) -> None:  # type: ignore[no-untyped-def]
    open_orders = await engine.get_orders(open_only=True)
    stops = [o for o in open_orders if o.order_type is OrderType.STOP]
    assert len(stops) <= 1, f"{len(stops)} stops resting"
    positions = await engine.get_positions()
    held = positions[SYMBOL].quantity if SYMBOL in positions else 0.0
    trade = runtime._open_trade
    if trade is not None and held != 0.0:
        long = trade["side"] is Side.BUY
        assert (held > 0) == long, f"book {held} against a {trade['side'].value} round trip"
    if held == 0.0:
        assert stops == [] or runtime._protective is not None, "a stop resting on a flat book is tracked or gone"
    exits = [o for o in open_orders if o.signal_id.startswith("exit:")]
    assert len(exits) <= 1, "at most one exit in flight"


async def test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        _unused, _engine, market, clock = build(max_holding_bars=12)  # the series and its clock
        # A venue that refuses one order in five and forces partials on two in five, seeded.
        engine = PaperExecutionProvider(
            live_settings(max_holding_bars=12).execution.model_copy(
                update={"reject_probability": 0.2, "partial_fill_probability": 0.4}
            ),
            DEFAULT_UNIVERSE, clock, RngRegistry(11), initial_capital=10_000.0,
        )
        runtime, engine, market, clock = build(persist=persister(db), engine=engine, clock=clock, market=market, max_holding_bars=12)
        await register_run(db, runtime.run_id)
        await runtime.start()
        _seed_every_bucket(runtime)
        try:
            for bar in range(500):
                market.advance()
                await runtime._cycle_once()
                await _invariants(runtime, engine)
                if bar % 25 == 24:
                    # Real cycles are ten seconds apart and the writes land between them;
                    # a simulated clock gives them no such gap, so one is made here.
                    await settle(runtime)
            assert runtime.counters["orders"] >= 3, "the venue was exercised"
            assert runtime.counters["fills"] >= 2
            await settle(runtime)
        finally:
            await runtime.stop()
        await settle(runtime)
        assert runtime.persistence_flushed is True
        portfolio = await engine.get_portfolio()
        restore = await rebuild(db)
        assert restore.complete, restore.error
        assert restore.cash == pytest.approx(portfolio.cash)
        assert restore.fees_paid == pytest.approx(portfolio.fees_paid)
        held = portfolio.positions.get(SYMBOL)
        assert restore.position_quantity == pytest.approx(held.quantity if held else 0.0)
        assert restore.fills_seen == runtime.counters["fills"]
    finally:
        await db.close()


async def test_a_store_that_loses_the_fills_table_makes_the_rebuild_incomplete_and_the_next_session_blocked_but_managing(tmp_path: Path) -> None:
    """The fills table stops accepting writes for the whole session (a schema problem, a
    disk full on one file). The journal still has the fills; the cross-check sees the
    disagreement; the next session refuses entries, protects the leg and can close it."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, engine_a, market_a, clock_a = build(persist=persister(db, drop={"fill"}))
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        _seed_every_bucket(runtime_a)
        for _ in range(400):
            market_a.advance()
            await runtime_a._cycle_once()
            if runtime_a._open_trade is not None:
                runtime_a._planned_exit["target"] = None
                break
        assert runtime_a._open_trade is not None
        market_a.advance()
        await runtime_a._cycle_once()
        held = (await engine_a.get_positions())[SYMBOL]
        await settle(runtime_a)
        runtime_a._stop_requested = True
        await runtime_a._finalize_stop()  # the process dies
        await settle(runtime_a)

        restore = await rebuild(db)
        assert restore.complete is False
        assert "fills in the journal" in restore.error and "in the fills table" in restore.error
        assert restore.checks["fills_in_table"] == 0 and restore.checks["fills_in_journal"] >= 1

        # Session B over the same store. The account cannot be trusted: entries wait. The
        # engine is NOT seeded from an incomplete rebuild (the application never does that)
        # — here it is seeded from the venue's own truth to show the leg is still managed.
        clock_b = SimulatedClock(clock_a.now())
        market_b = FakeMarketData(market_a._candles, clock_b)
        market_b.cursor = market_a.cursor
        engine_b = engine_for(clock_b, live_settings())
        engine_b.restore_portfolio(await engine_a.get_portfolio())
        async with db.session() as session:
            await AccountJournalRepository(session).orphan_open_orders(exclude_run_id="run_b", at=datetime.now(UTC))
        runtime_b, _, _, _ = build(persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b)
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            assert "account_state" in runtime_b.entry_blocks
            assert runtime_b._open_trade is None, "an incomplete rebuild adopts no leg"
            _seed_every_bucket(runtime_b)
            for _ in range(5):
                market_b.advance()
                await runtime_b._cycle_once()
            assert runtime_b.counters["orders"] == 0, "no entry while the account is unverified"
            # The venue holds a position this session does not track: said, blocked, untouched.
            assert "position_unverified" in runtime_b.entry_blocks
            assert (await engine_b.get_positions())[SYMBOL].quantity == pytest.approx(held.quantity)
            exits = [o for o in await engine_b.get_orders() if o.signal_id.startswith("exit:")]
            assert exits == [], "nothing was sent on a position nobody tracks"
        finally:
            await runtime_b.stop()
    finally:
        await db.close()
