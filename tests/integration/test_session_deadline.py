"""A validation session ends itself: the deadline is enforced inside the loop.

Every scenario the operating rules name: the clock runs out while flat, while a position
is open, while the feed is down or stale, while the session is in SAFE_MODE, while
persistence fails, and after a restart under the interrupted session's deadline. The
stop is idempotent and never starts a second session. The clock is the simulated clock
the fake feed advances one bar per ``advance()``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.integration.test_live_runtime import (
    FakeExecution,
    FakeMarketData,
    _open_a_position,
    _seed_every_bucket,
    live_settings,
)
from tia.core.clock import SimulatedClock
from tia.core.errors import InvalidStateTransitionError, ProviderUnavailableError
from tia.domain.enums import OrderType
from tia.runtime.live import LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario
from tia.runtime.states import LiveState


def build(  # type: ignore[no-untyped-def]
    *, persist=None, session_deadline: datetime | None = None, market_cls: type = FakeMarketData,
    **live_overrides: Any,
):
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = market_cls(candles, clock)
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(**live_overrides), activation=None, market_data=market,
        execution=execution, clock=clock, persist=persist, poll_interval_seconds=0.0,
        session_deadline=session_deadline,
    )
    return runtime, execution, market, clock


async def _drive(runtime: LiveRuntime, market: FakeMarketData, bars: int) -> None:
    for _ in range(bars):
        if runtime.state.is_terminal:
            return
        market.advance()
        await runtime._cycle_once()
        if runtime._stop_requested:
            # What the loop task does after an iteration that asked it to stop.
            await runtime._finalize_stop()
            return


def _incidents(saved: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [p["kind"] for k, p in saved if k == "incident"]


# ------------------------------------------------------------------ the normal end


async def test_the_configured_span_becomes_a_deadline_at_start_and_ends_the_session_flat() -> None:
    """``session_max_hours`` measured from start: 2 bars in, the session halts entries,
    reconciles, stamps its run row and lands in STOPPED — from inside its own loop."""
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market, clock = build(
        persist=lambda k, p: saved.append((k, p)), session_max_hours=2 / 60,
    )
    await runtime.start()
    assert runtime.session_deadline == pytest.approx(clock.now() + timedelta(minutes=2), abs=timedelta(seconds=1))
    assert runtime.snapshot()["session"]["deadline_at"] is not None
    await _drive(runtime, market, 6)
    assert runtime.state is LiveState.STOPPED
    assert runtime.is_running is False
    assert "session deadline" in runtime.session_report()["stop_reason"]
    assert execution.submissions == 0
    kinds = _incidents(saved)
    assert "session_deadline" in kinds and "session_completed" in kinds
    stamps = [p for k, p in saved if k == "run_stop"]
    assert len(stamps) == 1 and stamps[0]["run_id"] == runtime.run_id
    assert any(k == "reconciliation" for k, _ in saved), "the end reconciles"
    history = [c["to"] for c in runtime.machine.as_dict()["history"]]
    assert history[-3:] == ["halt_new_orders", "stopping", "stopped"]


async def test_an_explicit_deadline_wins_over_the_configured_span() -> None:
    _probe, _, _, probe_clock = build()
    explicit = probe_clock.now() + timedelta(minutes=1)
    runtime, _, market, _ = build(session_deadline=explicit, session_max_hours=5.0)
    await runtime.start()
    assert runtime.session_deadline == explicit
    assert runtime.session_report()["max_hours"] is None
    await _drive(runtime, market, 5)
    assert runtime.state is LiveState.STOPPED


async def test_without_a_deadline_the_session_runs_on_as_the_24_7_one_does() -> None:
    runtime, _, market, _ = build()
    await runtime.start()
    try:
        assert runtime.session_deadline is None
        await _drive(runtime, market, 20)
        assert runtime.state in {LiveState.RUNNING, LiveState.HALT_NEW_ORDERS}
        assert runtime.snapshot()["session"]["deadline_at"] is None
    finally:
        await runtime.stop()


# ------------------------------------------------------------- stop is idempotent


async def test_stop_is_idempotent_before_and_after_the_deadline_ended_the_session() -> None:
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, _, market, _ = build(persist=lambda k, p: saved.append((k, p)), session_max_hours=1 / 60)
    await runtime.start()
    await _drive(runtime, market, 4)
    assert runtime.state is LiveState.STOPPED
    await runtime.stop()
    await runtime.stop(reason="again")
    assert runtime.state is LiveState.STOPPED
    assert len([1 for k, _ in saved if k == "run_stop"]) == 1, "stamped once"
    with pytest.raises(InvalidStateTransitionError):
        await runtime.start()  # the end of a session never starts another


async def test_an_operator_stop_twice_is_one_stop() -> None:
    runtime, _, _, _ = build()
    await runtime.start()
    await runtime.stop()
    await runtime.stop()
    assert runtime.state is LiveState.STOPPED
    assert runtime.machine.as_dict()["history"][-1]["to"] == "stopped"


# ------------------------------------------------------------ an open position


async def test_a_position_open_at_the_deadline_is_managed_through_the_grace_then_closed_and_the_session_ends() -> None:
    """No entries after the deadline; the position keeps its protective stop while the
    grace runs; then it is closed through the time-stop path (stop cancelled first,
    reduce-only market order, round trip scored) and the session stops. The stop was
    never cancelled on its own."""
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market, clock = build(
        persist=lambda k, p: saved.append((k, p)), session_wind_down_bars=3,
    )
    await runtime.start()
    await _open_a_position(runtime, execution, market)
    market.advance()
    await runtime._cycle_once()  # the protective stop is placed on the next bar
    stops = [o for o in execution.orders.values() if o.order_type is OrderType.STOP and not o.state.is_terminal]
    assert len(stops) == 1
    # Keep the position from leaving on its own rules during the grace.
    runtime._planned_exit["target"] = None
    runtime._planned_exit["stop"] = runtime._open_trade["price"] * (0.5 if runtime._open_trade["side"].value == "buy" else 1.5)

    runtime._session_deadline = clock.now()  # the clock ran out now
    sent_before = execution.submissions
    market.advance()
    await runtime._cycle_once()
    assert runtime.state is LiveState.HALT_NEW_ORDERS
    assert runtime._open_trade is not None
    assert runtime.session_report()["winding_down"] is True
    assert "session_deadline" in _incidents(saved)
    # During the grace: still protected, nothing closed.
    for _ in range(2):
        market.advance()
        await runtime._cycle_once()
    assert runtime._open_trade is not None
    assert any(o.order_type is OrderType.STOP and not o.state.is_terminal for o in execution.orders.values())
    assert runtime.counters["exits_deadline"] == 0
    # Grace over: closed at market, scored, session ends.
    await _drive(runtime, market, 6)
    assert runtime.counters["exits_deadline"] == 1
    assert runtime._open_trade is None
    assert runtime.counters["round_trips"] == 1
    assert execution.submissions > sent_before
    assert runtime.state is LiveState.STOPPED
    assert [k for k, _ in saved if k == "edge_outcome"], "the closed round trip is evidence"


async def test_a_resting_entry_is_cancelled_at_the_deadline_but_an_entry_is_never_abandoned_half_filled() -> None:
    runtime, execution, market, clock = build(entry_order_type="limit")
    execution.rest_limits = True
    await runtime.start()
    _seed_every_bucket(runtime)
    for _ in range(300):
        market.advance()
        await runtime._cycle_once()
        if runtime._resting is not None:
            break
    assert runtime._resting is not None, "an entry is resting"
    resting_id = runtime._resting["order_id"]
    runtime._session_deadline = clock.now()
    await _drive(runtime, market, 3)
    assert resting_id in execution.cancelled
    assert runtime.counters["deadline_cancelled"] == 1
    assert runtime.state is LiveState.STOPPED


# ------------------------------------------------ feed down, stale data, errors


class FlakyThenDeadFeed(FakeMarketData):
    """Raises on every poll after ``fail_after`` advances: the feed went away."""

    fail_after = 3

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        if self.cursor >= 150 + self.fail_after:
            raise ProviderUnavailableError("feed gone")
        return await super().get_candles(symbol, timeframe, limit=limit, end=end)


async def test_the_deadline_ends_a_session_whose_feed_is_down_without_touching_a_position_it_cannot_see() -> None:
    """Feed lost → the loop's own handling halts entries; the deadline then ends the
    session when it is flat. No orders are sent into a venue nobody can see."""
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market, clock = build(
        persist=lambda k, p: saved.append((k, p)), market_cls=FlakyThenDeadFeed,
    )
    await runtime.start()
    for _ in range(6):
        market.advance()
        await runtime._loop_body_once_for_tests()
    assert runtime.state is LiveState.HALT_NEW_ORDERS, "the feed outage halted entries"
    runtime._session_deadline = clock.now()
    for _ in range(3):
        await runtime._loop_body_once_for_tests()
        if runtime._stop_requested:
            await runtime._finalize_stop()
    assert runtime.state is LiveState.STOPPED
    assert execution.submissions == 0


async def test_stale_data_halts_entries_and_the_deadline_still_ends_the_session() -> None:
    runtime, _execution, market, clock = build()
    runtime.market_data_ttl_seconds = 30.0
    await runtime.start()
    market.advance()
    await runtime._cycle_once()
    clock.advance_by(timedelta(minutes=10))  # no bar for ten minutes
    await runtime._cycle_once()
    assert runtime.state is LiveState.HALT_NEW_ORDERS
    runtime._session_deadline = clock.now()
    await _drive(runtime, market, 3)
    assert runtime.state is LiveState.STOPPED


class ExplodingFeed(FakeMarketData):
    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        if self.cursor >= 152:
            raise RuntimeError("unexpected failure inside the cycle")
        return await super().get_candles(symbol, timeframe, limit=limit, end=end)


async def test_an_unexpected_exception_puts_the_session_in_safe_mode_and_the_deadline_still_stops_it() -> None:
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market, clock = build(
        persist=lambda k, p: saved.append((k, p)), market_cls=ExplodingFeed,
    )
    await runtime.start()
    for _ in range(4):
        market.advance()
        await runtime._loop_body_once_for_tests()
    assert runtime.state is LiveState.SAFE_MODE
    runtime._session_deadline = clock.now()
    for _ in range(3):
        await runtime._loop_body_once_for_tests()
        if runtime._stop_requested:
            await runtime._finalize_stop()
    assert runtime.state is LiveState.STOPPED
    assert "session_completed" in _incidents(saved)
    assert execution.submissions == 0


async def test_in_safe_mode_with_a_position_open_the_deadline_touches_nothing_and_says_so() -> None:
    """SAFE_MODE means the state is in doubt: the deadline neither cancels the stop nor
    closes the position. After the grace the session stops with an incident naming the
    position left for an operator."""
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market, clock = build(
        persist=lambda k, p: saved.append((k, p)), session_wind_down_bars=1,
    )
    await runtime.start()
    await _open_a_position(runtime, execution, market)
    market.advance()
    await runtime._cycle_once()
    runtime.machine.transition(LiveState.SAFE_MODE, reason="test: doubt")
    sent_before = execution.submissions
    cancelled_before = list(execution.cancelled)
    runtime._session_deadline = clock.now()
    await _drive(runtime, market, 5)
    assert runtime.state is LiveState.STOPPED
    assert execution.submissions == sent_before, "nothing sent"
    assert execution.cancelled == cancelled_before, "the protective stop was not cancelled"
    assert runtime._open_trade is not None, "the position is left as it is"
    assert "session_deadline_in_safe_mode" in _incidents(saved)


async def test_persistence_failing_does_not_stop_the_session_from_ending_cleanly() -> None:
    def broken(kind: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("database gone")

    runtime, execution, market, _clock = build(persist=broken, session_max_hours=1 / 60)
    await runtime.start()
    await _drive(runtime, market, 4)
    assert runtime.state is LiveState.STOPPED
    assert execution.submissions == 0


# --------------------------------------------------------------------- restart


async def test_a_restart_under_an_expired_deadline_ends_on_its_first_cycle_without_entries() -> None:
    """The boot-time decision refuses to resume an expired run; if one were constructed
    anyway (a race, an operator), the runtime itself ends it at once."""
    long_ago = datetime(2000, 1, 1, tzinfo=UTC)  # before any bar the fake feed serves
    runtime, execution, market, _clock = build(session_deadline=long_ago)
    await runtime.start()
    await _drive(runtime, market, 3)
    assert runtime.state is LiveState.STOPPED
    assert execution.submissions == 0


async def test_a_restart_under_a_live_deadline_keeps_that_deadline() -> None:
    probe, _, _, _ = build(session_deadline=None)
    deadline = probe._clock.now() + timedelta(minutes=3)
    resumed, _execution, market, _clock = build(session_deadline=deadline, session_max_hours=8.0)
    await resumed.start()
    assert resumed.session_deadline == deadline, "no fresh eight hours"
    await _drive(resumed, market, 10)
    assert resumed.state is LiveState.STOPPED


async def test_the_deadline_never_starts_a_second_session() -> None:
    runtime, _, market, _ = build(session_max_hours=1 / 60)
    await runtime.start()
    await _drive(runtime, market, 4)
    assert runtime.state is LiveState.STOPPED
    assert runtime._task is not None
    with pytest.raises(InvalidStateTransitionError):
        await runtime.start()
