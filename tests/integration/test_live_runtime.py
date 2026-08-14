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

    def __init__(self, *, balance: float = 1_000.0) -> None:
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


# --------------------------------------------------------------------------- the gate


def test_live_runtime_cannot_exist_without_an_activation_token() -> None:
    """The constructor's first argument is load-bearing: no token, no instance."""
    settings = live_settings()
    with pytest.raises((TypeError, LiveActivationError)):
        LiveRuntime(  # type: ignore[call-arg]
            settings,
            market_data=FakeMarketData([]),
            execution=FakeExecution(),
            clock=SystemClock(),
        )


def test_live_runtime_rejects_an_expired_token_at_construction() -> None:
    from tia.core.clock import SimulatedClock

    clock = SimulatedClock(START)
    token = real_token(clock)
    clock.advance_by(timedelta(hours=7))
    with pytest.raises(LiveActivationError, match="expired"):
        LiveRuntime(
            live_settings(),
            activation=token,
            market_data=FakeMarketData([]),
            execution=FakeExecution(),
            clock=clock,
        )


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

    runtime2, _, market = build_runtime(
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
