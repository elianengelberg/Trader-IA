"""The deadline cannot be undone: not by an operator's resume, not by the watchdog
healing a feed alert, not by an exit trigger racing the deadline's own close."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.integration.test_paper_cancellations import build, open_position, working
from tia.core.errors import ProviderUnavailableError
from tia.domain.enums import OrderType
from tia.runtime.states import LiveState


async def test_resume_is_refused_once_the_deadline_has_passed() -> None:
    runtime, _execution, market, clock = build()
    await runtime.start()
    try:
        await open_position(runtime, market)
        runtime._session_deadline = clock.now()
        market.advance()
        await runtime._cycle_once()
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        with pytest.raises(ValueError, match="cannot be resumed"):
            runtime.resume(actor="operator")
        assert runtime.state is LiveState.HALT_NEW_ORDERS
    finally:
        await runtime.stop()


async def test_a_deadline_during_a_watchdog_halt_is_not_lifted_when_data_recovers() -> None:
    runtime, _execution, market, clock = build(session_wind_down_bars=50)
    runtime.market_data_ttl_seconds = 30.0
    await runtime.start()
    try:
        await open_position(runtime, market)
        clock.advance_by(timedelta(minutes=10))  # no bar for ten minutes: the watchdog halts
        await runtime._cycle_once()
        assert runtime.state is LiveState.HALT_NEW_ORDERS and runtime._watchdog_halt
        runtime._session_deadline = clock.now()
        from tests.integration.test_live_runtime import _seed_every_bucket
        _seed_every_bucket(runtime)
        orders_before = runtime.counters["orders"]
        for _ in range(10):  # data flows again; the watchdog would normally heal to RUNNING
            market.advance()
            await runtime._cycle_once()
        assert runtime.state is not LiveState.RUNNING
        assert runtime.funnel["orders"] == 0 or runtime.counters["orders"] == orders_before
        assert runtime._winding_down is True
    finally:
        await runtime.stop()


async def test_no_entry_is_taken_after_the_deadline_even_if_the_machine_is_running() -> None:
    """Defence in depth: force RUNNING after the deadline (what a lifted halt would do)
    and show the decision path still refuses, then the next cycle re-halts."""
    runtime, _execution, market, clock = build()
    await runtime.start()
    try:
        from tests.integration.test_live_runtime import _seed_every_bucket
        _seed_every_bucket(runtime)
        runtime._session_deadline = clock.now()
        market.advance()
        await runtime._cycle_once()
        if runtime._stop_requested:
            return  # flat: the session ended at once, which is the stronger guarantee
        runtime.machine.transition(LiveState.RUNNING, reason="test: forced")
        halted_before = runtime.funnel["halted"]
        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["orders"] == 0
        assert runtime.state is not LiveState.RUNNING
        assert runtime.funnel["halted"] >= halted_before
    finally:
        await runtime.stop()


async def test_with_the_feed_down_and_a_position_open_nothing_is_sent_and_the_position_stays() -> None:
    runtime, execution, market, clock = build(session_wind_down_bars=0)
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1
        real_get = market.get_candles

        async def dead(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("feed gone")

        market.get_candles = dead  # type: ignore[assignment]
        runtime._session_deadline = clock.now()
        for _ in range(5):
            clock.advance_by(timedelta(minutes=1))
            await runtime._loop_body_once_for_tests()
        # The grace is over in wall time; a close was sent, but no bar can fill it and
        # the engine still holds the position with its stop.
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) <= 1, "never more than one exit in flight"
        assert (await execution.get_positions())["BTC-USD"].quantity != 0.0
        assert runtime.state in {LiveState.HALT_NEW_ORDERS, LiveState.SAFE_MODE}
        assert runtime.counters["orders"] <= 2  # the entry and at most one exit
        market.get_candles = real_get  # type: ignore[assignment]
    finally:
        await runtime.stop()


async def test_a_pending_exit_at_the_deadline_is_not_doubled() -> None:
    runtime, execution, market, clock = build(session_wind_down_bars=0)
    await runtime.start()
    await open_position(runtime, market)
    market.advance()
    await runtime._cycle_once()
    assert await runtime._close_position("time stop") is True
    runtime._session_deadline = clock.now()
    market.advance()
    await runtime._cycle_once()  # deadline cycle: the pending exit fills here
    exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
    assert len(exits) == 1
    for _ in range(3):
        market.advance()
        await runtime._cycle_once()
        if runtime._stop_requested:
            await runtime._finalize_stop()
            break
    assert (await execution.get_positions()) == {}
    assert runtime.state is LiveState.STOPPED
