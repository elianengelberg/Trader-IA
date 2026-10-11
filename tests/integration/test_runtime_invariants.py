"""Runtime invariants against the REAL paper engine (Phase 1.3, Stage B: G7, G8, G12, G13).

The venue does not pause when the session does, the reconciliation must compare the
venue's book with *this session's* records, a stop must say when the record is still in
flight, and the venue's position must agree with the tracked round trip in size, not only
in side.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.integration.test_order_integrity import _position_with_stop, _record
from tests.integration.test_paper_cancellations import build, working
from tia.domain.enums import OrderState, OrderType
from tia.domain.orders import Fill
from tia.runtime.states import LiveState


def _through_the_stop(market, stop, *, long: bool):  # type: ignore[no-untyped-def]
    """The next bar, moved so it trades through the stop's level."""
    candle = market._candles[market.cursor]
    level = float(stop.stop_price)
    return candle.model_copy(update={
        "open": level * (0.995 if long else 1.005),
        "high": max(candle.high, level * 1.01),
        "low": min(candle.low, level * 0.99),
        "close": level * (0.995 if long else 1.005),
    })


# ------------------------------------------------------- G7: the venue does not pause


async def test_a_stop_that_fires_while_the_session_is_in_safe_mode_is_booked_on_the_next_cycle() -> None:
    """Before 1.3 a paused or safe-moded cycle returned before reading any order: the
    round trip the stop closed stayed open in the runtime until the state changed."""
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    try:
        stop = await _position_with_stop(runtime, execution, market)
        long = runtime._open_trade["side"].value == "buy"
        runtime.machine.transition(LiveState.SAFE_MODE, reason="test: operator doubt")
        # The venue matches the next bar on its own; the session reads no bars meanwhile.
        execution.on_bar(_through_the_stop(market, stop, long=long))
        assert stop.state is OrderState.FILLED and await execution.get_positions() == {}
        await runtime._cycle_once()  # SAFE_MODE: no decisions — but the venue is read
        assert runtime._open_trade is None, "the stop's fill was routed and the round trip scored"
        assert runtime.counters["round_trips"] == 1 and runtime.counters["exits_stop"] == 1
        assert runtime._protective is None
        assert runtime.state is LiveState.SAFE_MODE, "and the state was not touched"
        assert not [i for i in incidents if i["kind"].startswith("entries_blocked")]
    finally:
        await runtime.stop()


async def test_an_exit_that_fills_while_no_new_bar_closes_is_booked_without_waiting_for_one() -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        assert await runtime._close_position("time stop") is True
        pending = runtime._pending_exit
        assert pending is not None
        # The venue fills the close on its own tape; the feed delivers no new closed bar.
        execution.on_bar(market._candles[market.cursor])
        await runtime._cycle_once()  # same bar as before: "no new closed bar yet"
        assert runtime._pending_exit is None, "the fill was read on a cycle without a bar"
        assert runtime._open_trade is None and runtime.counters["round_trips"] == 1
    finally:
        await runtime.stop()


# ---------------------------------------- G8: the venue's book against our records


async def test_an_open_order_at_the_venue_that_no_record_names_is_a_divergence() -> None:
    """Before 1.3 the order comparison was the provider's own mirror against itself and
    could never disagree; an orphan stop resting at the venue went unreported."""
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is False, "the tracked stop is not a divergence"

        # An order this session never placed and tracks nowhere: a hand-placed one, or an
        # earlier session's stop the venue kept.
        from tests.unit.test_order_filters import intent

        far_below = execution._last_price["BTC-USD"] * 0.5  # rests for good, above the minimum notional
        orphan = await execution.submit_order(
            intent(quantity=0.001, order_type=OrderType.LIMIT, limit_price=far_below, signal_id="someone-elses")
        )
        assert orphan.state is OrderState.ACKNOWLEDGED
        await runtime._reconcile()
        assert runtime.counters_last_reconciliation_broke() is True
        assert runtime.state is LiveState.SAFE_MODE
        safe = [i for i in incidents if i["kind"] == "safe_mode"]
        assert safe and any("not tracked by this session" in d for d in safe[-1]["detail"]["divergences"])
    finally:
        await runtime.stop()


async def test_a_market_entry_is_tracked_while_it_works_so_the_reconciliation_does_not_flag_it() -> None:
    """In paper a market order fills on the next bar and rests until then. It is tracked
    as the working order (G8), and cleared the moment it fills."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        from tests.integration.test_live_runtime import _seed_every_bucket

        _seed_every_bucket(runtime)
        for _ in range(400):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders"] >= 1:
                break
        assert runtime.counters["orders"] >= 1
        entry = next(o for o in await execution.get_orders() if not o.signal_id.startswith(("exit:", "protective:")))
        if not entry.state.is_terminal:
            assert runtime._resting is not None and runtime._resting["order_id"] == entry.order_id
            assert runtime._resting["limit"] is False
            await runtime._reconcile()
            assert runtime.counters_last_reconciliation_broke() is False
            market.advance()
            await runtime._cycle_once()  # fills on this bar
        assert entry.state is OrderState.FILLED
        assert runtime._resting is None and runtime._open_trade is not None
        assert runtime.counters["orders_expired"] == 0
    finally:
        await runtime.stop()


# -------------------------------------------- G12: a stop says when the record is short


async def test_a_stop_that_cannot_drain_the_persistence_queue_says_so() -> None:
    runtime, _execution, market, _clock = build()
    stuck = asyncio.Event()

    async def never(kind: str, payload: dict[str, Any]) -> None:
        await stuck.wait()

    runtime._persist = never
    runtime._flush_timeout_seconds = 0.2
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()  # schedules at least the heartbeat write
        assert runtime._persist_tasks, "a write is in flight"
    finally:
        await runtime.stop()
    assert runtime.persistence_flushed is False
    assert "still in flight" in runtime.last_error
    stuck.set()
    await asyncio.sleep(0)


async def test_a_clean_stop_reports_the_record_flushed() -> None:
    runtime, _execution, market, _clock = build()
    writes: list[str] = []

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        writes.append(kind)

    runtime._persist = persist
    await runtime.start()
    market.advance()
    await runtime._cycle_once()
    await runtime.stop()
    assert runtime.persistence_flushed is True and runtime.last_error == ""
    assert "run_heartbeat" in writes, "the session stamped its heartbeat"


# ------------------------------- G13: the venue's size against the tracked round trip


async def test_a_position_larger_at_the_venue_than_the_tracked_leg_blocks_entries() -> None:
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        held = execution._portfolio.positions["BTC-USD"]
        side = runtime._open_trade["side"]
        # A fill the venue applied and this session never saw doubles the position.
        execution._portfolio.apply_fill(
            Fill(
                fill_id="ghost", order_id="ghost-order", sequence=99, symbol="BTC-USD", side=side,
                quantity=abs(held.quantity), price=held.average_price, fee=0.0,
                filled_at=market._candles[market.cursor - 1].close_time,
            )
        )
        market.advance()
        await runtime._cycle_once()
        assert "position_unverified" in runtime.entry_blocks
        assert "tracked round trip says" in runtime.entry_blocks["position_unverified"]
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        assert [i for i in incidents if i["kind"] == "entries_blocked:position_unverified"]
        assert runtime._open_trade is not None, "nothing was invented to make the numbers agree"
    finally:
        await runtime.stop()


async def test_a_venue_flat_behind_a_tracked_round_trip_blocks_entries_and_scores_nothing() -> None:
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        held = execution._portfolio.positions["BTC-USD"]
        closing = held.quantity > 0
        from tia.domain.enums import Side

        execution._portfolio.apply_fill(
            Fill(
                fill_id="manual-close", order_id="manual", sequence=98, symbol="BTC-USD",
                side=Side.SELL if closing else Side.BUY, quantity=abs(held.quantity),
                price=held.average_price, fee=0.0,
                filled_at=market._candles[market.cursor - 1].close_time,
            )
        )
        assert await execution.get_positions() == {}
        market.advance()
        await runtime._cycle_once()
        assert "position_unverified" in runtime.entry_blocks
        assert "flat" in runtime.entry_blocks["position_unverified"]
        assert runtime.counters["round_trips"] == 0, "no fill was read, so nothing was scored"
        assert runtime._open_trade is not None
        assert [i for i in incidents if i["kind"] == "entries_blocked:position_unverified"]
        # The stop is cancelled as it always was for a flat book — the venue's book stays flat.
        assert await working(execution, OrderType.STOP) == []
    finally:
        await runtime.stop()


@pytest.mark.parametrize("state", [LiveState.PAUSED, LiveState.SAFE_MODE])
async def test_no_order_is_sent_from_a_paused_or_safe_moded_cycle(state: LiveState) -> None:
    """The polling added for G7 reads; it must never write to the venue."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        before = len(await execution.get_orders())
        if state is LiveState.PAUSED:
            runtime.pause(actor="operator")
        else:
            runtime.machine.transition(state, reason="test")
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
        assert len(await execution.get_orders()) == before
    finally:
        await runtime.stop()
