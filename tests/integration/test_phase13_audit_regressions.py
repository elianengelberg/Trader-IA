"""Regressions for the Phase 1.3 audit findings that could be reproduced (F9, F14, F16, G15).

Each test drives the paper-live runtime over the real paper engine and the fake bar feed
(``tests.integration.test_paper_cancellations.build``) into the situation the finding
described, and asserts the behaviour the fix introduced. Pre-fix evidence for each is in
``docs/PHASE_1_3_COSTS_RISK_PARITY_REPORT.md``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from tests.integration.test_live_runtime import _seed_every_bucket
from tests.integration.test_order_integrity import _position_with_stop, _record
from tests.integration.test_paper_cancellations import build, working
from tia.domain.enums import OrderType, Side
from tia.domain.orders import Fill
from tia.runtime.states import LiveState


def _saves(runtime, kind: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Capture one kind of persisted record (the engine-only ``build`` has no store)."""
    rows: list[dict[str, Any]] = []

    def persist(k: str, payload: dict[str, Any]) -> None:
        if k == kind:
            rows.append(payload)

    runtime._persist = persist
    return rows


# --------------------------------------------- F9: a dead feed and the deadline's close


async def test_a_deadline_close_no_bar_can_fill_is_reported_stuck_in_wall_time() -> None:
    """The feed stalls after the deadline passed with a position open. The close is sent
    once; no bar ever comes to fill it. Before F9 the "unfilled" detection counted bars
    only, so with no bars it never fired and the halt stood silently. Now three bars'
    worth of wall time says the same thing."""
    runtime, execution, market, clock = build(session_wind_down_bars=0)
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        bars_before = runtime.counters["bars"]
        runtime._session_deadline = clock.now()
        await runtime._cycle_once()  # the deadline cycle: no new bar, the close is sent
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1 and runtime._pending_exit is not None
        assert runtime._deadline_close_stuck is False

        for _ in range(3):  # three minutes pass; the feed delivers nothing
            clock.advance_by(timedelta(minutes=1))
            await runtime._cycle_once()

        assert runtime.counters["bars"] == bars_before, "no bar arrived"
        assert runtime._deadline_close_stuck is True
        kinds = [i["kind"] for i in incidents]
        assert kinds.count("session_deadline_close_unfilled") == 1, "said once"
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1, "no retry"
        assert (await execution.get_positions())["BTC-USD"].quantity != 0.0, "the position stays"
        assert runtime.state is not LiveState.RUNNING
    finally:
        await runtime.stop()


async def test_the_wall_time_detection_does_not_fire_before_three_bars_of_time() -> None:
    runtime, execution, market, clock = build(session_wind_down_bars=0)
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        runtime._session_deadline = clock.now()
        await runtime._cycle_once()
        clock.advance_by(timedelta(seconds=150))
        await runtime._cycle_once()
        assert runtime._deadline_close_stuck is False
        assert "session_deadline_close_unfilled" not in [i["kind"] for i in incidents]
    finally:
        await runtime.stop()


# ------------------------------------------ F14: a venue rejection spends no budget


async def test_a_venue_rejection_is_counted_and_spends_nothing_from_the_days_budget() -> None:
    """Every entry the venue refuses: counted as sent *and* as rejected, nothing opened,
    and the day's trade counter — the budget's and the frequency limits' input — stays at
    zero. Before F14 each rejected order consumed one of the day's trades."""
    runtime, execution, market, _clock = build()
    execution._config = execution._config.model_copy(update={"reject_probability": 1.0})
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(400):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders"] >= 2:
                break
        assert runtime.counters["orders"] >= 1
        assert runtime.counters["orders_rejected"] == runtime.counters["orders"]
        assert runtime._trades_today == 0
        assert runtime._open_trade is None and runtime._resting is None
        assert await execution.get_positions() == {}
        assert runtime.counters["round_trips"] == 0
    finally:
        await runtime.stop()


async def test_a_filled_entry_still_counts_as_a_trade_of_the_day() -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        assert runtime._trades_today == 1
        assert runtime.counters["orders_rejected"] == 0
    finally:
        await runtime.stop()


# ----------------------------- F16: the venue's position against the tracked round trip


async def test_a_venue_position_no_round_trip_tracks_is_a_recorded_divergence_not_safe_mode() -> None:
    """The docstring promised a position comparison the code never made. A position at
    the venue that this session does not track is now a divergence in the reconciliation
    record and the break counter; it is not an order-state divergence, so it does not put
    the session in SAFE_MODE (the position path blocks entries on it)."""
    runtime, execution, market, _clock = build()
    reconciliations = _saves(runtime, "reconciliation")
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is False
        breaks_before = runtime.counters["reconciliation_breaks"]

        price = execution._last_price["BTC-USD"]
        execution._portfolio.apply_fill(
            Fill(
                fill_id="hand-placed", order_id="hand-placed-order", sequence=1, symbol="BTC-USD",
                side=Side.BUY, quantity=0.01, price=price, fee=0.0,
                filled_at=market._candles[market.cursor - 1].close_time,
            )
        )
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is True
        assert runtime.counters["reconciliation_breaks"] == breaks_before + 1
        last = reconciliations[-1]
        assert last["clean"] is False
        assert any("no round trip is tracked" in d for d in last["divergences"]), last["divergences"]
        assert runtime.state is not LiveState.SAFE_MODE
        assert runtime._open_trade is None, "nothing was invented to explain the position"
    finally:
        await runtime.stop()


async def test_a_tracked_round_trip_the_venue_holds_on_the_other_side_is_a_divergence() -> None:
    runtime, execution, market, _clock = build()
    reconciliations = _saves(runtime, "reconciliation")
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is False, "tracked and held: agreed"
        held = execution._portfolio.positions["BTC-USD"]
        flip = Side.SELL if held.quantity > 0 else Side.BUY
        execution._portfolio.apply_fill(
            Fill(
                fill_id="flip", order_id="flip-order", sequence=2, symbol="BTC-USD", side=flip,
                quantity=abs(held.quantity) * 2, price=held.average_price, fee=0.0,
                filled_at=market._candles[market.cursor - 1].close_time,
            )
        )
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is True
        assert any("opposite side" in d for d in reconciliations[-1]["divergences"])
    finally:
        await runtime.stop()


# ------------------------------ G15: nothing is placed over a close that is in flight


async def test_a_bar_that_cannot_fill_the_close_leaves_no_stop_placed_over_it() -> None:
    """The close is sent (stop cancelled first); the next bar has no volume, so the
    simulator fills nothing. Before G15 the position path fell through to the stop sync
    and re-placed a protective stop over the working close — two orders able to close
    the same position. Now nothing is placed while the close is pending."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        assert await runtime._close_position("time stop") is True
        assert runtime._pending_exit is not None
        assert await working(execution, OrderType.STOP) == [], "the stop was cancelled before the close"

        index = market.cursor
        market._candles[index] = market._candles[index].model_copy(update={"volume": 0.0})
        market.advance()
        await runtime._cycle_once()

        assert runtime._pending_exit is not None, "the close is still in flight"
        assert await working(execution, OrderType.STOP) == [], "no stop re-placed over the working close"
        assert runtime._protective is None
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1, "and no second close"
        assert runtime._open_trade is not None

        market.advance()  # a normal bar: the close fills
        await runtime._cycle_once()
        assert runtime._pending_exit is None and runtime._open_trade is None
        assert runtime.counters["round_trips"] == 1
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()
