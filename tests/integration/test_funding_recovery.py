"""A funding settlement converges to one correct account whatever fails around it
(Phase 1.8).

The journal is the source of truth. A settlement and the plan that records it travel in
one batched write; at restore the settled set is seeded from the rows the journal holds,
not from the plan's pointer. Here the write is interrupted at every step — before anything
lands, after the adjustment but not the plan, after the plan but not the adjustment, after
both — and a fresh session is started on the same isolated store. In every case the
restarted session's cash equals the cash rebuilt from the journal, the journal holds the
settlement at most once, and the leg's tally plus the unattributed carry equals what the
journal holds. The same holds through a failed restore, a repeated settlement pass and two
concurrent passes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

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
from tests.integration.test_funding_restore import _funding_rows, _resumed_market
from tests.integration.test_funding_settlement import _ArchiveMarket
from tests.integration.test_live_runtime import _previous_funding_block, live_settings
from tia.portfolio.account_journal import EVENT_ADJUSTMENT, AccountRestore
from tia.runtime.live import (
    funding_period_from_index,
    funding_period_index,
    funding_period_key,
    funding_period_of,
    funding_period_start,
)

RATE = 0.0001
MARK = 50_000.0


def faulting_persister(db, *, mode: str):  # type: ignore[no-untyped-def]
    """The account persister with the funding write interrupted at a chosen point.

    ``drop_batch``: the batch never reaches the store (the process died first).
    ``adjustment_only``: the adjustment lands, the plan does not (what a non-atomic store
    could do; the single-session batch makes it unreachable in production).
    ``plan_only``: the inverse. ``all``: nothing fails. Writes without a funding
    adjustment are untouched.
    """
    base = persister(db)
    seen: dict[str, int] = {"batches": 0}

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        if kind == "account_events":
            envelopes = list(payload["envelopes"])
            funding = [
                e for e in envelopes
                if e.event_type == EVENT_ADJUSTMENT and getattr(e.payload, "kind", None) == "funding"
            ]
            if funding:
                seen["batches"] += 1
                if mode == "drop_batch":
                    raise RuntimeError("database unavailable during account_events")
                if mode == "adjustment_only":
                    payload = {**payload, "envelopes": funding}
                elif mode == "plan_only":
                    payload = {**payload, "envelopes": [e for e in envelopes if e not in funding]}
        await base(kind, payload)

    persist.seen = seen  # type: ignore[attr-defined]
    return persist


def _settlement_after(now: datetime) -> datetime:
    return funding_period_start(funding_period_from_index(funding_period_index(funding_period_of(now)) + 1))


async def _step_until(runtime, clock, target: datetime) -> None:  # type: ignore[no-untyped-def]
    for _ in range(600):
        if clock.now() >= target:
            return
        clock.advance_by(timedelta(seconds=60))
        await runtime._cycle_once()
    raise AssertionError("the clock never reached the target")


async def _session_a(db, *, mode: str):  # type: ignore[no-untyped-def]
    """Open a position, watch the next settlement happen (observed, at the current
    reading), write it through the faulting persister, stop. Returns what A knew."""
    persist = faulting_persister(db, mode=mode)
    runtime, engine, market, clock = build(
        persist=persist, charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0,
    )
    runtime._funding_rate = lambda: RATE
    await register_run(db, runtime.run_id)
    await runtime.start()
    await open_position(runtime, market)
    held = (await engine.get_positions())[SYMBOL]
    runtime._planned_exit["stop"] = runtime._open_trade["price"] * (0.5 if held.quantity > 0 else 1.5)
    boundary = _settlement_after(clock.now())
    await _step_until(runtime, clock, boundary + timedelta(seconds=1))
    assert runtime.funding["payments"] == 1, "A watched the settlement and booked it"
    paid = runtime.funding["paid_usd"]
    period = funding_period_key(funding_period_of(boundary))
    await settle(runtime)  # the write is queued; let it reach the (faulting) store
    assert persist.seen["batches"] == 1, "one batched write carried the settlement"  # type: ignore[attr-defined]
    await runtime.stop()
    await settle(runtime)
    return {
        "runtime": runtime, "engine": engine, "market": market, "clock": clock, "held": held,
        "paid": paid, "period": period, "boundary": boundary,
        "cash_in_memory": (await engine.get_portfolio()).cash,
    }


async def _session_b(db, a, *, restore: AccountRestore | None = None, archive: bool = True):  # type: ignore[no-untyped-def]
    """A fresh session on the same store, one second later, with the venue's realised
    rate and the mark at the settlement on record."""
    restore = restore or await rebuild(db, now=a["clock"].now() + timedelta(minutes=1))
    market_b, clock_b = _resumed_market(a["market"], a["clock"], at=a["clock"].now() + timedelta(seconds=1))
    if archive:
        feed = _ArchiveMarket(market_b._candles, clock_b)
        feed.cursor = market_b.cursor
        feed.archive = {a["boundary"]: MARK}
        market_b = feed
    engine_b = engine_for(clock_b, live_settings(charge_funding=True))
    if restore.complete:
        engine_b.restore_portfolio(restore.portfolio_state())
    runtime_b, _, _, _ = build(
        persist=persister(db), account=restore, engine=engine_b, clock=clock_b, market=market_b,
        charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0,
    )
    runtime_b._funding_rate = lambda: RATE
    runtime_b._funding_rate_at = lambda at: RATE if at == a["boundary"] else None
    await register_run(db, runtime_b.run_id)
    return runtime_b, engine_b, market_b, clock_b


async def _assert_converged(db, runtime, engine, clock) -> AccountRestore:  # type: ignore[no-untyped-def]
    """The one state every path must end in: in-memory cash equals the journal's, the
    journal holds each settlement once, and the carry is accounted exactly once between
    the leg's tally and the account's unattributed carry."""
    await settle(runtime)
    restore = await rebuild(db, now=clock.now() + timedelta(minutes=1))
    assert restore.complete, restore.error
    assert (await engine.get_portfolio()).cash == pytest.approx(restore.cash, abs=1e-6)
    rows = await _funding_rows(db)
    assert len(rows) == len(set(rows)), "a settlement is one row"
    journal_paid = -sum(restore.funding_settled.values())
    tally = (runtime._open_trade["funding_paid"] if runtime._open_trade else 0.0) + runtime.funding["unattributed_usd"]
    assert tally == pytest.approx(journal_paid, abs=1e-6), "attributed + unattributed = what the journal holds"
    return restore


# ----------------------------------------------------------------- interrupted writes


async def test_a_batch_that_never_reached_the_store_is_settled_once_by_the_next_session(tmp_path: Path) -> None:
    """Failure 1 and 4: the process booked the settlement in memory and died before the
    write landed. The dead process's cash is not the account's; the journal is. The next
    session finds the period pending and settles it once, from its own data."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="drop_batch")
        before = await rebuild(db, now=a["clock"].now() + timedelta(minutes=1))
        assert await _funding_rows(db) == [], "nothing landed"
        assert before.cash != pytest.approx(a["cash_in_memory"], abs=1e-6), "the dead session's cash is not the record"
        assert before.plan["funding_period"] != a["period"], "the plan never learned of the settlement"

        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a)
        await runtime_b.start()
        try:
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 1 and runtime_b.funding["reconstructed_payments"] == 1
            assert runtime_b.funding["recovered_from_journal"] == 0
            await settle(runtime_b)
            assert await _funding_rows(db) == [a["period"]]
            await _assert_converged(db, runtime_b, engine_b, clock_b)
            assert runtime_b._open_trade["funding_paid"] == pytest.approx(
                RATE * abs(a["held"].quantity) * MARK * (1.0 if a["held"].quantity > 0 else -1.0), rel=1e-9
            )
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_an_adjustment_without_its_plan_is_recognised_from_the_journal_and_never_charged_again(tmp_path: Path) -> None:
    """Failure 2: the adjustment landed, the plan did not. The next session seeds its
    settled set from the journal, skips the period, and folds the payment into the leg's
    tally — once."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="adjustment_only")
        before = await rebuild(db, now=a["clock"].now() + timedelta(minutes=1))
        assert await _funding_rows(db) == [a["period"]]
        assert before.plan["funding_period"] != a["period"], "the plan still points before the settlement"
        assert before.plan["funding_paid"] == 0.0 and before.funding_settled == {a["period"]: pytest.approx(-a["paid"], abs=1e-6)}

        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a)
        await runtime_b.start()
        try:
            assert a["period"] in runtime_b._funding_settled
            assert runtime_b.funding["recovered_from_journal"] == 1
            assert runtime_b._open_trade["funding_paid"] == pytest.approx(a["paid"], abs=1e-6)
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0, "nothing charged again"
            assert runtime_b.funding["unreconciled_periods"] == 0
            assert runtime_b.funding["period"] == a["period"]
            await settle(runtime_b)
            assert await _funding_rows(db) == [a["period"]]
            await _assert_converged(db, runtime_b, engine_b, clock_b)
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_a_plan_without_its_adjustment_is_the_one_state_a_non_atomic_store_cannot_recover(tmp_path: Path) -> None:
    """Failure 3 inverted: the plan landed, the adjustment did not. No session can tell a
    lost row from a settlement at a zero rate, so the account lacks the payment while the
    plan's tally has it. The batched write makes this unreachable in production (see the
    next test); here the outcome is pinned so the limitation is documented, not hidden."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="plan_only")
        before = await rebuild(db, now=a["clock"].now() + timedelta(minutes=1))
        assert await _funding_rows(db) == []
        assert before.plan["funding_period"] == a["period"] and before.plan["funding_paid"] == pytest.approx(a["paid"], abs=1e-6)

        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a)
        await runtime_b.start()
        try:
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0, "no double charge either way"
            await settle(runtime_b)
            assert await _funding_rows(db) == []
            # The discrepancy is exactly one settlement, in the attribution and not in the account.
            final = await rebuild(db, now=clock_b.now() + timedelta(minutes=1))
            assert (await engine_b.get_portfolio()).cash == pytest.approx(final.cash, abs=1e-6)
            assert runtime_b._open_trade["funding_paid"] - (-sum(final.funding_settled.values())) == pytest.approx(a["paid"], abs=1e-6)
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_the_settlement_and_its_plan_land_together_or_not_at_all(tmp_path: Path) -> None:
    """Failure 3: both landed. And the write is one batch: the persister saw a single
    ``account_events`` write carrying the adjustment and the plan."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="all")
        before = await rebuild(db, now=a["clock"].now() + timedelta(minutes=1))
        assert await _funding_rows(db) == [a["period"]]
        assert before.plan["funding_period"] == a["period"]
        assert before.plan["funding_paid"] == pytest.approx(a["paid"], abs=1e-6)
        assert before.funding_settled == {a["period"]: pytest.approx(-a["paid"], abs=1e-6)}
        assert before.cash == pytest.approx(a["cash_in_memory"], abs=1e-6), "the record and the dead session agree"

        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a)
        await runtime_b.start()
        try:
            assert runtime_b.funding["recovered_from_journal"] == 0, "the plan already carried it"
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0
            assert runtime_b._open_trade["funding_paid"] == pytest.approx(a["paid"], abs=1e-6)
            await _assert_converged(db, runtime_b, engine_b, clock_b)
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


# ------------------------------------------------------------ restore, repeat, race


async def test_a_failed_restore_settles_nothing_and_a_later_good_one_converges(tmp_path: Path) -> None:
    """Failure 5: the store could not be read at start. The session blocks entries,
    knows no position and charges nothing; when a person reconciles with a complete
    rebuild, the settled set comes from the journal and nothing is charged twice."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="all")
        failed = AccountRestore.failed("database unavailable at startup", initial_capital=CAPITAL)
        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a, restore=failed)
        await runtime_b.start()
        try:
            assert "account_state" in runtime_b.entry_blocks and runtime_b._open_trade is None
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0 and runtime_b.funding["unreconciled_periods"] == 0

            good = await rebuild(db, now=clock_b.now() + timedelta(minutes=1))
            engine_b.restore_portfolio(good.portfolio_state())
            runtime_b.restore_account_state(good, venue_position=good.position_quantity)
            assert runtime_b.entry_blocks == {} and runtime_b._open_trade is not None
            assert a["period"] in runtime_b._funding_settled
            market_b.advance()
            await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0
            await settle(runtime_b)
            assert await _funding_rows(db) == [a["period"]]
            await _assert_converged(db, runtime_b, engine_b, clock_b)
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_repeating_the_settlement_pass_for_a_period_the_journal_holds_charges_nothing(tmp_path: Path) -> None:
    """Failure 6: the same event again — a pointer moved back, a pass re-run."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        a = await _session_a(db, mode="all")
        runtime_b, engine_b, market_b, clock_b = await _session_b(db, a)
        await runtime_b.start()
        try:
            for _ in range(3):
                market_b.advance()
                runtime_b._funding_period = _previous_funding_block(clock_b.now())
                await runtime_b._cycle_once()
            assert runtime_b.funding["payments"] == 0
            await settle(runtime_b)
            assert await _funding_rows(db) == [a["period"]]
            await _assert_converged(db, runtime_b, engine_b, clock_b)
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


async def test_two_concurrent_settlement_passes_book_one_settlement(tmp_path: Path) -> None:
    """Failure 7: two passes at once see the same pending period; the lock serialises
    them and the second finds nothing pending."""
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, engine, market, clock = build(persist=persister(db), charge_funding=True)
        runtime._funding_rate = lambda: RATE
        await register_run(db, runtime.run_id)
        await runtime.start()
        try:
            await open_position(runtime, market)
            market.advance()
            runtime._funding_period = _previous_funding_block(clock.now())
            now = clock.now()
            await asyncio.gather(runtime._settle_funding(now), runtime._settle_funding(now), runtime._settle_funding(now))
            assert runtime.funding["payments"] == 1
            await settle(runtime)
            rows = await _funding_rows(db)
            assert len(rows) == 1
            await _assert_converged(db, runtime, engine, clock)
        finally:
            await runtime.stop()
    finally:
        await db.close()
