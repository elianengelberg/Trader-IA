"""Order integrity against the REAL paper engine (Phase 1.3, Stage A: G1-G4, G6).

Each case here is a route through which a session could end up with two resting stops,
a stop nothing tracked, a close sent over a position the stop had just taken out, an
exit that could never be re-sent, or a client id that repeats across restarts. Every
case ends by reading the engine's own book.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.test_paper_cancellations import build, open_position, resting, working
from tia.core.errors import DuplicateOrderError, ProviderUnavailableError
from tia.domain.enums import OrderState, OrderType
from tia.risk.restore import is_entry_signal_id
from tia.runtime.live import UNKNOWN_POLLS_BEFORE_LOST
from tia.runtime.states import LiveState


def _record(runtime) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    """Capture the incidents a runtime records (the engine-only ``build`` has no store)."""
    incidents: list[dict[str, Any]] = []

    def persist(kind: str, payload: dict[str, Any]) -> None:
        if kind == "incident":
            incidents.append(payload)

    runtime._persist = persist
    return incidents


async def _position_with_stop(runtime, execution, market):  # type: ignore[no-untyped-def]
    await open_position(runtime, market)
    market.advance()
    await runtime._cycle_once()
    stops = await working(execution, OrderType.STOP)
    assert len(stops) == 1, "one protective stop resting in the engine"
    return stops[0]


def _break_cancel(monkeypatch: pytest.MonkeyPatch, execution) -> None:  # type: ignore[no-untyped-def]
    async def broken_cancel(order_id: str):  # type: ignore[no-untyped-def]
        raise DuplicateOrderError(f"venue refused cancel of {order_id}", order_id=order_id)

    monkeypatch.setattr(execution, "cancel_order", broken_cancel)


# ------------------------------------------------------------ G1: replacing a stop


async def test_a_stop_replacement_whose_cancel_fails_places_no_second_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing wants a tighter stop; the venue refuses to cancel the old one. Before 1.3
    the new stop was placed anyway and the record overwritten, so two stops rested and
    only one was known."""
    runtime, execution, market, _clock = build(trail_atr_multiple=2.0, breakeven_after_r=0.0)
    await runtime.start()
    try:
        first = await _position_with_stop(runtime, execution, market)
        entry = runtime._open_trade["price"]
        long = runtime._open_trade["side"].value == "buy"
        runtime._planned_exit["stop"] = entry * (0.90 if long else 1.10)
        runtime._planned_exit["initial_stop"] = runtime._planned_exit["stop"]
        runtime._last_atr = entry * 0.0001
        _break_cancel(monkeypatch, execution)
        market.advance()
        await runtime._cycle_once()
        stops = await working(execution, OrderType.STOP)
        assert [s.order_id for s in stops] == [first.order_id], "exactly the old stop rests"
        assert runtime._protective is not None and runtime._protective["order_id"] == first.order_id
        assert runtime.counters["cancel_failures"] >= 1
        assert "orders_unverified" in runtime.entry_blocks

        monkeypatch.undo()
        market.advance()
        await runtime._cycle_once()
        stops = await working(execution, OrderType.STOP)
        assert len(stops) == 1, "once the cancel goes through, the replacement — one stop"
        assert stops[0].order_id != first.order_id
        assert (await execution.get_order(first.order_id)).state is OrderState.CANCELLED
        assert runtime._protective["order_id"] == stops[0].order_id
    finally:
        await runtime.stop()


# ------------------------------------------------- G3: the venue cannot be asked


async def test_a_venue_that_cannot_be_read_keeps_the_stop_tracked_and_places_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient read failure is not "the stop is gone". Before 1.3 the poller dropped
    the record on any exception and the next cycle placed a fresh stop on top of the one
    still resting."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        first = await _position_with_stop(runtime, execution, market)

        async def unreachable(order_id: str):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("venue unreachable", provider="paper")

        monkeypatch.setattr(execution, "get_order", unreachable)
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
        assert [s.order_id for s in await working(execution, OrderType.STOP)] == [first.order_id]
        assert runtime._protective is not None and runtime._protective["order_id"] == first.order_id
        assert runtime.counters["order_poll_failures"] >= 3
        assert runtime.counters["orders_lost"] == 0

        monkeypatch.undo()
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1, "still exactly one stop"
    finally:
        await runtime.stop()


async def test_a_resting_entry_the_venue_does_not_know_is_kept_then_given_up_with_an_incident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, execution, market, _clock = build(entry_order_type="limit", entry_limit_timeout_bars=60)
    incidents = _record(runtime)
    await runtime.start()
    try:
        from tests.integration.test_live_runtime import _seed_every_bucket

        _seed_every_bucket(runtime)
        runtime._limit_price_for = lambda side, reference: reference * (0.5 if side.value == "buy" else 2.0)  # type: ignore[assignment]
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime._resting is not None:
                break
        assert runtime._resting is not None
        resting_id = runtime._resting["order_id"]
        # The venue answers, and says it does not know the order.
        real_get = execution.get_order

        async def unknown(order_id: str):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(execution, "get_order", unknown)
        for n in range(1, UNKNOWN_POLLS_BEFORE_LOST):
            market.advance()
            await runtime._cycle_once()
            assert runtime._resting is not None, f"kept after {n} unknown poll(s)"
            assert "orders_unverified" in runtime.entry_blocks
        market.advance()
        await runtime._cycle_once()
        assert runtime._resting is None, "given up after the threshold"
        assert runtime.counters["orders_lost"] == 1
        assert [i["kind"] for i in incidents if i["kind"].endswith("_lost")] == ["resting_order_lost"]
        assert "orders_unverified" in runtime.entry_blocks, "entries stay blocked"
        monkeypatch.setattr(execution, "get_order", real_get)
        assert (await execution.get_order(resting_id)) is not None, "the engine still holds it"
    finally:
        await runtime.stop()


async def test_an_exit_the_venue_never_accepted_is_given_up_and_the_position_can_be_closed_again() -> None:
    """Before 1.3 an exit unknown to the venue blocked entries *and* every later exit:
    the pending record was never cleared, so the position could not be closed at all."""
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    try:
        await _position_with_stop(runtime, execution, market)
        held = (await execution.get_positions())["BTC-USD"].quantity
        assert await runtime._close_position("time stop") is True
        pending = runtime._pending_exit
        assert pending is not None
        # The submission was acknowledged locally but never reached the venue's book.
        execution._resting.remove(pending["order_id"])
        execution._orders.pop(pending["order_id"])
        execution._by_client_id.pop(pending["client_order_id"])
        runtime.halt_new_orders(reason="test: only the exit may act")

        assert UNKNOWN_POLLS_BEFORE_LOST == 3, "the steps below count polls one by one"
        market.advance()
        await runtime._cycle_once()  # poll 1: the cycle's own
        assert runtime._pending_exit is not None and "position_unverified" in runtime.entry_blocks
        assert await runtime._close_position("target reached") is False, "nothing on top of it"  # poll 2
        assert runtime._pending_exit is not None, "still pending after two unknown answers"
        market.advance()
        await runtime._cycle_once()  # poll 3: given up
        assert runtime._pending_exit is None, "given up"
        assert [i["kind"] for i in incidents if i["kind"] == "exit_lost"] == ["exit_lost"]
        assert (await execution.get_positions())["BTC-USD"].quantity == pytest.approx(held)
        assert runtime._open_trade is not None, "the round trip is still open"

        # The next exit trigger closes the position that is still there.
        assert await runtime._close_position("time stop") is True
        market.advance()
        await runtime._cycle_once()
        assert await execution.get_positions() == {}
        assert runtime._open_trade is None and runtime.counters["round_trips"] == 1
        assert runtime._pending_exit is None
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1 and exits[0].state is OrderState.FILLED
    finally:
        await runtime.stop()


# ------------------------------------------ G4: the cancel finds the stop filled


async def test_a_close_whose_cancel_finds_the_stop_already_filled_sends_no_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The race a real venue has: the stop fills in the moment between the decision to
    close and the cancel arriving. The cancel answers with the FILLED order. Before 1.3
    that counted as "cancelled", the fills were not booked, and a full-size market close
    went out over a flat position."""
    runtime, execution, market, _clock = build()
    await runtime.start()
    try:
        stop = await _position_with_stop(runtime, execution, market)
        held = (await execution.get_positions())["BTC-USD"].quantity
        long = held > 0
        real_cancel = execution.cancel_order

        async def cancel_after_the_stop_fired(order_id: str):  # type: ignore[no-untyped-def]
            # The venue matched the stop against the tape just before the cancel landed.
            candle = market._candles[market.cursor]
            level = float(stop.stop_price)
            through = candle.model_copy(update={
                "open": level * (0.995 if long else 1.005),
                "high": max(candle.high, level * 1.01),
                "low": min(candle.low, level * 0.99),
                "close": level * (0.995 if long else 1.005),
            })
            execution.on_bar(through)
            return await real_cancel(order_id)

        monkeypatch.setattr(execution, "cancel_order", cancel_after_the_stop_fired)
        assert await runtime._close_position("time stop") is False, "nothing to close: the stop did"
        assert stop.state is OrderState.FILLED
        assert await execution.get_positions() == {}, "flat — and not the other way"
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert exits == [], "no market close was sent"
        assert runtime._open_trade is None, "the stop's fill closed and scored the round trip"
        assert runtime.counters["round_trips"] == 1 and runtime.counters["exits_stop"] == 1
        assert runtime._protective is None and runtime._pending_exit is None
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()


# -------------------------------------------------- G2: cancel-all and flatten


async def test_a_flatten_whose_cancels_fail_keeps_the_stop_tracked_and_sends_no_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before 1.3 ``_cancel_all_open`` forgot the stop before cancelling it: a refused
    cancel left it resting untracked, and the flatten's market close went out on top."""
    runtime, execution, market, _clock = build()
    incidents = _record(runtime)
    await runtime.start()
    stop = await _position_with_stop(runtime, execution, market)
    held = (await execution.get_positions())["BTC-USD"].quantity
    _break_cancel(monkeypatch, execution)
    result = await runtime.emergency_flatten(reason="drill", actor="operator")
    assert result["cancelled_orders"] == 0
    assert result["closing_orders"] == [
        {"symbol": "BTC-USD", "quantity": abs(held), "state": "not sent (protective stop cancel unconfirmed)"}
    ]
    assert runtime._protective is not None and runtime._protective["order_id"] == stop.order_id
    assert stop.order_id in resting(execution)
    exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
    assert exits == [], "no close over a stop that may still rest"
    flatten = [i for i in incidents if i["kind"] == "emergency_flatten"]
    assert flatten and flatten[0]["detail"]["unconfirmed_cancels"] == [stop.client_order_id]
    assert runtime.state is LiveState.CANCEL_ONLY

    # The venue recovers: the operator's second flatten cancels, then closes.
    monkeypatch.undo()
    result = await runtime.emergency_flatten(reason="drill, again", actor="operator")
    assert result["cancelled_orders"] == 1
    assert result["closing_orders"][0]["state"] in {"acknowledged", "filled"}
    assert runtime._protective is None
    assert stop.state is OrderState.CANCELLED
    execution.on_bar(market._candles[market.cursor])
    assert await execution.get_positions() == {}


async def test_the_kill_switch_keeps_tracking_an_order_the_venue_did_not_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, execution, market, _clock = build()
    await runtime.start()
    stop = await _position_with_stop(runtime, execution, market)
    _break_cancel(monkeypatch, execution)
    result = await runtime.kill_switch(reason="drill", actor="operator")
    assert result["cancelled_orders"] == 0
    assert runtime._protective is not None and runtime._protective["order_id"] == stop.order_id
    assert runtime._unconfirmed_cancels == [stop.client_order_id]
    assert runtime.state is LiveState.SAFE_MODE
    monkeypatch.undo()
    await runtime.stop()


# ------------------------------------------- G6: client ids across sessions


async def test_exit_and_stop_client_ids_differ_between_two_sessions_at_the_same_bar() -> None:
    """Two sessions over the same series open the same position on the same bar count
    and close it for the same reason. Before 1.3 their exits and stops carried the same
    client id (the bar counter restarts per session), which re-keyed the earlier
    session's order row and would be a duplicate at a real venue."""
    ids: list[tuple[str, str, str, str]] = []
    for _ in range(2):
        runtime, execution, market, _clock = build()
        await runtime.start()
        try:
            stop = await _position_with_stop(runtime, execution, market)
            assert await runtime._close_position("time stop") is True
            exit_order = next(o for o in await execution.get_orders() if o.signal_id.startswith("exit:"))
            ids.append((runtime.run_id, stop.client_order_id, exit_order.client_order_id, exit_order.signal_id))
        finally:
            await runtime.stop()
    (run_a, stop_a, exit_a, sig_a), (run_b, stop_b, exit_b, sig_b) = ids
    assert run_a != run_b
    assert stop_a != stop_b, "protective stops of different sessions never share a client id"
    assert exit_a != exit_b, "nor do their exits"
    assert sig_a.startswith("exit:time-stop:") and sig_b.startswith("exit:time-stop:")
    assert not is_entry_signal_id(sig_a), "still classified as an exit by the risk rebuild"
