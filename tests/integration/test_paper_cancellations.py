"""Cancellations against the REAL paper matching engine, not a fake venue.

The audit found that the runtime cancels by ``client_order_id`` while the paper engine
only knew its own ``order_id``: every cancel failed silently, every "cancelled" stop or
entry kept resting, and the fake venue the other tests use hid it by accepting both ids.
These tests drive the runtime with ``PaperExecutionProvider`` itself and read the engine's
own book afterwards, so the original incompatibility — or any cancel the engine does not
honour — fails them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.integration.test_live_runtime import FakeMarketData, _seed_every_bucket, live_settings
from tia.core.clock import SimulatedClock
from tia.core.errors import DuplicateOrderError
from tia.core.rng import RngRegistry
from tia.domain.enums import OrderState, OrderType
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.paper import PaperExecutionProvider
from tia.runtime.live import LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario
from tia.runtime.states import LiveState


def build(**live_overrides: Any):  # type: ignore[no-untyped-def]
    """A paper-live runtime over the real paper engine and the fake bar feed."""
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = FakeMarketData(candles, clock)
    settings = live_settings(**live_overrides)
    execution = PaperExecutionProvider(
        settings.execution.model_copy(update={"reject_probability": 0.0, "partial_fill_probability": 0.0}),
        DEFAULT_UNIVERSE, clock, RngRegistry(1), initial_capital=10_000.0,
    )
    runtime = LiveRuntime(
        settings, activation=None, market_data=market, execution=execution, clock=clock,
        poll_interval_seconds=0.0,
    )
    return runtime, execution, market, clock


async def open_position(runtime: LiveRuntime, market: FakeMarketData, *, bars: int = 400) -> None:
    _seed_every_bucket(runtime)
    for _ in range(bars):
        market.advance()
        await runtime._cycle_once()
        if runtime._open_trade is not None:
            runtime._planned_exit["target"] = None
            return
    raise AssertionError("no position was opened")


def resting(execution: PaperExecutionProvider) -> list[str]:
    return list(execution._resting)


async def working(execution: PaperExecutionProvider, order_type: OrderType | None = None) -> list[Any]:
    orders = await execution.get_orders(open_only=True)
    return [o for o in orders if order_type is None or o.order_type is order_type]


# ------------------------------------------------------------------ the engine itself


async def test_the_engine_cancels_by_either_id_and_a_cancelled_order_never_fills_later() -> None:
    from tests.unit.test_order_filters import bar, intent

    engine = PaperExecutionProvider(
        live_settings().execution.model_copy(update={"reject_probability": 0.0, "partial_fill_probability": 0.0}),
        DEFAULT_UNIVERSE, SimulatedClock(datetime(2026, 1, 5, tzinfo=UTC)), RngRegistry(1), initial_capital=10_000.0,
    )
    engine.on_bar(bar(0))
    order = await engine.submit_order(intent(quantity=0.001, order_type=OrderType.LIMIT, limit_price=99_000.0))
    assert order.state is OrderState.ACKNOWLEDGED and order.order_id in engine._resting
    assert (await engine.get_order(order.client_order_id)) is order, "get_order resolves the client id"
    cancelled = await engine.cancel_order(order.client_order_id)
    assert cancelled.state is OrderState.CANCELLED
    assert order.order_id not in engine._resting
    # A bar that would have filled it (trades through 99,000) produces nothing.
    assert engine.on_bar(bar(1, price=98_000.0)) == []
    assert order.fills == [] and await engine.get_positions() == {}
    with pytest.raises(DuplicateOrderError):
        await engine.cancel_order("neither-an-order-id-nor-a-client-id")


# ----------------------------------------------------------------- the runtime's routes


async def test_a_close_cancels_the_protective_stop_in_the_engine_and_the_old_stop_cannot_fire() -> None:
    """The route that used to leave stops resting: close, then a bar through the old stop
    level. With the stop truly cancelled nothing fills and the book stays flat."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        stops = await working(execution, OrderType.STOP)
        assert len(stops) == 1, "one protective stop resting in the engine"
        stop_id = stops[0].order_id

        assert await runtime._close_position("time stop") is True
        assert stop_id not in resting(execution), "the engine no longer rests the stop"
        assert (await execution.get_order(stop_id)).state is OrderState.CANCELLED
        assert runtime.counters["cancel_failures"] == 0
        assert runtime.entry_blocks == {}

        runtime.halt_new_orders(reason="test: no fresh entries, only the old stop could act")
        market.advance()
        await runtime._cycle_once()  # the market close fills on this bar
        assert runtime._open_trade is None
        assert await execution.get_positions() == {}
        # Bars through the old stop level: the cancelled stop produces no fill.
        for _ in range(5):
            market.advance()
            await runtime._cycle_once()
        assert await execution.get_positions() == {}, "no position the other way"
        assert await working(execution, OrderType.STOP) == []
        assert (await execution.get_order(stop_id)).fills == []
    finally:
        await runtime.stop()


async def test_a_trailing_replacement_leaves_exactly_one_stop_in_the_engine() -> None:
    runtime, execution, market, _clock = build(trail_atr_multiple=2.0, breakeven_after_r=0.0)
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        entry = runtime._open_trade["price"]
        long = runtime._open_trade["side"].value == "buy"
        runtime._planned_exit["stop"] = entry * (0.90 if long else 1.10)
        runtime._planned_exit["initial_stop"] = runtime._planned_exit["stop"]
        runtime._last_atr = entry * 0.0001
        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["stops_tightened"] >= 1
        stops = await working(execution, OrderType.STOP)
        assert len(stops) == 1, f"one stop resting, found {len(stops)}"
        assert len([r for r in resting(execution) if r == stops[0].order_id]) == 1
        assert runtime.counters["cancel_failures"] == 0
    finally:
        await runtime.stop()


async def test_an_expired_resting_entry_is_cancelled_in_the_engine_and_never_fills_later() -> None:
    runtime, execution, market, _clock = build(entry_order_type="limit", entry_limit_timeout_bars=1)
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        # Make every resting entry unfillable: the limit sits far from the market.
        runtime._limit_price_for = lambda side, reference: reference * (0.5 if side.value == "buy" else 2.0)  # type: ignore[assignment]
        expired_ids: list[str] = []
        for _ in range(300):
            if runtime._resting is not None:
                candidate = runtime._resting["order_id"]
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders_expired"] >= 1:
                expired_ids.append(candidate)
                break
        assert runtime.counters["orders_expired"] >= 1 and expired_ids
        expired = await execution.get_order(expired_ids[0])
        assert expired.state is OrderState.CANCELLED, "the engine cancelled the expired entry"
        assert expired_ids[0] not in resting(execution)
        assert runtime.counters["cancel_failures"] == 0
        runtime._limit_price_for = lambda side, reference: reference  # type: ignore[assignment]
        runtime.halt_new_orders(reason="test: only the expired order could fill from here")
        for _ in range(20):
            market.advance()
            await runtime._cycle_once()
        assert expired.fills == [], "a cancelled entry never fills on later bars"
    finally:
        await runtime.stop()


async def test_the_deadline_cancels_a_resting_entry_in_the_engine() -> None:
    runtime, execution, market, clock = build(entry_order_type="limit", entry_limit_timeout_bars=60)
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
    runtime._session_deadline = clock.now()
    market.advance()
    await runtime._cycle_once()
    assert (await execution.get_order(resting_id)).state is OrderState.CANCELLED
    assert resting_id not in resting(execution)
    assert runtime.counters["deadline_cancelled"] == 1
    if runtime._stop_requested:
        await runtime._finalize_stop()
    assert runtime.state is LiveState.STOPPED


async def test_emergency_flatten_cancels_the_stop_and_closes_through_the_engine() -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    await open_position(runtime, market)
    market.advance()
    await runtime._cycle_once()
    assert len(await working(execution, OrderType.STOP)) == 1
    result = await runtime.emergency_flatten(reason="drill", actor="operator")
    assert result["cancelled_orders"] == 1
    assert await working(execution, OrderType.STOP) == []
    assert runtime.counters["cancel_failures"] == 0
    market.advance()
    await runtime._cycle_once()  # SAFE_MODE/CANCEL_ONLY: the cycle returns early
    execution.on_bar(market._candles[market.cursor - 1])  # the venue still matches the bar
    assert await execution.get_positions() == {}
    assert runtime.state is LiveState.CANCEL_ONLY


# --------------------------------------------------------------- a cancel that fails


async def test_a_cancel_the_venue_does_not_confirm_blocks_entries_and_keeps_the_stop_tracked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression guard for the original defect: if cancels fail again, the runtime
    must not believe them. It keeps tracking the stop, sends no close on top of it, and
    refuses new entries until a cancel succeeds."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        stop = (await working(execution, OrderType.STOP))[0]

        async def broken_cancel(order_id: str):  # type: ignore[no-untyped-def]
            raise DuplicateOrderError(f"unknown order {order_id}", order_id=order_id)

        monkeypatch.setattr(execution, "cancel_order", broken_cancel)
        assert await runtime._close_position("time stop") is False, "no close on top of a live stop"
        assert runtime._protective is not None and runtime._protective["order_id"] == stop.order_id
        assert runtime.counters["cancel_failures"] == 1
        assert "orders_unverified" in runtime.entry_blocks
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        assert runtime._pending_exit is None
        assert stop.order_id in resting(execution), "the stop is still resting, and still known"

        monkeypatch.undo()
        assert await runtime._close_position("time stop") is True, "a confirmed cancel lets the close through"
        assert "orders_unverified" not in runtime.entry_blocks
    finally:
        await runtime.stop()
