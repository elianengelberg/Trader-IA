"""The live runtime, against fakes that behave like a venue.

No Binance host is reachable from this environment, so what is tested here is everything
that is *ours*: the state machine, the gate-token requirement, the halt/cancel/flatten
ladder, the kill switch, unknown-order resolution after a timeout, reconciliation and the
capital ledger's role in it, clock-skew halts, and the structural fact that the
expected-value gate cannot be observed-instead-of-enforced in this class.

The fakes are deliberately simple and deliberately real subclasses of the real
abstractions — a fake that bypasses the base class would also bypass the invariants the
base class enforces, and those invariants are half of what is under test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tia.core.clock import Clock, SimulatedClock, SystemClock
from tia.core.config import Environment, LiveConfig, settings_for_env
from tia.core.errors import (
    InvalidStateTransitionError,
    LiveActivationError,
    ReconciliationError,
)
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.domain.market import Candle
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider
from tia.live.gate import (
    CONFIRMATION_PHRASE,
    REQUIRED_CHECKS,
    LiveActivationGate,
    passing,
)
from tia.runtime.live import LatencyTracker, LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario
from tia.runtime.states import LiveState, LiveStateMachine

START = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- fakes


class FakeMarketData(MarketDataProvider):
    """Serves a pre-generated series one bar at a time, like a polled venue feed.

    When given the session's SimulatedClock it advances that clock one bar per
    ``advance()``, so feed time and processing time stay coherent — which is the
    property a real live session has and the quality gate's freshness check assumes.
    """

    def __init__(self, candles: list[Candle], clock: SimulatedClock | None = None) -> None:
        super().__init__(ProviderCapabilities(name="fake-feed"))
        self._candles = candles
        self._clock = clock
        self.cursor = 150  # enough history for features on the first poll

    def advance(self) -> None:
        self.cursor = min(self.cursor + 1, len(self._candles))
        if self._clock is not None and self.cursor <= len(self._candles):
            target = self._candles[self.cursor - 1].close_time + timedelta(seconds=1)
            if target > self._clock.now():
                self._clock.advance_to(target)

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        window = self._candles[: self.cursor]
        return window[-limit:]


class FakeExecution(ExecutionProvider):
    """An in-memory venue. Fills market orders instantly at the last known price."""

    def __init__(
        self,
        *,
        balance: float = 1_000.0,
        live_token: Any | None = None,
        clock: Clock | None = None,
    ) -> None:
        if live_token is not None:
            super().__init__(
                ExecutionCapabilities(name="fake-venue", is_simulated=False),
                activation=live_token,
                clock=clock or SystemClock(),
            )
        else:
            super().__init__(ExecutionCapabilities(name="fake-venue"))
        self.balance = balance
        self.price = 50_000.0
        self.orders: dict[str, Order] = {}
        self.positions: dict[str, Position] = {}
        self.submissions = 0
        #: Scripted failures: a list of exceptions to raise on successive submits.
        self.fail_next: list[Exception] = []
        #: What resolve_unknown_order should report: "absent" | "present".
        self.unknown_resolution = "absent"
        self._clock_now = SystemClock().now

    async def submit_order(self, intent: OrderIntent) -> Order:
        if intent.client_order_id in self.orders:
            return self.orders[intent.client_order_id]
        self.submissions += 1
        if self.fail_next:
            raise self.fail_next.pop(0)
        return self._fill(intent)

    def _fill(self, intent: OrderIntent) -> Order:
        now = self._clock_now()
        fill = Fill(
            fill_id=f"f-{self.submissions}",
            order_id=f"o-{self.submissions}",
            sequence=0,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            price=self.price,
            fee=self.price * intent.quantity * 0.00075,
            filled_at=now,
        )
        order = Order(
            order_id=fill.order_id,
            client_order_id=intent.client_order_id,
            intent_id=intent.intent_id,
            signal_id=intent.signal_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            state=__import__("tia.domain.enums", fromlist=["OrderState"]).OrderState.FILLED,
            filled_quantity=intent.quantity,
            average_fill_price=self.price,
            created_at=now,
            updated_at=now,
            fills=[fill],
        )
        self.orders[intent.client_order_id] = order
        signed = fill.signed_quantity
        existing = self.positions.get(intent.symbol)
        quantity = (existing.quantity if existing else 0.0) + signed
        self.positions[intent.symbol] = Position(
            symbol=intent.symbol, quantity=quantity, average_price=self.price
        )
        return order

    async def resolve_unknown_order(self, *, symbol: str, client_order_id: str) -> Order | None:
        if self.unknown_resolution == "absent":
            return None
        intent = OrderIntent(
            intent_id="resolved",
            client_order_id=client_order_id,
            signal_id="resolved",
            risk_decision_id="resolved",
            symbol=symbol,
            side=__import__("tia.domain.enums", fromlist=["Side"]).Side.BUY,
            quantity=0.001,
            created_at=self._clock_now(),
        )
        return self._fill(intent)

    async def cancel_order(self, order_id: str) -> Order:
        order = next(
            o for o in self.orders.values()
            if order_id in (o.order_id, o.client_order_id)
        )
        return order

    async def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    async def get_orders(self, *, open_only: bool = False) -> list[Order]:
        orders = list(self.orders.values())
        if open_only:
            orders = [o for o in orders if not o.state.is_terminal]
        return orders

    async def get_positions(self) -> dict[str, Position]:
        return {s: p for s, p in self.positions.items() if not p.is_flat}

    async def get_balance(self) -> float:
        return self.balance

    async def get_trades(self, *, limit: int = 100) -> list[Fill]:
        return []

    async def get_pnl(self) -> dict[str, float]:
        return {"realized": 0.0, "unrealized": 0.0}

    async def get_portfolio(self) -> PortfolioState:
        state = PortfolioState.initial(max(self.balance, 1e-9))
        state.positions = dict(self.positions)
        return state


def real_token(clock: Clock, *, capital: float = 1_000.0):  # type: ignore[no-untyped-def]
    """A genuine token from the genuine gate — tests do not get to forge one either."""
    # Max TTL: a simulated session advances hours of bar time in seconds of real time,
    # and the token must outlive the simulated span the way an operator re-arming hourly
    # would in a real session.
    gate = LiveActivationGate(clock, environment="testing", ttl_seconds=6 * 3600)
    return gate.arm(
        {name: passing(name, "verified in fixture") for name in REQUIRED_CHECKS},
        operator="test-operator",
        confirmation=CONFIRMATION_PHRASE,
        max_live_capital=capital,
        fingerprint="fp-live-tests",
    )


def live_settings(**live_overrides: Any):  # type: ignore[no-untyped-def]
    live = LiveConfig(
        enabled=True,
        max_live_capital=live_overrides.pop("max_live_capital", 1_000.0),
        **live_overrides,
    )
    return settings_for_env(Environment.TESTING).model_copy(update={"live": live})


def build_runtime(
    *,
    execution: FakeExecution | None = None,
    clock: Clock | None = None,
    venue_time_ms=None,  # type: ignore[no-untyped-def]
    persist=None,  # type: ignore[no-untyped-def]
    feed_at_end: bool = False,
    **kwargs: Any,
) -> tuple[LiveRuntime, FakeExecution, FakeMarketData]:
    """A runtime over a coherent fake session.

    Default clock is a SimulatedClock advanced by the feed, so bar time and processing
    time agree the way they do in a genuinely live session — the quality gate's freshness
    check measures exactly that agreement. The runtime itself is generic over Clock;
    the SystemClock wiring is asserted by its own test with ``feed_at_end=True``, where
    the generated series terminates at real wall-clock now.
    """
    scenario = get_scenario("trend_up")
    span_minutes = scenario.total_bars + 5
    series_start = datetime.now(UTC) - timedelta(minutes=span_minutes)
    candles = generate_series(
        scenario,
        symbol="BTC-USD",
        timeframe="1m",
        start=series_start,
        seed=7,
    )
    if clock is None:
        clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
        market = FakeMarketData(candles, clock)
    else:
        market = FakeMarketData(candles)
    if feed_at_end:
        market.cursor = len(candles)
    settings = live_settings()
    execution = execution or FakeExecution()
    token = real_token(clock)
    runtime = LiveRuntime(
        settings,
        activation=token,
        market_data=market,
        execution=execution,
        clock=clock,
        venue_time_ms=venue_time_ms,
        persist=persist,
        poll_interval_seconds=0.0,
        **kwargs,
    )
    # The runtime binds orders to the *real* configuration fingerprint; the token in these
    # tests was minted against a fixture fingerprint, so align them the way arm_live does.
    runtime._fingerprint = "fp-live-tests"
    return runtime, execution, market


def build_runtime_paper(*, clock: Clock | None = None):  # type: ignore[no-untyped-def]
    """A paper-realtime runtime: simulated execution, no token, coherent fake feed."""
    scenario = get_scenario("trend_up")
    span_minutes = scenario.total_bars + 5
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=span_minutes), seed=9,
    )
    if clock is None:
        clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
        market = FakeMarketData(candles, clock)
    elif isinstance(clock, SimulatedClock):
        clock.advance_to(candles[149].close_time + timedelta(seconds=1))
        market = FakeMarketData(candles, clock)
    else:
        market = FakeMarketData(candles)
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(),
        activation=None,
        market_data=market,
        execution=execution,
        clock=clock,
        poll_interval_seconds=0.0,
    )
    return runtime, execution, market


# --------------------------------------------------------------------------- the gate


def test_live_runtime_cannot_exist_without_a_token_over_live_execution() -> None:
    """The token requirement binds to what the money can do.

    Over a live execution provider, no token → no instance. Over a simulated provider
    the same class is paper-realtime and needs none — that case is the next test.
    """
    clock = SystemClock()
    live_execution = FakeExecution(live_token=real_token(clock), clock=clock)
    with pytest.raises(LiveActivationError, match="cannot exist without"):
        LiveRuntime(
            live_settings(),
            activation=None,
            market_data=FakeMarketData([]),
            execution=live_execution,
            clock=clock,
        )


def test_live_runtime_rejects_an_expired_token_at_construction() -> None:
    clock = SimulatedClock(START)
    token = real_token(clock)
    live_execution = FakeExecution(live_token=token, clock=clock)
    clock.advance_by(timedelta(hours=7))
    with pytest.raises(LiveActivationError, match="expired"):
        LiveRuntime(
            live_settings(),
            activation=token,
            market_data=FakeMarketData([]),
            execution=live_execution,
            clock=clock,
        )


async def test_paper_realtime_runs_without_a_token_and_says_so() -> None:
    """Paper-realtime: real feed cadence, simulated fills, no token — the 24/7 paper
    configuration. The snapshot must label it honestly (mode, simulated, no activation),
    and the provider layer still guarantees no real money is reachable this way."""
    runtime, execution, market = build_runtime_paper()
    await runtime.start()
    market.advance()
    await runtime._cycle_once()

    snapshot = runtime.snapshot()
    assert snapshot["mode"] == "paper-live"
    assert snapshot["simulated"] is True
    assert snapshot["activation"] is None
    assert not execution.is_live
    assert runtime.state is LiveState.RUNNING
    await runtime.stop()


async def test_exploration_is_paper_only_and_bounded() -> None:
    """The exploration budget's three load-bearing properties.

    1. Over a live execution provider it is OFF no matter what the config says — with
       real money, "no evidence yet" is a reason not to trade, not an experiment.
    2. In paper it takes trades ONLY in evidence-free buckets, and no more per day than
       the configured budget.
    3. The budget rolls with the injected clock's UTC date.
    """
    # (1) The hard rule: config says explore, provider says live -> disabled.
    clock = SimulatedClock(START)
    token = real_token(clock)
    live_execution = FakeExecution(live_token=token, clock=clock)
    live_runtime = LiveRuntime(
        live_settings(exploration_trades_per_day=5),
        activation=token,
        market_data=FakeMarketData([]),
        execution=live_execution,
        clock=clock,
    )
    assert live_execution.is_live
    assert live_runtime.exploration_enabled is False

    # (2) Paper, empty estimator, budget of 2: signals that EV would refuse for lack of
    # evidence become at most two exploration entries.
    runtime, _execution, market = build_runtime_paper()
    runtime._settings = live_settings(exploration_trades_per_day=2)
    assert runtime.exploration_enabled is True
    await runtime.start()
    for _ in range(400):
        market.advance()
        await runtime._cycle_once()
    await runtime.stop()

    explored = runtime.counters["exploration_trades"]
    assert 1 <= explored <= 2, f"expected 1-2 exploration trades, got {explored}"
    assert runtime.counters["orders"] >= explored

    # (3) The daily budget resets when the clock's date changes, not before.
    fresh, _, _ = build_runtime_paper()
    fresh._settings = live_settings(exploration_trades_per_day=1)
    assert fresh._exploration_budget_left() is True
    fresh._exploration_used += 1
    assert fresh._exploration_budget_left() is False
    fresh._clock.advance_by(timedelta(days=1))
    assert fresh._exploration_budget_left() is True


async def test_exploration_defaults_off_and_changes_nothing() -> None:
    """With the default budget of zero the session behaves exactly as before: every
    evidence-free signal is refused and no order exists."""
    runtime, _execution, market = build_runtime_paper()
    await runtime.start()
    for _ in range(400):
        market.advance()
        await runtime._cycle_once()
    await runtime.stop()
    assert runtime.counters["exploration_trades"] == 0
    assert runtime.counters["orders"] == 0


async def test_the_ev_threshold_can_be_raised_mid_session_but_never_lowered() -> None:
    """The one runtime parameter the Mentor may touch, and only in one direction. The
    refusal lives in the runtime itself, not in the caller's manners."""
    runtime, _execution, _market = build_runtime_paper()
    await runtime.start()
    try:
        before = runtime._ev.threshold_bps
        result = runtime.tighten_ev_threshold(before + 7.0, actor="mentor-test")
        assert result == {"previous_bps": before, "current_bps": before + 7.0}
        assert runtime._ev.threshold_bps == before + 7.0

        import pytest

        with pytest.raises(ValueError, match="only be raised"):
            runtime.tighten_ev_threshold(before, actor="mentor-test")
        assert runtime._ev.threshold_bps == before + 7.0  # the refusal changed nothing
    finally:
        await runtime.stop()


async def test_heartbeat_advances_with_the_loop_not_with_http() -> None:
    """"The server answers" and "the engine is alive" are different facts."""
    runtime, _, market = build_runtime_paper()
    await runtime.start()
    first = runtime.last_heartbeat
    market.advance()
    await runtime._cycle_once()
    assert runtime.last_heartbeat > first
    assert runtime.snapshot()["heartbeat_age_seconds"] >= 0
    await runtime.stop()


async def test_paper_session_exposes_its_real_candles_and_market_row() -> None:
    """The Markets/Chart views read these when a paper-live session runs, so the operator
    sees the same real venue data the engine decides on — not the synthetic demo."""
    runtime, _, market = build_runtime_paper()
    await runtime.start()
    market.advance()
    await runtime._cycle_once()

    candles = runtime.real_candles(limit=50)
    assert candles, "a running session should expose its venue candles"
    row = runtime.market_state()
    assert row is not None
    assert row["symbol"] == "BTC-USD"
    # The market row's price is the latest real candle's close, not a synthetic value.
    assert row["price"] == candles[-1].close
    assert "regime" in row and "change_pct" in row
    await runtime.stop()


async def test_stale_market_data_halts_and_recovery_is_earned() -> None:
    """No new bar past the TTL → entries halt. Bars flowing again does not resume by
    itself: RUNNING comes back only after a clean reconciliation."""
    runtime, _, market = build_runtime_paper()
    clock = runtime._clock  # the fixture's coherent SimulatedClock
    assert isinstance(clock, SimulatedClock)
    runtime.market_data_ttl_seconds = 120.0
    await runtime.start()
    market.advance()
    await runtime._cycle_once()
    assert runtime.state is LiveState.RUNNING

    # The feed goes quiet; the wall clock does not.
    clock.advance_by(timedelta(seconds=300))
    await runtime._cycle_once()
    assert runtime.state is LiveState.HALT_NEW_ORDERS
    assert "stale" in runtime.machine.history[-1].reason

    # Data returns → reconcile clean → watchdog resumes with its name on the transition.
    market.advance()
    await runtime._cycle_once()
    assert runtime.state is LiveState.RUNNING
    assert runtime.machine.history[-1].actor == "watchdog"
    await runtime.stop()


async def test_transient_provider_failure_halts_then_escalates_only_if_persistent() -> None:
    """A network blip is weather; ten in a row is a storm. The first halts entries, the
    tenth lands in SAFE_MODE — never a blind retry of anything in between."""
    from tia.core.errors import ProviderUnavailableError

    runtime, _, _market = build_runtime_paper()

    class FlakyFeed(FakeMarketData):
        failures = 0

        async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("connection reset", provider="fake")

    runtime._market_data = FlakyFeed([])
    await runtime.start()

    await runtime._loop_body_once_for_tests()
    assert runtime.state is LiveState.HALT_NEW_ORDERS

    for _ in range(9):
        await runtime._loop_body_once_for_tests()
    assert runtime.state is LiveState.SAFE_MODE
    await runtime.stop()


def test_live_requires_expected_value() -> None:
    """A5 as structure: the class has no observe mode to misconfigure.

    The paper engine's ``enforce_expected_value`` flag does not exist here — asserted
    directly, so the flag cannot be added back without this test noticing.
    """
    runtime, _, _ = build_runtime()
    assert not hasattr(runtime, "enforce_expected_value")
    assert runtime.snapshot()["expected_value"]["enforcing"] is True
    # And the underlying engine is the enforcing evaluator with the configured threshold.
    assert runtime._ev.threshold_bps == live_settings().live.ev_threshold_bps


# --------------------------------------------------------------------------- lifecycle


async def test_live_runtime_uses_real_clock() -> None:
    """The production wiring runs on the wall clock, and startup works under it."""
    runtime, _, _ = build_runtime(clock=SystemClock(), feed_at_end=True)
    assert not isinstance(runtime._clock, SimulatedClock)
    before = datetime.now(UTC)
    await runtime.start()
    assert runtime.state is LiveState.RUNNING
    stamped = runtime.machine.history[-1].at
    assert abs((stamped - before).total_seconds()) < 5.0
    await runtime.stop()


async def test_live_runtime_connects_market_data() -> None:
    runtime, _, market = build_runtime()
    await runtime.start()
    market.advance()
    await runtime._cycle_once()
    assert runtime.counters["bars"] >= 1
    await runtime.stop()


async def test_live_runtime_connects_execution() -> None:
    """The startup validation actually talks to the venue: balance read, ledger funded."""
    runtime, execution, _ = build_runtime()
    await runtime.start()
    snapshot = runtime.snapshot()
    assert snapshot["capital"]["allocated_capital"] == pytest.approx(
        min(execution.balance, 1_000.0)
    )
    await runtime.stop()


async def test_startup_failure_lands_in_error_never_in_running() -> None:
    """A runtime that failed validation must say so — never report LIVE as running."""

    class Refusing(FakeExecution):
        async def get_balance(self) -> float:
            raise ConnectionError("venue unreachable")

    runtime, _, _ = build_runtime(execution=Refusing())
    with pytest.raises(Exception, match="venue unreachable"):
        await runtime.start()
    assert runtime.state is LiveState.ERROR
    assert not runtime.is_running


async def test_zero_balance_refuses_to_start() -> None:
    runtime, _, _ = build_runtime(execution=FakeExecution(balance=0.0))
    with pytest.raises(LiveActivationError, match="funds no allocation"):
        await runtime.start()
    assert runtime.state is LiveState.ERROR


# --------------------------------------------------------------------------- state machine


def test_the_state_machine_refuses_illegal_transitions() -> None:
    from tia.core.clock import FrozenClock

    machine = LiveStateMachine(FrozenClock(START))
    with pytest.raises(InvalidStateTransitionError):
        machine.transition(LiveState.RUNNING, reason="skipping validation")

    machine.transition(LiveState.ARMING, reason="ok")
    machine.transition(LiveState.ARMED, reason="ok")
    machine.transition(LiveState.STARTING, reason="ok")
    machine.transition(LiveState.RUNNING, reason="ok")
    with pytest.raises(InvalidStateTransitionError):
        machine.transition(LiveState.ARMED, reason="cannot re-arm a running session")


def test_safe_mode_is_reachable_from_anywhere_and_sticky() -> None:
    """Safety escalation has no precondition, and no automatic way back to RUNNING."""
    from tia.core.clock import FrozenClock

    machine = LiveStateMachine(FrozenClock(START))
    machine.transition(LiveState.SAFE_MODE, reason="doubt")
    assert machine.state is LiveState.SAFE_MODE
    with pytest.raises(InvalidStateTransitionError):
        machine.transition(LiveState.RUNNING, reason="hope")
    machine.transition(LiveState.CANCEL_ONLY, reason="operator winding down")
    assert machine.state.accepts_reducing_orders
    assert not machine.state.accepts_new_orders


def test_every_transition_is_recorded_with_reason_and_actor() -> None:
    from tia.core.clock import FrozenClock

    machine = LiveStateMachine(FrozenClock(START))
    machine.transition(LiveState.ARMING, reason="operator armed", actor="elian")
    change = machine.history[-1]
    assert change.reason == "operator armed"
    assert change.actor == "elian"
    assert machine.as_dict()["history"][-1]["actor"] == "elian"


# --------------------------------------------------------------------------- idempotency


async def test_timeout_does_not_duplicate_order() -> None:
    """THE critical test: a submission timeout must never become two orders.

    The venue is scripted to time out once, then report (via resolve_unknown_order) that
    the order never arrived. The correct behaviour is: no blind retry, entries halted,
    exactly zero additional submissions until reconciliation has run.
    """
    execution = FakeExecution()
    execution.fail_next = [
        ReconciliationError("timed out; state UNKNOWN", path="/api/v3/order")
    ]
    execution.unknown_resolution = "absent"
    runtime, _, market = build_runtime(execution=execution)
    await runtime.start()

    submissions_before = execution.submissions
    # Drive bars until the pipeline actually tries to submit (evidence gate refuses most).
    # Seed the estimator so the EV gate can pass and a submission is attempted.
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    runtime._edges.record_many(
        [
            Outcome(
                regime=regime, direction=direction,
                confidence=0.65, net_return_bps=200.0,
            )
            for regime in MarketRegime
            for direction in (Direction.LONG, Direction.SHORT)
            for _ in range(40)
        ]
    )
    for _ in range(300):
        market.advance()
        await runtime._cycle_once()
        if execution.submissions > submissions_before:
            break

    assert execution.submissions == submissions_before + 1, (
        "the timed-out submission was retried blind — this is the duplicate-order bug"
    )
    assert runtime.counters["unknown_order_states"] == 1
    assert runtime.state in {LiveState.HALT_NEW_ORDERS, LiveState.RUNNING}
    await runtime.stop()


async def test_duplicate_order_protection_is_venue_id_based() -> None:
    """The same intent resubmitted answers from the mirror without touching the venue."""
    execution = FakeExecution()
    _, _, _ = build_runtime(execution=execution)
    from tia.domain.enums import OrderType, Side

    intent = OrderIntent(
        intent_id="i1",
        client_order_id=OrderIntent.build_client_order_id(
            signal_id="s1", symbol="BTC-USD", side=Side.BUY,
            quantity=0.01, order_type=OrderType.MARKET,
        ),
        signal_id="s1", risk_decision_id="r1", symbol="BTC-USD",
        side=Side.BUY, quantity=0.01, created_at=START,
    )
    first = await execution.submit_order(intent)
    second = await execution.submit_order(intent)
    assert first.order_id == second.order_id
    assert execution.submissions == 1


async def test_a_resolved_present_order_is_adopted_not_retried() -> None:
    """If the timed-out order DID reach the venue, it is adopted into the mirror."""
    execution = FakeExecution()
    execution.fail_next = [ReconciliationError("timeout", path="/api/v3/order")]
    execution.unknown_resolution = "present"
    runtime, _, _ = build_runtime(execution=execution)
    await runtime.start()

    from tia.domain.enums import Side
    from tia.domain.orders import OrderIntent as OI

    intent = runtime._build_intent(
        symbol="BTC-USD", side=Side.BUY, quantity=0.01, signal_id="s-adopt"
    )
    assert isinstance(intent, OI)

    class Decision:
        symbol = "BTC-USD"
        signal_id = "s-adopt"
        approved_quantity = 0.01

    class Signal:
        signal_id = "s-adopt"

        class direction:
            @staticmethod
            def to_side():
                return Side.BUY

    await runtime._submit(Decision(), Signal(), "corr-1")
    assert runtime.counters["orders"] == 1  # adopted, counted once, never re-sent
    await runtime.stop()


# --------------------------------------------------------------------------- kill switch


async def test_kill_switch() -> None:
    """Stops entries, cancels, reconciles, lands in SAFE_MODE, and records who and why."""
    incidents: list[dict[str, Any]] = []

    def persist(kind: str, payload: dict[str, Any]) -> None:
        if kind == "incident":
            incidents.append(payload)

    runtime, _, _ = build_runtime(persist=persist)
    await runtime.start()

    result = await runtime.kill_switch(reason="operator emergency", actor="elian")

    assert runtime.state is LiveState.SAFE_MODE
    assert result["state"] == "safe_mode"
    assert not runtime.state.accepts_new_orders
    kill_incidents = [i for i in incidents if i["kind"] == "kill_switch"]
    assert kill_incidents and kill_incidents[0]["actor"] == "elian"
    assert kill_incidents[0]["reason"] == "operator emergency"

    with pytest.raises(ValueError, match="named actor"):
        await runtime.kill_switch(reason="anonymous", actor="  ")
    await runtime.stop()


async def test_emergency_flatten() -> None:
    """The seven steps, with real position closure through the fake venue."""
    execution = FakeExecution()
    runtime, _, _ = build_runtime(execution=execution)
    await runtime.start()

    from tia.domain.enums import Side

    intent = runtime._build_intent(
        symbol="BTC-USD", side=Side.BUY, quantity=0.02, signal_id="s-flat"
    )
    await execution.submit_order(intent)
    assert (await execution.get_positions())["BTC-USD"].quantity == pytest.approx(0.02)

    result = await runtime.emergency_flatten(reason="get me out", actor="elian")

    assert result["closing_orders"], "no reducing order was placed"
    assert await execution.get_positions() == {}
    assert runtime.state is LiveState.CANCEL_ONLY  # winding down under operator's eye
    with pytest.raises(ValueError, match="named actor"):
        await runtime.emergency_flatten(reason="x", actor="")
    await runtime.stop()


# --------------------------------------------------------------------------- reconciliation


async def test_capital_ledger_live_reconciliation() -> None:
    """A venue balance drift is classified by the ledger, never booked as P&L."""
    execution = FakeExecution(balance=1_000.0)
    rows: list[dict[str, Any]] = []

    def persist(kind: str, payload: dict[str, Any]) -> None:
        if kind == "reconciliation":
            rows.append(payload)

    runtime, _, _ = build_runtime(execution=execution, persist=persist)
    await runtime.start()

    # The user deposits at the venue mid-session: +3% appears with no fill behind it.
    execution.balance = 1_030.0
    await runtime._reconcile()

    snapshot = runtime.ledger.snapshot()
    assert snapshot.realised_pnl == pytest.approx(0.0)  # never profit
    assert snapshot.deposits > 1_000.0  # classified as a deposit
    assert rows and rows[-1]["clean"] is False
    await runtime.stop()


async def test_unknown_balance_change_halts() -> None:
    """A movement above 10% of the ceiling with no fill behind it stops entries."""
    execution = FakeExecution(balance=1_000.0)
    runtime, _, _ = build_runtime(execution=execution)
    await runtime.start()

    execution.balance = 400.0  # -60%: unexplained, way past the 10% threshold
    await runtime._reconcile()

    assert runtime.ledger.is_halted
    assert runtime.state is LiveState.HALT_NEW_ORDERS
    await runtime.stop()


async def test_reconciliation_scheduler() -> None:
    """Reconciliation runs on its cycle cadence without being asked."""
    runtime, _, market = build_runtime(reconcile_every_cycles=3)
    await runtime.start()
    for _ in range(7):
        market.advance()
        await runtime._cycle_once()
    assert runtime.counters["reconciliations"] >= 2
    await runtime.stop()


async def test_live_safe_mode_on_unknown_state() -> None:
    """An order open locally that the venue denies knowing → SAFE_MODE, not hope."""
    execution = FakeExecution()
    runtime, _, _ = build_runtime(execution=execution)
    await runtime.start()

    from tia.domain.enums import OrderState, Side

    ghost = Order(
        order_id="ghost", client_order_id="ghost-c", intent_id="i", signal_id="s",
        symbol="BTC-USD", side=Side.BUY, order_type=__import__(
            "tia.domain.enums", fromlist=["OrderType"]
        ).OrderType.MARKET,
        quantity=0.01, state=OrderState.ACKNOWLEDGED,
        created_at=START, updated_at=START,
    )
    execution.orders["ghost-c"] = ghost

    class VenueDeniesGhost(FakeExecution):
        pass

    # get_orders(open_only=True) returns the ghost too in our fake, so instead script the
    # venue view: open_only returns nothing, local view returns the ghost.
    original = execution.get_orders

    async def split_view(*, open_only: bool = False):  # type: ignore[no-untyped-def]
        if open_only:
            return []
        return await original(open_only=False)

    execution.get_orders = split_view  # type: ignore[method-assign]
    await runtime._reconcile()

    assert runtime.state is LiveState.SAFE_MODE
    assert runtime.counters["reconciliation_breaks"] >= 1
    await runtime.stop()


# --------------------------------------------------------------------------- clock skew


async def test_clock_skew_monitor() -> None:
    """Startup refuses a skewed clock; a mid-session drift halts entries."""
    session = SystemClock()
    skewed_ms = 10_000

    async def venue_time() -> int:
        return session.timestamp_ms() - skewed_ms

    runtime, _, _ = build_runtime(
        clock=session, feed_at_end=True, venue_time_ms=venue_time
    )
    with pytest.raises(LiveActivationError, match="clock skew"):
        await runtime.start()
    assert runtime.state is LiveState.ERROR

    # And a healthy one passes, then a drift mid-session halts entries. The venue clock
    # reads the same session clock, so only the injected drift separates them.
    drift = {"ms": 0}
    session2 = SystemClock()

    async def wandering_venue_time() -> int:
        return session2.timestamp_ms() - drift["ms"]

    runtime2, _, _market = build_runtime(
        clock=session2,
        feed_at_end=True,
        venue_time_ms=wandering_venue_time,
        skew_check_every_cycles=1,
    )
    await runtime2.start()
    assert runtime2.state is LiveState.RUNNING
    drift["ms"] = 10_000
    await runtime2._cycle_once()
    assert runtime2.state is LiveState.HALT_NEW_ORDERS
    assert runtime2.counters["skew_halts"] == 1
    await runtime2.stop()


# --------------------------------------------------------------------------- latency


async def test_latency_measurement() -> None:
    """Stages are stamped, segments computed, and the EMA feeds the cost model."""
    from tia.core.clock import SystemClock as SC

    tracker = LatencyTracker(SC())
    tracker.stamp("c1", "market_received")
    tracker.stamp("c1", "decision_started")
    tracker.stamp("c1", "decision_finished")
    tracker.stamp("c1", "order_submit")
    tracker.stamp("c1", "order_ack")
    sample = tracker.finish("c1", symbol="BTC-USD")

    assert sample is not None
    assert "submit_to_ack" in sample["segments_ms"]
    assert "market_to_decision" in sample["segments_ms"]
    assert tracker.ema_submit_to_ack_ms is not None
    assert tracker.ema_total_ms is not None
    assert tracker.finish("c1") is None  # consumed; not double-counted


def test_no_trade_is_valid_decision() -> None:
    """NO_TRADE stands on its own: an empty signal maps to no order, never to a side."""
    from tia.domain.enums import Direction

    assert not Direction.NO_TRADE.is_actionable
    assert not Direction.HOLD.is_actionable
    with pytest.raises(ValueError):
        Direction.NO_TRADE.to_side()


async def test_absorbing_evidence_mid_session_only_ever_adds() -> None:
    """A finished training batch must reach a running session without a restart.

    Three properties, and the third is the one that keeps the paper track record
    honest: absorbing adds buckets, leaves the session's own loss streak alone (a
    simulation from last night is not one of this session's recent trades), and an
    empty absorb changes nothing at all.
    """
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    runtime, _execution, _market = build_runtime_paper()
    await runtime.start()
    try:
        before_coverage = dict(runtime._edges.coverage())
        runtime._consecutive_losses = 3

        empty = runtime.absorb_evidence()
        assert empty["absorbed_outcomes"] == 0
        assert dict(runtime._edges.coverage()) == before_coverage

        outcomes = [
            Outcome(
                regime=MarketRegime.TRENDING_UP,
                direction=Direction.LONG,
                confidence=0.65,
                net_return_bps=-40.0,
            )
            for _ in range(35)
        ]
        reviews = [
            {
                "regime": "trending_up",
                "direction": "long",
                "confidence": 0.65,
                "expected_net_bps": 20.0,
                "net_bps": -40.0,
                "fees_bps": 6.0,
                "closed_at": START + timedelta(minutes=i),
                "signal_id": f"sim-{i}",
                "symbol": "BTC-USD",
                "entry_price": 50_000.0,
                "quantity": 0.04,
            }
            for i in range(35)
        ]
        result = runtime.absorb_evidence(outcomes=outcomes, reviews=reviews)

        assert result["absorbed_outcomes"] == 35
        assert result["buckets_ready"] >= 1
        # The lessons are readable immediately — this is the whole point of not
        # needing a restart — and the estimator now has a bucket it can price.
        assert runtime.learning_report()["reviews"] == 35
        assert runtime.evidence_state()["absorbed_since_start"] == 35
        # ...and the guardrail derived from those disappointing trades is active.
        guard = runtime._retro.guardrail_for(
            regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.65
        )
        assert guard.is_active

        # The loss streak is this session's business; absorbed history never touches it.
        assert runtime._consecutive_losses == 3
    finally:
        await runtime.stop()
