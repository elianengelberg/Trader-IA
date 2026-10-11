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
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tia.core.clock import Clock, ensure_utc
from tia.core.config import Settings
from tia.core.errors import (
    LiveActivationError,
    ProviderUnavailableError,
    ReconciliationError,
    TiaError,
)
from tia.core.ids import deterministic_id, new_ulid
from tia.core.logging import get_logger
from tia.core.money import quantize_price_passive
from tia.data.providers.base import MarketDataProvider
from tia.data.quality import DataQualityEngine
from tia.domain.enums import Direction, MarketRegime, OrderState, OrderType, Side, TimeInForce
from tia.domain.instruments import DEFAULT_UNIVERSE, Timeframe
from tia.domain.market import Candle
from tia.domain.orders import Fill, Order, OrderIntent
from tia.economics.conviction import conviction_fraction
from tia.economics.costs import FUNDING_PERIOD_SECONDS, CostModel, FeeSchedule, MarketConditions
from tia.economics.expected_value import EdgeEstimator, ExpectedValueEngine, Outcome
from tia.events.envelope import EventEnvelope
from tia.execution.exits import r_multiple, tighten_stop
from tia.execution.filters import OrderFilterError, filters_for, validate_quantity
from tia.execution.provider import ExecutionProvider
from tia.learning.retrospective import RetrospectiveEngine
from tia.learning.scoreboard import StrategyScoreboard, credited_strategy_version
from tia.live.gate import LiveActivationToken, configuration_fingerprint
from tia.portfolio.account_journal import (
    EVENT_ADJUSTMENT,
    EVENT_FILL,
    EVENT_MARK,
    EVENT_PLAN,
    AccountAdjustmentPayload,
    AccountFillPayload,
    AccountMarkPayload,
    AccountPlanPayload,
    AccountRestore,
)
from tia.portfolio.capital import CapitalLedger, CapitalPolicy
from tia.quant.features import FeatureBuilder
from tia.quant.trend_context import TrendContext, trend_context
from tia.regime.classifier import RegimeClassifier
from tia.risk.budget import BudgetInputs, RiskBudgetEngine, RiskProfileName
from tia.risk.engine import RiskEngine
from tia.risk.restore import RiskRestore
from tia.risk.sizing import apply_risk_budget
from tia.runtime.states import LiveState, LiveStateMachine
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import build_strategies

_log = get_logger("runtime.live")

#: Above this measured skew against the venue, new orders halt. Half of the signing
#: recvWindow, so the halt fires before the venue starts rejecting.
MAX_CLOCK_SKEW_MS = 2_500
#: How far ahead of our clock a quote may be stamped and still be a quote: the skew two
#: clocks are allowed before orders halt. A book dated further into the future than that
#: was stamped by a clock that is wrong, and is not a book this session can price off
#: (Phase 1.6). Latency only ever makes a quote older, never newer.
QUOTE_FUTURE_TOLERANCE_SECONDS = MAX_CLOCK_SKEW_MS / 1000.0
#: The perpetual settles funding three times a day, at 00:00, 08:00 and 16:00 UTC. A
#: *period* is the eight hours a settlement opens, named by its UTC date and index (0, 1,
#: 2); the session accounts for the settlement that opens a period when it sees the clock
#: enter it, in every state (Phase 1.7).
FUNDING_PERIOD_HOURS = 8
#: A settlement seen within this many seconds of the session's previous check was watched
#: as it happened: the position as held and the monitor's current reading are that
#: settlement's own data. Seen later — after a restart or a stalled loop — it is settled
#: from the venue's realised rate for it and the mark at that time, or recorded as
#: unreconciled. Today's numbers are never used for yesterday's settlement.
FUNDING_PROMPT_GRACE_SECONDS = 300.0
#: How many pending periods a session looks up in history after a gap (two days of
#: settlements); anything older is recorded as unreconciled without a lookup.
FUNDING_RECONSTRUCT_MAX_PERIODS = 6
#: How many unreconciled periods the funding record lists; the count is always exact.
FUNDING_UNRECONCILED_LISTED = 32


def funding_period_of(at: datetime) -> tuple[str, int]:
    """The eight-hour funding period ``at`` falls in: ``(UTC date, index 0..2)``."""
    at = ensure_utc(at)
    return at.date().isoformat(), at.hour // FUNDING_PERIOD_HOURS


def funding_period_index(period: tuple[str, int]) -> int:
    """Periods as consecutive integers, so a gap is a range."""
    return date.fromisoformat(period[0]).toordinal() * 3 + int(period[1])


def funding_period_from_index(index: int) -> tuple[str, int]:
    return date.fromordinal(index // 3).isoformat(), index % 3


def funding_period_start(period: tuple[str, int]) -> datetime:
    """When the settlement that opens ``period`` happens."""
    day = date.fromisoformat(period[0])
    return datetime(day.year, day.month, day.day, int(period[1]) * FUNDING_PERIOD_HOURS, tzinfo=UTC)


def funding_period_key(period: tuple[str, int]) -> str:
    """``YYYY-MM-DD:k`` — the journal's and the plan's name for a period."""
    return f"{period[0]}:{int(period[1])}"


def parse_funding_period(text: Any) -> tuple[str, int] | None:
    """The inverse of :func:`funding_period_key`; ``None`` for anything malformed."""
    if not text:
        return None
    day, _, index = str(text).rpartition(":")
    try:
        period = (date.fromisoformat(day).isoformat(), int(index))
    except (TypeError, ValueError):
        return None
    return period if 0 <= period[1] <= 2 else None
#: How many consecutive polls the venue may answer "unknown order" for a tracked order
#: before the runtime gives it up as lost (Phase 1.3, G3). One answer can be a venue
#: still indexing a just-accepted order; three are an order that is not there.
UNKNOWN_POLLS_BEFORE_LOST = 3


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
        prior_realised_pnl: float = 0.0,
        funding_rate: Callable[[], float | None] | None = None,
        funding_status: Callable[[], dict[str, Any]] | None = None,
        funding_rate_at: Callable[[datetime], float | None] | None = None,
        symbol_filters: dict[str, Any] | None = None,
        poll_interval_seconds: float = 5.0,
        reconcile_every_cycles: int = 12,
        skew_check_every_cycles: int = 60,
        prior_risk_state: RiskRestore | None = None,
        session_deadline: datetime | None = None,
        session_max_hours: float | None = None,
        prior_account_state: AccountRestore | None = None,
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
        # Leverage is a property of the simulated perpetual account and nothing else: a
        # real spot venue does not borrow, so over live execution the multiple is 1 and
        # the configured limits stand exactly as written. In paper the three exposure
        # limits scale with the multiple; the risk per trade does not — leverage lets a
        # tight stop carry a bigger position, it never lets a trade lose more.
        self._leverage = 1.0 if execution.is_live else max(1.0, float(settings.live.leverage))
        risk_limits = settings.risk
        if self._leverage > 1.0:
            risk_limits = settings.risk.model_copy(
                update={
                    "max_position_notional_pct": min(
                        2000.0, settings.risk.max_position_notional_pct * self._leverage
                    ),
                    "max_gross_exposure_pct": min(
                        2000.0, settings.risk.max_gross_exposure_pct * self._leverage
                    ),
                    "max_net_exposure_pct": min(
                        2000.0, settings.risk.max_net_exposure_pct * self._leverage
                    ),
                }
            )
        self._risk = RiskEngine(risk_limits, DEFAULT_UNIVERSE, clock, leverage=self._leverage)
        self._budget = RiskBudgetEngine(RiskProfileName(settings.live.risk_profile))
        self._costs = CostModel(
            FeeSchedule(
                maker_bps=settings.execution.maker_fee_bps,
                taker_bps=settings.execution.taker_fee_bps,
                verified_at_source=False,
                source="configured — replace with account facts via validate_binance.py",
            )
        )
        #: Which persisted round trips the estimator and the retrospective may learn from.
        #: ``legacy`` admits every row; ``real_only`` admits only rows closed against real
        #: market data, so a scenario generator's engineered drift can neither declare a
        #: bucket tradeable nor declare it lost. The scoreboard applies its own policy of
        #: the same shape to the same rows, independently.
        self._evidence_policy = settings.live.ev_evidence_policy
        admitted_outcomes = [
            outcome for outcome in prior_outcomes if self._evidence_admitted(outcome.market_data)
        ]
        admitted_reviews = [
            review for review in prior_reviews if self._evidence_admitted(review.get("market_data"))
        ]
        self._evidence_excluded = len(prior_outcomes) - len(admitted_outcomes)
        self._edges = EdgeEstimator()
        self._edges.record_many(admitted_outcomes)
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
        self._retro.record_many(admitted_reviews)
        #: Each strategy answers for its own closed trades; one whose record is negative
        #: with enough trades to mean it is muted before risk sees its signals. Rebuilt
        #: from the same persisted rows as the estimator, where they name a strategy.
        #: Which of those rows may judge is the configured policy's call (``legacy``:
        #: all of them; ``real_only``: those closed against real market data).
        self._scoreboard = StrategyScoreboard(policy=settings.live.scoreboard_policy)
        self._scoreboard.record_many(list(prior_reviews))
        if execution.is_live:
            # Real money: the configured ceiling, whose fail-closed default of zero is
            # rejected by CapitalPolicy — exactly the refusal we want.
            ledger_ceiling = settings.live.max_live_capital
        elif activation is not None:
            # A token over a simulated venue (dress rehearsals, tests): the token's
            # ceiling governs, as it would with money; the paper balance is the fallback
            # for the fail-closed zero default.
            ledger_ceiling = settings.live.max_live_capital or settings.live.paper_capital
        else:
            # Paper-realtime: nothing here can spend, so the live ceiling governs nothing
            # here. The simulated account's starting balance bounds the ledger; the
            # record's carried P&L is booked as realised on top of it, not allocated.
            ledger_ceiling = settings.live.paper_capital
        self._ledger = CapitalLedger(
            CapitalPolicy(max_live_capital=ledger_ceiling),
            clock=clock,
        )
        self.skew = (
            ClockSkewMonitor(clock, venue_time_ms) if venue_time_ms is not None else None
        )
        self.latency = LatencyTracker(clock)

        #: Realised P&L the persisted record already holds for this account, booked at
        #: start so the balance keeps moving across restarts as one account would.
        self._prior_realised = float(prior_realised_pnl)
        #: The perpetual's latest funding rate, read from the funding monitor when the
        #: application provides one. None means "no reading": nothing is charged and
        #: the snapshot says so.
        self._funding_rate = funding_rate
        #: The monitor's own account of what it can vouch for (``absent`` / ``stale`` /
        #: ``ok``, Phase 1.5), so a missing rate is counted under its reason rather than
        #: under one bucket. Optional: a bare rate callable still works and reads as
        #: ``absent`` when it returns None.
        self._funding_status = funding_status
        #: The venue's realised rate for a given settlement, from the monitor's history
        #: (Phase 1.7): what a settlement the session did not watch is priced with.
        self._funding_rate_at = funding_rate_at
        self._funding_period: tuple[str, int] | None = None
        #: When the settlement check last ran; a boundary seen within
        #: ``FUNDING_PROMPT_GRACE_SECONDS`` of it was watched as it happened.
        self._funding_checked_at: datetime | None = None
        #: Periods this process has settled: a pointer moved backwards (a restore adopting
        #: an older plan) can never charge one of them twice.
        self._funding_settled: set[str] = set()
        #: One settlement pass at a time: two overlapping passes would both see the same
        #: pending period before either booked it (Phase 1.8).
        self._funding_lock = asyncio.Lock()
        #: The last fill this process saw; a settlement earlier than it cannot be
        #: reconstructed from the position as held now.
        self._last_fill_at: datetime | None = None
        self.funding: dict[str, Any] = {
            "payments": 0, "paid_usd": 0.0, "last_rate": None, "last_at": None,
            #: Settlements that passed over an open position with no usable rate — the
            #: total, and by reason (Phase 1.5): ``absent`` (no monitor or no reading
            #: yet), ``stale`` (older than ``funding_max_age_seconds``), ``invalid`` (a
            #: non-finite number). Nothing was charged for them; nothing was guessed.
            "skipped_no_rate": 0,
            "skipped_absent": 0, "skipped_stale": 0, "skipped_invalid": 0,
            "last_skip_reason": None,
            #: Entries priced with a bounded horizon but no funding reading to price the
            #: carry over it (Phase 1.3): nothing was charged for it in the estimate, as
            #: nothing would be charged by the accrual — counted, not hidden, with the
            #: reason (Phase 1.5). ``blocked`` counts entries refused under the ``block``
            #: policy (``LiveConfig.funding_unknown_policy``).
            "ev_carry_unpriced": 0,
            "ev_carry_unpriced_reason": None,
            "blocked": 0,
            #: Settlements charged to the account over a position no round trip here
            #: tracked (Phase 1.6): the venue charges the position, so the account pays;
            #: no trade can carry the amount, so it is counted here and pinned on none.
            "unattributed_payments": 0, "unattributed_usd": 0.0,
            #: Phase 1.7: the period pointer (``YYYY-MM-DD:k``), the settlements priced
            #: from the venue's realised rate and the mark at the settlement after a gap,
            #: and the periods that could not be settled at all — counted exactly, listed
            #: up to a bound, each with its reason (``rate_unknown``, ``mark_unknown``,
            #: ``position_changed``, ``too_old``, or the monitor's ``absent`` / ``stale``
            #: / ``invalid`` for a settlement watched without a usable reading).
            "period": None,
            "reconstructed_payments": 0,
            "unreconciled_periods": 0,
            "unreconciled": [],
            "last_unreconciled_reason": None,
            #: Phase 1.8: which rate priced each settlement — the venue's *realised* rate
            #: for it (from the monitor's history) or the monitor's current reading, an
            #: *estimate* of it — and settlements the journal held that the plan had not
            #: recorded yet, folded back into the tallies at restore.
            "realised_payments": 0,
            "estimate_payments": 0,
            "last_rate_source": None,
            "recovered_from_journal": 0,
        }
        #: The last portfolio view, for the snapshot: unrealised P&L and the open
        #: position's size and mark, from which the liquidation price is computed.
        self._last_unrealised = 0.0
        self._last_position: tuple[float, float] | None = None

        self._consecutive_losses = 0
        for outcome in reversed(admitted_outcomes):
            if outcome.net_return_bps > 0:
                break
            self._consecutive_losses += 1

        self._buffer: deque[Candle] = deque(maxlen=400)
        self._last_close = None
        self._open_trade: dict[str, Any] | None = None
        self._entry_beliefs: dict[str, Any] | None = None
        self._peak_equity = 0.0
        self._trades_today = 0
        self._trading_day = ""
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
            "stops_tightened": 0, "exits_breakeven": 0, "exits_trail": 0,
            "spread_rejected": 0, "strategy_muted": 0, "sized_down": 0,
            "htf_rejected": 0, "htf_sized_down": 0,
            "liquidations": 0, "exits_liquidation": 0, "funding_payments": 0,
            "ev_unknown": 0, "ev_unproven": 0, "ev_disproven": 0,
            # Execution, not placement: entries that actually opened a position, and round
            # trips that actually closed. ``orders`` counts what was sent.
            "entries_filled": 0, "round_trips": 0,
            # Entries refused by the instrument's own filters (lot, minimum notional)
            # after sizing: a size no venue would accept, never sent.
            "filter_rejected": 0,
            # The session deadline: resting entries it cancelled, positions it closed
            # after the wind-down grace.
            "deadline_cancelled": 0, "exits_deadline": 0,
            # Exit integrity: exits not sent because one was already in flight, exits the
            # venue rejected, exits that ended without filling, cancels the venue did not
            # confirm, and emergency flattens.
            "exits_skipped_pending": 0, "exits_rejected": 0, "exits_unfilled": 0,
            "cancel_failures": 0, "exits_flatten": 0,
            # Order polling (Phase 1.3): reads of a tracked order the venue could not
            # answer (kept tracked, nothing placed on top), and tracked orders the venue
            # said it did not know for UNKNOWN_POLLS_BEFORE_LOST consecutive polls.
            "order_poll_failures": 0, "orders_lost": 0,
            # Entries the venue refused outright (F14): sent, never opened, no budget spent.
            "orders_rejected": 0,
            #: Entries refused because the spread gate is on and no fresh, valid quote
            #: could verify it (Phase 1.5). Distinct from ``spread_rejected`` (a quote
            #: that was read and was too wide).
            "spread_unverifiable": 0,
        }
        #: The one protective stop covering the open position, if any. Exactly one, sized
        #: to the position: a stop that protects the wrong size is worse than none.
        self._protective: dict[str, Any] | None = None
        #: The exit levels the entry was approved with, carried from the decision to the
        #: position, and the bar the position opened on (for the optional time stop).
        self._planned_exit: dict[str, Any] = {}
        self._position_opened_bar: int | None = None
        #: The most favourable price seen since entry (highest high for a long, lowest
        #: low for a short) — what the trailing stop follows — and the last bar's ATR in
        #: price units, which sets the trailing distance.
        self._best_price: float | None = None
        self._last_atr: float = 0.0
        #: The venue's live top of book on the latest bar, when the feed can supply it.
        #: Prices the costs the estimate is measured against and gates dislocated books.
        self._last_quote: dict[str, Any] | None = None
        #: Why there is no usable quote when there is none (Phase 1.5): ``unsupported``
        #: (the feed has no book), ``absent``, ``invalid``, ``unavailable`` (the read
        #: failed), ``stale`` (older than ``quote_max_age_seconds``), or ``ok``.
        self._quote_state = "absent"
        #: How the last entry was sized relative to the risk engine's approval, and why.
        self._last_size: dict[str, Any] | None = None
        #: The higher-timeframe tide, refreshed from hourly bars on a slow clock. None
        #: until the first read; unavailable when the feed cannot serve hourly bars.
        self._trend: TrendContext | None = None
        self._trend_refreshed: datetime | None = None
        #: Why the round trip in progress is ending, for the record. Set by whichever
        #: path closes it; read once by the scorer.
        self._exit_reason: str | None = None
        #: What the Orders & Fills page shows for this session: the engine's row shape,
        #: newest first. The database has the durable copy; this is the live window.
        self.recent_orders: deque[dict[str, Any]] = deque(maxlen=200)
        self.recent_fills: deque[dict[str, Any]] = deque(maxlen=200)
        #: Why signals did not become orders, by stage, since start — the answer to "is
        #: it really trading?" when the account has not moved. Every refusal lands here
        #: with its reason; the last few are kept whole for the dashboard.
        self.funnel: dict[str, int] = {
            "evaluated": 0, "not_actionable": 0, "actionable": 0, "resting": 0,
            "risk": 0, "position_open": 0, "halted": 0, "budget": 0, "capital": 0,
            "spread": 0, "tide": 0, "muted": 0, "expected_value": 0, "guardrail": 0,
            "orders": 0, "exploration": 0, "filters": 0,
        }
        self._risk_reasons: dict[str, int] = {}
        self.recent_refusals: deque[dict[str, Any]] = deque(maxlen=50)
        #: The one order allowed to rest at a time, if entries are limit orders. While it
        #: rests, no new entry is considered — stacking resting orders is how a session
        #: ends up long three times on one signal.
        self._resting: dict[str, Any] | None = None
        #: Fill ids already routed to the ledger and the round-trip tracker. A fill can be
        #: seen twice — on the submit response and again on a later order read — and it
        #: must be counted once.
        self._seen_fills: set[str] = set()
        #: Persistence writes run in scheduling order — see :meth:`_sequenced`. The
        #: tasks still in flight are kept so a stop can wait for the record to land:
        #: a fill the process forgot to write before exiting is a round trip the next
        #: restart cannot rebuild (F3/F4).
        self._persist_lock = asyncio.Lock()
        self._persist_tasks: set[asyncio.Task[Any]] = set()
        self._exploration_used = 0
        self._exploration_day = ""
        #: What the persisted execution record said about today's entries when this
        #: session started — see :mod:`tia.risk.restore`. A runtime with no store has
        #: nothing to restore and is complete by construction; a runtime whose store
        #: could not be read is *unverified* and refuses new entries until a complete
        #: rebuild replaces this (:meth:`restore_risk_state`). Exits, protective stops
        #: and reconciliation are unaffected: a position is managed whatever the
        #: counters say.
        self._risk_restore: RiskRestore = RiskRestore.empty(
            day=clock.now().date().isoformat(),
            source="no persistent store" if persist is None else "not consulted",
        )
        #: Why new entries are refused, by cause, while anything about the account, the
        #: orders or the position is unverified. Empty means entries may be considered.
        #: Exits, protective stops and reconciliation never consult this.
        self._blocks: dict[str, str] = {}
        if prior_risk_state is not None:
            self._apply_risk_restore(prior_risk_state)
        #: The account as the journal said it was when this session started — see
        #: :mod:`tia.portfolio.account_journal`. The engine was seeded from it by the
        #: application; the runtime adopts the open leg and its exit plan from it. An
        #: incomplete rebuild blocks entries until a complete one is reconciled.
        self._account_restore: AccountRestore = AccountRestore.empty(
            initial_capital=float(settings.live.paper_capital),
            source="no persistent store" if persist is None else "not consulted",
        )
        self._last_plan_key: tuple[Any, ...] | None = None
        self._mark_every_bars = 15
        #: Set by the day roll so the first bar of a UTC day is always journaled: that
        #: mark is the day's opening equity the loss limit measures from.
        self._day_opened = False
        if prior_account_state is not None:
            self._apply_account_restore(prior_account_state)
        #: The session's own deadline, when it is a validation session rather than the
        #: 24/7 one. An explicit deadline (a restart resuming under the interrupted
        #: session's) wins over the configured span, which is measured from start.
        self._session_deadline: datetime | None = (
            ensure_utc(session_deadline) if session_deadline is not None else None
        )
        # The span is informational once a deadline is explicit (a resumed session has a
        # deadline and no span of its own); it is the rule when no deadline was given.
        self._session_max_hours: float | None = (
            session_max_hours
            if session_max_hours is not None
            else (None if session_deadline is not None else (settings.live.session_max_hours or None))
        )
        #: The one exit order in flight for the position, if any: its identity, what it
        #: reduces and why. While it is working no other exit is sent — two full-size
        #: closes that both fill is a position the other way, not a flat book.
        self._pending_exit: dict[str, Any] | None = None
        self._exit_lock = asyncio.Lock()
        #: Order ids a cancel-all could not get the venue to confirm (Phase 1.3, G2).
        self._unconfirmed_cancels: list[str] = []
        #: How long a stop waits for the persistence writes still in flight, and whether
        #: the last stop had to give up on some (Phase 1.3, G12).
        self._flush_timeout_seconds = 10.0
        self.persistence_flushed: bool | None = None
        #: The run row's heartbeat: written every ``_heartbeat_every_seconds`` of the
        #: session's clock so another process can tell a running session from a dead one
        #: (Phase 1.3, G9). ``None`` until the first write.
        self._heartbeat_every_seconds = 30.0
        self._heartbeat_persisted_mono: float | None = None
        self._winding_down = False
        self._wind_down_started_at: datetime | None = None
        self._wind_down_bar: int | None = None
        self._deadline_close_bar: int | None = None
        self._deadline_close_at: datetime | None = None
        self._deadline_close_stuck = False
        self._stop_reason = ""
        #: True only when the runtime ended its own session (the deadline). An operator
        #: stop stamps the run row through the API; a process shutdown stamps nothing,
        #: so the next boot resumes it — that contract must survive this feature.
        self._self_ended = False
        #: Evidence folded in *after* startup — training runs that finished while this
        #: session was already live. See :meth:`absorb_evidence`.
        self._evidence_absorbed = 0
        self._evidence_absorbed_at: datetime | None = None

    def _evidence_admitted(self, market_data: str | None) -> bool:
        """Whether a persisted round trip may teach the estimator and the retrospective."""
        if self._evidence_policy == "legacy":
            return True
        return market_data == "real"

    def _lot_size(self, symbol: str) -> float:
        """The smallest whole quantity for ``symbol``: the venue's step when filters are
        loaded, the instrument's own lot otherwise, zero when neither is known."""
        step = self._filters.get("step_size")
        if step:
            return float(step)
        instrument = DEFAULT_UNIVERSE.get(symbol)
        return float(instrument.lot_size) if instrument is not None else 0.0

    def _apply_risk_restore(self, restore: RiskRestore) -> None:
        self._risk_restore = restore
        if not restore.complete:
            self._blocks["risk_state"] = (
                "today's entries could not be rebuilt from the execution record: "
                f"{restore.error or 'unknown error'}"
            )
            _log.warning(
                "risk_state_unverified",
                error=restore.error,
                detail="new entries refused until the execution record can be read",
            )
            return
        self._risk.restore(restore)
        # The budget's own counter (orders sent today) and the exploration budget
        # (lessons bought today) are seeded from the same record; both roll over at the
        # next UTC midnight exactly as they would have without the restart.
        self._trading_day = restore.day
        self._trades_today = int(restore.entry_orders_today)
        self._exploration_day = restore.day
        self._exploration_used = int(restore.exploration_closed_today)
        self._blocks.pop("risk_state", None)

    def restore_risk_state(self, restore: RiskRestore) -> dict[str, Any]:
        """Replace the startup rebuild with a fresh one — the reconciliation path.

        A complete rebuild lifts the refusal an incomplete startup left in place; an
        incomplete one keeps it. Never raises: the answer says what happened.
        """
        self._apply_risk_restore(restore)
        self._emit("live.risk_state", self.risk_state_report())
        return self.risk_state_report()

    def risk_state_report(self) -> dict[str, Any]:
        """The frequency state as the engine holds it now, next to what seeded it."""
        state = self._risk.state
        return {
            "verified": "risk_state" not in self._blocks,
            "restore": self._risk_restore.as_dict(),
            "engine": {
                "day": state.current_day,
                "trades_today": state.trades_today,
                "trades_today_by_symbol": dict(state.trades_today_by_symbol),
                "last_trade_at": {k: v.isoformat() for k, v in state.last_trade_at.items()},
            },
            "budget_orders_today": self._trades_today,
            "exploration_used_today": self._exploration_used,
        }

    def _apply_account_restore(self, restore: AccountRestore) -> None:
        self._account_restore = restore
        if not restore.complete:
            self._block_entries(
                "account_state",
                f"the account could not be rebuilt from its journal: {restore.error or 'unknown error'}",
            )
            return
        self._peak_equity = max(self._peak_equity, float(restore.peak_equity))
        # The journal is the source of truth for what was paid (Phase 1.8): every funding
        # settlement it holds is settled, whatever the plan's pointer says. A pointer
        # written after a settlement can be lost to a crash; a row on disk cannot.
        self._funding_settled.update(restore.funding_settled)
        if restore.has_position:
            side = Side.BUY if restore.position_quantity > 0 else Side.SELL
            self._open_trade = {
                "price": float(restore.position_average_price),
                "quantity": abs(float(restore.position_quantity)),
                "side": side,
                "fee": float(restore.open_leg_fees),
                "exit_value": 0.0,
                "exit_quantity": 0.0,
                "exit_fees": 0.0,
                # What the leg paid in funding before the restart, from its journaled
                # plan (Phase 1.6). The account already carries every settlement as an
                # adjustment; this tally only lets the round trip report its whole carry
                # once it closes. A plan written before the field existed reads as zero.
                "funding_paid": float((restore.plan or {}).get("funding_paid") or 0.0),
                "opened_at": ensure_utc(restore.position_opened_at) if restore.position_opened_at else None,
                "restored": True,
            }
            plan = restore.plan or {}
            # The funding pointer travels with the leg (Phase 1.7): every period after it
            # is pending, settled from history or recorded as unreconciled at the first
            # check. A plan without one joins the current period late, as before.
            self._funding_period = parse_funding_period(plan.get("funding_period"))
            self.funding["period"] = funding_period_key(self._funding_period) if self._funding_period else None
            self.funding["unreconciled_periods"] = int(plan.get("funding_unreconciled_periods") or 0)
            self.funding["unreconciled"] = list(plan.get("funding_unreconciled") or [])[-FUNDING_UNRECONCILED_LISTED:]
            # Settlements the journal holds beyond the plan's pointer were paid by a
            # session that did not get to record them in the plan (Phase 1.8): they are
            # folded into the leg's tally when the leg was provably open at the
            # settlement, into the account's otherwise — never charged again.
            pointer = funding_period_index(self._funding_period) if self._funding_period else None
            opened_at = self._open_trade.get("opened_at")
            for period_key, cash in sorted(restore.funding_settled.items()):
                period = parse_funding_period(period_key)
                if period is None or pointer is None or funding_period_index(period) <= pointer:
                    continue
                payment = -float(cash)
                if opened_at is not None and opened_at <= funding_period_start(period):
                    self._open_trade["funding_paid"] = float(self._open_trade["funding_paid"]) + payment
                else:
                    self.funding["unattributed_payments"] += 1
                    self.funding["unattributed_usd"] = round(self.funding["unattributed_usd"] + payment, 6)
                self.funding["recovered_from_journal"] += 1
            direction = plan.get("direction")
            self._planned_exit = {
                "stop": plan.get("stop"),
                "initial_stop": plan.get("initial_stop") or plan.get("stop"),
                "kind": plan.get("kind") or "protective",
                "target": plan.get("target"),
                "direction": Direction(direction) if direction else (
                    Direction.LONG if side is Side.BUY else Direction.SHORT
                ),
            }
            beliefs = restore.beliefs
            if beliefs:
                with contextlib.suppress(Exception):
                    self._entry_beliefs = {
                        "regime": MarketRegime(beliefs["regime"]),
                        "direction": Direction(beliefs["direction"]),
                        "confidence": float(beliefs["confidence"]),
                        "signal_id": str(beliefs.get("signal_id") or ""),
                        "strategy_id": beliefs.get("strategy_id"),
                        "strategy_version": beliefs.get("strategy_version"),
                        "size_fraction": beliefs.get("size_fraction"),
                        "expected_net_bps": float(beliefs.get("expected_net_bps") or 0.0),
                        "exploratory": bool(beliefs.get("exploratory")),
                    }
            self._position_opened_bar = None  # the time stop does not know this leg's age
            self._best_price = None
            self._pending_exit = None
            if self._entry_beliefs is None:
                self._block_entries(
                    "account_state",
                    "a restored position carries no recorded entry beliefs; it is managed and "
                    "closable but new entries wait for a person to reconcile",
                )
                return
        self._unblock_entries("account_state")

    def restore_account_state(self, restore: AccountRestore, *, venue_position: float | None = None) -> dict[str, Any]:
        """Replace the startup rebuild — the reconciliation path.

        A complete rebuild lifts the block only when the venue's own position agrees
        with it (``venue_position``, the engine's quantity for the symbol): the journal
        says what the account should hold, the venue says what it holds, and entries are
        allowed only while the two agree.
        """
        if restore.complete and venue_position is not None and abs(
            float(venue_position) - float(restore.position_quantity)
        ) > 1e-9:
            restore = AccountRestore(**{
                **restore.__dict__, "complete": False,
                "error": f"the venue holds {venue_position} but the journal says {restore.position_quantity}",
            })
        if restore.complete and self._open_trade is not None and abs(
            self._open_trade["quantity"] - abs(float(restore.position_quantity))
        ) > 1e-9:
            restore = AccountRestore(**{
                **restore.__dict__, "complete": False,
                "error": "the tracked round trip disagrees with the journal's position",
            })
        if restore.complete and self._open_trade is None and restore.has_position:
            # Adopt the leg the journal holds and this session does not track yet.
            self._apply_account_restore(restore)
        else:
            self._account_restore = restore
            if restore.complete:
                self._peak_equity = max(self._peak_equity, float(restore.peak_equity))
                self._unblock_entries("account_state")
            else:
                self._block_entries(
                    "account_state",
                    f"the account could not be verified: {restore.error or 'unknown error'}",
                )
        self._emit("live.account_state", self.account_state_report())
        return self.account_state_report()

    def account_state_report(self) -> dict[str, Any]:
        return {
            "verified": "account_state" not in self._blocks,
            "restore": self._account_restore.as_dict(),
            "tracked_position": (
                {"side": self._open_trade["side"].value, "quantity": self._open_trade["quantity"],
                 "price": self._open_trade["price"], "restored": bool(self._open_trade.get("restored"))}
                if self._open_trade else None
            ),
            "peak_equity": self._peak_equity,
        }

    # ------------------------------------------------------------- the account journal

    def _journal(self, event_type: str, payload: Any, *, key: str, occurred_at: datetime) -> None:
        """Append one account event. Idempotent by ``key``; never raises into the loop."""
        envelope = self._envelope(event_type, payload, key=key, occurred_at=occurred_at)
        if envelope is not None:
            self._save("account_event", {"run_id": self.run_id, "envelope": envelope})

    def _journal_events(self, envelopes: Sequence[EventEnvelope[Any]]) -> None:
        """Append several account events that belong together, in one write: the store
        commits them in one session, so a settlement and the plan that records it as
        settled land together or not at all (Phase 1.8)."""
        if self._persist is None or not envelopes:
            return
        if len(envelopes) == 1:
            self._save("account_event", {"run_id": self.run_id, "envelope": envelopes[0]})
            return
        self._save("account_events", {"run_id": self.run_id, "envelopes": list(envelopes)})

    def _envelope(
        self, event_type: str, payload: Any, *, key: str, occurred_at: datetime
    ) -> EventEnvelope[Any] | None:
        """One account event, built but not written; ``None`` without a store or for a
        payload the envelope refuses (logged, never a crash)."""
        if self._persist is None:
            return None
        now = self._clock.now()
        try:
            return EventEnvelope(
                event_id=deterministic_id("evt", event_type, key),
                event_type=event_type,
                source="live",
                occurred_at=ensure_utc(occurred_at),
                ingestion_at=now,
                recorded_at=now,
                correlation_id=self.run_id,
                idempotency_key=f"{event_type}:{key}"[:128],
                payload=payload,
            )
        except Exception as exc:  # a malformed event is logged, never a crash
            _log.warning("account_journal_envelope_failed", event=event_type, error=str(exc)[:200])
            return None

    def _journal_fill(self, fill: Fill) -> None:
        self._journal(
            EVENT_FILL,
            AccountFillPayload(
                symbol=fill.symbol, fill_id=fill.fill_id, order_id=fill.order_id,
                side=fill.side.value, quantity=fill.quantity, price=fill.price, fee=fill.fee,
                filled_at=fill.filled_at,
            ),
            key=fill.fill_id, occurred_at=fill.filled_at,
        )

    def _journal_adjustment(
        self,
        amount: float,
        reason: str,
        *,
        key: str,
        kind: str | None = None,
        period: str | None = None,
        save: bool = True,
    ) -> EventEnvelope[Any] | None:
        """A cash movement that is not a fill. ``kind`` and ``period`` key it in the
        journal (Phase 1.8); with ``save=False`` the event is returned for a batched write."""
        now = self._clock.now()
        envelope = self._envelope(
            EVENT_ADJUSTMENT,
            AccountAdjustmentPayload(
                symbol=self._symbol, amount=float(amount), reason=reason, at=now, kind=kind, period=period,
            ),
            key=key, occurred_at=now,
        )
        if save and envelope is not None:
            self._save("account_event", {"run_id": self.run_id, "envelope": envelope})
        return envelope

    def _journal_mark(self, candle: Candle, portfolio: Any) -> None:
        position = portfolio.positions.get(self._symbol)
        quantity = float(position.quantity) if position is not None else 0.0
        holding = abs(quantity) > 1e-12
        day_open = self._day_opened
        self._day_opened = False
        if not holding and not day_open and self.counters["bars"] % self._mark_every_bars != 0:
            return
        self._journal(
            EVENT_MARK,
            AccountMarkPayload(
                symbol=self._symbol, price=float(candle.close), at=candle.close_time,
                cash=float(portfolio.cash), position_quantity=quantity, equity=float(portfolio.equity),
            ),
            key=f"{self.run_id}:{candle.close_time.isoformat()}", occurred_at=candle.close_time,
        )

    def _journal_plan(self, *, save: bool = True) -> EventEnvelope[Any] | None:
        """Record the open leg's exit plan, entry beliefs and funding record whenever any
        of them changes. With ``save=False`` the event is returned for a batched write
        (Phase 1.8) and ``None`` means nothing changed."""
        if self._open_trade is None or self._persist is None:
            return None
        plan = self._planned_exit
        beliefs = self._entry_beliefs or {}
        serial = {
            k: (v.value if hasattr(v, "value") else v) for k, v in beliefs.items()
        }
        direction = plan.get("direction")
        funding_paid = float(self._open_trade.get("funding_paid", 0.0))
        funding_period = self.funding.get("period")
        unreconciled_periods = int(self.funding.get("unreconciled_periods") or 0)
        key_tuple = (
            plan.get("stop"), plan.get("target"), plan.get("kind"),
            serial.get("signal_id"), serial.get("strategy_id"), round(funding_paid, 8),
            funding_period, unreconciled_periods,
        )
        if key_tuple == self._last_plan_key:
            return None
        self._last_plan_key = key_tuple
        now = self._clock.now()
        envelope = self._envelope(
            EVENT_PLAN,
            AccountPlanPayload(
                symbol=self._symbol, at=now,
                stop=plan.get("stop"), initial_stop=plan.get("initial_stop"),
                target=plan.get("target"), kind=plan.get("kind"),
                direction=direction.value if hasattr(direction, "value") else direction,
                beliefs=serial,
                funding_paid=funding_paid,
                funding_period=funding_period,
                funding_unreconciled_periods=unreconciled_periods,
                funding_unreconciled=list(self.funding.get("unreconciled") or []),
            ),
            key=f"{self.run_id}:{self.counters['bars']}:{len(self.machine.history)}:{hash(key_tuple) & 0xFFFFFFFF}",
            occurred_at=now,
        )
        if save and envelope is not None:
            self._save("account_event", {"run_id": self.run_id, "envelope": envelope})
        return envelope

    @property
    def risk_state_verified(self) -> bool:
        return "risk_state" not in self._blocks

    @property
    def entry_blocks(self) -> dict[str, str]:
        """Every reason new entries are currently refused (empty when none)."""
        return dict(self._blocks)

    def _block_entries(self, key: str, reason: str) -> None:
        if key not in self._blocks:
            _log.warning("entries_blocked", cause=key, reason=reason[:300])
            self._incident(f"entries_blocked:{key}", reason=reason[:500])
        self._blocks[key] = reason[:500]

    def _unblock_entries(self, key: str) -> None:
        if self._blocks.pop(key, None) is not None:
            _log.info("entries_unblocked", cause=key)

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

    def _roll_trading_day(self) -> None:
        """Reset the per-day trade count when the UTC day changes.

        The risk budget caps entries per day; a counter that never rolled over capped
        them per *session* instead, so a session that used its eight entries on Monday
        refused every signal until someone restarted it. Keyed on the injected clock,
        like the exploration budget, so replays and tests behave.
        """
        today = self._clock.now().date().isoformat()
        if today != self._trading_day:
            rolled = bool(self._trading_day)
            self._trading_day = today
            self._trades_today = 0
            self._day_opened = rolled

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
                allocation = float(balance) - self._prior_realised
                note = (
                    f"paper-realtime start: simulated balance {balance}"
                    + (
                        f" (of which {self._prior_realised:+.2f} is realised P&L carried "
                        "from the record)"
                        if self._prior_realised
                        else ""
                    )
                )
            if allocation <= 0 or float(balance) <= 0:
                raise LiveActivationError(
                    f"venue balance {balance} funds no allocation under the ceiling "
                    f"{self._settings.live.max_live_capital}; nothing to trade with"
                    + (
                        " — the simulated account is wiped out; reset it to continue"
                        if not self._execution.is_live and float(balance) <= 0
                        else ""
                    )
                )
            self._ledger.allocate(allocation, at=self._clock.now(), note=note)
            if self._prior_realised:
                self._ledger.record_realised_pnl(self._prior_realised, at=self._clock.now())
            self._peak_equity = allocation + self._prior_realised
        except Exception as exc:
            self.last_error = str(exc)[:500]
            self.machine.transition(LiveState.STOPPING, reason=f"startup failed: {exc}")
            self.machine.transition(LiveState.ERROR, reason="startup validation failed")
            self._incident("startup_failed", reason=str(exc)[:500])
            raise

        if self._session_deadline is None and self._session_max_hours:
            self._session_deadline = self._clock.now() + timedelta(hours=self._session_max_hours)
        self._stop_requested = False
        self._task = asyncio.create_task(self._loop())
        self.machine.transition(LiveState.RUNNING, reason="startup validation passed")
        self._emit("live.state", self.machine.as_dict())

    async def stop(self, *, reason: str = "operator stop") -> None:
        """Stop the session. Idempotent: a stopped session stays stopped, quietly.

        Safe to call from outside the loop (the operator) and from inside it (the
        deadline): the loop task is cancelled only when the caller is not that task.
        """
        if self.machine.state.is_terminal:
            return
        if self.machine.state is not LiveState.STOPPING:
            self.machine.transition(LiveState.STOPPING, reason=reason)
            self._stop_reason = self._stop_reason or reason
        self._stop_requested = True
        task = self._task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._finalize_stop()
        self.persistence_flushed = await self.flush_persistence(
            timeout_seconds=self._flush_timeout_seconds
        )
        if not self.persistence_flushed:
            # Said, not swallowed: a fill or a stop stamp still in flight when the process
            # goes away is a record the next restart rebuilds from short (Phase 1.3, G12).
            pending = sum(1 for t in self._persist_tasks if not t.done())
            self.last_error = (
                f"{pending} persistence write(s) still in flight after "
                f"{self._flush_timeout_seconds:.0f}s at stop; the record may be incomplete"
            )
            _log.error(
                "persistence_flush_incomplete", run_id=self.run_id, pending=pending,
                timeout_seconds=self._flush_timeout_seconds,
            )

    async def _finalize_stop(self) -> None:
        """Close the providers and land in STOPPED exactly once."""
        if self.machine.state.is_terminal:
            return
        if self.machine.state is not LiveState.STOPPING:
            self.machine.transition(LiveState.STOPPING, reason=self._stop_reason or "stopping")
        with contextlib.suppress(Exception):
            await self._execution.close()
        closer = getattr(self._market_data, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                await closer()
        self.machine.transition(LiveState.STOPPED, reason="loop stopped")
        if self._self_ended:
            self._save(
                "run_stop",
                {"run_id": self.run_id, "stopped_at": self._clock.now(), "reason": self._stop_reason},
            )
        self._emit("live.state", self.machine.as_dict())

    # ------------------------------------------------------------------ the deadline

    @property
    def session_deadline(self) -> datetime | None:
        return self._session_deadline

    def session_report(self) -> dict[str, Any]:
        now = self._clock.now()
        deadline = self._session_deadline
        return {
            "deadline_at": deadline.isoformat() if deadline else None,
            "max_hours": self._session_max_hours,
            "seconds_remaining": (
                max(0.0, (deadline - now).total_seconds()) if deadline else None
            ),
            "winding_down": self._winding_down,
            "wind_down_started_at": (
                self._wind_down_started_at.isoformat() if self._wind_down_started_at else None
            ),
            "wind_down_grace_bars": self._settings.live.session_wind_down_bars,
            "stop_reason": self._stop_reason,
        }

    def _bar_seconds(self) -> float:
        try:
            return max(1.0, Timeframe.parse(self._timeframe).delta.total_seconds())
        except Exception:
            return 60.0

    async def _check_deadline(self) -> None:
        """Enforce the session's deadline from inside the loop that owns the session.

        At the deadline: no more entries (HALT_NEW_ORDERS, an operator-level halt the
        watchdog does not lift), the resting *entry* is cancelled (an unfilled entry is
        not a position), and the session ends as soon as it is flat. An open position is
        not abandoned and its protective stop is not cancelled: it keeps being managed
        for ``session_wind_down_bars`` bars so it can leave under its own rules, after
        which it is closed at market through the same path a time stop uses — stop
        cancelled first, reduce-only market order, round trip scored. In SAFE_MODE
        nothing is touched: the doubt that caused it is a person's to resolve, the
        session stops with an incident saying so and the position stays as it is.
        """
        deadline = self._session_deadline
        if deadline is None or self.machine.state.is_terminal or self._stop_requested:
            return
        now = self._clock.now()
        if now < deadline:
            return

        if not self._winding_down:
            self._winding_down = True
            self._wind_down_started_at = now
            self._wind_down_bar = self.counters["bars"]
            if self.machine.state is LiveState.RUNNING:
                self.machine.transition(
                    LiveState.HALT_NEW_ORDERS,
                    reason=f"session deadline {deadline.isoformat()} reached",
                    actor="session-deadline",
                )
            resting = self._resting
            if resting is not None and not resting.get("reducing"):
                cancelled = await self._cancel(
                    resting["client_order_id"] or resting["order_id"], purpose="deadline"
                )
                if cancelled is not None:
                    self._resting = None
                    self.counters["deadline_cancelled"] += 1
            self._incident(
                "session_deadline",
                reason=f"deadline {deadline.isoformat()} reached; no new entries",
                actor="session-deadline",
                detail={"position_open": self._open_trade is not None},
            )
            self._emit("live.session_deadline", self.session_report())

        if self.machine.state is LiveState.RUNNING:
            # Lifted by an operator or the watchdog after the deadline: put back. The
            # deadline is not a halt a person may undo; ending the session is.
            self.machine.transition(
                LiveState.HALT_NEW_ORDERS, reason="session deadline stands", actor="session-deadline",
            )
        if self._resting is not None and not self._resting.get("reducing") and (
            await self._cancel(
                self._resting["client_order_id"] or self._resting["order_id"], purpose="deadline"
            ) is not None
        ):
            # A resting entry the earlier cancel could not confirm, cancelled now.
            self._resting = None
            self.counters["deadline_cancelled"] += 1

        try:
            portfolio = await self._execution.get_portfolio()
        except Exception as exc:
            # The venue cannot be read: whether a position is open is unknown, and an
            # unknown position is not abandoned. The halt stands; the loop keeps asking.
            self.last_error = f"deadline: venue unreadable: {exc}"[:500]
            return
        position = portfolio.positions.get(self._symbol)
        flat = position is None or position.is_flat

        await self._poll_pending_exit()
        if flat and self._open_trade is None and self._pending_exit is None:
            await self._finish_session("session deadline reached; flat")
            return

        # The grace is counted in bars where bars flow, and in the bars' worth of wall
        # time where they do not (SAFE_MODE and PAUSED read no bars; a dead feed
        # delivers none): a session cannot wait for bars that will never come.
        grace = self._settings.live.session_wind_down_bars
        waited_bars = self.counters["bars"] - int(self._wind_down_bar or 0)
        elapsed = (now - (self._wind_down_started_at or now)).total_seconds()
        grace_over = waited_bars >= grace or elapsed >= grace * self._bar_seconds()
        if self.machine.state is LiveState.SAFE_MODE:
            if grace_over:
                self._incident(
                    "session_deadline_in_safe_mode",
                    reason="deadline passed in SAFE_MODE with a position open; nothing was "
                    "touched — an operator must resolve the position",
                    actor="session-deadline",
                )
                await self._finish_session("session deadline reached in safe mode; position left")
            return
        if not grace_over or not self.machine.state.accepts_reducing_orders:
            return
        if self._deadline_close_bar is None:
            # Once. The close fills on the next bar in paper; a second close on top of
            # an unfilled first would be a second position the other way.
            self._deadline_close_bar = self.counters["bars"]
            self._deadline_close_at = now
            await self._close_position("session deadline")
        elif not self._deadline_close_stuck and (
            self.counters["bars"] - self._deadline_close_bar >= 3
            or (
                # Bars may never come again (a dead feed): three bars' worth of wall
                # time says the same thing (F9).
                self._deadline_close_at is not None
                and (now - self._deadline_close_at).total_seconds() >= 3 * self._bar_seconds()
            )
        ):
            # Sent, and the position is still there. Said once; the halt stands and the
            # loop keeps managing the position — an operator decides, not a retry loop.
            self._deadline_close_stuck = True
            self._incident(
                "session_deadline_close_unfilled",
                reason="the deadline's closing order did not flatten the position within "
                "three bars; no retry — the position stays protected and an operator "
                "must resolve it",
                actor="session-deadline",
            )

    async def _finish_session(self, reason: str) -> None:
        """Reconcile, record, and ask the loop to end. Never cancels the loop task
        from inside itself; the loop finalizes after this iteration."""
        if self._stop_requested or self.machine.state.is_terminal:
            return
        with contextlib.suppress(Exception):
            await self._reconcile()
        self._stop_reason = reason
        self._self_ended = True
        self._incident("session_completed", reason=reason, actor="session-deadline")
        self.machine.transition(LiveState.STOPPING, reason=reason, actor="session-deadline")
        self._stop_requested = True
        self._emit("live.state", self.machine.as_dict())

    def pause(self, *, actor: str) -> None:
        self.machine.transition(LiveState.PAUSING, reason="operator pause", actor=actor)
        self.machine.transition(LiveState.PAUSED, reason="paused", actor=actor)

    def resume(self, *, actor: str) -> None:
        """PAUSED or HALT_NEW_ORDERS back to RUNNING. Requires a named operator."""
        if not actor.strip():
            raise ValueError("resuming live trading requires a named operator")
        if self._winding_down:
            raise ValueError(
                "the session's deadline has passed; it is winding down and cannot be resumed"
            )
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
        # The same evidence policy as at startup: what the estimator may not learn from at
        # construction, it may not learn from an hour later either.
        admitted_outcomes = [o for o in outcomes if self._evidence_admitted(o.market_data)]
        admitted_reviews = [r for r in reviews if self._evidence_admitted(r.get("market_data"))]
        self._edges.record_many(admitted_outcomes)
        self._retro.record_many(admitted_reviews)
        credited = self._scoreboard.record_many(reviews)
        self._evidence_absorbed += len(admitted_outcomes)
        self._evidence_excluded += len(outcomes) - len(admitted_outcomes)
        self._evidence_absorbed_at = self._clock.now()
        result = {
            "absorbed_outcomes": len(admitted_outcomes),
            "excluded_outcomes": len(outcomes) - len(admitted_outcomes),
            "absorbed_reviews": len(admitted_reviews),
            "strategies_credited": credited,
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
            protective = self._protective
            if (
                symbol == self._symbol
                and protective is not None
                and protective.get("order_id")
            ):
                # The protective stop is still tracked because the venue did not confirm
                # its cancel. A market close on top of a stop that may still rest is the
                # double fill this method exists to avoid; the position stays protected
                # and the operator is told to retry once the cancel goes through.
                closed.append(
                    {
                        "symbol": symbol, "quantity": quantity,
                        "state": "not sent (protective stop cancel unconfirmed)",
                    }
                )
                continue
            order = await self._submit_exit(
                symbol=symbol, side=side, quantity=quantity, reason="emergency flatten"
            )
            closed.append(
                {
                    "symbol": symbol, "quantity": quantity,
                    "state": order.state.value if order is not None else "not sent (exit pending or refused)",
                }
            )

        await self._reconcile()
        self._incident(
            "emergency_flatten",
            reason=reason,
            actor=actor,
            detail={
                "cancelled_orders": cancelled,
                "closing_orders": closed,
                "unconfirmed_cancels": list(self._unconfirmed_cancels),
            },
        )
        self._emit("live.state", self.machine.as_dict())
        return {
            "state": self.machine.state.value,
            "cancelled_orders": cancelled,
            "closing_orders": closed,
        }

    async def _cancel_all_open(self) -> int:
        """Cancel every order the venue lists as open; forget a tracked record only once
        the venue confirmed that order's cancel.

        Before 1.3 the protective stop's and the resting entry's records were dropped
        *before* the cancels were sent, so a cancel the venue refused left a stop
        resting that nothing tracked — and a flatten then closed over it. The ids the
        venue did not confirm are kept in ``_unconfirmed_cancels`` for the caller.
        """
        cancelled = 0
        self._unconfirmed_cancels = []
        try:
            open_orders = await self._execution.get_orders(open_only=True)
        except Exception as exc:
            _log.warning("cancel_all_could_not_list", error=str(exc)[:200])
            self.counters["order_poll_failures"] += 1
            return 0
        for order in open_orders:
            if order.state.is_terminal:
                continue
            ref = order.client_order_id or order.order_id
            if await self._cancel(ref, purpose="cancel all") is not None:
                cancelled += 1
                self._forget_tracked(order)
            else:
                self._unconfirmed_cancels.append(ref)
        return cancelled

    def _forget_tracked(self, order: Order) -> None:
        """Drop the runtime's record of ``order`` after the venue confirmed it is over."""
        ids = {order.order_id, order.client_order_id}
        if self._protective is not None and self._protective.get("order_id") in ids:
            self._protective = None
        if self._resting is not None and self._resting.get("order_id") in ids:
            self._resting = None
            if self._open_trade is None:
                self._entry_beliefs = None

    # ------------------------------------------------------------------ the loop

    async def _loop(self) -> None:
        while not self._stop_requested:
            await self._loop_iteration()
            if self._stop_requested:
                break
            # A streaming feed wakes the loop the moment a bar closes; a polling feed
            # is asked again after the interval. Same loop either way.
            waiter = getattr(self._market_data, "wait_for_bar", None)
            if callable(waiter):
                await waiter(timeout_seconds=self._poll_interval)
            else:
                await asyncio.sleep(self._poll_interval)
        # The loop ended on its own (the deadline): it finalizes itself. An operator
        # stop cancels the task before this line and finalizes from outside; a flag
        # flipped by anything else leaves finalization to whoever flipped it.
        if self._self_ended:
            await self._finalize_stop()

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
        self._persist_heartbeat(self.last_heartbeat)

        # The session's own deadline, before anything else and whatever the state: a
        # paused or safe-moded session still ends when its time is up.
        await self._check_deadline()
        if self._stop_requested:
            return

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

        # Funding settles by the clock, in every state (Phase 1.7): a paused or safe-moded
        # session still holds its position and the venue still charges it. Accounting
        # only — it places no order, reads no signal, fills nothing.
        await self._settle_funding(self._clock.now())

        if self.machine.state in {LiveState.PAUSED, LiveState.SAFE_MODE}:
            # No decisions, but the venue does not pause: a stop can fire and an exit can
            # fill while the session stands still, and what they did must be read, booked
            # and journaled now rather than when the state changes (Phase 1.3, G7).
            await self._poll_tracked_orders()
            return

        candles = await self._market_data.get_candles(
            self._symbol, self._timeframe, limit=200
        )
        if not candles:
            await self._poll_tracked_orders()
            return
        latest = candles[-1]
        if self._last_close is not None and latest.close_time <= self._last_close:
            await self._poll_tracked_orders()  # a quiet feed is not a quiet venue (G7)
            return  # no new closed bar yet
        self._last_close = latest.close_time
        self._last_bar_wall = self._clock.now()
        self._provider_failures = 0
        self._buffer.clear()
        self._buffer.extend(candles)
        self.counters["bars"] += 1
        self._roll_trading_day()
        await self._refresh_quote()
        await self._refresh_trend()

        # Paper-realtime: the simulated matching engine fills resting orders against the
        # bar the way the live venue would have filled them against the tape.
        on_bar = getattr(self._execution, "on_bar", None)
        if callable(on_bar):
            for fill in on_bar(latest):
                self._on_fill(fill)

        if self._resting is not None:
            await self._manage_resting()
        await self._manage_position(latest)
        with contextlib.suppress(Exception):
            self._journal_mark(latest, await self._execution.get_portfolio())
        self._journal_plan()

        # Watchdog self-heal: data is flowing again. RUNNING is earned back through a
        # clean reconciliation, not assumed — and only for halts the watchdog itself
        # caused; an operator's halt stays until the operator lifts it.
        if (
            self._watchdog_halt
            and self.machine.state is LiveState.HALT_NEW_ORDERS
            and not self._winding_down
        ):
            await self._reconcile()
            if not self.counters_last_reconciliation_broke():
                self._watchdog_halt = False
                self.machine.transition(
                    LiveState.RUNNING,
                    reason="watchdog: data restored and reconciliation clean",
                    actor="watchdog",
                )

        await self._process_bar(latest)

    async def _poll_tracked_orders(self) -> None:
        """Read the venue's view of every order this session tracks and route what it
        produced. The cycle's duty whatever its state and whether or not a bar closed:
        reads only, nothing is cancelled or sent here (Phase 1.3, G7)."""
        await self._poll_protective()
        await self._poll_pending_exit()
        await self._poll_resting()

    def _persist_heartbeat(self, now: datetime) -> None:
        """Stamp the run row with the session's clock, at most every
        ``_heartbeat_every_seconds``: the lease another process reads before it resumes
        or starts a session over the same account (Phase 1.3, G9)."""
        if self._persist is None:
            return
        # Throttled on wall time, not the session's clock: a replayed or simulated clock
        # advances a bar per cycle and would otherwise write a row per cycle.
        mono = time.monotonic()
        last = self._heartbeat_persisted_mono
        if last is not None and mono - last < self._heartbeat_every_seconds:
            return
        self._heartbeat_persisted_mono = mono
        self._save("run_heartbeat", {"run_id": self.run_id, "at": now})

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
        values = features.finite_values()
        # ATR in price units, kept for the trailing stop on the bars that follow.
        self._last_atr = max(0.0, values.get("atr_pct", 0.0) / 100.0) * candle.close
        regime = self._regimes.classify(features, now=candle.close_time)
        signal, _ = self._strategies.evaluate(
            features=features,
            regime=regime,
            quality=report,
            context=None,
            correlation_id=correlation_id,
        )
        self.counters["signals"] += 1
        self.funnel["evaluated"] += 1
        self.latency.stamp(correlation_id, "decision_finished")

        if not signal.direction.is_actionable:
            self.funnel["not_actionable"] += 1
            return
        self.funnel["actionable"] += 1

        # The higher-timeframe tide. Against an agreed one-to-four-week trend an entry
        # is refused (hard) or halved (soft); with it, or with no tide known, nothing
        # changes. The estimator's buckets are untouched either way — this is a gate on
        # entries, like the spread gate, and it can only ever refuse or shrink.
        htf_fraction = 1.0
        trend = self._trend
        agrees = (
            trend.agrees_with(signal.direction is Direction.LONG)
            if trend is not None and self._settings.live.htf_mode != "off"
            else None
        )
        if agrees is False:
            if self._settings.live.htf_mode == "hard":
                self.counters["htf_rejected"] += 1
                self._refuse(
                    "tide",
                    f"against the tide — the {trend.timeframe} record says "
                    f"{trend.bias} ({trend.reason}); a {signal.direction.value} "
                    "entry is not taken against a one-to-four-week trend",
                    correlation_id,
                    signal=signal,
                    regime=regime,
                )
                return
            htf_fraction = 0.5

        if self._scoreboard.is_muted(signal.strategy_id):
            # The strategy's own record says it loses. Refused before risk, before
            # expected value: a proposal from a source that has proven itself wrong is
            # not a proposal this session considers.
            self.counters["strategy_muted"] += 1
            self._refuse(
                "muted", self._scoreboard.reason(signal.strategy_id), correlation_id,
                signal=signal, regime=regime,
            )
            return

        if self._resting is not None:
            # An order is already working. A second one on the next bar would not be a
            # second opinion, it would be a second position.
            self.counters["resting_skipped"] += 1
            self.funnel["resting"] += 1
            return

        if self._winding_down:
            # The session's clock has run out. Whatever state an operator or the
            # watchdog put the machine in afterwards, no entry is taken past the deadline.
            self.funnel["halted"] += 1
            return

        if self._blocks:
            # Something the entry decision rests on is unverified: today's entries could
            # not be rebuilt, the account could not be restored, a cancel the venue did
            # not confirm, a position the runtime does not track. Refusing here, before
            # risk, is the fail-safe. Exits and protective stops are unaffected.
            self._refuse(
                "risk",
                "entries blocked (state unverified) — " + "; ".join(
                    f"{key}: {reason}" for key, reason in self._blocks.items()
                ),
                correlation_id,
                signal=signal,
                regime=regime,
            )
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
            # The observed spread, when a fresh quote shows one, so ``RiskLimits.
            # max_spread_bps`` is the hard ceiling it documents (Phase 1.5); never the
            # configured constant, which is an estimate and not an observation.
            spread_bps=self._observed_spread_bps(),
            now=self._clock.now(),
        )
        self.latency.stamp(correlation_id, "risk_finished")
        if not decision.allows_execution:
            self.counters["risk_rejected"] += 1
            why = "; ".join(decision.reasons) if decision.reasons else decision.verdict.value
            key = (decision.reasons[0] if decision.reasons else decision.verdict.value)[:80]
            self._risk_reasons[key] = self._risk_reasons.get(key, 0) + 1
            self._refuse(
                "risk", f"risk engine — {why}", correlation_id, signal=signal, regime=regime
            )
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
                self.funnel["position_open"] += 1
            return

        if not self.machine.state.accepts_new_orders:
            self.funnel["halted"] += 1
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
                # In units of the account's leveraged capacity, so the profile's cap
                # reads the same at 1x and at 5x.
                open_gross_exposure_pct=(
                    portfolio.gross_exposure / (equity * self._leverage) * 100.0
                    if equity > 0
                    else 0.0
                ),
            )
        )
        if not budget.allows_new_trades:
            self.counters["budget_rejected"] += 1
            self._refuse(
                "budget", f"risk budget — {budget.binding_constraint}", correlation_id,
                signal=signal, regime=regime,
            )
            return

        if self._ledger.loss_breached(unrealised_pnl=portfolio.unrealized_pnl):
            self.funnel["capital"] += 1
            self.halt_new_orders(reason="total loss limit breached")
            return
        if self._ledger.is_halted:
            self.funnel["capital"] += 1
            self.halt_new_orders(reason=self._ledger.halted_reason)
            return

        # Expected value — enforced. This class has no observe mode.
        measured_latency = self.latency.ema_total_ms or float(
            self._settings.execution.submit_latency_ms
            + self._settings.execution.ack_latency_ms
        )
        # The spread the market is showing, when the feed supplies a fresh quote; the
        # configured constant when the feed has no book at all (a replay, a fake). With
        # the gate on, a feed that *can* quote but shows no fresh, valid quote has the
        # entry refused: a constant is not a book, and a limit that cannot be checked is
        # not met (Phase 1.5). A book wider than the ceiling is a cost the estimate never
        # priced, and the entry waits for it to close.
        quote, quote_state = self._fresh_quote()
        spread_bps = float(quote["spread_bps"]) if quote else float(
            self._settings.execution.base_slippage_bps
        )
        max_spread = self._settings.live.max_spread_bps
        if quote is None and max_spread > 0 and self._feed_quotes():
            self.counters["spread_unverifiable"] += 1
            self._refuse(
                "spread",
                f"spread gate — no verifiable quote ({quote_state}); the {max_spread:.1f} bps "
                "ceiling cannot be checked and the configured constant is not a book",
                correlation_id,
                signal=signal,
                regime=regime,
            )
            return
        if quote and max_spread > 0 and spread_bps > max_spread:
            self.counters["spread_rejected"] += 1
            self._refuse(
                "spread",
                f"spread gate — the book is {spread_bps:.1f} bps wide, over the "
                f"{max_spread:.1f} bps ceiling; the entry waits for it to close",
                correlation_id,
                signal=signal,
                regime=regime,
            )
            return
        conditions = MarketConditions(
            price=max(candle.close, 1e-9),
            spread_bps=spread_bps,
            volatility_per_bar=max(0.0, values.get("atr_pct", 0.0) / 100.0),
            # Depth at the touch when the feed shows it; zero — priced as ignorance,
            # not as plenty — when it does not.
            top_of_book_quantity=(
                min(float(quote["bid_size"]), float(quote["ask_size"])) if quote else 0.0
            ),
            bar_volume=candle.volume,
            latency_ms=measured_latency,
            bar_seconds=60.0,
        )
        # The carry over the expected holding horizon (Phase 1.3): with a time stop the
        # horizon is bounded and the eight-hour settlements it may cross are priced at the
        # perpetual's live rate — paid when paid, never credited. Without a time stop the
        # horizon is unbounded and nothing is priced: the session's funding accrual charges
        # it as it happens, and the omission is said in the record (``funding_periods``).
        # Without a *reading* (no monitor, or one with nothing yet) nothing is priced
        # either: the accrual charges nothing for such a period and counts it
        # (``skipped_no_rate``), so the cost the gate subtracts stays the cost the
        # simulator will charge, and the omission is counted (``ev_carry_unpriced``).
        # Pricing it as *unknown* instead would refuse every entry while the funding feed
        # is down — a stricter policy recorded as a decision in the Phase 1.3 report.
        live_cfg = self._settings.live
        funding_periods = 0.0
        funding_rate: float | None = None
        carry_unpriced: str | None = None
        if live_cfg.charge_funding and live_cfg.max_holding_bars > 0 and not self._execution.is_live:
            rate, reason = self._funding_reading()
            if rate is not None:
                funding_rate = rate
                holding_seconds = live_cfg.max_holding_bars * self._bar_seconds()
                funding_periods = float(math.ceil(holding_seconds / FUNDING_PERIOD_SECONDS))
            else:
                carry_unpriced = reason
                self.funding["ev_carry_unpriced"] += 1
                self.funding["ev_carry_unpriced_reason"] = reason
                if live_cfg.funding_unknown_policy == "block":
                    # The explicit fail-closed policy (Phase 1.5): a bounded horizon whose
                    # carry cannot be priced is an unknown cost, and this configuration
                    # refuses to take an unknown cost.
                    self.funding["blocked"] += 1
                    self._refuse(
                        "funding",
                        f"funding gate — the carry over {live_cfg.max_holding_bars} bars cannot "
                        f"be priced (funding rate {reason}); policy is block",
                        correlation_id,
                        signal=signal,
                        regime=regime,
                    )
                    return
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
                direction=signal.direction,
                funding_rate=funding_rate,
                funding_periods=funding_periods,
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
        exploration_kind = ""
        if not evaluation.is_tradeable:
            # Paper-only exploration: a bucket the estimator knows nothing about, or one
            # whose edge is UNPROVEN — a positive mean that has not cleared its own
            # uncertainty — may be traded a bounded number of times per day, purely to
            # buy evidence with simulated money. Three refusals stand regardless: a
            # bucket the evidence says LOSES (mean at or below zero, or an edge that has
            # decayed) is respected, an active guardrail is respected, and a live
            # execution provider disables exploration entirely — with real money,
            # "not proven" is a reason not to trade.
            estimate = evaluation.edge_estimate
            if estimate is None:
                self.counters["ev_unknown"] += 1
                exploration_kind = "unknown"
            elif estimate.adjusted_bps < 0.0:
                # Disproven means the record is worse than its own noise: the mean sits
                # more than the estimator's standard-error discount below zero (or the
                # recent window does, where it overruled the whole record). A red mean
                # still inside its noise is the absence of evidence, not evidence of a
                # loss, and stays explorable — the same bar the mute rule applies.
                self.counters["ev_disproven"] += 1
            else:
                self.counters["ev_unproven"] += 1
                exploration_kind = "unproven"
            if (
                exploration_kind
                and self.exploration_enabled
                and not guard.is_active
                and self._exploration_budget_left()
            ):
                exploring = True
            else:
                self.counters["ev_rejected"] += 1
                self._refuse(
                    "expected_value", evaluation.explain(), correlation_id,
                    signal=signal, regime=regime,
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
            self._refuse("guardrail", reason, correlation_id, signal=signal, regime=regime)
            return

        if exploring:
            self._exploration_used += 1
            self.counters["exploration_trades"] += 1
            self.funnel["exploration"] += 1
            estimate = evaluation.edge_estimate
            basis = (
                "no evidence exists"
                if exploration_kind == "unknown" or estimate is None
                else (
                    f"the edge is unproven — {estimate.mean_bps:+.1f} bps on average over "
                    f"{estimate.samples} trades, not yet clear of its own uncertainty"
                )
            )
            self._emit(
                "live.exploration",
                {
                    "correlation_id": correlation_id,
                    "kind": exploration_kind,
                    "reason": (
                        f"exploration trade — {basis} for "
                        f"{regime.regime.value}/{signal.direction.value} at this "
                        f"confidence; buying a lesson with simulated money "
                        f"({self._exploration_used} of "
                        f"{self._settings.live.exploration_trades_per_day} today)"
                    ),
                },
            )

        # Conviction: the evidence decides what fraction of the budget this entry
        # deserves. Only ever downward, never above one.
        size_fraction = 1.0
        reason_text = "conviction sizing off"
        if self._settings.live.conviction_sizing or htf_fraction < 1.0:
            sizing = conviction_fraction(
                evaluation.edge_estimate,
                exploring=exploring,
                min_fraction=self._settings.live.min_size_fraction,
                exploration_fraction=self._settings.live.exploration_size_fraction,
                pooled_cap=self._settings.live.pooled_size_cap,
            ) if self._settings.live.conviction_sizing else None
            size_fraction = (sizing.fraction if sizing else 1.0) * htf_fraction
            reason_text = (sizing.reason if sizing else "conviction sizing off") + (
                f"; halved against the {trend.timeframe} tide" if htf_fraction < 1.0 and trend else ""
            )
            if htf_fraction < 1.0:
                self.counters["htf_sized_down"] += 1

        # The sizing contract (Phase 1.3, :func:`tia.risk.sizing.apply_risk_budget`):
        # the risk engine's approval is the ceiling, the risk budget — the profile's
        # risk per trade after its drawdown, volatility and streak multipliers — and the
        # conviction shrink it, the venue's step rounds it down, and a size that then
        # falls below the minimum notional is refused, never raised to reach it. Before
        # 1.3 the budget was computed and only its yes/no was read; the multipliers never
        # touched the size, and an exploration trade was bumped up to the minimum.
        filters = filters_for(self._symbol, DEFAULT_UNIVERSE, self._filters)
        budgeted = apply_risk_budget(
            approved_quantity=decision.approved_quantity,
            entry_price=signal.entry_reference,
            stop_price=decision.stop_price,
            limit_risk_currency=(
                decision.sizing.risk_budget_currency
                if decision.sizing is not None
                else equity * self._risk.limits.max_risk_per_trade_pct / 100.0
            ),
            budget_risk_currency=budget.risk_currency,
            conviction_fraction=size_fraction,
            step_size=filters.step_size,
            min_notional=filters.min_notional,
            allows_new_trades=budget.allows_new_trades,
        )
        self._last_size = {
            "fraction": round(size_fraction, 4),
            "reason": reason_text,
            "quantity": budgeted.quantity,
            "at": self._clock.now().isoformat(),
            **{f"risk_{k}": v for k, v in budgeted.as_dict().items() if k != "quantity"},
        }
        if not budgeted.accepted:
            if budgeted.refused_reason in {"below_min_notional", "below_lot_step"}:
                # The venue's size rules refused what the budget left: counted where
                # every other filter refusal is, and never raised to the minimum.
                self.counters["filter_rejected"] += 1
                self._refuse(
                    "filters",
                    f"order filters — {budgeted.quantity_text()} is below the minimum the venue "
                    f"accepts (allowed risk ${budgeted.allowed_risk_currency:,.2f} at a stop "
                    f"distance of {budgeted.stop_distance:.2f}); not raised to reach it",
                    correlation_id, signal=signal, regime=regime,
                )
            else:
                self.counters["budget_rejected"] += 1
                self._refuse(
                    "budget",
                    f"risk budget sizing — {budgeted.refused_reason}: allowed risk "
                    f"${budgeted.allowed_risk_currency:,.2f}",
                    correlation_id, signal=signal, regime=regime,
                )
            return
        if budgeted.quantity < decision.approved_quantity * (1.0 - 1e-9):
            self.counters["sized_down"] += 1
            decision = decision.model_copy(update={"approved_quantity": budgeted.quantity})

        self._planned_exit = {
            "stop": decision.stop_price,
            "initial_stop": decision.stop_price,
            "kind": "protective",
            "target": decision.target_price,
            "direction": signal.direction,
        }
        await self._submit(decision, signal, correlation_id)
        self._entry_beliefs = {
            "regime": regime.regime,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "signal_id": signal.signal_id,
            "strategy_id": signal.strategy_id,
            "strategy_version": credited_strategy_version(signal),
            "size_fraction": size_fraction,
            "expected_net_bps": evaluation.net_edge_bps,
            # The estimate priced no carry over its horizon and says why (Phase 1.5);
            # None when the carry was priced or no horizon was claimed.
            "carry_unpriced": carry_unpriced,
            # An exploration entry carries no claim about its own outcome: it was taken
            # *because* the bucket has no evidence. Recording it as an expectation the
            # system then missed would have the session punish itself for deliberately
            # buying a lesson — see RetrospectiveEngine.review.
            "exploratory": exploring,
        }
        self._journal_plan()

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
        return float(quantize_price_passive(raw, tick, buy=side is Side.BUY))

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
        # One rule set for every mode — see :mod:`tia.execution.filters`. The venue's
        # filters when a live session loaded them; the instrument's own lot and minimum
        # notional otherwise (paper-live), stated as the local rule they are. Quantized
        # DOWN, then judged after quantization: a size that was legal before rounding and
        # is not after it is refused, not sent.
        filters = filters_for(symbol, DEFAULT_UNIVERSE, self._filters)
        requested = quantity
        quantity = filters.quantize(quantity)
        if quantity <= 0:
            raise OrderFilterError(
                f"{symbol}: quantity {requested} quantized to zero — below the lot step "
                f"{filters.step_size} ({filters.source})"
            )
        price_hint = float(self._filters.get("last_price", 0.0) or 0.0)

        if order_type is None:
            order_type = OrderType.LIMIT if self.entry_is_limit else OrderType.MARKET
        limit_price: float | None = None
        if order_type is OrderType.LIMIT:
            reference = reference_price or price_hint
            if not reference or reference <= 0:
                order_type = OrderType.MARKET  # no price to rest at: cross honestly
            else:
                limit_price = self._limit_price_for(side, float(reference))

        # The notional is judged at the price the order will be judged at: its limit when
        # it rests, the caller's reference when it crosses, the last closed bar when the
        # caller gave none. Reduce-only orders are exempt — a position must always be
        # closable. With no price at all an entry is refused, never assumed.
        last_close = self._buffer[-1].close if self._buffer else None
        judged_at = limit_price if limit_price else (reference_price or price_hint or last_close)
        validate_quantity(
            filters, quantity, reference_price=judged_at, reduce_only=reduce_only
        )

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
        try:
            intent = self._build_intent(
                symbol=decision.symbol,
                side=side,
                quantity=decision.approved_quantity,
                signal_id=decision.signal_id,
                reference_price=self._buffer[-1].close if self._buffer else None,
            )
        except OrderFilterError as exc:
            # A size no venue would accept is a refusal with a reason, not a failure of
            # the session: it is counted where every other refusal is, and the loop goes
            # on. Nothing was sent, so nothing can have filled.
            self.counters["filter_rejected"] += 1
            self._refuse("filters", f"order filters — {exc}", correlation_id, signal=signal)
            return

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
        self.funnel["orders"] += 1
        if order.state.is_terminal and not order.fills:
            # Refused by the venue: nothing opened, so nothing is spent from the day's
            # budget (F14). Still counted among the orders sent — it was sent.
            self.counters["orders_rejected"] += 1
        else:
            self._trades_today += 1
        fills = list(order.fills)
        if fills:
            # The order row must exist before its fills are written: a fill references
            # its order, and a venue that fills on the acknowledgement hands both back
            # at once. Written again below with the state the fills left it in.
            self._save("order", {"run_id": self.run_id, "order": order})
            self.latency.stamp(correlation_id, "fill_received")
            for fill in fills:
                self._on_fill(fill)
        if not order.state.is_terminal:
            # Tracked while it works, a limit *or* a market order: in paper a market
            # order fills on the next bar and rests until then, and an order no record
            # names is one the reconciliation must flag as nobody's (Phase 1.3, G8).
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
                "limit": order.order_type is OrderType.LIMIT,
            }
            if order.order_type is OrderType.LIMIT:
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
        self._record_order(order)
        self._save("order", {"run_id": self.run_id, "order": order})

    def _save_order_if_changed(self, record: dict[str, Any], order: Order) -> None:
        """Write the venue's view of a tracked order when it changed since the last write.

        The persisted row must say what the venue says: a fill or a terminal state is a
        change worth writing. A partially filled order that keeps resting is not written
        again every cycle — that is a write per cycle for nothing, and a persistence
        queue a stop then cannot drain (Phase 1.3).
        """
        if not order.fills and not order.state.is_terminal:
            return
        mark = (order.state.value, len(order.fills), round(order.filled_quantity, 12))
        if record.get("persisted") == mark:
            return
        record["persisted"] = mark
        self._record_order(order)
        self._save("order", {"run_id": self.run_id, "order": order})

    async def _poll_resting(self) -> Order | None:
        """Read the venue's view of the resting entry and route what it produced.

        Returns the order while it is still working; clears the record once it is
        terminal. Keeps the record — and returns ``None`` — when the venue could not be
        read or does not know the order yet (see :meth:`_read_tracked_order`).
        """
        resting = self._resting
        if resting is None:
            return None
        order, outcome = await self._read_tracked_order(resting)
        if order is None:
            if outcome == "error":
                return None  # the venue could not be asked: still tracked, asked again next cycle
            # The venue says it does not know the order. Before 1.3 the record was
            # dropped at once and the next signal could rest a second entry on top of
            # one that might still be working (Phase 1.3, G3).
            if self._count_unknown(resting, what="resting order"):
                self._resting = None
                if self._open_trade is None:
                    self._entry_beliefs = None
            return None
        resting.pop("unknown_polls", None)

        for fill in order.fills:
            self._on_fill(fill)
        self._save_order_if_changed(resting, order)
        if order.state.is_terminal:
            self._resting = None
            return None
        return order

    async def _manage_resting(self) -> None:
        """Advance the one resting order: route its fills, or expire it.

        Fills are read from the venue's view of the order (the paper engine also hands
        them over on the bar, which is why routing de-duplicates by fill id). An order
        still open after the configured number of bars is cancelled — the moment the
        signal priced has passed. If it was an *exit*, a market order follows at once:
        a missed entry costs nothing, a missed exit is an open position nobody chose.
        """
        order = await self._poll_resting()
        if order is None:
            return
        resting = self._resting
        if resting is None:  # given up as lost while polling
            return
        lot = self._lot_size(order.symbol)
        if order.filled_quantity > 0 and lot > 0 and order.remaining_quantity < lot:
            # Filled to within one lot. What is left is dust no venue can fill; the order
            # is done, not resting, and must not be counted as expired. It is still
            # cancelled, and still tracked until the venue confirms the cancel.
            if await self._cancel(order.client_order_id or order.order_id, purpose="dust residue") is None:
                return
            self._resting = None
            return

        waited = self.counters["bars"] - int(resting["placed_bar"])
        if waited < self._settings.live.entry_limit_timeout_bars:
            return

        if await self._cancel(order.client_order_id or order.order_id, purpose="entry expiry") is None:
            return  # still resting, still tracked; retried next cycle
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
            # Through the one exit path, so it is tracked as the exit in flight, sized to
            # what the expired order left unfilled, and never sent on top of another exit
            # (Phase 1.3: before, this market order bypassed the guard and was tracked by
            # nothing).
            remaining = float(order.remaining_quantity)
            if remaining > 0:
                await self._submit_exit(
                    symbol=resting["symbol"], side=resting["side"], quantity=remaining,
                    reason="resting exit expired",
                )
        elif self._open_trade is None:
            # The entry never happened; the expectation formed for it must not be scored
            # against whatever trade comes next.
            self._entry_beliefs = None

    async def _settle_funding(self, now: datetime) -> None:
        """Charge (or receive) the perpetual's funding for every eight-hour period the
        clock has entered since the last check — in every state (Phase 1.7).

        A paused or safe-moded session still holds its position and the venue still
        settles it, so this runs ahead of the cycle's decision path and places no order.
        Only in paper, only through a provider that can move cash outside a fill.

        A settlement is **pending** from the moment the clock enters its period;
        **accounted** once this pass has moved the ledger and the engine's cash and
        queued the journal write (``_funding_settled`` holds its key for the rest of the
        process); **confirmed** once that write is on disk, which the application's
        persistence counters report and the next restart reads back. The journal is the
        source of truth: a restart seeds the settled set from the rows it holds, so a
        settlement whose plan write was lost is never charged twice, and one whose row
        was lost is pending again, settled from history or recorded as unreconciled. The
        settlement and the plan that records it travel in one batched write (Phase 1.8).

        A settlement watched as it happened (the previous check was within
        ``FUNDING_PROMPT_GRACE_SECONDS``) is charged on the position as held, at the
        venue's realised rate when the monitor's history already has it and otherwise at
        the monitor's current reading — an *estimate* of that rate, labelled as such. One
        the session was not there for is settled from the realised rate and the mark
        printed then, both of which must exist, or recorded as **unreconciled** with the
        reason. Nothing is guessed, nothing is charged twice; a position no round trip
        here tracks is charged like any other and counted as unattributed (1.6).
        """
        cfg = self._settings.live
        if not cfg.charge_funding or self._execution.is_live or self._funding_rate is None:
            return
        adjust = getattr(self._execution, "apply_cash_adjustment", None)
        if not callable(adjust):
            return
        async with self._funding_lock:
            await self._settle_funding_locked(ensure_utc(now))

    async def _settle_funding_locked(self, now: datetime) -> None:
        current = funding_period_of(now)
        checked_at, self._funding_checked_at = self._funding_checked_at, now
        if self._funding_period is None:
            # A session that starts mid-period did not hold through its settlement.
            self._funding_period = current
            self.funding["period"] = funding_period_key(current)
            return
        last_index = funding_period_index(self._funding_period)
        current_index = funding_period_index(current)
        if current_index <= last_index:
            return
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            self._funding_checked_at = checked_at  # the venue was not read: not a check
            return
        position = portfolio.positions.get(self._symbol)
        holding = position is not None and not position.is_flat
        pending = [funding_period_from_index(i) for i in range(last_index + 1, current_index + 1)]
        prompt = (
            len(pending) == 1
            and checked_at is not None
            and (now - checked_at).total_seconds() <= FUNDING_PROMPT_GRACE_SECONDS
        )
        events: list[EventEnvelope[Any]] = []
        for offset, period in enumerate(pending):
            key = funding_period_key(period)
            settlement_at = funding_period_start(period)
            if key in self._funding_settled:
                continue
            if not holding:
                if self._last_fill_at is not None and self._last_fill_at > settlement_at:
                    # Flat now, but a fill since the settlement: what was held at the
                    # settlement is not known from here.
                    self._record_unreconciled(key, "position_changed")
                continue
            if prompt:
                rate, rate_source, reason = self._settlement_rate(settlement_at)
                notional = float(position.notional)
                source = "observed"
                if rate is None:
                    # No usable rate: nothing is charged and nothing is guessed. Counted
                    # in total and by reason (Phase 1.5), and the period is unreconciled.
                    self.funding["skipped_no_rate"] += 1
                    self.funding[f"skipped_{reason}"] = int(self.funding.get(f"skipped_{reason}", 0)) + 1
                    self.funding["last_skip_reason"] = reason
                    self._record_unreconciled(key, reason)
                    continue
            else:
                source, rate_source = "reconstructed", "realised"
                if len(pending) - offset > FUNDING_RECONSTRUCT_MAX_PERIODS:
                    rate, notional, reason = None, None, "too_old"
                else:
                    rate, notional, reason = await self._reconstruct_settlement(settlement_at, position)
                if rate is None or notional is None:
                    self._record_unreconciled(key, reason)
                    continue
            payment = rate * notional * (1.0 if position.quantity > 0 else -1.0)
            if not math.isfinite(payment):  # pragma: no cover - rate and notional are finite
                self.funding["skipped_no_rate"] += 1
                self.funding["skipped_invalid"] += 1
                self.funding["last_skip_reason"] = "invalid"
                self._record_unreconciled(key, "invalid")
                continue
            envelope = self._book_funding(
                key, settlement_at=settlement_at, rate=rate, notional=notional, payment=payment,
                position=position, source=source, rate_source=rate_source, now=now,
            )
            if envelope is not None:
                events.append(envelope)
        self._funding_period = current
        self.funding["period"] = funding_period_key(current)
        if self._open_trade is not None:
            plan = self._journal_plan(save=False)  # the pointer travels with the open leg's plan
            if plan is not None:
                events.append(plan)
        self._journal_events(events)

    def _settlement_rate(self, settlement_at: datetime) -> tuple[float | None, str, str]:
        """``(rate, rate_source, reason)`` for a settlement watched as it happened.

        The venue's realised rate for it when the monitor's history already holds it
        (``realised``); otherwise the monitor's current reading, which is the venue's
        running estimate of the rate and is said to be one (``estimate``). The two are
        not the same number and are never conflated in the record (Phase 1.8). ``reason``
        is the monitor's, for a reading that is no rate at all.
        """
        if self._funding_rate_at is not None:
            try:
                raw = self._funding_rate_at(settlement_at)
                realised = float(raw) if raw is not None else None
            except Exception:
                realised = None
            if realised is not None and math.isfinite(realised):
                return realised, "realised", "ok"
        rate, reason = self._funding_reading()
        return rate, "estimate", reason

    async def _reconstruct_settlement(
        self, settlement_at: datetime, position: Any
    ) -> tuple[float | None, float | None, str]:
        """``(rate, notional, reason)`` for a settlement the session did not watch.

        The rate is the venue's realised rate for that settlement, from the monitor's
        history; the notional is the position as held — which no fill since the
        settlement may contradict — at the mark the market printed then. A missing
        piece is a reason, never a substitute (Phase 1.7).
        """
        if self._last_fill_at is not None and self._last_fill_at > settlement_at:
            return None, None, "position_changed"
        if self._funding_rate_at is None:
            return None, None, "rate_unknown"
        try:
            raw = self._funding_rate_at(settlement_at)
            rate = float(raw) if raw is not None else None
        except Exception:  # a broken history is a missing history, never a halted session
            rate = None
        if rate is None or not math.isfinite(rate):
            return None, None, "rate_unknown"
        mark = await self._mark_price_at(settlement_at)
        if mark is None:
            return None, None, "mark_unknown"
        return rate, abs(float(position.quantity)) * mark, "ok"

    async def _mark_price_at(self, at: datetime) -> float | None:
        """The close of the last bar that ended at or before ``at`` — from the bars in
        hand when they span it, else from the feed's history — provided that bar ended
        within two bar lengths of ``at``. Further away it is not that moment's mark."""
        bar = self._bar_seconds()
        buffered = list(self._buffer)
        if buffered and ensure_utc(buffered[0].close_time) <= at <= ensure_utc(buffered[-1].close_time):
            candidates = [c for c in buffered if ensure_utc(c.close_time) <= at]
        else:
            try:
                fetched = await self._market_data.get_candles(self._symbol, self._timeframe, limit=3, end=at)
            except Exception:
                return None
            candidates = [c for c in (fetched or []) if ensure_utc(c.close_time) <= at]
        if not candidates:
            return None
        last = max(candidates, key=lambda c: ensure_utc(c.close_time))
        if (at - ensure_utc(last.close_time)).total_seconds() > 2.0 * bar:
            return None
        close = float(last.close)
        return close if math.isfinite(close) and close > 0 else None

    def _record_unreconciled(self, key: str, reason: str) -> None:
        """A period whose settlement could not be made: counted, listed, said."""
        entry = {"period": key, "reason": reason}
        self.funding["unreconciled_periods"] += 1
        self.funding["unreconciled"] = [*self.funding["unreconciled"], entry][-FUNDING_UNRECONCILED_LISTED:]
        self.funding["last_unreconciled_reason"] = reason
        self._incident(
            "funding_unreconciled",
            reason=f"funding for period {key} was not settled: {reason}",
            detail=entry,
        )
        self._emit("live.funding_unreconciled", entry)

    def _book_funding(
        self,
        key: str,
        *,
        settlement_at: datetime,
        rate: float,
        notional: float,
        payment: float,
        position: Any,
        source: str,
        rate_source: str,
        now: datetime,
    ) -> EventEnvelope[Any] | None:
        """One settlement into the account and the record — once; the journal event is
        returned for the caller to write together with the plan (Phase 1.8)."""
        envelope: EventEnvelope[Any] | None = None
        if payment != 0.0:
            self._ledger.record_realised_pnl(-payment, at=now)
            self._execution.apply_cash_adjustment(  # type: ignore[attr-defined]
                -payment, reason=f"funding {rate:+.6f} on {notional:.2f} ({source}, {rate_source} rate, period {key})"
            )
            envelope = self._journal_adjustment(
                -payment, f"funding {rate:+.6f} ({source}, {rate_source} rate, period {key})",
                key=f"funding:{key}", kind="funding", period=key, save=False,
            )
        self._funding_settled.add(key)
        trade = self._open_trade
        opened_at = trade.get("opened_at") if trade else None
        # A settlement watched as it happened belongs to the leg tracked at that moment;
        # one reconstructed later belongs to a leg only if the leg was provably open at
        # the settlement. Anything else is the account's, attributed to no trade (1.6).
        attributed = trade is not None and (
            source == "observed" or (opened_at is not None and ensure_utc(opened_at) <= settlement_at)
        )
        if attributed:
            trade["funding_paid"] = float(trade.get("funding_paid", 0.0)) + payment
        else:
            self.funding["unattributed_payments"] += 1
            self.funding["unattributed_usd"] = round(self.funding["unattributed_usd"] + payment, 6)
        self.funding["payments"] += 1
        if source == "reconstructed":
            self.funding["reconstructed_payments"] += 1
        self.funding[f"{rate_source}_payments"] = int(self.funding.get(f"{rate_source}_payments", 0)) + 1
        self.funding["last_rate_source"] = rate_source
        self.funding["paid_usd"] = round(self.funding["paid_usd"] + payment, 6)
        self.funding["last_rate"] = float(rate)
        self.funding["last_at"] = now.isoformat()
        self.counters["funding_payments"] += 1
        self._emit(
            "live.funding",
            {"rate": float(rate), "rate_source": rate_source, "notional": round(notional, 2),
             "paid_usd": round(payment, 4), "side": "long" if position.quantity > 0 else "short",
             "attributed": attributed, "period": key, "settlement_at": settlement_at.isoformat(),
             "source": source},
        )
        return envelope

    async def _check_liquidation(self, position: Any, unrealised_pnl: float) -> bool:
        """Liquidate the position when equity no longer covers the maintenance margin.

        The simulated account's honesty test: a leveraged position that moves against
        it far enough is closed by the venue, not by the strategy, and charged for it.
        Every position carries a stop, so this triggers only on a gap through the stop
        or a sequence of losses that has already eaten the account. Returns True when
        the position was liquidated.
        """
        cfg = self._settings.live
        if self._execution.is_live:
            return False
        notional = position.notional
        if notional <= 0:
            return False
        equity = self._ledger.snapshot(unrealised_pnl=unrealised_pnl).equity
        maintenance = notional * cfg.maintenance_margin_pct / 100.0
        if equity > maintenance:
            return False
        fee = notional * cfg.liquidation_fee_bps / 10_000.0
        now = self._clock.now()
        self.counters["liquidations"] += 1
        if fee > 0:
            self._ledger.record_realised_pnl(-fee, at=now)
            adjust = getattr(self._execution, "apply_cash_adjustment", None)
            if callable(adjust):
                adjust(-fee, reason="liquidation fee")
                self._journal_adjustment(-fee, "liquidation fee", key=f"liquidation:{self.run_id}:{self.counters['bars']}", kind="liquidation")
        self._emit(
            "live.liquidation",
            {"equity": round(equity, 2), "maintenance": round(maintenance, 2),
             "notional": round(notional, 2), "fee_usd": round(fee, 2)},
        )
        _log.warning("position_liquidated", equity=round(equity, 2), notional=round(notional, 2))
        await self._close_position("liquidated")
        if equity - fee <= 0:
            self.halt_new_orders(
                reason=(
                    f"simulated account wiped out: equity {equity - fee:,.2f} after "
                    "liquidation; reset the paper account to continue"
                )
            )
        return True

    def _liquidation_price(self) -> float | None:
        """Where the open position would be liquidated, from the current equity."""
        if self._last_position is None or self._execution.is_live:
            return None
        quantity, price = self._last_position
        if quantity == 0 or price <= 0:
            return None
        equity = self._ledger.snapshot(unrealised_pnl=self._last_unrealised).equity
        m = self._settings.live.maintenance_margin_pct / 100.0
        size = abs(quantity)
        if quantity > 0:
            level = (size * price - equity) / (size * (1.0 - m))
        else:
            level = (equity + size * price) / (size * (1.0 + m))
        return max(0.0, level)

    async def _refresh_quote(self) -> None:
        """Read the venue's top of book for this bar, if the feed offers one.

        A quote prices the costs the expected-value engine subtracts with the spread the
        market is actually showing instead of a configured constant, and lets a
        dislocated book refuse an entry the estimate never priced. A feed without quotes
        (the test fakes, a CSV replay) leaves the constant in place — said so in the
        snapshot, never silently.
        """
        if not self._feed_quotes():
            self._quote_state = "unsupported"
            return
        try:
            quote = await self._market_data.get_quote(self._symbol)
        except Exception:  # a missing quote is a missing quote, never a halted session
            self._last_quote = None
            self._quote_state = "unavailable"
            return
        if quote is None:
            self._last_quote = None
            self._quote_state = "absent"
            return
        bid = float(getattr(quote, "bid", 0.0) or 0.0)
        ask = float(getattr(quote, "ask", 0.0) or 0.0)
        if not (math.isfinite(bid) and math.isfinite(ask)) or bid <= 0 or ask < bid:
            self._last_quote = None
            self._quote_state = "invalid"
            return
        mid = (bid + ask) / 2.0
        # The quote's own time when it carries one, so a provider that keeps serving an
        # old book reads as stale here rather than as fresh because we just asked.
        stamped = getattr(quote, "timestamp", None)
        self._last_quote = {
            "bid": bid,
            "ask": ask,
            "bid_size": float(getattr(quote, "bid_size", 0.0) or 0.0),
            "ask_size": float(getattr(quote, "ask_size", 0.0) or 0.0),
            "spread_bps": (ask - bid) / mid * 10_000.0,
            "at": (stamped if stamped is not None else self._clock.now()).isoformat(),
            "seen_at": self._clock.now().isoformat(),
        }
        self._quote_state = "ok"

    def _feed_quotes(self) -> bool:
        """Whether the feed can show a book at all: it declares ``quotes`` in its
        capabilities, or it overrides the base provider's no-op ``get_quote``. A replay
        or a bar-only fake does neither, and its missing quote is a fact about the feed,
        not about the market (Phase 1.5)."""
        from tia.data.providers.base import MarketDataProvider

        provider = self._market_data
        capabilities = getattr(provider, "capabilities", None)
        if capabilities is not None and bool(getattr(capabilities, "quotes", False)):
            return True
        own = getattr(type(provider), "get_quote", None)
        return own is not None and own is not MarketDataProvider.get_quote

    def _fresh_quote(self) -> tuple[dict[str, Any] | None, str]:
        """The last quote if it can still verify the spread gate, and the state otherwise.

        Fresh means no older than ``LiveConfig.quote_max_age_seconds`` by the quote's own
        time, and no further ahead of our clock than ``QUOTE_FUTURE_TOLERANCE_SECONDS``
        (a quote from a clock slightly ahead of ours is fresh; one from the future is a
        clock problem and reads ``invalid``, Phase 1.6). Anything else is not a book, and
        is never replaced by the configured constant *as if* it were one (Phase 1.5).
        """
        quote = self._last_quote
        if quote is None:
            return None, self._quote_state
        try:
            at = datetime.fromisoformat(str(quote["at"]))
        except (KeyError, TypeError, ValueError):
            self._quote_state = "invalid"
            return None, "invalid"
        age = (self._clock.now() - at).total_seconds()
        if age < -QUOTE_FUTURE_TOLERANCE_SECONDS:
            self._quote_state = "invalid"
            return None, "invalid"
        if age > self._settings.live.quote_max_age_seconds:
            self._quote_state = "stale"
            return None, "stale"
        return quote, "ok"

    def _observed_spread_bps(self) -> float | None:
        """The spread the market is showing, when a fresh quote shows it; else None."""
        quote, _state = self._fresh_quote()
        return float(quote["spread_bps"]) if quote else None

    def _funding_reading(self) -> tuple[float | None, str]:
        """``(rate, reason)``: the funding rate the session may use, or why there is none.

        Reasons (Phase 1.5): ``ok``; ``absent`` (no monitor, or no valid reading yet);
        ``stale`` (the monitor's last valid reading is older than its ``max_age``);
        ``invalid`` (the callable returned a non-finite number). A rate is only ever a
        finite float that the monitor currently vouches for; nothing else is a rate.
        """
        if self._funding_rate is None:
            return None, "absent"
        status: dict[str, Any] | None = None
        if self._funding_status is not None:
            try:
                status = self._funding_status()
            except Exception:  # a broken status is a missing status, never a halted session
                status = None
        try:
            raw = self._funding_rate()
        except Exception:
            return None, "absent"
        if raw is None:
            state = str(status.get("state", "")) if status else ""
            return None, state if state in {"absent", "stale"} else "absent"
        try:
            rate = float(raw)
        except (TypeError, ValueError):
            return None, "invalid"
        if not math.isfinite(rate):
            return None, "invalid"
        return rate, "ok"

    def _refuse(
        self,
        stage: str,
        reason: str,
        correlation_id: str = "",
        *,
        signal: Any = None,
        regime: Any = None,
    ) -> None:
        """Count a refusal by stage, keep its reason, and announce it on the stream.

        The signal it refused travels with it — strategy, version, confidence, direction,
        regime — because a funnel that only knows *where* signals died cannot say *whose*
        signals died there, and a strategy cannot be evaluated from refusals it is not
        named in.
        """
        self.funnel[stage] = self.funnel.get(stage, 0) + 1
        attribution: dict[str, Any] = {}
        if signal is not None:
            attribution = {
                "strategy_id": getattr(signal, "strategy_id", None),
                "strategy_version": credited_strategy_version(signal),
                "contributing_strategy_ids": list(
                    getattr(signal, "contributing_strategy_ids", ()) or ()
                ),
                "confidence": getattr(signal, "confidence", None),
                "direction": getattr(getattr(signal, "direction", None), "value", None),
            }
        if regime is not None:
            regime_value = getattr(regime, "regime", regime)
            attribution["regime"] = getattr(regime_value, "value", str(regime_value))
        self.recent_refusals.appendleft(
            {
                "at": self._clock.now().isoformat(),
                "stage": stage,
                "reason": reason[:400],
                **attribution,
            }
        )
        self._emit(
            "live.no_trade",
            {"correlation_id": correlation_id, "stage": stage, "reason": reason, **attribution},
        )

    async def _refresh_trend(self) -> None:
        """Re-read the higher-timeframe context when its refresh interval has passed.

        One request an hour for a thousand hourly bars — forty days, enough for the
        four-week horizon with room. Failure leaves the previous context in place (or
        none), never a halted session: the tide is a filter on entries, not a feed the
        loop depends on.
        """
        cfg = self._settings.live
        if cfg.htf_mode == "off":
            return
        now = self._clock.now()
        if (
            self._trend_refreshed is not None
            and (now - self._trend_refreshed).total_seconds() < cfg.htf_refresh_minutes * 60
        ):
            return
        self._trend_refreshed = now
        try:
            candles = await self._market_data.get_candles(
                self._symbol, cfg.htf_timeframe, limit=1000
            )
        except Exception as exc:
            _log.warning("htf_fetch_failed", error=str(exc)[:160])
            return
        self._trend = trend_context(
            candles, timeframe=cfg.htf_timeframe, z_threshold=cfg.htf_z_threshold
        )
        self._emit("live.trend", self._trend.as_dict())

    def _track_best_price(self, candle: Candle, *, long: bool) -> None:
        extreme = candle.high if long else candle.low
        if self._best_price is None:
            self._best_price = extreme
        else:
            self._best_price = max(self._best_price, extreme) if long else min(self._best_price, extreme)

    def _tighten_stop(self, candle: Candle, *, long: bool) -> None:
        """Move the planned stop to break-even or along the trail — tighter only.

        The rules live in :mod:`tia.execution.exits`, shared with the paper engine so
        the evidence describes the game this session plays. A moved stop changes
        ``_planned_exit`` and the next :meth:`_sync_protective_stop` replaces the resting
        order; nothing here touches the venue directly.
        """
        stop = self._planned_exit.get("stop")
        if not stop or stop <= 0 or self._open_trade is None:
            return
        cfg = self._settings.live
        update = tighten_stop(
            direction=Direction.LONG if long else Direction.SHORT,
            entry_price=float(self._open_trade["price"]),
            initial_stop=float(self._planned_exit.get("initial_stop") or stop),
            current_stop=float(stop),
            best_price=self._best_price or candle.close,
            last_close=candle.close,
            atr=self._last_atr,
            breakeven_after_r=cfg.breakeven_after_r,
            trail_atr_multiple=cfg.trail_atr_multiple,
            fee_buffer_bps=self._costs.fees.round_trip_bps(entry_maker=self.entry_is_limit),
        )
        if update is None:
            return
        self._planned_exit["stop"] = update.stop_price
        self._planned_exit["kind"] = update.kind
        self.counters["stops_tightened"] += 1
        self._emit(
            "live.stop_tightened",
            {
                "stop_price": update.stop_price,
                "kind": update.kind,
                "reason": update.reason,
                "best_price": self._best_price,
            },
        )

    async def _manage_position(self, candle: Candle) -> None:
        """Every bar, for the open position: target, time stop, and exactly one stop.

        The paper engine that produces the evidence protects every position with a stop
        and closes on a reversal. A session that learned from those trades and then ran
        without stops would be applying evidence from one game to a different one —
        every loss unbounded where the estimator had seen them capped. So this mirrors
        that discipline, in the same order the engine applies it.
        """
        await self._poll_protective()
        await self._poll_pending_exit()
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            return
        position = portfolio.positions.get(self._symbol)
        holding = position is not None and not position.is_flat
        if holding and self._open_trade is None:
            # The venue holds a position this runtime is not tracking: a fill it never
            # saw, a restart that lost the leg, a stop that fired after a close. Nothing
            # is sent on it and nothing new is opened until a person reconciles.
            self._block_entries(
                "position_unverified",
                f"the venue holds {position.quantity} {self._symbol} this session is not tracking",
            )
            self.halt_new_orders(reason="untracked position at the venue")
            return
        if holding and self._open_trade is not None and (
            (position.quantity > 0) != (self._open_trade["side"] is Side.BUY)
        ):
            self._block_entries(
                "position_unverified",
                f"the venue holds {position.quantity} {self._symbol} on the opposite side of "
                "the tracked round trip",
            )
            self.halt_new_orders(reason="position side disagrees with the tracked round trip")
            return
        if holding and self._open_trade is not None:
            tracked = float(self._open_trade["quantity"]) - float(self._open_trade.get("exit_quantity", 0.0))
            lot = self._lot_size(self._symbol)
            if abs(abs(float(position.quantity)) - tracked) > max(lot, abs(tracked) * 1e-6, 1e-9):
                # Same side, different size: a fill this session never saw, or one it
                # booked that the venue did not. Nothing is sized off either number
                # until a person reconciles (Phase 1.3, G13).
                self._block_entries(
                    "position_unverified",
                    f"the venue holds {position.quantity} {self._symbol} but the tracked round "
                    f"trip says {tracked}",
                )
                self.halt_new_orders(reason="position size disagrees with the tracked round trip")
                return
        if not holding and self._open_trade is not None and self._pending_exit is None:
            # Flat at the venue while a round trip is open here and no exit is in
            # flight: the leg was closed by something this session did not see (a fill
            # the venue never reported, a manual close). The round trip cannot be scored
            # from a fill that was never read; it stays open, entries wait (G13).
            self._block_entries(
                "position_unverified",
                f"the venue is flat in {self._symbol} while a round trip of "
                f"{self._open_trade['quantity']} is tracked and no exit is in flight",
            )
            self.halt_new_orders(reason="tracked position absent at the venue")
            return
        if "position_unverified" in self._blocks and self._pending_exit is None:
            # The venue's position has just been read and agrees with the tracked leg
            # (or both are flat): the doubt that blocked entries is answered by the venue.
            self._unblock_entries("position_unverified")
        self._last_unrealised = float(portfolio.unrealized_pnl)
        self._last_position = (
            (float(position.quantity), float(position.last_price or position.average_price))
            if holding
            else None
        )

        if not holding:
            if self._protective is not None:
                await self._cancel_protective()
            return
        if self._pending_exit is not None:
            # A close is in flight: nothing else is placed on the position — not a new
            # protective stop, not a second close — until the venue says what became of
            # it. Before 1.3 a bar on which the target was no longer touched fell through
            # to the stop sync and re-placed a stop over the working close. An exit
            # trigger that fires meanwhile is counted as skipped, as it always was.
            long = position.quantity > 0
            target = self._planned_exit.get("target")
            max_bars = self._settings.live.max_holding_bars
            if (
                target and target > 0 and (candle.high >= target if long else candle.low <= target)
            ) or (
                max_bars > 0 and self._position_opened_bar is not None
                and self.counters["bars"] - self._position_opened_bar >= max_bars
            ):
                self.counters["exits_skipped_pending"] += 1
            return
        if not self.machine.state.accepts_reducing_orders:
            return

        if await self._check_liquidation(position, portfolio.unrealized_pnl):
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

        self._track_best_price(candle, long=long)
        self._tighten_stop(candle, long=long)
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
            if order is None:
                if self._protective is not None and self._protective.get("order_id"):
                    # The venue could not say what became of the stop. It may still
                    # rest; a second one is not placed on top of it (Phase 1.3, G3).
                    return
                # Terminal, or given up as lost: fall through and place a fresh one.
            else:
                covered = order.quantity - order.filled_quantity
                same_size = abs(covered - quantity) <= max(quantity * 1e-6, 1e-9)
                same_level = abs(float(existing.get("stop_price") or 0.0) - float(stop_price)) <= 1e-9
                if same_size and same_level:
                    return
                if not await self._cancel_protective():
                    # The venue did not confirm the cancel: the old stop stays tracked and
                    # no replacement is sent — two resting stops on one position is the
                    # position the other way once both fire (Phase 1.3, G1).
                    return

        side = Side.SELL if position_quantity > 0 else Side.BUY
        intent = OrderIntent(
            intent_id=deterministic_id("int", "stop", self._symbol, quantity, self._clock.now()),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"protective:{self._symbol}:{self.run_id}:{self.counters['bars']}",
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
        if order.fills:  # a stop already through its level fills at once
            self._save("order", {"run_id": self.run_id, "order": order})
        for fill in order.fills:
            self._on_fill(fill)
        self._record_order(order)
        self._save("order", {"run_id": self.run_id, "order": order})
        self._emit(
            "live.stop_placed",
            {"stop_price": float(stop_price), "quantity": quantity, "side": side.value},
        )

    async def _read_tracked_order(self, record: dict[str, Any]) -> tuple[Order | None, str]:
        """The venue's view of a tracked order, by either of its ids.

        Returns ``(order, "found")``, ``(None, "unknown")`` when the venue answered and
        knows neither id, or ``(None, "error")`` when a read raised. The two ``None``
        cases are different facts: an order the venue cannot be asked about may still be
        resting, and before 1.3 every poller treated it as gone — a transient outage
        then dropped the protective stop's record and a fresh stop was placed on top of
        the one still resting.
        """
        raised = False
        for key in (record.get("order_id"), record.get("client_order_id")):
            if not key:
                continue
            try:
                order = await self._execution.get_order(key)
            except Exception as exc:
                raised = True
                _log.warning("order_read_failed", order=key, error=str(exc)[:200])
                continue
            if order is not None:
                return order, "found"
        if raised:
            self.counters["order_poll_failures"] += 1
            return None, "error"
        return None, "unknown"

    def _count_unknown(self, record: dict[str, Any], *, what: str) -> bool:
        """Count one poll the venue answered "unknown" to. True once the order is to be
        given up as lost: UNKNOWN_POLLS_BEFORE_LOST consecutive such answers, said in an
        incident. Until then the record stays and entries are blocked."""
        record["unknown_polls"] = int(record.get("unknown_polls", 0)) + 1
        ref = record.get("client_order_id") or record.get("order_id")
        if record["unknown_polls"] < UNKNOWN_POLLS_BEFORE_LOST:
            self._block_entries(
                "orders_unverified",
                f"{what} {ref} is unknown to the venue "
                f"({record['unknown_polls']}/{UNKNOWN_POLLS_BEFORE_LOST})",
            )
            return False
        self.counters["orders_lost"] += 1
        self._incident(
            f"{what.replace(' ', '_')}_lost",
            reason=(
                f"{what} {ref} was unknown to the venue on {record['unknown_polls']} "
                "consecutive polls; its record is dropped and entries stay blocked until "
                "a cancel is confirmed"
            ),
        )
        return True

    async def _poll_protective(self) -> Order | None:
        """Read the venue's view of the protective stop and route any fills it produced.

        Returns the order while it is still working; clears the record and returns
        ``None`` once it is terminal. Returns ``None`` *without* clearing the record when
        the venue could not be read, or said it does not know the order for fewer than
        UNKNOWN_POLLS_BEFORE_LOST polls — the caller then places nothing on top of it.
        Called before any decision about the position, because the position going flat
        is the *consequence* of the stop filling, and the fill must be scored — it is
        the round trip's end.
        """
        existing = self._protective
        if not existing or not existing.get("order_id"):
            return None
        order, outcome = await self._read_tracked_order(existing)
        if order is None:
            if outcome == "unknown" and self._count_unknown(existing, what="protective stop"):
                self._protective = None
            return None
        existing.pop("unknown_polls", None)
        for fill in order.fills:
            self._on_fill(fill)
        self._save_order_if_changed(existing, order)
        if order.state.is_terminal:
            self._protective = None
            return None
        return order

    async def _cancel(self, order_ref: str, *, purpose: str) -> Order | None:
        """Cancel at the venue and believe only the venue's answer.

        Returns the order in its terminal state, or ``None`` when the venue refused,
        raised, or answered with an order that is still working. A failed cancel is
        never swallowed into "cancelled": it is recorded as an incident, new entries are
        blocked until a cancel succeeds, and the caller keeps tracking the order.
        """
        try:
            order = await self._execution.cancel_order(order_ref)
        except Exception as exc:
            self.counters["cancel_failures"] += 1
            self._block_entries(
                "orders_unverified",
                f"cancel failed ({purpose}) for {order_ref}: {str(exc)[:200]}",
            )
            self.halt_new_orders(reason=f"cancel failed ({purpose}); orders unverified")
            return None
        if not order.state.is_terminal:
            self.counters["cancel_failures"] += 1
            self._block_entries(
                "orders_unverified",
                f"venue did not cancel {order_ref} ({purpose}): state {order.state.value}",
            )
            self.halt_new_orders(reason=f"cancel not confirmed ({purpose}); orders unverified")
            return None
        self._unblock_entries("orders_unverified")
        if order.fills:
            # Terminal because it *filled* before the cancel reached the venue (a stop
            # through its level, an entry taken on the touch): what it did to the
            # position is booked here, before the caller acts on "cancelled" (Phase 1.3,
            # G4). Routing de-duplicates by fill id.
            self._save("order", {"run_id": self.run_id, "order": order})
            for fill in order.fills:
                self._on_fill(fill)
        self._record_order(order)
        self._save("order", {"run_id": self.run_id, "order": order})
        return order

    async def _cancel_protective(self) -> bool:
        """Cancel the protective stop. False — and the stop stays tracked — when the
        venue did not confirm; a stop believed cancelled while still resting is how a
        closed position comes back the other way."""
        existing = self._protective
        if not existing or not existing.get("order_id"):
            self._protective = None
            return True
        cancelled = await self._cancel(
            existing["client_order_id"] or existing["order_id"], purpose="protective stop"
        )
        if cancelled is None:
            return False
        self._protective = None
        return True

    async def _poll_pending_exit(self) -> None:
        """Read the venue's view of the exit in flight and route what it produced.

        Clears the record only on a terminal state the venue reports. A cancelled or
        expired exit that left quantity unfilled is said out loud: the position is still
        there and the next exit trigger may try again, once.
        """
        pending = self._pending_exit
        if pending is None:
            return
        order, outcome = await self._read_tracked_order(pending)
        if order is None:
            if outcome == "error":
                # The venue could not be asked. The exit may have filled; it stays
                # pending and nothing is sent on top of it until the venue answers.
                return
            # The venue answered and knows neither id: the exit's fate cannot be read.
            # Nothing else is sent on top of it and entries wait. Said so for
            # UNKNOWN_POLLS_BEFORE_LOST polls; then the exit is given up as never
            # accepted, so the next exit trigger may close the position that is still
            # there — before 1.3 the record stayed forever and no exit could ever be
            # sent again (Phase 1.3, G3). Entries stay blocked until the venue's
            # position is read and agrees with the tracked leg.
            pending["unknown_polls"] = int(pending.get("unknown_polls", 0)) + 1
            self._block_entries(
                "position_unverified",
                f"exit {pending['client_order_id']} is unknown to the venue "
                f"({pending['unknown_polls']}/{UNKNOWN_POLLS_BEFORE_LOST})",
            )
            if pending["unknown_polls"] >= UNKNOWN_POLLS_BEFORE_LOST:
                self.counters["orders_lost"] += 1
                self._pending_exit = None
                self._incident(
                    "exit_lost",
                    reason=(
                        f"exit ({pending['reason']}) {pending['client_order_id']} was unknown "
                        f"to the venue on {pending['unknown_polls']} consecutive polls; it is "
                        "treated as never accepted — the position remains and the next exit "
                        "trigger may close it; entries wait for the venue's position to agree"
                    ),
                )
            return
        pending.pop("unknown_polls", None)
        for fill in order.fills:
            self._on_fill(fill)
        if not order.state.is_terminal:
            return
        self._record_order(order)
        self._save("order", {"run_id": self.run_id, "order": order})
        self._pending_exit = None
        if order.remaining_quantity > 0 and order.state is not OrderState.FILLED:
            self.counters["exits_unfilled"] += 1
            self._incident(
                "exit_unfilled",
                reason=(
                    f"exit ({pending['reason']}) ended {order.state.value} with "
                    f"{order.remaining_quantity} unfilled; the position remains and will be "
                    "closed again by the next exit trigger"
                ),
            )

    async def _submit_exit(self, *, symbol: str, side: Side, quantity: float, reason: str) -> Order | None:
        """The one path every exit goes through: at most one exit in flight per position.

        Under the lock: a second caller in the same cycle (deadline and a time stop, two
        callbacks racing) finds the first's order pending and sends nothing. The order's
        result is believed only as the venue reports it; an unknown result blocks entries
        until a reconciliation says what the venue holds.
        """
        async with self._exit_lock:
            await self._poll_pending_exit()
            if self._pending_exit is not None:
                self.counters["exits_skipped_pending"] += 1
                _log.info(
                    "exit_skipped_pending", reason=reason,
                    pending=self._pending_exit["reason"],
                )
                return None
            self._exit_reason = reason
            slug = reason.replace(" ", "-")
            try:
                intent = self._build_intent(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    # The bar counter restarts with every session; the run id makes the
                    # client id unique across restarts (Phase 1.3, G6) — the same bar
                    # count and size in a later session would otherwise re-key the
                    # earlier session's order row and be a duplicate at a real venue.
                    signal_id=f"exit:{slug}:{self.run_id}:{self.counters['bars']}",
                    reduce_only=True,
                    order_type=OrderType.MARKET,
                )
            except OrderFilterError as exc:
                self._incident("exit_refused_by_filters", reason=f"{reason}: {exc}"[:500])
                self.halt_new_orders(reason=f"exit refused by filters ({reason})")
                return None
            try:
                order = await self._execution.submit_order(intent)
            except ReconciliationError:
                self.counters["unknown_order_states"] += 1
                try:
                    resolved = await self._resolve_unknown(intent)
                except ReconciliationError as exc:
                    # The venue cannot say whether the exit exists. Nothing more is
                    # sent on a position whose orders are unknown; entries wait until
                    # the venue's view of the position is read and agrees.
                    self._block_entries(
                        "position_unverified",
                        f"exit ({reason}) timed out and cannot be resolved: {str(exc)[:200]}",
                    )
                    self.halt_new_orders(reason="exit result unknown; manual reconciliation required")
                    return None
                if resolved is None:
                    # The venue confirms it never arrived: nothing is in flight.
                    self._incident(
                        "exit_not_accepted", reason=f"{reason}: submission timed out; venue confirms absent",
                    )
                    return None
                order = resolved
            except Exception as exc:
                _log.warning("close_position_failed", reason=reason, error=str(exc)[:200])
                self._incident("exit_submit_failed", reason=f"{reason}: {str(exc)[:300]}")
                return None
            self.counters["orders"] += 1
            key = {
                "target reached": "exits_target",
                "time stop": "exits_time",
                "signal reversed": "exits_reversal",
                "liquidated": "exits_liquidation",
                "session deadline": "exits_deadline",
                "emergency flatten": "exits_flatten",
            }.get(reason)
            if key:
                self.counters[key] += 1
            if not order.state.is_terminal or order.fills:
                self._pending_exit = {
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "reason": reason,
                    "bar": self.counters["bars"],
                    "at": self._clock.now().isoformat(),
                }
            if order.fills:
                self._save("order", {"run_id": self.run_id, "order": order})
            for fill in order.fills:
                self._on_fill(fill)
            self._record_order(order)
            self._save("order", {"run_id": self.run_id, "order": order})
            if order.state.is_terminal:
                self._pending_exit = None
                if not order.fills:
                    self.counters["exits_rejected"] += 1
                    self._incident(
                        "exit_rejected",
                        reason=f"{reason}: {order.reject_reason or order.state.value}; the position "
                        "remains and keeps its protection",
                    )
            self._emit(
                "live.exit",
                {"reason": reason, "side": side.value, "quantity": quantity,
                 "state": order.state.value},
            )
            return order

    async def _close_position(self, reason: str) -> bool:
        """Close the open position with a reduce-only market order, stop cancelled first.

        Market on purpose: a close is the one order whose fill matters more than its
        price. The reason travels with the round trip into the record. Returns whether
        an exit was sent; nothing is sent while another exit is in flight, and nothing
        is sent while the protective stop could not be confirmed cancelled — a market
        close on top of a live stop is the same double fill by another route.
        """
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            return False
        position = portfolio.positions.get(self._symbol)
        if position is None or position.is_flat:
            return False
        await self._poll_pending_exit()
        if self._pending_exit is not None:
            self.counters["exits_skipped_pending"] += 1
            return False
        if self._resting is not None:
            cancelled = await self._cancel(
                self._resting["client_order_id"] or self._resting["order_id"], purpose="close"
            )
            if cancelled is None:
                return False
            self._resting = None
        if not await self._cancel_protective():
            return False
        # The cancels may have found the stop (or the resting entry) already filled, and
        # those fills are booked by now: the position is read again, and the close is
        # sized to what is held *after* them. A close sized to the earlier read would be
        # the position the other way when the stop had just closed it (Phase 1.3, G4).
        try:
            portfolio = await self._execution.get_portfolio()
        except Exception:
            return False
        position = portfolio.positions.get(self._symbol)
        if position is None or position.is_flat:
            return False

        quantity = abs(position.quantity)
        side = Side.SELL if position.quantity > 0 else Side.BUY
        order = await self._submit_exit(symbol=self._symbol, side=side, quantity=quantity, reason=reason)
        return order is not None

    async def _resolve_unknown(self, intent: OrderIntent) -> Order | None:
        resolver = getattr(self._execution, "resolve_unknown_order", None)
        if resolver is None:
            raise ReconciliationError(
                "submission timed out and this provider cannot resolve unknown orders; "
                "manual reconciliation required before trading resumes",
                client_order_id=intent.client_order_id,
            )
        return await resolver(symbol=intent.symbol, client_order_id=intent.client_order_id)

    def _record_order(self, order: Order) -> None:
        self.recent_orders.appendleft(
            {
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "state": order.state.value,
                "filled_quantity": order.filled_quantity,
                "average_fill_price": order.average_fill_price,
                "fees_paid": order.fees_paid,
                "reject_reason": order.reject_reason or "",
                "signal_id": order.signal_id,
                "correlation_id": order.correlation_id,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat(),
            }
        )
        self._emit("order.state_changed", self.recent_orders[0])

    def _on_fill(self, fill: Fill) -> None:
        if fill.fill_id in self._seen_fills:
            return
        self._seen_fills.add(fill.fill_id)
        self._last_fill_at = ensure_utc(fill.filled_at)
        self.recent_fills.appendleft(
            {
                "fill_id": fill.fill_id,
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "fee": fill.fee,
                "slippage_bps": fill.slippage_bps,
                "liquidity": fill.liquidity,
                "filled_at": fill.filled_at.isoformat(),
            }
        )
        self._emit("order.fill_simulated", self.recent_fills[0])
        if self._protective is not None and fill.order_id == self._protective["order_id"]:
            kind = self._planned_exit.get("kind", "protective")
            self._exit_reason = {
                "break-even": "break-even stop",
                "trailing": "trailing stop",
            }.get(kind, "protective stop")
            self.counters["exits_stop"] += 1
            if kind == "break-even":
                self.counters["exits_breakeven"] += 1
            elif kind == "trailing":
                self.counters["exits_trail"] += 1
        self.counters["fills"] += 1
        if fill.liquidity == "maker":
            self.counters["maker_fills"] += 1
        self._ledger.record_fee(fill.fee, at=fill.filled_at)
        self._save("fill", {"run_id": self.run_id, "fill": fill})
        self._journal_fill(fill)
        self._track_round_trip(fill)

    def _track_round_trip(self, fill: Fill) -> None:
        if self._open_trade is None:
            self.counters["entries_filled"] += 1
            # The risk engine's frequency limits and cooldown count executions, not
            # intentions. Told here — once per round trip opened — so a session cannot
            # re-enter a bar after a stop-out while the configured cooldown says wait.
            self._risk.record_execution(fill.symbol, fill.filled_at)
            self._exit_reason = None
            self._position_opened_bar = self.counters["bars"]
            self._best_price = fill.price
            self._open_trade = {
                "price": fill.price,
                "quantity": fill.quantity,
                "side": fill.side,
                "fee": fill.fee,
                "exit_value": 0.0,
                "exit_quantity": 0.0,
                "exit_fees": 0.0,
                "funding_paid": 0.0,
                "opened_at": ensure_utc(fill.filled_at),
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
        self._best_price = None
        if trade is None or beliefs is None or trade["exit_quantity"] <= 0:
            return

        self.counters["round_trips"] += 1
        entry_price = trade["price"]
        exit_price = trade["exit_value"] / trade["exit_quantity"]
        long_side = trade["side"] is Side.BUY
        raw = (exit_price - entry_price) / entry_price * 10_000.0
        gross_bps = raw if long_side else -raw
        notional = trade["quantity"] * entry_price
        fees_bps = (
            (trade["fee"] + trade["exit_fees"]) / notional * 10_000.0 if notional > 0 else 0.0
        )
        # The carry this round trip paid (negative: received) while it was open, in bps
        # of its entry notional (Phase 1.5). It is already in the account — the accrual
        # booked each settlement — so the ledger below is booked *before* carry and the
        # reported net is *after* it: counted once in each place, never twice.
        funding_paid = float(trade.get("funding_paid", 0.0))
        funding_bps = funding_paid / notional * 10_000.0 if notional > 0 else 0.0
        net_before_carry_bps = gross_bps - fees_bps
        net_bps = net_before_carry_bps - funding_bps

        self._edges.record(
            Outcome(
                regime=beliefs["regime"],
                direction=beliefs["direction"],
                confidence=beliefs["confidence"],
                net_return_bps=net_bps,
                fees_bps=fees_bps,
                gross_return_bps=gross_bps,
                market_data="real",
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
        # This session's own round trips close against the venue's prices — real market
        # data whichever execution provider filled them — so they count under every
        # scoreboard policy.
        self._scoreboard.record(
            str(beliefs.get("strategy_id") or ""), net_bps,
            exploratory=bool(beliefs.get("exploratory")),
            market_data="real",
        )
        self._consecutive_losses = 0 if net_bps > 0 else self._consecutive_losses + 1
        self._ledger.record_realised_pnl(
            notional * net_before_carry_bps / 10_000.0, at=exit_fill.filled_at
        )
        self._emit(
            "trade.closed",
            {
                "symbol": self._symbol,
                "signal_id": beliefs["signal_id"],
                "regime": beliefs["regime"].value,
                "direction": beliefs["direction"].value,
                "confidence": beliefs["confidence"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": trade["quantity"],
                "notional_usd": round(notional, 2),
                "gross_bps": round(gross_bps, 4),
                "fees_bps": round(fees_bps, 4),
                "funding_bps": round(funding_bps, 4),
                "net_bps": round(net_bps, 4),
                "net_usd": round(notional * net_bps / 10_000.0, 2),
                "expected_net_bps": beliefs["expected_net_bps"],
                "carry_unpriced": beliefs.get("carry_unpriced"),
                "exploratory": bool(beliefs.get("exploratory")),
                "exit_reason": self._exit_reason or "signal reversed",
                "strategy_id": beliefs.get("strategy_id"),
                "size_fraction": beliefs.get("size_fraction"),
                "closed_at": exit_fill.filled_at.isoformat(),
                "source": "live",
            },
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
                # Net of fees *and* of the funding paid while open (Phase 1.5); the row
                # has no carry column, so ``gross - fees - net`` recovers it.
                "net_bps": net_bps,
                "expected_net_bps": beliefs["expected_net_bps"],
                "exploratory": bool(beliefs.get("exploratory")),
                "exit_reason": self._exit_reason or "signal reversed",
                "strategy_id": beliefs.get("strategy_id"),
                "strategy_version": beliefs.get("strategy_version"),
                "closed_at": exit_fill.filled_at,
                "source": "live",
                # Real market data either way; the fills are simulated unless the
                # execution provider is the armed live one. Paper-live is therefore
                # real + simulated, and only a live session ever writes real + real.
                "market_data": "real",
                "execution_mode": "real" if self._execution.is_live else "simulated",
            },
        )

    # ------------------------------------------------------------------ reconciliation

    async def _reconcile(self) -> None:
        """Our books against the venue's. The venue wins every disagreement.

        Three comparisons — orders (the venue's book against the provider's mirror and
        against this session's own records), positions (the venue's position against the
        round trip this session tracks; F16) and balance — and the balance one goes
        through the capital ledger's classifier, so a deposit is never booked as profit
        and an unexplained movement halts entries rather than being absorbed. An order
        divergence puts the session in SAFE_MODE; a position divergence is recorded and
        counted (the position path in :meth:`_manage_position` blocks entries on it).
        """
        self.counters["reconciliations"] += 1
        divergences: list[str] = []
        try:
            venue_orders = await self._execution.get_orders(open_only=True)
            venue_open = {order.client_order_id for order in venue_orders}
            local_open = {
                order.client_order_id
                for order in await self._execution.get_orders(open_only=False)
                if not order.state.is_terminal
            }
            for missing in local_open - venue_open:
                divergences.append(f"order {missing} open locally but not at the venue")
            for extra in venue_open - local_open:
                divergences.append(f"order {extra} open at the venue but unknown locally")
            # The venue's book against *this session's* records, not the provider's own
            # mirror of itself (which agrees with it by construction): an order resting
            # in this symbol that no record here names is an order nothing manages — an
            # earlier session's, a stop believed cancelled, a hand-placed one (Phase 1.3,
            # G8).
            tracked = {
                record[key]
                for record in (self._protective, self._resting, self._pending_exit)
                if record
                for key in ("order_id", "client_order_id")
                if record.get(key)
            }
            for order in venue_orders:
                if order.symbol != self._symbol or order.state.is_terminal:
                    continue
                if order.order_id in tracked or order.client_order_id in tracked:
                    continue
                divergences.append(
                    f"order {order.client_order_id} ({order.order_type.value} {order.side.value} "
                    f"{order.quantity}) is open at the venue but not tracked by this session"
                )
            # The venue's position against the round trip this session tracks (F16).
            held = (await self._execution.get_positions()).get(self._symbol)
            held_quantity = float(held.quantity) if held is not None else 0.0
            tracked = self._open_trade
            if abs(held_quantity) > 1e-12 and tracked is None:
                divergences.append(
                    f"position {held_quantity} {self._symbol} at the venue but no round trip is tracked"
                )
            elif (
                abs(held_quantity) <= 1e-12 and tracked is not None
                and self._pending_exit is None and self._resting is None
            ):
                divergences.append(
                    f"a round trip of {tracked['quantity']} {self._symbol} is tracked but the venue is flat"
                )
            elif abs(held_quantity) > 1e-12 and tracked is not None and (
                (held_quantity > 0) != (tracked["side"] is Side.BUY)
            ):
                divergences.append(
                    f"position {held_quantity} {self._symbol} at the venue is on the opposite side "
                    "of the tracked round trip"
                )

            if self._execution.is_live or self._activation is not None:
                # An account someone can deposit into: the venue's cash is classified.
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
            else:
                # Paper-realtime. A simulated venue receives no deposits and makes no withdrawals, and
                # a leveraged position leaves its cash negative by design — classifying
                # that cash as a movement would halt the session on its own fills. What
                # can go wrong in a simulator is the two sets of books drifting apart,
                # so the check is that our equity and the venue's agree.
                portfolio = await self._execution.get_portfolio()
                expected = self._ledger.snapshot(unrealised_pnl=portfolio.unrealized_pnl).equity
                observed = float(portfolio.equity)
                tolerance = max(1.0, abs(expected) * 0.02)
                if abs(observed - expected) > tolerance:
                    divergences.append(
                        f"simulated account equity {observed:,.2f} differs from the ledger's "
                        f"{expected:,.2f} by more than {tolerance:,.2f}"
                    )
        except Exception as exc:
            divergences.append(f"reconciliation itself failed: {exc}")

        clean = not divergences
        self._last_reconciliation_clean = clean
        if not clean:
            self.counters["reconciliation_breaks"] += 1
            if any(
                "unknown locally" in d or "not at the venue" in d or "not tracked" in d
                for d in divergences
            ):
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
                task = asyncio.ensure_future(self._sequenced(result))
                self._persist_tasks.add(task)
                task.add_done_callback(self._persist_tasks.discard)
                task.add_done_callback(_swallow)
        except Exception as exc:  # persistence must never stop the loop
            _log.warning("live_persist_failed", kind=kind, error=str(exc)[:200])

    async def _sequenced(self, write: Any) -> None:
        """Run persistence writes one at a time, in the order they were scheduled.

        A fill row references its order row. Two writes scheduled back to back on
        separate sessions can interleave at the database, and the fill then arrives
        before the order it belongs to and is refused by the foreign key — a fill the
        record never sees, which is a round trip the next restart cannot rebuild. The
        lock keeps the schedule order the write order.
        """
        async with self._persist_lock:
            await write

    async def flush_persistence(self, *, timeout_seconds: float = 10.0) -> bool:
        """Wait for the persistence writes scheduled so far to finish.

        Returns ``True`` when every write landed (or failed, which is logged) within
        ``timeout_seconds``; ``False`` when some were still in flight. A session that
        stops waits here so the fills, the account events and the stop stamp are on
        disk before the process that wrote them goes away. Writes scheduled while
        waiting (a stop stamp after the last fill) are waited for too.
        """
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while self._persist_tasks:
            pending = [t for t in self._persist_tasks if not t.done()]
            if not pending:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.wait(pending, timeout=remaining)
        return True

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Push one event to the API's broadcast. ``data`` is the key the SSE endpoint
        serialises; an earlier version used ``payload`` and every live event reached the
        browser as an empty object — the pages polled instead and nobody noticed."""
        with contextlib.suppress(Exception):
            self._on_event({"type": event_type, "data": payload})

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

    #: Binance spot order rate limits, from exchangeInfo's rateLimits (documented):
    #: 100 orders per 10 seconds and 200,000 per day, per account.
    ORDER_LIMIT_PER_10S = 100
    ORDER_LIMIT_PER_DAY = 200_000

    def spread_check(self, *, size_btc: float = 0.01) -> dict[str, Any]:
        """Price the spread-capture idea against the book and the rules as they are.

        The idea: rest a bid and an ask around the price and earn the gap between
        them, many times a second. Three facts decide it, and all three are measured
        or documented rather than assumed: the spread the book is actually showing, the
        maker fee paid on both legs, and how many orders the venue accepts per second.
        The fourth — being first in the queue when someone crosses — is not something
        a server on the public internet gets to have, and the verdict says so.
        """
        quote = self._last_quote
        last = self._buffer[-1] if self._buffer else None
        if quote is None or last is None:
            return {"available": False, "reason": "no live quote yet"}
        bid, ask = float(quote["bid"]), float(quote["ask"])
        mid = (bid + ask) / 2.0
        spread_usd = ask - bid
        size = max(0.0, float(size_btc))
        notional = size * mid
        fees = self._costs.fees
        maker_round_trip_bps = fees.round_trip_bps(entry_maker=True, exit_maker=True)
        gross = spread_usd * size
        fee_usd = notional * maker_round_trip_bps / 10_000.0
        net = gross - fee_usd
        market_btc_per_s = float(last.volume) / 60.0
        orders_per_s = self.ORDER_LIMIT_PER_10S / 10.0
        max_round_trips_per_s = orders_per_s / 2.0
        share_at_100 = (100.0 * size / market_btc_per_s) if market_btc_per_s > 0 else None
        breakeven_spread_usd = mid * maker_round_trip_bps / 10_000.0

        if net <= 0:
            verdict = (
                f"At the book's spread of ${spread_usd:.2f} a round trip on {size:g} BTC "
                f"earns ${gross:.4f} and pays ${fee_usd:.4f} in maker fees: "
                f"${net:+.4f} per round trip. The spread would have to exceed "
                f"${breakeven_spread_usd:.2f} just to cover the fees, before the trade "
                "that fills you is the one running you over."
            )
        else:
            verdict = (
                f"At the book's spread of ${spread_usd:.2f} a round trip on {size:g} BTC "
                f"nets ${net:+.4f} after maker fees — when both legs fill, which needs a "
                "buyer and a seller to cross into you while you are at the front of the "
                "queue. The venue accepts about "
                f"{orders_per_s:.0f} orders a second, so at most {max_round_trips_per_s:.0f} "
                "round trips a second, not a hundred; and the market itself trades about "
                f"{market_btc_per_s:.3f} BTC a second right now, so a hundred fills a "
                "second at this size would need to be the other side of "
                f"{(share_at_100 or 0) * 100:.0f}% of everything traded."
            )
        return {
            "available": True,
            "as_of": self._clock.now().isoformat(),
            "bid": bid,
            "ask": ask,
            "mid": round(mid, 2),
            "spread_usd": round(spread_usd, 4),
            "spread_bps": round(float(quote["spread_bps"]), 4),
            "bid_size": float(quote["bid_size"]),
            "ask_size": float(quote["ask_size"]),
            "size_btc": size,
            "notional_usd": round(notional, 2),
            "maker_fee_bps_per_leg": fees.maker_bps,
            "gross_per_round_trip_usd": round(gross, 6),
            "fees_per_round_trip_usd": round(fee_usd, 6),
            "net_per_round_trip_usd": round(net, 6),
            "breakeven_spread_usd": round(breakeven_spread_usd, 4),
            "order_limit_per_10s": self.ORDER_LIMIT_PER_10S,
            "order_limit_per_day": self.ORDER_LIMIT_PER_DAY,
            "max_round_trips_per_s": max_round_trips_per_s,
            "market_btc_per_s": round(market_btc_per_s, 4),
            "market_usd_per_s": round(market_btc_per_s * mid, 2),
            "share_of_market_at_100_per_s": (
                round(share_at_100, 4) if share_at_100 is not None else None
            ),
            "verdict": verdict,
            "caveats": [
                "Both legs fill only when someone crosses the spread into you, and only "
                "after everyone ahead of you in the queue at that price.",
                "The order that fills you is, more often than not, the one that knows "
                "where the price is going next (adverse selection).",
                "Fees are the retail maker tier; a firm doing this pays a fraction of "
                "them and sits in the venue's data centre.",
                "This is a calculation on the live book, not a simulation: the paper "
                "engine cannot model a queue and would overstate fills.",
            ],
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
        ledger = self._ledger.snapshot(unrealised_pnl=self._last_unrealised)
        gross = (
            abs(self._last_position[0]) * self._last_position[1] if self._last_position else 0.0
        )
        equity = ledger.equity
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
                "entry_price": self._open_trade["price"] if self._open_trade else None,
                "stop_price": self._planned_exit.get("stop"),
                "initial_stop": self._planned_exit.get("initial_stop"),
                "stop_kind": self._planned_exit.get("kind"),
                "target_price": self._planned_exit.get("target"),
                "best_price": self._best_price,
                "r_multiple": (
                    round(
                        r_multiple(
                            direction=self._planned_exit["direction"],
                            entry_price=float(self._open_trade["price"]),
                            initial_stop=float(self._planned_exit.get("initial_stop") or 0.0),
                            price=self._best_price or float(self._open_trade["price"]),
                        ),
                        2,
                    )
                    if self._open_trade and self._planned_exit.get("direction") is not None
                    else None
                ),
                "protected": bool(self._protective and self._protective.get("order_id")),
                "opened_bar": self._position_opened_bar,
                "max_holding_bars": self._settings.live.max_holding_bars,
            },
            "exits": {
                "breakeven_after_r": self._settings.live.breakeven_after_r,
                "trail_atr_multiple": self._settings.live.trail_atr_multiple,
                "last_atr": round(self._last_atr, 4),
            },
            "market": {
                "quote": self._last_quote,
                "quote_state": self._fresh_quote()[1],
                "max_spread_bps": self._settings.live.max_spread_bps,
                "quote_max_age_seconds": self._settings.live.quote_max_age_seconds,
                "spread_source": (
                    "venue top of book" if self._fresh_quote()[0] else "configured constant"
                ),
            },
            "sizing": {
                "conviction": self._settings.live.conviction_sizing,
                "min_fraction": self._settings.live.min_size_fraction,
                "exploration_fraction": self._settings.live.exploration_size_fraction,
                "pooled_cap": self._settings.live.pooled_size_cap,
                "last": self._last_size,
            },
            "strategies": self._scoreboard.report(),
            "scoreboard_policy": self._scoreboard.policy,
            "evidence_policy": self._evidence_policy,
            "evidence_excluded": self._evidence_excluded,
            "risk_state": self.risk_state_report(),
            "session": self.session_report(),
            "entry_blocks": dict(self._blocks),
            "account_state": self.account_state_report(),
            "pending_exit": (
                {k: (v.value if hasattr(v, "value") else v) for k, v in self._pending_exit.items()}
                if self._pending_exit else None
            ),
            "feed": (
                self._market_data.feed_state()
                if callable(getattr(self._market_data, "feed_state", None))
                else {"transport": "rest", "poll_seconds": self._poll_interval}
            ),
            "funnel": {
                "stages": dict(self.funnel),
                "risk_reasons": dict(
                    sorted(self._risk_reasons.items(), key=lambda kv: -kv[1])[:8]
                ),
                "recent_refusals": list(self.recent_refusals)[:20],
                "exploration": {
                    "enabled": self.exploration_enabled,
                    "per_day": self._settings.live.exploration_trades_per_day,
                    "used_today": self._exploration_used,
                },
                "trades_today": self._trades_today,
                "trades_per_day_cap": self._budget.profile.max_trades_per_day,
                "risk_profile": self._settings.live.risk_profile,
            },
            "account": {
                "simulated": not self._execution.is_live,
                "starting_capital": (
                    self._settings.live.max_live_capital
                    if self._execution.is_live
                    else self._settings.live.paper_capital
                ),
                "prior_realised_pnl": round(self._prior_realised, 2),
                "equity": round(equity, 2),
                "return_pct": (
                    round((equity / self._settings.live.paper_capital - 1.0) * 100.0, 4)
                    if not self._execution.is_live and self._settings.live.paper_capital > 0
                    else None
                ),
                "leverage_max": self._leverage,
                "leverage_used": round(gross / equity, 3) if equity > 0 else None,
                "margin_used_pct": (
                    round(gross / (equity * self._leverage) * 100.0, 2) if equity > 0 else None
                ),
                "maintenance_margin_pct": self._settings.live.maintenance_margin_pct,
                "liquidation_fee_bps": self._settings.live.liquidation_fee_bps,
                "liquidation_price": (
                    round(self._liquidation_price(), 2)
                    if self._liquidation_price() is not None
                    else None
                ),
                "liquidations": self.counters["liquidations"],
                "funding": dict(self.funding),
                "charge_funding": self._settings.live.charge_funding,
            },
            "trend": {
                "mode": self._settings.live.htf_mode,
                "z_threshold": self._settings.live.htf_z_threshold,
                "refreshed_at": (
                    self._trend_refreshed.isoformat() if self._trend_refreshed else None
                ),
                **(self._trend.as_dict() if self._trend else {"available": False, "bias": "unknown", "reason": "not read yet"}),
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
