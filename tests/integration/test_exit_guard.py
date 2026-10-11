"""At most one exit in flight per position — against the real paper engine.

The audit reproduced a long position turned short: the deadline's close and a time stop
fired in one cycle, both filled on the next bar. Every case here ends by reading the
engine's own book: position sign and size, and which orders still rest.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.test_paper_cancellations import build, open_position, working
from tia.core.errors import ReconciliationError
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Order
from tia.execution.state_machine import transition
from tia.runtime.states import LiveState


async def _settle_bars(runtime, market, n: int) -> None:  # type: ignore[no-untyped-def]
    for _ in range(n):
        market.advance()
        await runtime._cycle_once()
        if runtime._stop_requested:
            await runtime._finalize_stop()
            return


async def _book(execution) -> tuple[float, list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
    positions = await execution.get_positions()
    qty = positions["BTC-USD"].quantity if "BTC-USD" in positions else 0.0
    open_orders = [(o.signal_id, o.state.value) for o in await execution.get_orders(open_only=True)]
    return qty, open_orders


# ------------------------------------------------------------- two triggers, one exit


async def test_deadline_and_time_stop_in_the_same_cycle_send_one_exit_and_the_book_ends_flat() -> None:
    runtime, execution, market, clock = build(max_holding_bars=1, session_wind_down_bars=0)
    await runtime.start()
    await open_position(runtime, market)
    before = (await execution.get_positions())["BTC-USD"].quantity
    runtime._session_deadline = clock.now()
    market.advance()
    await runtime._cycle_once()
    exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
    assert len(exits) == 1, [o.signal_id for o in exits]
    assert runtime.counters["exits_skipped_pending"] >= 1
    assert runtime._pending_exit is not None and runtime._pending_exit["reason"] == "session deadline"
    await _settle_bars(runtime, market, 4)
    qty, open_orders = await _book(execution)
    assert qty == 0.0, f"flat, not {qty} (was {before})"
    assert open_orders == []
    assert runtime.counters["round_trips"] == 1
    assert runtime.state is LiveState.STOPPED


async def test_deadline_and_target_in_the_same_cycle_send_one_exit() -> None:
    runtime, execution, market, clock = build(session_wind_down_bars=0)
    await runtime.start()
    await open_position(runtime, market)
    entry = runtime._open_trade["price"]
    long = runtime._open_trade["side"] is Side.BUY
    # A target the very next bar reaches for certain.
    runtime._planned_exit["target"] = entry * (0.5 if long else 2.0)
    runtime._session_deadline = clock.now()
    market.advance()
    await runtime._cycle_once()
    exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
    assert len(exits) == 1, [o.signal_id for o in exits]
    await _settle_bars(runtime, market, 4)
    qty, open_orders = await _book(execution)
    assert qty == 0.0 and open_orders == []
    assert runtime.state is LiveState.STOPPED


async def test_two_concurrent_close_callbacks_send_one_exit() -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        sent = await asyncio.gather(
            runtime._close_position("time stop"), runtime._close_position("target reached")
        )
        assert sorted(sent) == [False, True]
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1
        assert runtime.counters["exits_skipped_pending"] == 1
        market.advance()
        await runtime._cycle_once()
        qty, open_orders = await _book(execution)
        assert qty == 0.0 and open_orders == []
    finally:
        await runtime.stop()


# ------------------------------------------------------------- the exit's own fate


async def test_a_partially_filled_exit_keeps_the_pending_state_until_it_completes() -> None:
    """The participation cap fills the close over several bars. No second exit is sent
    meanwhile, the round trip is scored only when the position is flat, and the book
    never goes the other way."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        held = (await execution.get_positions())["BTC-USD"].quantity
        # Cap the engine so each bar can fill at most ~40 % of the position.
        volume = market._candles[market.cursor].volume
        execution._config = execution._config.model_copy(
            update={"max_participation_rate": max(1e-6, abs(held) * 0.4 / max(volume, 1e-9))}
        )
        assert await runtime._close_position("time stop") is True
        runtime.halt_new_orders(reason="test: no fresh entries while the exit works")
        pending_id = runtime._pending_exit["order_id"]
        market.advance()
        await runtime._cycle_once()  # first partial
        assert runtime._pending_exit is not None and runtime._pending_exit["order_id"] == pending_id
        assert runtime._open_trade is not None, "not flat yet: not scored yet"
        assert await runtime._close_position("target reached") is False, "no second exit while one works"
        for _ in range(6):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is None:
                break
        qty, open_orders = await _book(execution)
        assert qty == 0.0 and open_orders == []
        assert runtime._pending_exit is None
        assert runtime.counters["round_trips"] == 1
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1 and exits[0].state is OrderState.FILLED
    finally:
        await runtime.stop()


async def test_a_rejected_exit_leaves_the_position_tracked_and_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        real_submit = execution.submit_order

        async def reject_once(intent):  # type: ignore[no-untyped-def]
            monkeypatch.setattr(execution, "submit_order", real_submit)
            order = await real_submit(intent)
            transition(order, OrderState.CANCEL_REQUESTED, at=clock.now())
            transition(order, OrderState.CANCELLED, at=clock.now(), reason="simulated venue rejection")
            order.reject_reason = "simulated venue rejection"
            if order.order_id in execution._resting:
                execution._resting.remove(order.order_id)
            return order

        monkeypatch.setattr(execution, "submit_order", reject_once)
        assert await runtime._close_position("time stop") is True  # sent, then rejected
        assert runtime._pending_exit is None
        assert runtime.counters["exits_rejected"] == 1
        assert runtime._open_trade is not None
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1, "re-protected on the next bar"
        qty, _ = await _book(execution)
        assert qty != 0.0, "the position is still there"
        # A later trigger closes it normally.
        assert await runtime._close_position("time stop") is True
        market.advance()
        await runtime._cycle_once()
        qty, open_orders = await _book(execution)
        assert qty == 0.0 and open_orders == []
    finally:
        await runtime.stop()


async def test_an_exit_whose_result_is_unknown_and_unresolvable_blocks_entries_until_the_venue_agrees(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()

        async def timeout(intent):  # type: ignore[no-untyped-def]
            raise ReconciliationError("timeout", path="/order")

        monkeypatch.setattr(execution, "submit_order", timeout)
        assert await runtime._close_position("time stop") is False
        assert "position_unverified" in runtime.entry_blocks
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        assert runtime._pending_exit is None
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert exits == [], "nothing was sent blind"
        monkeypatch.undo()
        # The venue's position is read again and agrees with the tracked leg: unblocked.
        market.advance()
        await runtime._cycle_once()
        assert "position_unverified" not in runtime.entry_blocks
    finally:
        await runtime.stop()


async def test_an_unknown_exit_resolved_as_present_is_adopted_not_resent(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        real_submit = execution.submit_order
        placed: list[Order] = []

        async def placed_then_timeout(intent):  # type: ignore[no-untyped-def]
            placed.append(await real_submit(intent))
            raise ReconciliationError("timeout after the venue took it", path="/order")

        async def resolver(*, symbol, client_order_id):  # type: ignore[no-untyped-def]
            return await execution.get_order(client_order_id)

        monkeypatch.setattr(execution, "submit_order", placed_then_timeout)
        monkeypatch.setattr(execution, "resolve_unknown_order", resolver, raising=False)
        assert await runtime._close_position("time stop") is True
        assert runtime._pending_exit is not None and runtime._pending_exit["order_id"] == placed[0].order_id
        monkeypatch.undo()
        assert await runtime._close_position("target reached") is False
        market.advance()
        await runtime._cycle_once()
        qty, open_orders = await _book(execution)
        assert qty == 0.0 and open_orders == []
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1
    finally:
        await runtime.stop()


async def test_a_position_the_runtime_does_not_track_blocks_entries_and_sends_nothing() -> None:
    """A fill the runtime never saw (here: a position planted straight in the engine).
    Nothing is sent on it and no entry is opened until the venue's view is reconciled."""
    runtime, execution, market, clock = build()
    await runtime.start()
    try:
        from tia.domain.orders import Fill

        market.advance()
        await runtime._cycle_once()
        # A fill that reached the venue's books but never the runtime (the engine routes
        # its own bar fills to the runtime, so plant it straight into the portfolio).
        execution._portfolio.apply_fill(Fill(
            fill_id="planted-fill", order_id="planted-order", sequence=0, symbol="BTC-USD",
            side=Side.BUY, quantity=0.002, price=50_000.0, fee=0.75, filled_at=clock.now(),
        ))
        assert (await execution.get_positions())["BTC-USD"].quantity == pytest.approx(0.002)
        market.advance()
        await runtime._cycle_once()
        assert "position_unverified" in runtime.entry_blocks
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        for _ in range(5):
            market.advance()
            await runtime._cycle_once()
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert exits == [], "nothing is sent on a position the runtime cannot vouch for"
        assert (await execution.get_positions())["BTC-USD"].quantity == pytest.approx(0.002)
    finally:
        await runtime.stop()
