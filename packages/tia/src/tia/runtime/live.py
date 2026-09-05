"""The live runtime — the same pipeline as paper, against a venue that holds real money.

Deliberately a separate class from the paper engine rather than a mode flag on it. The two
share every *component* — quality gate, features, regimes, strategies, risk engine, budget,
cost model, EV engine, capital ledger — but differ in exactly the places where a shared
code path would be a shared failure mode:

* **Time is real.** A ``SystemClock``, wall-clock polling, and a venue whose clock is not
  ours (hence the skew monitor).
* **State is unknown by default.** The venue's answer wins every disagreement, a timeout
  means *unknown* rather than *failed*, and reconciliation runs on a schedule instead of
  at convenient moments.
* **The expected-value gate enforces. Always.** There is no flag. The paper engine
  observes because paper is how evidence is produced; here, a signal without a measured
  edge that clears its costs does not become an order, and no configuration can change
  that — the enforcement is the absence of the switch.

Construction over a **live** execution provider requires a
:class:`~tia.live.gate.LiveActivationToken` — tests mint theirs through the real gate, so
"no real-money runtime without a passed gate" holds in the suite too. Over a *simulated*
provider the same class runs as **paper-realtime**: real market data, real clock, paper
fills — the configuration a 24/7 paper track record is built on. The token requirement
binds to what the money can do, and the provider layer enforces the same rule
independently at construction.

What this runtime does **not** do: withdraw, transfer, or touch any funds beyond placing
and cancelling spot orders inside its capital ceiling. The adapter beneath it has no such
surface and the API key must lack the permission — see ``docs/SECURITY.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any

from tia.core.clock import Clock
from tia.core.config import Settings
from tia.core.errors import (
    LiveActivationError,
    ProviderUnavailableError,
    ReconciliationError,
    TiaError,
)
from tia.core.ids import deterministic_id, new_ulid
from tia.core.logging import get_logger
from tia.core.money import D, meets_min_notional, quantize_down
from tia.data.providers.base import MarketDataProvider
from tia.data.quality import DataQualityEngine
from tia.domain.enums import Direction, MarketRegime, OrderType, Side, TimeInForce
from tia.domain.market import Candle
from tia.domain.orders import Fill, Order, OrderIntent
from tia.economics.costs import CostModel, FeeSchedule, MarketConditions
from tia.economics.expected_value import EdgeEstimator, ExpectedValueEngine, Outcome
from tia.execution.provider import ExecutionProvider
from tia.learning.retrospective import RetrospectiveEngine
from tia.live.gate import LiveActivationToken, configuration_fingerprint
from tia.portfolio.capital import CapitalLedger, CapitalPolicy
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeClassifier
from tia.risk.budget import BudgetInputs, RiskBudgetEngine, RiskProfileName
from tia.risk.engine import RiskEngine
from tia.runtime.states import LiveState, LiveStateMachine
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import build_strategies

_log = get_logger("runtime.live")

#: Above this measured skew against the venue, new orders halt. Half of the signing
#: recvWindow, so the halt fires before the venue starts rejecting.
MAX_CLOCK_SKEW_MS = 2_500


class ClockSkewMonitor:
    """Measures our clock against the venue's, and remembers the answer.

    The failure this catches is quiet: a drifting clock produces signed-request rejections
    whose error text does not mention time, and an unmonitored drift is diagnosed at 2 a.m.
    by someone reading HMAC documentation. Checked at startup, then periodically, and the
    latest answer is part of the runtime snapshot.
    """

    def __init__(
        self,
        clock: Clock,
        venue_time_ms: Callable[[], Awaitable[int]],
        *,
        max_skew_ms: float = MAX_CLOCK_SKEW_MS,
    ) -> None:
        self._clock = clock
        self._venue_time_ms = venue_time_ms
        self._max = max_skew_ms
        self.last_skew_ms: float | None = None
        self.last_ok: bool | None = None

    async def check(self) -> tuple[float, bool]:
        venue_ms = await self._venue_time_ms()
        local_ms = self._clock.timestamp_ms()
        skew = float(local_ms - venue_ms)
        self.last_skew_ms = skew
        self.last_ok = abs(skew) <= self._max
        return skew, self.last_ok

    def as_dict(self) -> dict[str, Any]:
        return {
            "last_skew_ms": self.last_skew_ms,
            "ok": self.last_ok,
            "threshold_ms": self._max,
        }


class LatencyTracker:
    """Measured stage timings for the decision-to-fill path. Measured, never assumed.

    The cost model charges latency as a cost, and a charged number that comes from
    configuration is a guess wearing a decimal point. This tracker feeds it the observed
    exponential moving average instead.
    """

    STAGES = (
        "market_received",
        "decision_started",
        "decision_finished",
        "risk_started",
        "risk_finished",
        "order_submit",
        "order_ack",
        "fill_received",
    )

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._open: dict[str, dict[str, int]] = {}
        self.samples: deque[dict[str, Any]] = deque(maxlen=500)
        self.ema_submit_to_ack_ms: float | None = None
        self.ema_total_ms: float | None = None

    def stamp(self, correlation_id: str, stage: str) -> None:
        self._open.setdefault(correlation_id, {})[stage] = self._clock.monotonic_ns()

    def finish(self, correlation_id: str, *, symbol: str = "") -> dict[str, Any] | None:
        stamps = self._open.pop(correlation_id, None)
        if not stamps:
            return None

        def span(a: str, b: str) -> float | None:
            if a in stamps and b in stamps:
                return (stamps[b] - stamps[a]) / 1e6
            return None

        segments = {
            "market_to_decision": span("market_received", "decision_started"),
            "decision": span("decision_started", "decision_finished"),
            "decision_to_risk": span("decision_finished", "risk_started"),
            "risk": span("risk_started", "risk_finished"),
            "risk_to_submit": span("risk_finished", "order_submit"),
            "submit_to_ack": span("order_submit", "order_ack"),
            "ack_to_fill": span("order_ack", "fill_received"),
        }
        total = span("market_received", "fill_received") or span(
            "market_received", "order_ack"
        )
        sample = {
            "correlation_id": correlation_id,
            "symbol": symbol,
            "segments_ms": {k: round(v, 3) for k, v in segments.items() if v is not None},
            "total_ms": round(total, 3) if total is not None else None,
            "at": self._clock.now(),
        }
        self.samples.appendleft(sample)

        ack = segments.get("submit_to_ack")
        if ack is not None:
            self.ema_submit_to_ack_ms = (
                ack
                if self.ema_submit_to_ack_ms is None
                else 0.2 * ack + 0.8 * self.ema_submit_to_ack_ms
            )
        if total is not None:
            self.ema_total_ms = (
                total if self.ema_total_ms is None else 0.2 * total + 0.8 * self.ema_total_ms
            )
        return sample

    def as_dict(self) -> dict[str, Any]:
        return {
            "ema_submit_to_ack_ms": self.ema_submit_to_ack_ms,
            "ema_total_ms": self.ema_total_ms,
            "recent": list(self.samples)[:10],
        }


class LiveRuntime:
    """Runs the decision pipeline against a real venue, under an activation token."""

    def __init__(
        self,
        settings: Settings,
        *,
        activation: LiveActivationToken | None,
        market_data: MarketDataProvider,
        execution: ExecutionProvider,
        clock: Clock,
        venue_time_ms: Callable[[], Awaitable[int]] | None = None,
        persist: Callable[[str, dict[str, Any]], Any] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        prior_outcomes: Sequence[Outcome] = (),
        prior_reviews: Sequence[dict[str, Any]] = (),
        symbol_filters: dict[str, Any] | None = None,
        poll_interval_seconds: float = 5.0,
        reconcile_every_cycles: int = 12,
        skew_check_every_cycles: int = 60,
    ) -> None:
        # Paper-realtime is this same runtime over a *simulated* execution provider and
        # real market data — the configuration a 24/7 paper track record runs on. The
        # token requirement binds to what the money can do, not to the class name: a
        # provider that can spend real funds demands a token; a simulator demands none,
        # and the provider layer independently enforces the same rule at construction.
        if execution.is_live:
            if activation is None:
                raise LiveActivationError(
                    "a LiveRuntime over a live execution provider cannot exist without "
                    "an activation token"
                )
            activation.assert_usable(now=clock.now())

        self._settings = settings
        self._activation = activation
        self._market_data = market_data
        self._execution = execution
        self._clock = clock
        self._venue_time_ms = venue_time_ms
        self._persist = persist
        self._on_event = on_event or (lambda _e: None)
        self._symbol = settings.live.symbol
        self._timeframe = settings.market_data.timeframe
        self._poll_interval = poll_interval_seconds
        self._reconcile_every = max(1, reconcile_every_cycles)
        self._skew_every = max(1, skew_check_every_cycles)
        self._filters = symbol_filters or {}

        self.run_id = f"live_{new_ulid(clock)}"
        self.machine = LiveStateMachine(clock)
        self.machine.transition(LiveState.ARMING, reason="constructing live runtime")
        if activation is not None:
            self.machine.transition(
                LiveState.ARMED,
                reason=f"activation token accepted (issued by {activation.issued_by})",
                actor=activation.issued_by,
            )
        else:
            self.machine.transition(
                LiveState.ARMED,
                reason="paper-realtime: simulated execution, no token required",
            )

        #: The fingerprint the token was bound to, recomputed per order so a limit change
        #: after arming voids every subsequent submission.
        self._fingerprint = configuration_fingerprint(settings.risk, settings.live)

        # --- shared components, identical to paper -----------------------------------
        self._quality = DataQualityEngine(settings.data_quality)
        self._features = FeatureBuilder()
        self._regimes = RegimeClassifier()
        self._strategies = StrategyEngine(
            build_strategies(settings.strategy.enabled), settings.strategy, clock
        )
        from tia.domain.instruments import DEFAULT_UNIVERSE

        self._risk = RiskEngine(settings.risk, DEFAULT_UNIVERSE, clock)
        self._budget = RiskBudgetEngine(RiskProfileName(settings.live.risk_profile))
        self._costs = CostModel(
            FeeSchedule(
                maker_bps=settings.execution.maker_fee_bps,
                taker_bps=settings.execution.taker_fee_bps,
                verified_at_source=False,
                source="configured — replace with account facts via validate_binance.py",
            )
        )
        self._edges = EdgeEstimator()
        self._edges.record_many(list(prior_outcomes))
        # Enforcement is structural: threshold from config, but there is no observe mode
        # in this class at all. The paper engine is where observation happens.
        self._ev = ExpectedValueEngine(
            self._edges,
            threshold_bps=settings.live.ev_threshold_bps,
            max_cost_ratio=settings.live.max_cost_ratio,
        )
        # The retrospective reads a lesson from every closed trade and — unlike in the demo
        # — its guardrails *act*: a bucket that has recently disappointed must clear a
        # higher edge threshold before this session will trade it again. Rebuilt from the
        # persisted trade record so a restart keeps the lessons, exactly like the estimator.
        self._retro = RetrospectiveEngine()
        self._retro.record_many(list(prior_reviews))
        if execution.is_live:
            # Real money: the configured ceiling, whose fail-closed default of zero is
            # rejected by CapitalPolicy — exactly the refusal we want.
            ledger_ceiling = settings.live.max_live_capital
        else:
            # Paper-realtime: nothing here can spend, so the live ceiling's zero default
            # must not stop the session. The simulated bankroll bounds the ledger; a
            # configured live ceiling still binds if one is set.
            ledger_ceiling = settings.live.max_live_capital or settings.initial_capital
        self._ledger = CapitalLedger(
            CapitalPolicy(max_live_capital=ledger_ceiling),
            clock=clock,
        )
        self.skew = (
            ClockSkewMonitor(clock, venue_time_ms) if venue_time_ms is not None else None
        )
        self.latency = LatencyTracker(clock)

        self._consecutive_losses = 0
        for outcome in reversed(list(prior_outcomes)):
            if outcome.net_return_bps > 0:
                break
            self._consecutive_losses += 1

        self._buffer: deque[Candle] = deque(maxlen=400)
        self._last_close = None
        self._open_trade: dict[str, Any] | None = None
        self._entry_beliefs: dict[str, Any] | None = None
        self._peak_equity = 0.0
        self._trades_today = 0
        self._cycle = 0
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self.last_error = ""
        #: Watchdog state. A transient provider failure halts entries and heals itself
        #: after a clean reconciliation; a *persistent* one escalates to SAFE_MODE.
        self._provider_failures = 0
        self._watchdog_halt = False
        self._last_bar_wall = clock.now()
        #: Updated every loop cycle. "The HTTP server answers" and "the trading engine is
        #: alive" are different facts; this is the second one.
        self.last_heartbeat = clock.now()
        self.market_data_ttl_seconds = 300.0
        self._last_reconciliation_clean: bool | None = None
        self.counters: dict[str, int] = {
            "cycles": 0, "bars": 0, "quality_skipped": 0, "signals": 0,
            "risk_rejected": 0, "budget_rejected": 0, "ev_rejected": 0,
            "guardrail_rejected": 0, "exploration_trades": 0,
            "orders": 0, "fills": 0, "reconciliations": 0, "reconciliation_breaks": 0,
            "unknown_order_states": 0, "skew_halts": 0,
            "maker_fills": 0, "orders_expired": 0, "resting_skipped": 0,
            "stops_placed": 0, "exits_stop": 0, "exits_target": 0,
            "exits_reversal": 0, "exits_time": 0, "suppressed_position_open": 0,
            "unprotected_positions": 0,
        }
        #: The one protective stop covering the open position, if any. Exactly one, sized
        #: to the position: a stop that protects the wrong size is worse than none.
        self._protective: dict[str, Any] | None = None
        #: The exit levels the entry was approved with, carried from the decision to the
        #: position, and the bar the position opened on (for the optional time stop).
        self._planned_exit: dict[str, Any] = {}
        self._position_opened_bar: int | None = None
        #: Why the round trip in progress is ending, for the record. Set by whichever
        #: path closes it; read once by the scorer.
        self._exit_reason: str | None = None
        #: The one order allowed to rest at a time, if entries are limit orders. While it
        #: rests, no new entry is considered — stacking resting orders is how a session
        #: ends up long three times on one signal.
        self._resting: dict[str, Any] | None = None
        #: Fill ids already routed to the ledger and the round-trip tracker. A fill can be
        #: seen twice — on the submit response and again on a later order read — and it
        #: must be counted once.
        self._seen_fills: set[str] = set()
        self._exploration_used = 0
        self._exploration_day = ""
        #: Evidence folded in *after* startup — training runs that finished while this
        #: session was already live. See :meth:`absorb_evidence`.
        self._evidence_absorbed = 0
        self._evidence_absorbed_at: datetime | None = None

    @property
    def exploration_enabled(self) -> bool:
        """Whether exploration trades exist at all for this runtime.

        Two conditions, and the second is not configurable: a positive budget in config,
        AND a simulated execution provider. Over real money this is False no matter what
        the configuration says — exploration buys lessons, and lessons are only worth
        buying with simulated funds.
        """
        return (
            self._settings.live.exploration_trades_per_day > 0
            and not self._execution.is_live
        )

    def _exploration_budget_left(self) -> bool:
        """Per-UTC-day budget, keyed on the injected clock so replays behave."""
        today = self._clock.now().date().isoformat()
        if today != self._exploration_day:
            self._exploration_day = today
            self._exploration_used = 0
        return self._exploration_used < self._settings.live.exploration_trades_per_day

    # ------------------------------------------------------------------ properties

    @property
    def entry_is_limit(self) -> bool:
        """Whether entries rest as maker orders. Read live, so a config reload applies."""
        return self._settings.live.entry_order_type == "limit"

    @property
    def typical_trade_notional_usd(self) -> float:
        """Median dollars-at-work per closed trade — the bps→USD conversion factor."""
        return self._retro.typical_notional_usd

    @property
    def state(self) -> LiveState:
        return self.machine.state

    @property
    def is_running(self) -> bool:
        return self.machine.state in {
            LiveState.RUNNING,
            LiveState.HALT_NEW_ORDERS,
            LiveState.CANCEL_ONLY,
            LiveState.PAUSED,
        }

    @property
    def ledger(self) -> CapitalLedger:
        return self._ledger

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Startup validation, then the loop. RUNNING is set only when both succeeded.

        Order of checks is deliberate: cheapest and most-likely-to-fail first, and no
        order is placeable until every one has passed.
        """
        self.machine.require(LiveState.ARMED, action="start")
        self.machine.transition(LiveState.STARTING, reason="startup validation")

        try:
            # 1. The token must still be alive — arming and starting can be minutes apart.
            if self._execution.is_live and self._activation is not None:
                self._activation.assert_usable(
                    now=self._clock.now(), fingerprint=self._fingerprint
                )

            # 2. The venue's clock and ours must agree within the signing window.
            if self.skew is not None:
                skew, ok = await self.skew.check()
                if not ok:
                    raise LiveActivationError(
                        f"clock skew {skew:.0f} ms exceeds ±{MAX_CLOCK_SKEW_MS} ms; fix "
                        "NTP before starting — signed requests would be rejected with an "
                        "error that does not mention the clock"
                    )

            # 3. The venue must answer, and the balance funds the ledger.
            balance = await self._execution.get_balance()
            if self._execution.is_live:
                # The ceiling governs real money. A live ceiling of zero funds nothing,
                # which is the fail-closed default doing its job.
                allocation = min(float(balance), self._settings.live.max_live_capital)
                note = f"live start: min(venue balance {balance}, ceiling)"
            else:
                # Paper-realtime: simulated capital, already capped at construction.
                # Binding it to the *live* ceiling would make the safe default
                # (max_live_capital=0) refuse a session that cannot spend anything.
                allocation = float(balance)
                note = f"paper-realtime start: simulated balance {balance}"
            if allocation <= 0:
                raise LiveActivationError(
                    f"venue balance {balance} funds no allocation under the ceiling "
                    f"{self._settings.live.max_live_capital}; nothing to trade with"
                )
            self._ledger.allocate(allocation, at=self._clock.now(), note=note)
            self._peak_equity = allocation
        except Exception as exc:
            self.last_error = str(exc)[:500]
            self.machine.transition(LiveState.STOPPING, reason=f"startup failed: {exc}")
            self.machine.transition(LiveState.ERROR, reason="startup validation failed")
            self._incident("startup_failed", reason=str(exc)[:500])
            raise

        self._stop_requested = False
        self._task = asyncio.create_task(self._loop())
        self.machine.transition(LiveState.RUNNING, reason="startup validation passed")
        self._emit("live.state", self.machine.as_dict())

    async def stop(self, *, reason: str = "operator stop") -> None:
        if self.machine.state.is_terminal:
            return
        self.machine.transition(LiveState.STOPPING, reason=reason)
        self._stop_requested = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        with contextlib.suppress(Exception):
            await self._execution.close()
        self.machine.transition(LiveState.STOPPED, reason="loop stopped")
        self._emit("live.state", self.machine.as_dict())

    def pause(self, *, actor: str) -> None:
        self.machine.transition(LiveState.PAUSING, reason="operator pause", actor=actor)
        self.machine.transition(LiveState.PAUSED, reason="paused", actor=actor)

    def resume(self, *, actor: str) -> None:
        """PAUSED or HALT_NEW_ORDERS back to RUNNING. Requires a named operator."""
        if not actor.strip():
            raise ValueError("resuming live trading requires a named operator")
        self.machine.require(
            LiveState.PAUSED, LiveState.HALT_NEW_ORDERS, action="resume"
        )
        self.machine.transition(LiveState.RUNNING, reason="operator resume", actor=actor)

    def halt_new_orders(self, *, reason: str, actor: str = "system") -> bool:
        """Stop taking new entries. Returns whether this call is what did it.

        A halt is only reachable from RUNNING, so calling this on an already-halted
        session is a no-op — and a no-op that reports success is how an operator ends up
        clicking the same button six times wondering why nothing happens.
        """
        if self.machine.state is not LiveState.RUNNING:
            return False
        self.machine.transition(LiveState.HALT_NEW_ORDERS, reason=reason, actor=actor)
        self._incident("halt_new_orders", reason=reason, actor=actor)
        return True

    def absorb_evidence(
        self,
        *,
        outcomes: Sequence[Outcome] = (),
        reviews: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        """Fold newly-persisted trade evidence into the running session.

        Training simulations write to the same evidence store this session learns from,
        but a session that read that store only at startup keeps showing yesterday's
        lessons until someone restarts it. This is the useful half of a restart without
        the restart: the estimator's buckets and the retrospective's memory take the new
        rows, and the guardrails recompute from the enlarged record on their next read.

        Three properties make this safe to do mid-session:

        * It only ever **adds**. Nothing here erases a lesson the session already paid
          for, and a guardrail that eases does so because the enlarged record says the
          pattern behaves — not because absorbing reset anything.
        * It is synchronous and free of awaits, so it cannot interleave with a trading
          cycle. No decision is ever made against a half-absorbed record.
        * It leaves the loss streak alone. That counter is about *this* session's recent
          trades; a simulation from last night is not one of them.

        The caller passes only rows this session did not itself produce — its own closed
        trades are already in memory, and handing them back would count them twice.
        """
        outcomes = list(outcomes)
        reviews = list(reviews)
        if not outcomes and not reviews:
            return {"absorbed_outcomes": 0, "absorbed_reviews": 0, "buckets_ready": 0}
        self._edges.record_many(outcomes)
        self._retro.record_many(reviews)
        self._evidence_absorbed += len(outcomes)
        self._evidence_absorbed_at = self._clock.now()
        result = {
            "absorbed_outcomes": len(outcomes),
            "absorbed_reviews": len(reviews),
            "buckets_ready": sum(
                1
                for count in self._edges.coverage().values()
                if count >= self._edges.min_samples
            ),
            "at": self._evidence_absorbed_at.isoformat(),
        }
        _log.info("evidence_absorbed", **result)
        self._emit("live.evidence_absorbed", result)
        return result

    def tighten_ev_threshold(self, new_threshold_bps: float, *, actor: str) -> dict[str, Any]:
        """Raise the expected-value bar mid-session. Raise only — this is the one runtime
        parameter the Mentor may touch, and the direction is enforced here, not by the
        caller's good intentions. Lowering the bar means restarting the session with a new
        configuration, which re-runs every check that configuration is subject to."""
        current = self._ev.threshold_bps
        if new_threshold_bps <= current:
            raise ValueError(
                f"the EV threshold may only be raised mid-session "
                f"(current {current:.2f} bps, requested {new_threshold_bps:.2f} bps)"
            )
        self._ev.threshold_bps = new_threshold_bps
        self._incident(
            "ev_threshold_raised",
            reason=f"{current:.2f} -> {new_threshold_bps:.2f} bps",
            actor=actor,
        )
        self._emit(
            "live.ev_threshold",
            {"previous_bps": current, "current_bps": new_threshold_bps, "actor": actor},
        )
        return {"previous_bps": current, "current_bps": new_threshold_bps}

    # ------------------------------------------------------------------ kill switch

    async def kill_switch(self, *, reason: str, actor: str) -> dict[str, Any]:
        """The emergency stop. Independent of every model and every strategy.

        Stops new entries, cancels resting orders, reconciles, and lands in SAFE_MODE —
        which has no automatic exit. It does **not** close positions: that is
        :meth:`emergency_flatten`, a separate and more drastic decision, because "the
        software is in doubt" and "I want out of the market" are different emergencies.
        """
        if not actor.strip():
            raise ValueError("the kill switch requires a named actor")
        self.machine.transition(LiveState.SAFE_MODE, reason=f"kill switch: {reason}", actor=actor)
        cancelled = await self._cancel_all_open()
        await self._reconcile()
        self._incident(
            "kill_switch", reason=reason, actor=actor, detail={"cancelled_orders": cancelled}
        )
        self._emit("live.state", self.machine.as_dict())
        return {"state": self.machine.state.value, "cancelled_orders": cancelled}

    async def emergency_flatten(self, *, reason: str, actor: str) -> dict[str, Any]:
        """Close everything, in order, with verification. An operator decision only.

        The seven steps, in the order that leaves the least unknown state if any one of
        them fails: stop new orders → cancel resting → read real positions from the venue →
        submit reducing orders → verify fills → reconcile → record.
        """
        if not actor.strip():
            raise ValueError("emergency flatten requires a named actor")

        self.machine.transition(
            LiveState.SAFE_MODE, reason=f"emergency flatten: {reason}", actor=actor
        )
        cancelled = await self._cancel_all_open()
        self.machine.transition(
            LiveState.CANCEL_ONLY, reason="flatten: reducing positions", actor=actor
        )

        positions = await self._execution.get_positions()
        closed: list[dict[str, Any]] = []
        for symbol, position in positions.items():
            if position.is_flat:
                continue
            side = Side.SELL if position.quantity > 0 else Side.BUY
            quantity = abs(position.quantity)
            intent = self._build_intent(
                symbol=symbol,
                side=side,
                quantity=quantity,
                signal_id=f"flatten:{symbol}:{self.run_id}",
                reduce_only=True,
            )
            order = await self._execution.submit_order(intent)
            closed.append(
                {"symbol": symbol, "quantity": quantity, "state": order.state.value}
            )

        await self._reconcile()
        self._incident(
            "emergency_flatten",
            reason=reason,
            actor=actor,
            detail={"cancelled_orders": cancelled, "closing_orders": closed},
        )
        self._emit("live.state", self.machine.as_dict())
        return {
            "state": self.machine.state.value,
            "cancelled_orders": cancelled,
            "closing_orders": closed,
        }

    async def _cancel_all_open(self) -> int:
        self._protective = None
        self._resting = None
        cancelled = 0
        try:
            open_orders = await self._execution.get_orders(open_only=True)
        except Exception as exc:
            _log.warning("cancel_all_could_not_list", error=str(exc)[:200])
            return 0
        for order in open_orders:
            if order.state.is_terminal:
                continue
            try:
                await self._execution.cancel_order(order.client_order_id or order.order_id)
                cancelled += 1
            except Exception as exc:  # keep cancelling the rest
                _log.warning(
                    "cancel_failed", order=order.order_id, error=str(exc)[:200]
                )
        return cancelled

    # ------------------------------------------------------------------ the loop

    async def _loop(self) -> None:
        while not self._stop_requested:
            await self._loop_iteration()
            await asyncio.sleep(self._poll_interval)

    async def _loop_body_once_for_tests(self) -> None:
        """One loop iteration, no sleep. For tests that drive the loop by hand."""
        await self._loop_iteration()

    async def _loop_iteration(self) -> None:
        """The loop body: one cycle plus the full failure taxonomy around it."""
        if True:
            try:
                await self._cycle_once()
            except asyncio.CancelledError:
                raise
            except ReconciliationError as exc:
                # An order's fate is unknown. Halt entries and resolve before anything
                # else is submitted — this is the anti-duplicate path.
                self.counters["unknown_order_states"] += 1
                self.last_error = str(exc)[:500]
                self.halt_new_orders(reason=f"unknown order state: {exc}")
                await self._reconcile()
            except ProviderUnavailableError as exc:
                # A network blip is expected weather, not an emergency: halt entries,
                # keep polling, escalate only if it persists.
                self._provider_failures += 1
                self.last_error = str(exc)[:500]
                if self._provider_failures >= 10:
                    self.machine.transition(
                        LiveState.SAFE_MODE,
                        reason=f"provider unreachable {self._provider_failures} times",
                    )
                    self._incident(
                        "safe_mode",
                        reason=f"persistent provider failure: {exc}"[:500],
                    )
                else:
                    self._watchdog_halt = True
                    self.halt_new_orders(
                        reason=f"provider unreachable (attempt {self._provider_failures}): "
                        f"{str(exc)[:200]}"
                    )
            except TiaError as exc:
                self.last_error = str(exc)[:500]
                self.machine.transition(
                    LiveState.SAFE_MODE, reason=f"runtime error: {exc}"
                )
                self._incident("safe_mode", reason=str(exc)[:500])
            except Exception as exc:  # unknown failure: never trade through it
                self.last_error = str(exc)[:500]
                self.machine.transition(
                    LiveState.SAFE_MODE, reason=f"unexpected error: {exc}"
                )
                self._incident("safe_mode", reason=str(exc)[:500])

    async def _cycle_once(self) -> None:
        self._cycle += 1
        self.counters["cycles"] += 1
        self.last_heartbeat = self._clock.now()

        # Market-data watchdog: a feed that stopped producing bars is not a quiet market,
        # it is an unknown one. Entries halt until bars flow again and a reconciliation
        # comes back clean.
        bar_age = (self._clock.now() - self._last_bar_wall).total_seconds()
        if bar_age > self.market_data_ttl_seconds and self.machine.state is LiveState.RUNNING:
            self._watchdog_halt = True
            self.halt_new_orders(
                reason=f"market data stale: no new bar for {bar_age:.0f}s "
                f"(TTL {self.market_data_ttl_seconds:.0f}s)"
            )

        if self._cycle % self._skew_every == 0 and self.skew is not None:
            skew, ok = await self.skew.check()
            if not ok:
                self.counters["skew_halts"] += 1
                self.halt_new_orders(
                    reason=f"clock skew {skew:.0f} ms beyond ±{MAX_CLOCK_SKEW_MS} ms"
                )

        if self._cycle % self._reconcile_every == 0:
            await self._reconcile()

        if self.machine.state in {LiveState.PAUSED, LiveState.SAFE_MODE}:
            return

        candles = await self._market_data.get_candles(
            self._symbol, self._timeframe, limit=200
        )
        if not candles:
            return
        latest = candles[-1]
        if self._last_close is not None and latest.close_time <= self._last_close:
            return  # no new closed bar yet
        self._last_close = latest.close_time
        self._last_bar_wall = self._clock.now()
        self._provider_failures = 0
        self._buffer.clear()
        self._buffer.extend(candles)
        self.counters["bars"] += 1

        # Paper-realtime: the simulated matching engine fills resting orders against the
        # bar the way the live venue would have filled them against the tape.
        on_bar = getattr(self._execution, "on_bar", None)
        if callable(on_bar):
            for fill in on_bar(latest):
                self._on_fill(fill)

        if self._resting is not None:
            await self._manage_resting()
        await self._manage_position(latest)

        # Watchdog self-heal: data is flowing again. RUNNING is earned back through a
        # clean reconciliation, not assumed — and only for halts the watchdog itself
        # caused; an operator's halt stays until the operator lifts it.
        if self._watchdog_halt and self.machine.state is LiveState.HALT_NEW_ORDERS:
            await self._reconcile()
            if not self.counters_last_reconciliation_broke():
                self._watchdog_halt = False
                self.machine.transition(
                    LiveState.RUNNING,
                    reason="watchdog: data restored and reconciliation clean",
                    actor="watchdog",
                )

        await self._process_bar(latest)

    async def _process_bar(self, candle: Candle) -> None:
        correlation_id = f"{self.run_id}:{self._symbol}:{self.counters['bars']}"
        self.latency.stamp(correlation_id, "market_received")

        window = list(self._buffer)
        if len(window) < self._features.min_bars:
            return

        report = self._quality.evaluate(
            symbol=self._symbol,
            timeframe=self._timeframe,
            candles=window,
            now=self._clock.now(),
            last_feed_message_at=candle.close_time,
        )
        if report.hard_fail:
            self.counters["quality_skipped"] += 1
            return

        self.latency.stamp(correlation_id, "decision_started")
        features = self._features.build(self._symbol, self._timeframe, window)
        regime = self._regimes.classify(features, now=candle.close_time)
        signal, _ = self._strategies.evaluate(
            features=features,
            regime=regime,
            quality=report,
            context=None,
            correlation_id=correlation_id,
        )
        self.counters["signals"] += 1
        self.latency.stamp(correlation_id, "decision_finished")

        if not signal.direction.is_actionable:
            return

        if self._resting is not None:
            # An order is already working. A second one on the next bar would not be a
            # second opinion, it would be a second position.
            self.counters["resting_skipped"] += 1
            return

        self.latency.stamp(correlation_id, "risk_started")
        portfolio = await self._execution.get_portfolio()
        # `now` is wall-clock here, not bar time: the signal was created moments ago on
        # this machine's clock, and its TTL must be measured on the same clock. Bar time
        # lags wall time by up to one bar plus feed latency, which is exactly the window
        # a TTL exists to bound.
        decision = self._risk.evaluate(
            signal=signal,
            portfolio=portfolio,
            features=features,
            quality=report,
            now=self._clock.now(),
        )
        self.latency.stamp(correlation_id, "risk_finished")
        if not decision.allows_execution:
            self.counters["risk_rejected"] += 1
            return

        position = portfolio.positions.get(self._symbol)
        if position is not None and not position.is_flat:
            # A position already open plus an approved signal the OTHER way is the system
            # changing its mind, and the honest response is to close — through no edge
            # gate, because an exit is not a discretionary trade and must never be
            # blocked by an edge calculation. The same way means it still believes it,
            # and nothing happens: pyramiding would exceed the size risk approved.
            opposing = (position.quantity > 0) != (signal.direction is Direction.LONG)
            if opposing and self.machine.state.accepts_reducing_orders:
                await self._close_position("signal reversed")
            else:
                self.counters["suppressed_position_open"] += 1
            return

        if not self.machine.state.accepts_new_orders:
            return

        snapshot = self._ledger.snapshot(used_capital=portfolio.gross_exposure)
        equity = snapshot.equity
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = (
            0.0
            if self._peak_equity <= 0
            else max(0.0, (self._peak_equity - equity) / self._peak_equity * 100.0)
        )
        budget = self._budget.compute(
            BudgetInputs(
                equity=equity,
                peak_equity=self._peak_equity,
                drawdown_pct=drawdown,
                realised_annual_volatility=max(
                    0.0, features.finite_values().get("realized_vol_20", 0.0)
                ),
                consecutive_losses=self._consecutive_losses,
                trades_today=self._trades_today,
                open_gross_exposure_pct=(
                    portfolio.gross_exposure / equity * 100.0 if equity > 0 else 0.0
                ),
            )
        )
        if not budget.allows_new_trades:
            self.counters["budget_rejected"] += 1
            return

        if self._ledger.loss_breached(unrealised_pnl=portfolio.unrealized_pnl):
            self.halt_new_orders(reason="total loss limit breached")
            return
        if self._ledger.is_halted:
            self.halt_new_orders(reason=self._ledger.halted_reason)
            return

        # Expected value — enforced. This class has no observe mode.
        measured_latency = self.latency.ema_total_ms or float(
            self._settings.execution.submit_latency_ms
            + self._settings.execution.ack_latency_ms
        )
        values = features.finite_values()
        conditions = MarketConditions(
            price=max(candle.close, 1e-9),
            spread_bps=self._settings.execution.base_slippage_bps,
            volatility_per_bar=max(0.0, values.get("atr_pct", 0.0) / 100.0),
            top_of_book_quantity=0.0,  # no depth feed yet — priced as ignorance, not zero
            bar_volume=candle.volume,
            latency_ms=measured_latency,
            bar_seconds=60.0,
        )
        evaluation = self._ev.evaluate(
            regime=regime.regime,
            direction=signal.direction,
            confidence=signal.confidence,
            # Priced the way it will be executed: a resting maker entry pays the maker
            # fee and crosses no spread. The exit is priced as a taker regardless — an
            # expired exit is re-sent as market, so the worst case is the honest case.
            costs=self._costs.estimate(
                quantity=decision.approved_quantity,
                conditions=conditions,
                entry_maker=self.entry_is_limit,
            ),
        )
        # The learning guardrail: a bucket that has recently lost money or overstated its
        # edge must clear a *raised* threshold before this session re-enters it. This can
        # only ever refuse a trade the EV engine would have taken — it never authorises one.
        guard = self._retro.guardrail_for(
            regime=regime.regime,
            direction=signal.direction,
            confidence=signal.confidence,
        )

        exploring = False
        if not evaluation.is_tradeable:
            # Paper-only exploration: a bucket the estimator knows NOTHING about may be
            # traded a bounded number of times per day, purely to buy evidence with
            # simulated money. Three refusals stand regardless: evidence that says the
            # bucket loses (edge_estimate present) is respected, an active guardrail is
            # respected, and a live execution provider disables exploration entirely —
            # with real money, "I don't know yet" is a reason not to trade.
            if (
                self.exploration_enabled
                and evaluation.edge_estimate is None
                and not guard.is_active
                and self._exploration_budget_left()
            ):
                exploring = True
            else:
                self.counters["ev_rejected"] += 1
                self._emit(
                    "live.no_trade",
                    {"correlation_id": correlation_id, "reason": evaluation.explain()},
                )
                return

        if not exploring and guard.is_active and evaluation.net_edge_bps < (
            evaluation.threshold_bps + guard.threshold_add_bps
        ):
            self.counters["guardrail_rejected"] += 1
            raised_bar = evaluation.threshold_bps + guard.threshold_add_bps
            notional = evaluation.costs.notional
            if notional > 0:
                reason = (
                    f"learning guardrail — expected net profit "
                    f"${evaluation.net_edge_bps * notional / 10_000:,.2f} is below the "
                    f"raised bar of ${raised_bar * notional / 10_000:,.2f} on a "
                    f"${notional:,.0f} position. {guard.reason}"
                )
            else:
                reason = (
                    f"learning guardrail — net edge {evaluation.net_edge_bps:.1f} bps "
                    f"below the raised bar of {raised_bar:.1f} bps. {guard.reason}"
                )
            self._emit(
                "live.no_trade",
                {"correlation_id": correlation_id, "reason": reason},
            )
            return

        if exploring:
            self._exploration_used += 1
            self.counters["exploration_trades"] += 1
            self._emit(
                "live.exploration",
                {
                    "correlation_id": correlation_id,
                    "reason": (
                        "exploration trade — no evidence exists for "
                        f"{regime.regime.value}/{signal.direction.value} at this "
                        f"confidence yet; buying a lesson with simulated money "
                        f"({self._exploration_used} of "
                        f"{self._settings.live.exploration_trades_per_day} today)"
                    ),
                },
            )

        self._planned_exit = {
            "stop": decision.stop_price,
            "target": decision.target_price,
            "direction": signal.direction,
        }
        await self._submit(decision, signal, correlation_id)
        self._entry_beliefs = {
            "regime": regime.regime,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "signal_id": signal.signal_id,
            "expected_net_bps": evaluation.net_edge_bps,
            # An exploration entry carries no claim about its own outcome: it was taken
            # *because* the bucket has no evidence. Recording it as an expectation the
            # system then missed would have the session punish itself for deliberately
            # buying a lesson — see RetrospectiveEngine.review.
            "exploratory": exploring,
        }

    # ------------------------------------------------------------------ orders

    def _limit_price_for(self, side: Side, reference: float) -> float:
        """Where a post-only entry rests: at the touch, on our side of the spread.

        A buy rests half a spread below the reference and a sell half a spread above —
        the price a maker actually gets, not the mid. Quantized to the venue's tick where
        one is known: down for a buy and up for a sell, so rounding can only make the
        order more passive, never cross the book by accident.
        """
        half_spread = self._settings.execution.base_slippage_bps / 10_000.0 / 2.0
        raw = reference * (1.0 - half_spread) if side is Side.BUY else reference * (
            1.0 + half_spread
        )
        tick = self._filters.get("tick_size")
        if not tick:
            return raw
        floored = float(quantize_down(raw, tick))
        if side is Side.BUY or floored == raw:
            return floored
        return floored + float(tick)

    def _build_intent(
        self,
        *,
        symbol: str,
        side: Side,
        quantity: float,
        signal_id: str,
        reduce_only: bool = False,
        order_type: OrderType | None = None,
        reference_price: float | None = None,
    ) -> OrderIntent:
        """A venue-legal intent: quantity quantized DOWN to the lot step, in Decimal.

        Rounding down can only under-fill; rounding to nearest can exceed the sized risk.
        Refusing below the venue's minimum notional happens here too, because an order
        that will be rejected for size is better refused before it spends latency.
        """
        step = self._filters.get("step_size")
        if step:
            quantity = float(quantize_down(quantity, step))
        if quantity <= 0:
            raise ValueError("quantity quantized to zero — below the venue's lot step")

        min_notional = self._filters.get("min_notional")
        price_hint = self._filters.get("last_price", 0.0)
        if min_notional and price_hint and not meets_min_notional(
            quantity, price_hint, min_notional
        ):
            raise ValueError(
                f"order notional {float(D(quantity) * D(price_hint))} is below the "
                f"venue minimum {min_notional}"
            )

        if order_type is None:
            order_type = OrderType.LIMIT if self.entry_is_limit else OrderType.MARKET
        limit_price: float | None = None
        if order_type is OrderType.LIMIT:
            reference = reference_price or price_hint
            if not reference or reference <= 0:
                order_type = OrderType.MARKET  # no price to rest at: cross honestly
            else:
                limit_price = self._limit_price_for(side, float(reference))

        return OrderIntent(
            intent_id=deterministic_id("int", "live", signal_id, self._clock.now()),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=signal_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
            ),
            signal_id=signal_id,
            risk_decision_id=signal_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            time_in_force=TimeInForce.GTC,
            created_at=self._clock.now(),
            reduce_only=reduce_only,
        )

    async def _submit(self, decision: Any, signal: Any, correlation_id: str) -> None:
        # Re-validated immediately before every submission: the token may have expired
        # or the configuration fingerprint may no longer match. Both void the order.
        # In paper-realtime there is no token and nothing real to void.
        if self._execution.is_live:
            if self._activation is None:  # unreachable: the constructor refuses this
                raise LiveActivationError("live execution without an activation token")
            self._activation.assert_usable(
                now=self._clock.now(), fingerprint=self._fingerprint
            )
        self._execution.assert_may_trade()

        side = signal.direction.to_side()
        reducing = self._open_trade is not None and side is not self._open_trade["side"]
        intent = self._build_intent(
            symbol=decision.symbol,
            side=side,
            quantity=decision.approved_quantity,
            signal_id=decision.signal_id,
            reference_price=self._buffer[-1].close if self._buffer else None,
        )

        self.latency.stamp(correlation_id, "order_submit")
        try:
            order = await self._execution.submit_order(intent)
        except ReconciliationError:
            # Timeout: the order's fate is unknown. Resolve against the venue by our own
            # client_order_id BEFORE anything may submit again. Never retry blind.
            self.counters["unknown_order_states"] += 1
            resolved = await self._resolve_unknown(intent)
            if resolved is None:
                # The venue confirms it never arrived. The moment has passed; the trade
                # is skipped rather than replayed into a market that has moved on.
                self.halt_new_orders(reason="submission timed out; venue confirms absent")
                return
            order = resolved
        self.latency.stamp(correlation_id, "order_ack")

        self.counters["orders"] += 1
        self._trades_today += 1
        fills = list(order.fills)
        if fills:
            self.latency.stamp(correlation_id, "fill_received")
            for fill in fills:
                self._on_fill(fill)
        if not order.state.is_terminal and order.order_type is OrderType.LIMIT:
            self._resting = {
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "side": side,
                "symbol": decision.symbol,
                "quantity": decision.approved_quantity,
                "signal_id": decision.signal_id,
                "placed_bar": self.counters["bars"],
                "reducing": reducing,
                "limit_price": order.limit_price,
            }
            self._emit(
                "live.order_resting",
                {
                    "correlation_id": correlation_id,
                    "side": side.value,
                    "limit_price": order.limit_price,
                    "timeout_bars": self._settings.live.entry_limit_timeout_bars,
                },
            )
        sample = self.latency.finish(correlation_id, symbol=decision.symbol)
        if sample is not None:
            self._save(
                "latency",
                {
                    "sample_id": deterministic_id("lat", self.run_id, correlation_id),
                    "run_id": self.run_id,
                    "at": self._clock.now(),
                    "symbol": decision.symbol,
                    "correlation_id": correlation_id,
                    "segments_ms": sample["segments_ms"],
                    "total_ms": sample["total_ms"] or 0.0,
                },
            )
        self._save("order", {"run_id": self.run_id, "order": order})

    async def _manage_resting(self) -> None:
        """Advance the one resting order: route its fills, or expire it.

        Fills are read from the venue's view of the order (the paper engine also hands
        them over on the bar, which is why routing de-duplicates by fill id). An order
        still open after the configured number of bars is cancelled — the moment the
        signal priced has passed. If it was an *exit*, a market order follows at once:
        a missed entry costs nothing, a missed exit is an open position nobody chose.
        """
        resting = self._resting
        if resting is None:
            return
        order: Order | None = None
        for key in (resting["order_id"], resting["client_order_id"]):
            with contextlib.suppress(Exception):
                order = await self._execution.get_order(key)
            if order is not None:
                break
        if order is None:
            # Unknown to the venue: nothing to cancel, nothing to wait for.
            self._resting = None
            return

        for fill in order.fills:
            self._on_fill(fill)
        if order.state.is_terminal:
            self._resting = None
            return

        waited = self.counters["bars"] - int(resting["placed_bar"])
        if waited < self._settings.live.entry_limit_timeout_bars:
            return

        with contextlib.suppress(Exception):
            await self._execution.cancel_order(order.client_order_id or order.order_id)
        self.counters["orders_expired"] += 1
        self._resting = None
        self._emit(
            "live.order_expired",
            {
                "side": resting["side"].value,
                "limit_price": resting.get("limit_price"),
                "waited_bars": waited,
                "reducing": bool(resting["reducing"]),
            },
        )
        if resting["reducing"]:
            intent = self._build_intent(
                symbol=resting["symbol"],
                side=resting["side"],
                quantity=float(resting["quantity"]),
                signal_id=f"{resting['signal_id']}:exit-market",
                reduce_only=True,
                order_type=OrderType.MARKET,
            )
            with contextlib.suppress(Exception):
                market = await self._execution.submit_order(intent)
                self.counters["orders"] += 1
                for fill in market.fills:
                    self._on_fill(fill)
                self._save("order", {"run_id": self.run_id, "order": market})
        elif self._open_trade is None:
            # The entry never happened; the expectation formed for it must not be scored
            # against whatever trade comes next.
            self._entry_beliefs = None

    async def _manage_position(self, candle: Candle) -> None:
        """Every bar, for the open position: target, time stop, and exactly one stop.

        The paper engine that produces the evidence protects every position with a stop
        and closes on a reversal. A session that learned from those trades and then ran
        without stops would be applying evidence from one game to a different one —
        every loss unbounded where the estimator had seen them capped. So this mirrors
        that discipline, in the same order the engine applies it.
        """
        await self._poll_protective()
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            return
        position = portfolio.positions.get(self._symbol)
        holding = position is not None and not position.is_flat

        if not holding:
            if self._protective is not None:
                await self._cancel_protective()
            return
        if not self.machine.state.accepts_reducing_orders:
            return

        long = position.quantity > 0
        target = self._planned_exit.get("target")
        if target and target > 0:
            reached = candle.high >= target if long else candle.low <= target
            if reached:
                await self._close_position("target reached")
                return

        max_bars = self._settings.live.max_holding_bars
        if (
            max_bars > 0
            and self._position_opened_bar is not None
            and self.counters["bars"] - self._position_opened_bar >= max_bars
        ):
            await self._close_position("time stop")
            return

        await self._sync_protective_stop(position.quantity)

    async def _sync_protective_stop(self, position_quantity: float) -> None:
        """Keep exactly one protective stop matching the open position.

        Replaced when a partial fill changed the quantity it covers; its fills are read
        from the venue's view of the order so a triggered stop closes the round trip
        even on a venue that does not push fills. A position whose entry carried no
        stop is counted as unprotected and said so — never silently.
        """
        stop_price = self._planned_exit.get("stop")
        if not stop_price or stop_price <= 0:
            if self._protective is None:
                self.counters["unprotected_positions"] += 1
                _log.warning("position_unprotected", symbol=self._symbol)
                self._protective = {"order_id": "", "client_order_id": "", "quantity": 0.0,
                                    "stop_price": None, "unprotected": True}
            return

        quantity = abs(position_quantity)
        existing = self._protective
        if existing is not None and existing.get("order_id"):
            order = await self._poll_protective()
            if order is None or self._protective is None:
                pass  # gone or filled: fall through and place a fresh one if still held
            else:
                covered = order.quantity - order.filled_quantity
                if abs(covered - quantity) <= max(quantity * 1e-6, 1e-9):
                    return
                await self._cancel_protective()

        side = Side.SELL if position_quantity > 0 else Side.BUY
        intent = OrderIntent(
            intent_id=deterministic_id("int", "stop", self._symbol, quantity, self._clock.now()),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"protective:{self._symbol}:{self.counters['bars']}",
                symbol=self._symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.STOP,
            ),
            signal_id=f"protective:{self._symbol}",
            risk_decision_id=f"protective:{self._symbol}",
            symbol=self._symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=float(stop_price),
            time_in_force=TimeInForce.GTC,
            created_at=self._clock.now(),
            reduce_only=True,
        )
        try:
            order = await self._execution.submit_order(intent)
        except Exception as exc:
            _log.warning("protective_stop_failed", error=str(exc)[:200])
            return
        if order.state.is_terminal and not order.fills:
            _log.warning(
                "protective_stop_rejected",
                reason=order.reject_reason or order.state.value,
            )
            return
        self._protective = {
            "order_id": order.order_id,
            "client_order_id": order.client_order_id,
            "quantity": quantity,
            "stop_price": float(stop_price),
        }
        self.counters["stops_placed"] += 1
        for fill in order.fills:  # a stop already through its level fills at once
            self._on_fill(fill)
        self._save("order", {"run_id": self.run_id, "order": order})
        self._emit(
            "live.stop_placed",
            {"stop_price": float(stop_price), "quantity": quantity, "side": side.value},
        )

    async def _poll_protective(self) -> Order | None:
        """Read the venue's view of the protective stop and route any fills it produced.

        Returns the order while it is still working; clears the record and returns
        ``None`` once it is terminal or unknown. Called before any decision about the
        position, because the position going flat is the *consequence* of the stop
        filling, and the fill must be scored — it is the round trip's end.
        """
        existing = self._protective
        if not existing or not existing.get("order_id"):
            return None
        order: Order | None = None
        for key in (existing["order_id"], existing["client_order_id"]):
            with contextlib.suppress(Exception):
                order = await self._execution.get_order(key)
            if order is not None:
                break
        if order is None:
            self._protective = None
            return None
        for fill in order.fills:
            self._on_fill(fill)
        if order.state.is_terminal:
            self._protective = None
            return None
        return order

    async def _cancel_protective(self) -> None:
        existing = self._protective
        self._protective = None
        if not existing or not existing.get("order_id"):
            return
        with contextlib.suppress(Exception):
            await self._execution.cancel_order(
                existing["client_order_id"] or existing["order_id"]
            )

    async def _close_position(self, reason: str) -> None:
        """Close the open position with a reduce-only market order, stop cancelled first.

        Market on purpose: a close is the one order whose fill matters more than its
        price. The reason travels with the round trip into the record.
        """
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            return
        position = portfolio.positions.get(self._symbol)
        if position is None or position.is_flat:
            return
        if self._resting is not None:
            with contextlib.suppress(Exception):
                await self._execution.cancel_order(
                    self._resting["client_order_id"] or self._resting["order_id"]
                )
            self._resting = None
        await self._cancel_protective()

        quantity = abs(position.quantity)
        side = Side.SELL if position.quantity > 0 else Side.BUY
        self._exit_reason = reason
        slug = reason.replace(" ", "-")
        intent = self._build_intent(
            symbol=self._symbol,
            side=side,
            quantity=quantity,
            signal_id=f"exit:{slug}:{self.counters['bars']}",
            reduce_only=True,
            order_type=OrderType.MARKET,
        )
        try:
            order = await self._execution.submit_order(intent)
        except Exception as exc:
            _log.warning("close_position_failed", reason=reason, error=str(exc)[:200])
            return
        self.counters["orders"] += 1
        key = {
            "target reached": "exits_target",
            "time stop": "exits_time",
            "signal reversed": "exits_reversal",
        }.get(reason)
        if key:
            self.counters[key] += 1
        for fill in order.fills:
            self._on_fill(fill)
        self._save("order", {"run_id": self.run_id, "order": order})
        self._emit(
            "live.exit",
            {"reason": reason, "side": side.value, "quantity": quantity,
             "state": order.state.value},
        )

    async def _resolve_unknown(self, intent: OrderIntent) -> Order | None:
        resolver = getattr(self._execution, "resolve_unknown_order", None)
        if resolver is None:
            raise ReconciliationError(
                "submission timed out and this provider cannot resolve unknown orders; "
                "manual reconciliation required before trading resumes",
                client_order_id=intent.client_order_id,
            )
        return await resolver(symbol=intent.symbol, client_order_id=intent.client_order_id)

    def _on_fill(self, fill: Fill) -> None:
        if fill.fill_id in self._seen_fills:
            return
        self._seen_fills.add(fill.fill_id)
        if self._protective is not None and fill.order_id == self._protective["order_id"]:
            self._exit_reason = "protective stop"
            self.counters["exits_stop"] += 1
        self.counters["fills"] += 1
        if fill.liquidity == "maker":
            self.counters["maker_fills"] += 1
        self._ledger.record_fee(fill.fee, at=fill.filled_at)
        self._save("fill", {"run_id": self.run_id, "fill": fill})
        self._track_round_trip(fill)

    def _track_round_trip(self, fill: Fill) -> None:
        if self._open_trade is None:
            self._exit_reason = None
            self._position_opened_bar = self.counters["bars"]
            self._open_trade = {
                "price": fill.price,
                "quantity": fill.quantity,
                "side": fill.side,
                "fee": fill.fee,
                "exit_value": 0.0,
                "exit_quantity": 0.0,
                "exit_fees": 0.0,
            }
            return
        trade = self._open_trade
        if fill.side is trade["side"]:
            total = trade["quantity"] + fill.quantity
            trade["price"] = (
                trade["price"] * trade["quantity"] + fill.price * fill.quantity
            ) / total
            trade["quantity"] = total
            trade["fee"] += fill.fee
            return
        trade["exit_value"] += fill.price * fill.quantity
        trade["exit_quantity"] += fill.quantity
        trade["exit_fees"] += fill.fee
        if trade["exit_quantity"] + 1e-12 >= trade["quantity"]:
            self._score_round_trip(fill)

    def _score_round_trip(self, exit_fill: Fill) -> None:
        trade = self._open_trade
        beliefs = self._entry_beliefs
        self._open_trade = None
        self._entry_beliefs = None
        self._position_opened_bar = None
        self._planned_exit = {}
        if trade is None or beliefs is None or trade["exit_quantity"] <= 0:
            return

        entry_price = trade["price"]
        exit_price = trade["exit_value"] / trade["exit_quantity"]
        long_side = trade["side"] is Side.BUY
        raw = (exit_price - entry_price) / entry_price * 10_000.0
        gross_bps = raw if long_side else -raw
        notional = trade["quantity"] * entry_price
        fees_bps = (
            (trade["fee"] + trade["exit_fees"]) / notional * 10_000.0 if notional > 0 else 0.0
        )
        net_bps = gross_bps - fees_bps

        self._edges.record(
            Outcome(
                regime=beliefs["regime"],
                direction=beliefs["direction"],
                confidence=beliefs["confidence"],
                net_return_bps=net_bps,
            )
        )
        self._retro.review(
            regime=beliefs["regime"],
            direction=beliefs["direction"],
            confidence=beliefs["confidence"],
            expected_net_bps=beliefs["expected_net_bps"],
            realised_net_bps=net_bps,
            fees_bps=fees_bps,
            closed_at=exit_fill.filled_at,
            signal_id=beliefs["signal_id"],
            symbol=self._symbol,
            notional_usd=notional,
            exploratory=bool(beliefs.get("exploratory")),
        )
        self._consecutive_losses = 0 if net_bps > 0 else self._consecutive_losses + 1
        self._ledger.record_realised_pnl(
            notional * net_bps / 10_000.0, at=exit_fill.filled_at
        )
        self._save(
            "edge_outcome",
            {
                "outcome_id": deterministic_id(
                    "edge", self.run_id, self._symbol, beliefs["signal_id"],
                    exit_fill.filled_at,
                ),
                "run_id": self.run_id,
                "signal_id": beliefs["signal_id"],
                "symbol": self._symbol,
                "regime": beliefs["regime"].value,
                "direction": beliefs["direction"].value,
                "confidence": beliefs["confidence"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": trade["quantity"],
                "gross_bps": gross_bps,
                "fees_bps": fees_bps,
                "net_bps": net_bps,
                "expected_net_bps": beliefs["expected_net_bps"],
                "exploratory": bool(beliefs.get("exploratory")),
                "exit_reason": self._exit_reason or "signal reversed",
                "closed_at": exit_fill.filled_at,
                "source": "live",
            },
        )

    # ------------------------------------------------------------------ reconciliation

    async def _reconcile(self) -> None:
        """Our books against the venue's. The venue wins every disagreement.

        Three comparisons — orders, positions, balance — and the balance one goes through
        the capital ledger's classifier, so a deposit is never booked as profit and an
        unexplained movement halts entries rather than being absorbed.
        """
        self.counters["reconciliations"] += 1
        divergences: list[str] = []
        try:
            venue_open = {
                order.client_order_id
                for order in await self._execution.get_orders(open_only=True)
            }
            local_open = {
                order.client_order_id
                for order in await self._execution.get_orders(open_only=False)
                if not order.state.is_terminal
            }
            for missing in local_open - venue_open:
                divergences.append(f"order {missing} open locally but not at the venue")
            for extra in venue_open - local_open:
                divergences.append(f"order {extra} open at the venue but unknown locally")

            balance = float(await self._execution.get_balance())
            snapshot = self._ledger.snapshot()
            expected = snapshot.allocated_capital + snapshot.realised_pnl - snapshot.fees_paid
            reconciliation = self._ledger.classify_external_change(
                venue_balance=balance,
                expected_balance=expected,
                at=self._clock.now(),
            )
            if reconciliation.kind.value != "allocation":
                divergences.append(reconciliation.explanation)
            if reconciliation.halts_trading:
                self.halt_new_orders(reason=reconciliation.explanation)
        except Exception as exc:
            divergences.append(f"reconciliation itself failed: {exc}")

        clean = not divergences
        self._last_reconciliation_clean = clean
        if not clean:
            self.counters["reconciliation_breaks"] += 1
            if any("unknown locally" in d or "not at the venue" in d for d in divergences):
                self.machine.transition(
                    LiveState.SAFE_MODE,
                    reason="order-state divergence against the venue",
                )
                self._incident(
                    "safe_mode", reason="reconciliation divergence",
                    detail={"divergences": divergences},
                )
        self._save(
            "reconciliation",
            {
                "reconciliation_id": deterministic_id(
                    "recon", self.run_id, self.counters["reconciliations"]
                ),
                "run_id": self.run_id,
                "at": self._clock.now(),
                "source": "live",
                "clean": clean,
                "divergences": divergences,
                "detail": "",
            },
        )

    # ------------------------------------------------------------------ plumbing

    def _incident(
        self, kind: str, *, reason: str, actor: str = "system", detail: dict[str, Any] | None = None
    ) -> None:
        self._save(
            "incident",
            {
                "incident_id": deterministic_id("inc", self.run_id, kind, self._clock.now()),
                "at": self._clock.now(),
                "kind": kind,
                "actor": actor,
                "reason": reason,
                "run_id": self.run_id,
                "detail": detail or {},
            },
        )

    def _save(self, kind: str, payload: dict[str, Any]) -> None:
        if self._persist is None:
            return
        try:
            result = self._persist(kind, payload)
            if asyncio.iscoroutine(result):
                task = asyncio.ensure_future(result)
                task.add_done_callback(_swallow)
        except Exception as exc:  # persistence must never stop the loop
            _log.warning("live_persist_failed", kind=kind, error=str(exc)[:200])

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            self._on_event({"type": event_type, "payload": payload})

    def counters_last_reconciliation_broke(self) -> bool:
        """Whether the most recent reconciliation recorded a divergence."""
        return self._last_reconciliation_clean is False

    @property
    def risk_is_halted(self) -> bool:
        """True when this session's risk path is in a stop state (safe mode / halted)."""
        return (
            self.machine.state in {LiveState.SAFE_MODE, LiveState.ERROR}
            or self._risk.state.is_halted
        )

    @property
    def risk_has_evaluated(self) -> bool:
        """True once the risk engine has actually judged at least one signal."""
        return bool(self.counters["signals"] or self.counters["risk_rejected"])

    def real_candles(self, limit: int = 200) -> list[Candle]:
        """The real venue candles this session is trading on. Empty until the first bar.

        The dashboard's Markets/Chart views read this when a paper-live session is
        running, so what the operator sees is the same real data the engine decides on —
        not the synthetic demo runtime that also happens to exist.
        """
        return list(self._buffer)[-limit:]

    def market_state(self) -> dict[str, Any] | None:
        """One market row for the symbol this session trades, from real venue data."""
        if not self._buffer:
            return None
        latest = self._buffer[-1]
        prior = self._buffer[-2].close if len(self._buffer) > 1 else latest.open
        regime = self._regimes.current_regime(self._symbol).value
        return {
            "symbol": self._symbol,
            "price": latest.close,
            "open": latest.open,
            "high": latest.high,
            "low": latest.low,
            "volume": latest.volume,
            "change_pct": ((latest.close - prior) / prior * 100.0) if prior else 0.0,
            "at": latest.close_time.isoformat(),
            "regime": regime,
        }

    def learning_report(self) -> dict[str, Any]:
        """What this session has learned from its own closed trades, for the Learning view.

        Unlike the demo, this session *acts* on the lessons: ``applies_guardrails`` is true,
        and ``guardrail_rejected`` counts the trades the raised threshold has refused.
        """
        report = self._retro.report()
        report["applies_guardrails"] = True
        report["source"] = "live" if self._execution.is_live else "paper-live"
        report["guardrail_rejected"] = self.counters.get("guardrail_rejected", 0)
        report["evidence"] = self.evidence_state()
        report["selectivity"] = self.selectivity_report()
        return report

    def selectivity_report(self) -> dict[str, Any]:
        """The honest answer to "did it learn?" — replay the record under today's rules.

        The training win rate cannot rise with more training, because the trainer trades
        *everything* on purpose (expected-value observe mode) — its trades are the
        textbook's exercises, and most exercises are deliberately bad. What learning
        changes is which trades the system now REFUSES. So the measure of learning is a
        split: of every recorded trade, which would today's estimator, threshold and
        guardrails accept — and how did the accepted ones do against the refused ones?

        Approximate in one stated way: the acceptance bar here charges round-trip taker
        fees but not spread or slippage, so it accepts slightly more than the engine
        would. The bias is against us — the true accepted set is a subset of this one —
        which makes the reported improvement a floor, not a boast.
        """
        cost_floor_bps = self._costs.fees.round_trip_bps(
            entry_maker=self.entry_is_limit, exit_maker=False
        )
        threshold = self._ev.threshold_bps
        taken = {"trades": 0, "wins": 0, "net_bps_sum": 0.0}
        refused = {"trades": 0, "wins": 0, "net_bps_sum": 0.0}

        for (regime_s, direction_s, band), samples in self._edges.buckets().items():
            if not samples:
                continue
            regime = MarketRegime(regime_s)
            direction = Direction(direction_s)
            confidence = band[0] + 0.001
            estimate = self._edges.estimate(
                regime=regime, direction=direction, confidence=confidence
            )
            guard = self._retro.guardrail_for(
                regime=regime, direction=direction, confidence=confidence
            )
            bar = threshold + (guard.threshold_add_bps if guard.is_active else 0.0)
            accepted = (
                estimate is not None and estimate.adjusted_bps - cost_floor_bps >= bar
            )
            side = taken if accepted else refused
            side["trades"] += len(samples)
            side["wins"] += sum(1 for value in samples if value > 0)
            side["net_bps_sum"] += sum(samples)

        def shaped(side: dict[str, Any]) -> dict[str, Any]:
            trades = int(side["trades"])
            return {
                "trades": trades,
                "wins": int(side["wins"]),
                "win_rate": round(side["wins"] / trades, 4) if trades else 0.0,
                "mean_net_bps": (
                    round(side["net_bps_sum"] / trades, 2) if trades else 0.0
                ),
            }

        total = taken["trades"] + refused["trades"]
        return {
            "reviewed": total,
            "taken": shaped(taken),
            "refused": shaped(refused),
            "threshold_bps": threshold,
            "cost_floor_bps": cost_floor_bps,
            "explanation": (
                "Every recorded trade, replayed against today's evidence, threshold and "
                "guardrails. The trainer takes everything on purpose — that is how "
                "lessons are made — so the overall win rate measures the exercises, not "
                "the student. The split is the student: what today's rules keep versus "
                "what they refuse. Costs are floored at round-trip taker fees, so the "
                "true accepted set is, if anything, smaller and choosier than shown."
            ),
        }

    def evidence_state(self) -> dict[str, Any]:
        """How current this session's evidence is — what the Learning page's freshness
        line reads, so "is this stale?" has an answer instead of a guess."""
        return {
            "absorbed_since_start": self._evidence_absorbed,
            "last_absorbed_at": (
                self._evidence_absorbed_at.isoformat()
                if self._evidence_absorbed_at
                else None
            ),
            "buckets_ready": sum(
                1
                for count in self._edges.coverage().values()
                if count >= self._edges.min_samples
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        ledger = self._ledger.snapshot()
        return {
            "run_id": self.run_id,
            "mode": "live" if self._execution.is_live else "paper-live",
            "simulated": not self._execution.is_live,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "heartbeat_age_seconds": round(
                (self._clock.now() - self.last_heartbeat).total_seconds(), 1
            ),
            "market_data_age_seconds": round(
                (self._clock.now() - self._last_bar_wall).total_seconds(), 1
            ),
            "state": self.machine.state.value,
            "state_machine": self.machine.as_dict(),
            "symbol": self._symbol,
            "activation": self._activation.as_dict() if self._activation else None,
            "capital": ledger.as_dict(),
            "capital_halted": self._ledger.is_halted,
            "clock_skew": self.skew.as_dict() if self.skew else None,
            "latency": self.latency.as_dict(),
            "counters": dict(self.counters),
            # Spot balances carry no cost basis; ours comes from the fill journal, and a
            # fresh process that has not replayed it yet must say UNKNOWN, not 0.
            "position_cost_basis": "from fill journal; UNKNOWN until fills are replayed",
            "expected_value": {
                "enforcing": True,
                "threshold_bps": self._ev.threshold_bps,
                "coverage": self._edges.coverage(),
            },
            "evidence": self.evidence_state(),
            "position": {
                "open": self._open_trade is not None,
                "stop_price": self._planned_exit.get("stop"),
                "target_price": self._planned_exit.get("target"),
                "protected": bool(self._protective and self._protective.get("order_id")),
                "opened_bar": self._position_opened_bar,
                "max_holding_bars": self._settings.live.max_holding_bars,
            },
            "execution": {
                "entry_order_type": self._settings.live.entry_order_type,
                "limit_timeout_bars": self._settings.live.entry_limit_timeout_bars,
                "resting_order": (
                    {
                        "side": self._resting["side"].value,
                        "limit_price": self._resting.get("limit_price"),
                        "placed_bar": self._resting["placed_bar"],
                        "reducing": bool(self._resting["reducing"]),
                    }
                    if self._resting is not None
                    else None
                ),
            },
            "last_error": self.last_error,
        }


def _swallow(task: asyncio.Task[Any]) -> None:
    if not task.cancelled() and task.exception() is not None:
        _log.warning("live_persist_task_failed", error=str(task.exception())[:200])


__all__ = ["MAX_CLOCK_SKEW_MS", "ClockSkewMonitor", "LatencyTracker", "LiveRuntime"]
