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
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.market import Candle
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider
from tia.execution.state_machine import transition
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
        #: When True, LIMIT orders rest (ACKNOWLEDGED, no fills) instead of filling at
        #: once — the case a resting-order manager exists for.
        self.rest_limits = False
        self.cancelled: list[str] = []
        self.adjustments: list[tuple[float, str]] = []
        self._clock_now = SystemClock().now

    async def submit_order(self, intent: OrderIntent) -> Order:
        if intent.client_order_id in self.orders:
            return self.orders[intent.client_order_id]
        self.submissions += 1
        if self.fail_next:
            raise self.fail_next.pop(0)
        if (self.rest_limits and intent.order_type is OrderType.LIMIT) or (
            intent.order_type is OrderType.STOP
        ):
            now = self._clock_now()
            order = Order(
                order_id=f"o-{self.submissions}",
                client_order_id=intent.client_order_id,
                intent_id=intent.intent_id,
                signal_id=intent.signal_id,
                symbol=intent.symbol,
                side=intent.side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                limit_price=intent.limit_price,
                stop_price=intent.stop_price,
                state=OrderState.ACKNOWLEDGED,
                created_at=now,
                updated_at=now,
            )
            self.orders[intent.client_order_id] = order
            return order
        return self._fill(intent)

    def fill_resting(self, order: Order, price: float | None = None) -> Fill:
        """The venue reports a resting order filled — at its stop level by default."""
        now = self._clock_now()
        self.submissions += 1
        price = price or order.stop_price or order.limit_price or self.price
        fill = Fill(
            fill_id=f"f-{self.submissions}",
            order_id=order.order_id,
            sequence=0,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            fee=price * order.quantity * 0.00075,
            filled_at=now,
        )
        try:
            transition(order, OrderState.FILLED, at=now)
        except InvalidStateTransitionError:
            transition(order, OrderState.PARTIALLY_FILLED, at=now)
            transition(order, OrderState.FILLED, at=now)
        order.filled_quantity = order.quantity
        order.average_fill_price = price
        order.fills = [*order.fills, fill]
        existing = self.positions.get(order.symbol)
        quantity = (existing.quantity if existing else 0.0) + fill.signed_quantity
        self.positions[order.symbol] = Position(
            symbol=order.symbol, quantity=quantity, average_price=price
        )
        return fill

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
            limit_price=intent.limit_price,
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
        if not order.state.is_terminal:
            now = self._clock_now()
            transition(order, OrderState.CANCEL_REQUESTED, at=now)
            transition(order, OrderState.CANCELLED, at=now, reason="cancelled by caller")
            self.cancelled.append(order.order_id)
        return order

    async def get_order(self, order_id: str) -> Order | None:
        return next(
            (o for o in self.orders.values() if order_id in (o.order_id, o.client_order_id)),
            None,
        )

    async def get_orders(self, *, open_only: bool = False) -> list[Order]:
        orders = list(self.orders.values())
        if open_only:
            orders = [o for o in orders if not o.state.is_terminal]
        return orders

    async def get_positions(self) -> dict[str, Position]:
        return {s: p for s, p in self.positions.items() if not p.is_flat}

    async def get_balance(self) -> float:
        return self.balance

    def apply_cash_adjustment(self, amount: float, *, reason: str) -> float:
        """Funding and liquidation fees move cash outside a fill, as the paper venue does."""
        self.balance += amount
        self.adjustments.append((amount, reason))
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


async def test_selectivity_splits_the_record_by_what_todays_rules_would_take() -> None:
    """The answer to "did it learn?" is a split, not an average.

    The trainer trades everything on purpose, so the pooled win rate is pinned to the
    curriculum's base rate no matter how much is learned. What learning changes is which
    trades the rules now refuse — so the report replays every recorded trade against
    today's estimator, threshold and guardrails, and the two win rates must separate.
    """
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    runtime, _execution, _market = build_runtime_paper()
    # A bucket that demonstrably wins and one that demonstrably loses. Variance is real
    # (alternating around the mean) so the standard-error shrink is exercised, not skipped.
    runtime._edges.record_many(
        [
            Outcome(
                regime=MarketRegime.TRENDING_UP, direction=Direction.LONG,
                confidence=0.60, net_return_bps=50.0 + (4.0 if i % 2 == 0 else -4.0),
            )
            for i in range(40)
        ]
    )
    runtime._edges.record_many(
        [
            Outcome(
                regime=MarketRegime.RANGING, direction=Direction.SHORT,
                confidence=0.60, net_return_bps=-40.0 + (4.0 if i % 2 == 0 else -4.0),
            )
            for i in range(40)
        ]
    )

    report = runtime.selectivity_report()
    assert report["reviewed"] == 80
    assert report["taken"]["trades"] == 40
    assert report["taken"]["win_rate"] == 1.0
    assert report["taken"]["mean_net_bps"] == pytest.approx(50.0)
    assert report["refused"]["trades"] == 40
    assert report["refused"]["win_rate"] == 0.0
    # And the whole thing rides along with the learning report the page reads.
    assert runtime.learning_report()["selectivity"]["reviewed"] == 80


# ------------------------------------------------------------- maker entries


def _seed_every_bucket(runtime: LiveRuntime, net_bps: float = 200.0) -> None:
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    runtime._edges.record_many(
        [
            Outcome(
                regime=regime, direction=direction, confidence=0.65,
                net_return_bps=net_bps + (3.0 if i % 2 else -3.0),
            )
            for regime in MarketRegime
            for direction in (Direction.LONG, Direction.SHORT)
            for i in range(40)
        ]
    )


async def test_limit_entries_rest_on_our_side_of_the_spread_and_are_priced_as_maker() -> None:
    """The cheapest trade is the one that does not cross the spread.

    With entries configured as limit orders, the intent that reaches the venue is a LIMIT
    at the touch on our side (below the reference for a buy), and the session reports the
    style it is using. The cost model's maker path is tested on its own; what this pins
    is that the runtime actually asks for it.
    """
    runtime, execution, market = build_runtime_paper()
    runtime._settings = live_settings(entry_order_type="limit")
    assert runtime.entry_is_limit
    _seed_every_bucket(runtime)
    await runtime.start()
    try:
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if execution.submissions:
                break
        assert execution.submissions >= 1, "no entry was ever submitted"
        order = next(iter(execution.orders.values()))
        assert order.order_type is OrderType.LIMIT
        assert order.limit_price is not None
        reference = runtime._buffer[-1].close if runtime._buffer else None
        assert reference is not None
        if order.side is Side.BUY:
            assert order.limit_price <= reference
        else:
            assert order.limit_price >= reference
        assert runtime.snapshot()["execution"]["entry_order_type"] == "limit"
    finally:
        await runtime.stop()


async def test_an_unfilled_limit_entry_expires_and_frees_the_session() -> None:
    """A missed entry costs nothing — as long as it is actually missed.

    While the order rests, no second entry is considered (one signal, one order). After
    the configured bars it is cancelled, the expectation formed for it is dropped so it
    cannot be scored against the next trade, and the session is free to look again.
    """
    runtime, execution, market = build_runtime_paper()
    runtime._settings = live_settings(entry_order_type="limit", entry_limit_timeout_bars=2)
    execution.rest_limits = True
    _seed_every_bucket(runtime)
    await runtime.start()
    try:
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders_expired"]:
                break
        assert runtime.counters["orders_expired"] >= 1
        assert runtime._resting is None
        assert runtime.counters["resting_skipped"] >= 1
        assert execution.cancelled, "the venue was never asked to cancel"
        assert runtime._entry_beliefs is None
        assert runtime._open_trade is None
        snapshot = runtime.snapshot()["execution"]
        assert snapshot["resting_order"] is None
    finally:
        await runtime.stop()


async def test_market_entries_are_unchanged_by_default() -> None:
    """The default is the old behaviour, exactly: nothing rests, nothing expires."""
    runtime, execution, market = build_runtime_paper()
    assert not runtime.entry_is_limit
    _seed_every_bucket(runtime)
    await runtime.start()
    try:
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if execution.submissions:
                break
        assert execution.submissions >= 1
        assert next(iter(execution.orders.values())).order_type is OrderType.MARKET
        assert runtime.counters["orders_expired"] == 0
        assert runtime.counters["resting_skipped"] == 0
    finally:
        await runtime.stop()


# ------------------------------------------------------------- exit discipline


async def _open_a_position(
    runtime: LiveRuntime, execution: FakeExecution, market: FakeMarketData, *, keep_target: bool = False
) -> None:
    """Drive bars until an entry fills. Unless asked otherwise, disarm the strategy's
    target so the scenario's next bar cannot close the position before the property
    under test has been observed — the target has its own test."""
    _seed_every_bucket(runtime)
    for _ in range(300):
        market.advance()
        await runtime._cycle_once()
        if runtime._open_trade is not None:
            if not keep_target:
                runtime._planned_exit["target"] = None
            return
    raise AssertionError("no position was ever opened")


async def test_every_open_position_gets_exactly_one_protective_stop() -> None:
    """The evidence was produced by an engine that protects every position with a stop.
    A session that learned from it and ran unprotected would be applying evidence from
    one game to a different one — so the stop is placed on the bar the position opens,
    sized to it, and reported as such."""
    runtime, execution, market = build_runtime_paper()
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        # The stop is placed by the next bar's position management.
        market.advance()
        await runtime._cycle_once()
        stops = [o for o in execution.orders.values() if o.order_type is OrderType.STOP]
        assert len(stops) == 1, "exactly one protective stop"
        stop = stops[0]
        assert not stop.state.is_terminal
        assert stop.stop_price is not None and stop.stop_price > 0
        position = await execution.get_positions()
        held = abs(next(iter(position.values())).quantity)
        assert stop.quantity == pytest.approx(held)
        assert runtime.counters["stops_placed"] == 1
        assert runtime.snapshot()["position"]["protected"] is True
        # Another bar changes nothing: one stop, not one per bar.
        market.advance()
        await runtime._cycle_once()
        assert sum(1 for o in execution.orders.values() if o.order_type is OrderType.STOP) == 1
    finally:
        await runtime.stop()


async def test_a_triggered_stop_closes_the_round_trip_and_records_why() -> None:
    """The venue reports the stop filled; the session must notice without being pushed,
    score the round trip with the entry's own beliefs, and file the reason."""
    runtime, execution, market = build_runtime_paper()
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        market.advance()
        await runtime._cycle_once()
        stop = next(o for o in execution.orders.values() if o.order_type is OrderType.STOP)
        reviews_before = runtime._retro.reviews

        execution.fill_resting(stop)  # the market went through the stop
        market.advance()
        await runtime._cycle_once()

        # The round trip is scored — that is the fact. Whether the SAME bar then opens a
        # fresh position on the next signal is the strategy's business, not this test's.
        assert runtime.counters["exits_stop"] == 1
        assert runtime._retro.reviews == reviews_before + 1
        assert runtime._retro.recent(1)[0].signal_id != ""
        assert stop.state.is_terminal
    finally:
        await runtime.stop()


async def test_a_reached_target_closes_at_market_and_says_so() -> None:
    runtime, execution, market = build_runtime_paper()
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        # Put the target where the next bar cannot miss it.
        runtime._planned_exit["target"] = 1.0 if position.quantity > 0 else 10_000_000.0
        reviews_before = runtime._retro.reviews
        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["exits_target"] == 1
        assert runtime._retro.reviews == reviews_before + 1
        closing = [o for o in execution.orders.values() if o.signal_id.startswith("exit:target")]
        assert len(closing) == 1 and closing[0].order_type is OrderType.MARKET
    finally:
        await runtime.stop()


async def test_the_time_stop_is_off_by_default_and_closes_when_set() -> None:
    runtime, execution, market = build_runtime_paper()
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        runtime._planned_exit["stop"] = 1.0 if position.quantity > 0 else 10_000_000.0
        for _ in range(5):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["exits_time"] == 0, "off by default, parity with the evidence"

        runtime._settings = live_settings(max_holding_bars=2)
        reviews_before = runtime._retro.reviews
        for _ in range(4):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["exits_time"]:
                break
        assert runtime.counters["exits_time"] == 1
        assert runtime._retro.reviews == reviews_before + 1
    finally:
        await runtime.stop()


async def test_the_session_announces_closed_trades_and_orders_on_the_stream() -> None:
    """Pages subscribed to trade.closed for months without receiving one from the 24/7
    session: it never emitted it, and what it did emit went out under a key the stream
    did not read. Both are pinned here: the event exists, carries data, and the orders
    and fills pages can see the session's activity."""
    from tia.runtime.live import LiveRuntime as _LR  # noqa: F401 - explicit subject

    seen: list[dict[str, Any]] = []
    runtime, execution, market = build_runtime_paper()
    runtime._on_event = seen.append
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        runtime._planned_exit["target"] = 1.0 if position.quantity > 0 else 10_000_000.0
        market.advance()
        await runtime._cycle_once()
    finally:
        await runtime.stop()

    closed = [e for e in seen if e.get("type") == "trade.closed"]
    assert closed, "no trade.closed event was emitted"
    assert closed[0]["data"]["exit_reason"] == "target reached"
    assert isinstance(closed[0]["data"]["net_usd"], float)
    assert all("data" in e for e in seen), "every event carries its payload under data"
    assert runtime.recent_orders and runtime.recent_fills
    assert runtime.recent_orders[0]["order_type"] in {"market", "limit", "stop"}


# --------------------------------------------------------------------------- the upgrades


class QuotingMarketData(FakeMarketData):
    """A feed that also shows a top of book, at a spread the test controls."""

    def __init__(self, candles: list[Candle], clock: SimulatedClock | None = None) -> None:
        super().__init__(candles, clock)
        self.spread_bps = 1.0

    async def get_quote(self, symbol: str):  # type: ignore[no-untyped-def]
        from tia.domain.market import Quote

        mid = self._candles[self.cursor - 1].close
        half = mid * self.spread_bps / 10_000.0 / 2.0
        return Quote(
            symbol=symbol, timestamp=SystemClock().now(), bid=mid - half, ask=mid + half,
            bid_size=5.0, ask_size=5.0, provider="fake-book",
        )


def build_runtime_paper_with(  # type: ignore[no-untyped-def]
    *, quoting: bool = False, persist=None, **live_overrides: Any
):
    """A paper-realtime runtime with live-config overrides and, optionally, a quoting feed."""
    scenario = get_scenario("trend_up")
    span_minutes = scenario.total_bars + 5
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=span_minutes), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = (QuotingMarketData if quoting else FakeMarketData)(candles, clock)
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(**live_overrides),
        activation=None,
        market_data=market,
        execution=execution,
        clock=clock,
        persist=persist,
        poll_interval_seconds=0.0,
    )
    return runtime, execution, market


def _working_stops(execution: FakeExecution) -> list[Order]:
    return [
        o for o in execution.orders.values()
        if o.order_type is OrderType.STOP and not o.state.is_terminal
    ]


async def test_the_trailing_stop_follows_the_best_price_and_never_loosens() -> None:
    """The stop tightens along the trail, the resting order is replaced at the new level,
    and a wider trail on the next bar changes nothing — tighter only, ever."""
    runtime, execution, market = build_runtime_paper_with(trail_atr_multiple=2.0, breakeven_after_r=0.0)
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        long = position.quantity > 0
        entry = runtime._open_trade["price"]
        # A stop far away and a tiny ATR: the trail must pull the stop right up behind
        # the best price on the very next bar.
        runtime._planned_exit["stop"] = entry * (0.90 if long else 1.10)
        runtime._planned_exit["initial_stop"] = runtime._planned_exit["stop"]
        runtime._last_atr = entry * 0.0001

        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["stops_tightened"] == 1
        assert runtime._planned_exit["kind"] == "trailing"
        tightened = runtime._planned_exit["stop"]
        assert (tightened > entry * 0.90) if long else (tightened < entry * 1.10)
        stops = _working_stops(execution)
        assert len(stops) == 1 and stops[0].stop_price == pytest.approx(tightened)
        assert runtime.snapshot()["position"]["stop_kind"] == "trailing"
        assert runtime.snapshot()["position"]["best_price"] is not None

        # A huge ATR: the trail would now sit far behind. The stop stays where it is.
        runtime._last_atr = entry * 0.5
        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["stops_tightened"] == 1
        assert runtime._planned_exit["stop"] == tightened

        # A planned level that changed is a resting order that must be replaced.
        old_stop = _working_stops(execution)[0]
        tighter = tightened * (1.001 if long else 0.999)
        runtime._planned_exit["stop"] = tighter
        runtime._last_atr = entry * 0.5  # the rules propose nothing; the level alone changed
        market.advance()
        await runtime._cycle_once()
        assert old_stop.order_id in execution.cancelled
        replaced = _working_stops(execution)
        assert len(replaced) == 1 and replaced[0].stop_price == pytest.approx(tighter)
    finally:
        await runtime.stop()


async def test_a_break_even_stop_names_its_exit_and_the_record_credits_the_strategy() -> None:
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market = build_runtime_paper_with(
        breakeven_after_r=1.0, trail_atr_multiple=0.0,
        persist=lambda kind, payload: saved.append((kind, payload)),
    )
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        long = position.quantity > 0
        entry = runtime._open_trade["price"]
        # One R is 5% away; the best price is already 2R in favour.
        runtime._planned_exit["stop"] = entry * (0.95 if long else 1.05)
        runtime._planned_exit["initial_stop"] = runtime._planned_exit["stop"]
        runtime._best_price = entry * (1.10 if long else 0.90)

        market.advance()
        await runtime._cycle_once()
        assert runtime._planned_exit["kind"] == "break-even"
        stop = _working_stops(execution)[0]
        assert (stop.stop_price > entry * 0.95) if long else (stop.stop_price < entry * 1.05)

        reviews_before = runtime._retro.reviews
        execution.fill_resting(stop)  # the market came back through the moved stop
        market.advance()
        await runtime._cycle_once()

        assert runtime._retro.reviews == reviews_before + 1
        assert runtime.counters["exits_breakeven"] == 1
        assert runtime.counters["exits_stop"] == 1
        outcome = next(p for k, p in saved if k == "edge_outcome")
        assert outcome["exit_reason"] == "break-even stop"
        assert outcome["strategy_id"]  # the strategy that proposed the entry is on record
        board = runtime.snapshot()["strategies"]
        assert board and board[0]["strategy_id"] == outcome["strategy_id"]
        assert board[0]["trades"] == 1
    finally:
        await runtime.stop()


async def test_a_wide_spread_waits_and_a_normal_one_prices_the_costs() -> None:
    runtime, _execution, market = build_runtime_paper_with(quoting=True, max_spread_bps=10.0)
    market.spread_bps = 50.0
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(120):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["spread_rejected"] > 0
        assert runtime.counters["orders"] == 0
        market_view = runtime.snapshot()["market"]
        assert market_view["spread_source"] == "venue top of book"
        assert market_view["quote"]["spread_bps"] == pytest.approx(50.0, rel=1e-3)

        market.spread_bps = 1.0
        for _ in range(200):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders"] > 0:
                break
        assert runtime.counters["orders"] > 0
        assert runtime.snapshot()["market"]["quote"]["spread_bps"] == pytest.approx(1.0, rel=1e-3)
    finally:
        await runtime.stop()


async def test_a_feed_without_quotes_keeps_the_configured_spread_and_says_so() -> None:
    runtime, _execution, market = build_runtime_paper_with(max_spread_bps=10.0)
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()
        market_view = runtime.snapshot()["market"]
        assert market_view["quote"] is None
        assert market_view["spread_source"] == "configured constant"
        assert runtime.counters["spread_rejected"] == 0
    finally:
        await runtime.stop()


def _seed_weakly(runtime: LiveRuntime) -> None:
    """Evidence that clears the threshold and the cost ratio but is far from sure:
    mean 120 bps with a standard error near 47, so t is about 2.5."""
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    runtime._edges.record_many(
        [
            Outcome(
                regime=regime, direction=direction, confidence=0.65,
                net_return_bps=120.0 + (300.0 if i % 2 else -300.0),
            )
            for regime in MarketRegime
            for direction in (Direction.LONG, Direction.SHORT)
            for i in range(40)
        ]
    )


async def test_conviction_sizing_takes_less_than_the_approval_when_the_evidence_is_unsure() -> None:
    runtime, _execution, market = build_runtime_paper_with(conviction_sizing=True)
    await runtime.start()
    try:
        _seed_weakly(runtime)
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders"] > 0:
                break
        assert runtime.counters["orders"] > 0
        assert runtime.counters["sized_down"] >= 1
        last = runtime.snapshot()["sizing"]["last"]
        assert 0.35 <= last["fraction"] < 1.0
        assert "t = " in last["reason"]
        if runtime._entry_beliefs is not None:
            assert runtime._entry_beliefs["size_fraction"] == pytest.approx(last["fraction"], abs=1e-4)
    finally:
        await runtime.stop()


async def test_sure_evidence_takes_the_full_approved_size_and_never_more() -> None:
    runtime, execution, market = build_runtime_paper_with(conviction_sizing=True)
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)  # seeds t >> 3
        assert runtime.counters["sized_down"] == 0
        last = runtime.snapshot()["sizing"]["last"]
        assert last["fraction"] == 1.0
    finally:
        await runtime.stop()


async def test_a_strategy_with_a_losing_record_is_muted_and_its_signals_refused() -> None:
    runtime, execution, market = build_runtime_paper_with()
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        strategy_id = runtime._entry_beliefs["strategy_id"]
        assert strategy_id
        # Its own record, thirty-plus losers: worse than its noise, well past the floor.
        for i in range(40):
            runtime._scoreboard.record(strategy_id, -30.0 + (2.0 if i % 2 else -2.0))
        assert runtime._scoreboard.is_muted(strategy_id)

        refusals: list[dict[str, Any]] = []
        runtime._on_event = lambda e: refusals.append(e) if e["type"] == "live.no_trade" else None
        for _ in range(200):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["strategy_muted"] > 0
        assert any("muted" in str(e["data"].get("reason", "")) for e in refusals)
        row = next(r for r in runtime.snapshot()["strategies"] if r["strategy_id"] == strategy_id)
        assert row["muted"] is True
    finally:
        await runtime.stop()


async def test_absorbed_evidence_credits_the_strategies_it_names() -> None:
    runtime, _execution, _market = build_runtime_paper_with()
    result = runtime.absorb_evidence(
        outcomes=[],
        reviews=[
            {
                "regime": "trending_up", "direction": "long", "confidence": 0.6,
                "expected_net_bps": 5.0, "net_bps": 12.0, "fees_bps": 4.0,
                "closed_at": datetime.now(UTC), "signal_id": "s1", "symbol": "BTC-USD",
                "entry_price": 100.0, "quantity": 1.0, "exploratory": False,
                "strategy_id": "trend_following",
            },
            {
                "regime": "trending_up", "direction": "long", "confidence": 0.6,
                "expected_net_bps": 5.0, "net_bps": -3.0, "fees_bps": 4.0,
                "closed_at": datetime.now(UTC), "signal_id": "s2", "symbol": "BTC-USD",
                "entry_price": 100.0, "quantity": 1.0, "exploratory": False,
                "strategy_id": None,  # written before strategies were credited
            },
        ],
    )
    assert result["strategies_credited"] == 1
    board = runtime.snapshot()["strategies"]
    assert [r["strategy_id"] for r in board] == ["trend_following"]


# --------------------------------------------------------------------------- the tide


class HourlyMarketData(FakeMarketData):
    """A feed that serves hourly bars to hourly requests — the property the higher-
    timeframe context needs and the plain fake deliberately lacks."""

    def __init__(self, candles: list[Candle], clock: SimulatedClock | None, hourly: list[Candle]) -> None:
        super().__init__(candles, clock)
        self.hourly = hourly

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        if timeframe == "1h":
            return self.hourly[-limit:]
        return await super().get_candles(symbol, timeframe, limit=limit, end=end)


def _hourly_series(direction: str, hours: int = 800) -> list[Candle]:
    import math

    from tia.domain.market import Candle as _Candle

    start = datetime.now(UTC) - timedelta(hours=hours + 1)
    drift = 0.0008 if direction == "up" else -0.0008
    price, out = 50_000.0, []
    for i in range(hours):
        price *= math.exp(drift + (0.002 if i % 2 else -0.002))
        open_time = start + timedelta(hours=i)
        out.append(
            _Candle(
                symbol="BTC-USD", timeframe="1h", open_time=open_time,
                close_time=open_time + timedelta(hours=1) - timedelta(seconds=1),
                open=price, high=price * 1.001, low=price * 0.999, close=price, volume=1.0,
            )
        )
    return out


def build_runtime_with_tide(direction: str, **live_overrides: Any):  # type: ignore[no-untyped-def]
    scenario = get_scenario("trend_up")
    span_minutes = scenario.total_bars + 5
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=span_minutes), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = HourlyMarketData(candles, clock, _hourly_series(direction))
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(**live_overrides), activation=None, market_data=market,
        execution=execution, clock=clock, poll_interval_seconds=0.0,
    )
    return runtime, execution, market


async def test_the_plain_feed_leaves_the_tide_unknown_and_imposes_nothing() -> None:
    runtime, _execution, market = build_runtime_paper_with()
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()
        trend = runtime.snapshot()["trend"]
        assert trend["available"] is False
        assert "served" in trend["reason"]  # minute bars to an hourly request: refused
        assert runtime.counters["htf_rejected"] == 0
    finally:
        await runtime.stop()


async def test_entries_against_a_down_tide_are_refused_and_with_it_taken() -> None:
    """A four-week decline: every long the strategies propose is refused as against the
    tide; shorts pass the gate. Then the same session in soft mode halves instead."""
    runtime, _execution, market = build_runtime_with_tide("down", htf_mode="hard")
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        refusals: list[str] = []
        runtime._on_event = lambda e: refusals.append(str(e["data"].get("reason", ""))) if e["type"] == "live.no_trade" else None
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
        trend = runtime.snapshot()["trend"]
        assert trend["available"] is True and trend["bias"] == "down"
        assert runtime.counters["htf_rejected"] > 0
        assert any("against the tide" in r for r in refusals)
        # Whatever was taken went with the tide: every opening order is a sell.
        entries = [o for o in _execution.orders.values() if not o.signal_id.startswith(("protective", "exit"))]
        assert all(o.side is Side.SELL for o in entries)
    finally:
        await runtime.stop()

    runtime, _execution, market = build_runtime_with_tide("down", htf_mode="soft")
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["htf_sized_down"] > 0:
                break
        assert runtime.counters["htf_rejected"] == 0
        assert runtime.counters["htf_sized_down"] > 0
        last = runtime.snapshot()["sizing"]["last"]
        assert last["fraction"] <= 0.5 and "halved" in last["reason"]
    finally:
        await runtime.stop()


async def test_the_tide_is_read_on_a_slow_clock_not_every_bar() -> None:
    runtime, _execution, market = build_runtime_with_tide("up", htf_mode="hard", htf_refresh_minutes=60)
    reads = {"n": 0}
    original = market.get_candles

    async def counting(symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        if timeframe == "1h":
            reads["n"] += 1
        return await original(symbol, timeframe, limit=limit, end=end)

    market.get_candles = counting  # type: ignore[method-assign]
    await runtime.start()
    try:
        for _ in range(90):  # ninety one-minute bars: one hour and a half
            market.advance()
            await runtime._cycle_once()
        assert reads["n"] == 2
        assert runtime.snapshot()["trend"]["bias"] == "up"
    finally:
        await runtime.stop()


# --------------------------------------------------------------------------- the account


async def test_the_paper_account_starts_from_its_capital_and_carries_the_records_pnl() -> None:
    """A restart is not a new account: the record's realised P&L is booked as realised on
    top of the starting capital, never as a deposit, and the balance carries on."""
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    execution = FakeExecution(balance=10_250.0)  # 10,000 of capital plus 250 already made
    runtime = LiveRuntime(
        live_settings(paper_capital=10_000.0), activation=None,
        market_data=FakeMarketData(candles, clock), execution=execution, clock=clock,
        prior_realised_pnl=250.0, poll_interval_seconds=0.0,
    )
    await runtime.start()
    try:
        capital = runtime.snapshot()["capital"]
        assert capital["allocated_capital"] == pytest.approx(10_000.0)
        assert capital["realised_pnl"] == pytest.approx(250.0)
        assert capital["equity"] == pytest.approx(10_250.0)
        account = runtime.snapshot()["account"]
        assert account["starting_capital"] == 10_000.0
        assert account["prior_realised_pnl"] == 250.0
        assert account["equity"] == pytest.approx(10_250.0)
        assert account["return_pct"] == pytest.approx(2.5)
        assert account["leverage_max"] == 5.0
    finally:
        await runtime.stop()


async def test_a_wiped_out_paper_account_refuses_to_start_and_says_why() -> None:
    from tia.core.errors import LiveActivationError

    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    runtime = LiveRuntime(
        live_settings(paper_capital=10_000.0), activation=None,
        market_data=FakeMarketData(candles, clock), execution=FakeExecution(balance=0.0),
        clock=clock, prior_realised_pnl=-10_000.0, poll_interval_seconds=0.0,
    )
    with pytest.raises(LiveActivationError, match="wiped out"):
        await runtime.start()


async def test_leverage_scales_the_exposure_limits_in_paper_and_never_over_live_execution() -> None:
    paper, _execution, _market = build_runtime_paper_with(leverage=5.0)
    assert paper._leverage == 5.0
    assert paper._risk.limits.max_position_notional_pct == pytest.approx(
        paper._settings.risk.max_position_notional_pct * 5.0
    )
    assert paper._risk.limits.max_gross_exposure_pct == pytest.approx(
        paper._settings.risk.max_gross_exposure_pct * 5.0
    )
    # The configured limits themselves are untouched: a fingerprint bound to them holds.
    assert paper._settings.risk.max_position_notional_pct == 20.0

    clock = SimulatedClock(datetime.now(UTC))
    live, _e, _m = build_runtime(
        execution=FakeExecution(live_token=real_token(clock), clock=clock), clock=clock
    )
    assert live._execution.is_live
    assert live._leverage == 1.0
    assert live._risk.limits.max_position_notional_pct == 20.0


async def test_a_leveraged_account_is_liquidated_below_maintenance_and_charged_for_it() -> None:
    """Equity eaten down to the maintenance margin: the venue closes the position at
    market, charges the fee, files the exit as a liquidation, and halts a wiped account."""
    saved: list[tuple[str, dict[str, Any]]] = []
    runtime, execution, market = build_runtime_paper_with(
        leverage=5.0, maintenance_margin_pct=50.0, liquidation_fee_bps=50.0,
        persist=lambda kind, payload: saved.append((kind, payload)),
    )
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        notional = abs(position.quantity) * execution.price
        # Losses elsewhere have eaten the account down to a sliver of the margin.
        equity_before = runtime._ledger.snapshot().equity
        runtime._ledger.record_realised_pnl(-(equity_before - notional * 0.10))
        reviews_before = runtime._retro.reviews

        market.advance()
        await runtime._cycle_once()

        assert runtime.counters["liquidations"] == 1
        assert runtime.counters["exits_liquidation"] == 1
        assert runtime._retro.reviews == reviews_before + 1
        assert not (await execution.get_positions())
        assert any(amount < 0 and "liquidation" in reason for amount, reason in execution.adjustments)
        outcome = next(p for k, p in saved if k == "edge_outcome")
        assert outcome["exit_reason"] == "liquidated"
        # 10% of notional was left; the fee took half a percent of it. Not wiped: still running.
        assert runtime.state is LiveState.RUNNING
        assert runtime.snapshot()["account"]["liquidations"] == 1
    finally:
        await runtime.stop()


async def test_a_liquidation_that_empties_the_account_halts_new_orders() -> None:
    runtime, execution, market = build_runtime_paper_with(
        leverage=5.0, maintenance_margin_pct=50.0, liquidation_fee_bps=100.0,
    )
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        equity_before = runtime._ledger.snapshot().equity
        runtime._ledger.record_realised_pnl(-(equity_before - 1.0))  # one dollar left
        market.advance()
        await runtime._cycle_once()
        assert runtime.counters["liquidations"] == 1
        assert runtime.state is LiveState.HALT_NEW_ORDERS
        history = runtime.machine.as_dict()["history"]
        assert "wiped out" in history[-1]["reason"]
    finally:
        await runtime.stop()


async def test_funding_is_charged_once_per_settlement_at_the_live_rate() -> None:
    """Across an eight-hour boundary a long pays positive funding, a short receives it,
    and a period the session joined late is never charged."""
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = FakeMarketData(candles, clock)
    execution = FakeExecution()
    rate = {"value": 0.0001}
    runtime = LiveRuntime(
        live_settings(charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0),
        activation=None, market_data=market, execution=execution, clock=clock,
        funding_rate=lambda: rate["value"], poll_interval_seconds=0.0,
    )
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        long = position.quantity > 0
        notional = abs(position.quantity) * execution.price
        # Pin the stop far away so nothing but funding touches the account.
        runtime._planned_exit["stop"] = execution.price * (0.5 if long else 1.5)
        paid_before = runtime.funding["payments"]
        equity_before = runtime._ledger.snapshot().equity

        # The next bar belongs to a new eight-hour period as far as the session knows.
        runtime._funding_period = ("1970-01-01", 0)
        market.advance()
        await runtime._cycle_once()
        assert runtime._open_trade is not None, "the position closed before funding settled"
        assert runtime.funding["payments"] == paid_before + 1
        expected = 0.0001 * notional * (1.0 if long else -1.0)
        assert runtime.funding["paid_usd"] == pytest.approx(expected, rel=0.05)
        assert runtime._ledger.snapshot().equity == pytest.approx(equity_before - expected, rel=1e-6)
        assert execution.adjustments and "funding" in execution.adjustments[-1][1]
        assert runtime.snapshot()["account"]["funding"]["last_rate"] == 0.0001
    finally:
        await runtime.stop()


async def test_without_a_funding_reading_nothing_is_charged_and_it_is_counted() -> None:
    runtime, _execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: None
    await runtime.start()
    try:
        await _open_a_position(runtime, _execution, market)
        runtime._funding_period = ("1970-01-01", 0)  # force the next bar to be a new period
        market.advance()
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0
        assert runtime.funding["skipped_no_rate"] == 1
    finally:
        await runtime.stop()


async def test_paper_reconciliation_tolerates_a_leveraged_open_position() -> None:
    """A leveraged position leaves cash negative by design; the simulated account is
    reconciled on equity, so its own fills never read as a withdrawal or a halt."""
    runtime, execution, market = build_runtime_paper_with(leverage=5.0)
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        execution.balance = -25_000.0  # what a 5x long looks like in the till
        await runtime._reconcile()
        assert runtime.state is LiveState.RUNNING
        assert not runtime.ledger.is_halted
        assert runtime.ledger.snapshot().withdrawals == 0.0
    finally:
        await runtime.stop()


# --------------------------------------------------------------------------- the funnel


def _seed_unproven(runtime: LiveRuntime, mean_bps: float = 6.0, spread: float = 90.0) -> None:
    """Evidence with a positive mean that cannot clear its own uncertainty: unproven."""
    from tia.domain.enums import Direction, MarketRegime
    from tia.economics.expected_value import Outcome

    # Every confidence band, so no signal can land in a bucket the estimator knows
    # nothing about — the verdict under test is "unproven", not "unknown".
    runtime._edges.record_many(
        [
            Outcome(
                regime=regime, direction=direction, confidence=confidence,
                net_return_bps=mean_bps + (spread if i % 2 else -spread),
            )
            for regime in MarketRegime
            for direction in (Direction.LONG, Direction.SHORT)
            for confidence in (0.50, 0.65, 0.78, 0.90)
            for i in range(40)
        ]
    )


async def test_the_funnel_says_where_every_signal_went() -> None:
    runtime, _execution, market = build_runtime_paper_with()
    await runtime.start()
    try:
        for _ in range(120):
            market.advance()
            await runtime._cycle_once()
        funnel = runtime.snapshot()["funnel"]
        stages = funnel["stages"]
        assert stages["evaluated"] == runtime.counters["signals"] > 0
        assert stages["evaluated"] == stages["not_actionable"] + stages["actionable"]
        # No evidence at all and exploration off: every actionable signal that reached
        # the expected-value gate was refused there, and each refusal kept its reason.
        assert stages["expected_value"] > 0
        assert runtime.counters["ev_unknown"] == stages["expected_value"]
        assert funnel["recent_refusals"] and funnel["recent_refusals"][0]["stage"] in {
            "expected_value", "risk", "budget", "spread"
        }
        assert funnel["exploration"] == {"enabled": False, "per_day": 0, "used_today": 0}
    finally:
        await runtime.stop()


async def test_exploration_buys_lessons_in_unproven_buckets_but_never_in_disproven_ones() -> None:
    """A positive mean that has not cleared its noise is worth a cheap lesson in paper;
    a bucket whose mean is at or below zero is respected and never traded."""
    runtime, _execution, market = build_runtime_paper_with(exploration_trades_per_day=3)
    await runtime.start()
    try:
        _seed_unproven(runtime)
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["exploration_trades"] >= 1:
                break
        assert runtime.counters["ev_unproven"] > 0
        assert runtime.counters["exploration_trades"] >= 1
        assert runtime.snapshot()["funnel"]["stages"]["exploration"] >= 1
        beliefs = runtime._entry_beliefs
        if beliefs is not None:
            assert beliefs["exploratory"] is True
            assert beliefs["size_fraction"] == pytest.approx(0.25)
    finally:
        await runtime.stop()

    runtime, _execution, market = build_runtime_paper_with(exploration_trades_per_day=3)
    await runtime.start()
    try:
        _seed_unproven(runtime, mean_bps=-5.0)  # disproven: the mean itself is red
        for _ in range(200):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["ev_disproven"] > 0
        assert runtime.counters["exploration_trades"] == 0
        assert runtime.counters["orders"] == 0
    finally:
        await runtime.stop()


async def test_the_daily_trade_count_rolls_over_at_midnight_utc() -> None:
    """The budget caps entries per DAY. A counter that never reset capped them per
    session — eight entries on Monday and silence until a restart."""
    runtime, _execution, market = build_runtime_paper_with()
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()
        runtime._trades_today = 8
        runtime._roll_trading_day()
        assert runtime._trades_today == 8  # same day: nothing changes
        runtime._clock.advance_by(timedelta(days=1))
        runtime._roll_trading_day()
        assert runtime._trades_today == 0
        funnel = runtime.snapshot()["funnel"]
        assert funnel["trades_today"] == 0
        assert funnel["trades_per_day_cap"] == 8  # the conservative profile's cap
        assert funnel["risk_profile"] == "conservative"
    finally:
        await runtime.stop()


# --------------------------------------------------------------------------- the feed


async def test_the_loop_waits_on_the_feed_when_it_can_wake_on_a_bar() -> None:
    """A streaming feed replaces the poll sleep: the loop asks the feed to wake it on
    the next close, with the poll interval as the ceiling, and the snapshot names the
    transport in use."""
    runtime, _execution, market = build_runtime_paper_with()
    waits: list[float] = []

    async def wait_for_bar(timeout_seconds: float) -> bool:
        waits.append(timeout_seconds)
        market.advance()
        if len(waits) >= 3:
            runtime._stop_requested = True
        return True

    market.wait_for_bar = wait_for_bar  # type: ignore[attr-defined]
    market.feed_state = lambda: {"transport": "websocket", "latency_ms": 210}  # type: ignore[attr-defined]
    await runtime.start()
    try:
        await runtime._task  # the loop runs until the fake feed stops it
        assert waits == [0.0, 0.0, 0.0]
        assert runtime.snapshot()["feed"] == {"transport": "websocket", "latency_ms": 210}
    finally:
        await runtime.stop()


async def test_a_polling_feed_is_reported_as_such() -> None:
    runtime, _execution, _market = build_runtime_paper_with()
    assert runtime.snapshot()["feed"] == {"transport": "rest", "poll_seconds": 0.0}


async def test_the_spread_check_prices_the_idea_against_the_live_book() -> None:
    runtime, _execution, market = build_runtime_paper_with(quoting=True)
    market.spread_bps = 0.3  # about two dollars on a 60k coin
    await runtime.start()
    try:
        assert runtime.spread_check()["available"] is False  # no quote before the first bar
        market.advance()
        await runtime._cycle_once()
        check = runtime.spread_check(size_btc=0.01)
        assert check["available"] is True
        assert check["spread_usd"] == pytest.approx(check["mid"] * 0.3 / 10_000, rel=1e-3)
        assert check["gross_per_round_trip_usd"] == pytest.approx(check["spread_usd"] * 0.01, rel=1e-6)
        fee = check["notional_usd"] * 2 * check["maker_fee_bps_per_leg"] / 10_000
        assert check["fees_per_round_trip_usd"] == pytest.approx(fee, rel=1e-3)
        assert check["net_per_round_trip_usd"] < 0  # 0.3 bps of spread cannot pay two maker legs
        assert check["max_round_trips_per_s"] == 5.0
        assert "cover the fees" in check["verdict"]
        assert check["caveats"]
    finally:
        await runtime.stop()
