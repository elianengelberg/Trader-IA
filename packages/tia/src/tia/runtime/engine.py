"""The paper-trading runtime.

This is the pipeline the whole project exists to run, as one loop:

    bar → data quality → features → regime → strategies → fusion
        → context (LLM, advisory only) → Risk Engine → risk budget
        → cost model → expected value → order intent
        → paper execution → fill → position → P&L → persistence → broadcast

Three properties are worth stating because they are what make the loop trustworthy rather
than merely working.

**The fast loop never waits on the slow loop.** The context assessment is fetched with a
timeout, and a timeout produces a neutral assessment rather than a delay. A language model
having a bad minute cannot stall the deterministic pipeline, and cannot change what it
decides beyond removing risk.

**Every refusal is recorded as loudly as every action.** Bars skipped for data quality,
signals that produced NO_TRADE, risk vetoes, orders rejected by the simulator — all of them
are counted, persisted and shown. A dashboard that only displays trades cannot distinguish
a system that is working carefully from one that is broken and silent.

**A risk-approved signal is still not a trade.** The Risk Engine answers "is this
survivable?"; it does not answer "is this worth doing?". Two more gates sit between
approval and an order, and both refuse far more often than the risk engine does:

* the **risk budget**, which decides how much may be risked given the current drawdown,
  volatility and losing streak — and may decide the answer is nothing;
* the **expected value engine**, which subtracts the round-trip cost from a *measured*
  edge and refuses when the remainder does not clear a threshold. Early in a run it
  refuses everything, because there is no measured edge yet and the honest response to
  having no evidence is not to trade.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC as UTC_TZ
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from tia.core.clock import SimulatedClock
from tia.core.config import Settings
from tia.core.ids import deterministic_id, new_ulid
from tia.core.logging import get_logger
from tia.core.rng import RngRegistry
from tia.data.quality import DataQualityEngine
from tia.domain.enums import Direction, MarketRegime, OrderType, Side, TimeInForce
from tia.domain.instruments import DEFAULT_UNIVERSE, InstrumentUniverse
from tia.domain.market import Candle, NewsItem
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.risk import RiskDecision
from tia.domain.signals import ContextAssessment, SignalCandidate
from tia.economics.costs import CostModel, FeeSchedule, MarketConditions
from tia.economics.expected_value import (
    EdgeEstimator,
    ExpectedValue,
    ExpectedValueEngine,
    Outcome,
)
from tia.execution.paper import PaperExecutionProvider
from tia.execution.reconciliation import LedgerSnapshot, ReconciliationEngine
from tia.learning.retrospective import RetrospectiveEngine
from tia.llm.context import ContextRequest, ContextService
from tia.llm.governance import LLMGovernor
from tia.llm.provider import MockLLMProvider, build_provider
from tia.quant.features import FeatureBuilder, FeatureSet
from tia.regime.classifier import RegimeAssessment, RegimeClassifier
from tia.risk.budget import (
    BudgetInputs,
    RiskBudget,
    RiskBudgetEngine,
    RiskProfileName,
)
from tia.risk.engine import RiskEngine
from tia.runtime.scenarios import (
    Scenario,
    generate_series,
    get_scenario,
    scenario_news,
)
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import build_strategies

_log = get_logger("runtime.engine")

#: How long the fast loop will wait for the context layer before proceeding without it.
#: Short on purpose: the assessment is advisory, and a late one is worth less than the
#: latency it costs.
CONTEXT_TIMEOUT_SECONDS = 2.5

#: Simulated wall-clock origin for every scenario. Fixed rather than "now" so two runs of
#: the same scenario and seed produce identical timestamps and are diffable.
SCENARIO_START = datetime(2026, 1, 5, tzinfo=UTC_TZ)


class RuntimeState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    HALTED = "halted"
    FINISHED = "finished"


@dataclass
class SymbolStream:
    """One symbol's pre-generated bars and its rolling buffer."""

    symbol: str
    candles: list[Candle]
    news: dict[int, tuple[str, str, str]]
    index: int = 0
    buffer: deque[Candle] = field(default_factory=lambda: deque(maxlen=400))

    @property
    def exhausted(self) -> bool:
        return self.index >= len(self.candles)

    def next_bar(self) -> Candle | None:
        if self.exhausted:
            return None
        candle = self.candles[self.index]
        self.index += 1
        self.buffer.append(candle)
        return candle


@dataclass
class Counters:
    """What happened, counted. Mirrors the dashboard's system panel."""

    bars: int = 0
    warmup_skipped: int = 0
    quality_skipped: int = 0
    signals: int = 0
    no_trade: int = 0
    risk_rejected: int = 0
    approved: int = 0
    #: Risk-approved, then refused because the budget allowed nothing — emergency
    #: drawdown, the daily trade cap, or the gross exposure ceiling.
    budget_rejected: int = 0
    #: Risk-approved and within budget, then refused because the trade did not pay for
    #: itself. Only ever non-zero when the EV engine is enforcing.
    ev_rejected: int = 0
    #: What the EV engine *would* have refused, counted whether or not it is enforcing.
    #: In paper mode this is the number that matters: it says what enforcing would cost.
    ev_would_reject: int = 0
    #: Of those, the ones refused for lack of evidence rather than for a measured edge
    #: that was too small. Worth separating: one resolves with time, the other says the
    #: strategy does not clear its costs.
    ev_no_evidence: int = 0
    suppressed_position_open: int = 0
    intents: int = 0
    orders_rejected: int = 0
    fills: int = 0
    context_calls: int = 0
    context_neutral: int = 0
    context_vetoes: int = 0
    reconciliations: int = 0
    reconciliation_breaks: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class RuntimeConfig:
    """What a run is. Everything here is chosen before the run starts."""

    scenario: str = "trend_up"
    symbols: tuple[str, ...] = ("BTC-USD",)
    timeframe: str = "1m"
    initial_capital: float = 100_000.0
    seed: int = 20260812
    #: Wall-clock seconds between simulated bars. Governs how lively the demo looks; it
    #: has no effect on the results, which are decided by the seed.
    bar_interval_seconds: float = 0.35
    warmup_bars: int = 130
    enabled_strategies: tuple[str, ...] = ("trend_following", "mean_reversion", "breakout")
    llm_enabled: bool = True
    news_enabled: bool = True
    reconcile_every_bars: int = 50

    #: Whether the expected-value engine **vetoes** or merely **observes**.
    #:
    #: Default False, and the reason is a genuine circularity rather than a compromise.
    #: The EV engine refuses to trade without a measured edge, and an edge is measured
    #: from closed trades. Enforcing it in paper mode is therefore a deadlock: the system
    #: refuses every trade, never closes one, and never accumulates the evidence that
    #: would let it start — a system that is technically correct and permanently inert.
    #:
    #: The resolution is the one the design always assumed: **paper trading is how the
    #: evidence is produced without risking money.** So in paper and backtest the engine
    #: evaluates every decision, records the full arithmetic, and counts what it *would*
    #: have refused — but the trade proceeds, and its outcome becomes a sample. Live
    #: execution sets this True, at which point the accumulated evidence is what the gate
    #: reads and a signal without a measured edge does not become an order.
    #:
    #: The counter to watch while this is False is ``ev_would_reject``. If it stays near
    #: the signal count once the buckets have filled, the strategy does not clear its own
    #: costs, and turning enforcement on would stop it trading entirely. That is a finding,
    #: not a malfunction.
    enforce_expected_value: bool = False


class RuntimeEngine:
    """Runs the pipeline over a scenario, live, and reports everything it does."""

    def __init__(
        self,
        settings: Settings,
        config: RuntimeConfig,
        *,
        universe: InstrumentUniverse | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        persist: Callable[[str, dict[str, Any]], Any] | None = None,
        prior_outcomes: Sequence[Outcome] = (),
    ) -> None:
        self._settings = settings
        self._config = config
        self._universe = universe or DEFAULT_UNIVERSE
        self._on_event = on_event or (lambda _payload: None)
        self._persist = persist

        self.run_id = f"run_{new_ulid(SimulatedClock(datetime.now().astimezone()))}"
        self.state = RuntimeState.STOPPED
        self.counters = Counters()
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = None
        self.last_error: str = ""

        self._scenario: Scenario = get_scenario(config.scenario)
        self._streams: dict[str, SymbolStream] = {}
        #: Protective stop currently covering each open position, and the stop price the
        #: Risk Engine approved for it. A position without a stop has an unbounded loss,
        #: which would make every drawdown number on the dashboard meaningless.
        self._protective: dict[str, str] = {}
        self._stop_price: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._pause_requested = False
        self._new_trades_allowed = True

        # Constructed once and shared by every component below. It must never be
        # *replaced* afterwards: rebinding this attribute would leave each component
        # holding the original clock, which then never advances — the signal TTL would
        # expire on every bar and the LLM rate window would never slide. A RuntimeEngine
        # is therefore single-use; the API builds a new one per run.
        self._clock = SimulatedClock(SCENARIO_START)
        self._rng = RngRegistry(config.seed)

        self._quality = DataQualityEngine(settings.data_quality)
        self._features = FeatureBuilder()
        self._regimes = RegimeClassifier()
        self._strategies = StrategyEngine(
            build_strategies(config.enabled_strategies), settings.strategy, self._clock
        )
        self._risk = RiskEngine(self._effective_limits(), self._universe, self._clock)
        self._execution = PaperExecutionProvider(
            settings.execution,
            self._universe,
            self._clock,
            self._rng,
            initial_capital=config.initial_capital,
        )
        self._reconciler = ReconciliationEngine(on_critical=self._risk.enter_safe_mode)

        # --- economics -------------------------------------------------------------
        # The fee schedule mirrors the paper simulator's, so the cost the EV engine
        # subtracts is the cost the simulator actually charges. In a live deployment it
        # would come from the account instead, and `verified_at_source` stays False until
        # it does — which is one of the activation gate's checks.
        self._costs = CostModel(
            FeeSchedule(
                maker_bps=settings.execution.maker_fee_bps,
                taker_bps=settings.execution.taker_fee_bps,
                verified_at_source=False,
                source="paper simulator's configured fee model — not a live account",
            ),
            impact_coefficient=settings.execution.impact_coefficient,
        )
        self._edges = EdgeEstimator()
        # A restart is not amnesia: evidence persisted by earlier runs is reloaded before
        # the first bar, and the loss streak resumes from where the record left it. The
        # streak is *derived* — recomputed from the tail of the outcomes — because a
        # separately-stored counter can disagree with its own evidence.
        self._edges.record_many(list(prior_outcomes))
        self._consecutive_losses = 0
        for outcome in reversed(list(prior_outcomes)):
            if outcome.net_return_bps > 0:
                break
            self._consecutive_losses += 1
        self._prior_outcome_count = len(prior_outcomes)
        # The retrospective is observe-only in the demo: it reads a lesson from every close
        # so the Learning view fills as the run trades, but it does not gate the demo's
        # trades. The demo's job is to explore every bucket and produce evidence; the live
        # session is where the lessons actually tighten risk.
        self._retro = RetrospectiveEngine()
        self._ev = ExpectedValueEngine(
            self._edges,
            threshold_bps=settings.live.ev_threshold_bps,
            max_cost_ratio=settings.live.max_cost_ratio,
        )
        self._budget = RiskBudgetEngine(RiskProfileName(settings.live.risk_profile))
        #: The exact inputs the last per-bar budget decision used, kept so the snapshot
        #: reports the same numbers the decision path saw (defect D2: the snapshot used
        #: to recompute with volatility=0 and exposure=0 and could disagree).
        self._last_budget_inputs: BudgetInputs | None = None
        #: Open round trips, keyed by symbol, so a close can be scored against its entry
        #: and fed back to the edge estimator. Without this the estimator never fills and
        #: the system never trades — which is correct behaviour but a useless product.
        self._open_trades: dict[str, dict[str, Any]] = {}
        #: What the system believed when it entered, carried to the exit so the outcome
        #: lands in the same bucket the decision was drawn from.
        self._entry_beliefs: dict[str, dict[str, Any]] = {}

        llm_provider = (
            MockLLMProvider(seed=config.seed, fail_rate=self._scenario.llm_failure_rate)
            if settings.llm.provider == "stub" or not config.llm_enabled
            else build_provider(
                settings.llm,
                api_key=(
                    settings.anthropic_api_key.get_secret_value()
                    if settings.anthropic_api_key
                    else None
                ),
                seed=config.seed,
            )
        )
        llm_config = settings.llm.model_copy(update={"enabled": config.llm_enabled})
        self._context = ContextService(
            llm_provider,
            LLMGovernor(llm_config, self._clock),
            self._clock,
            llm_config,
            known_symbols=frozenset(i.symbol for i in self._universe.instruments),
        )

        # Recent history the API serves without touching the database, so the dashboard
        # stays responsive even while the runtime is writing.
        self.recent_decisions: deque[dict[str, Any]] = deque(maxlen=200)
        self.recent_orders: deque[dict[str, Any]] = deque(maxlen=200)
        self.recent_fills: deque[dict[str, Any]] = deque(maxlen=200)
        self.recent_assessments: deque[dict[str, Any]] = deque(maxlen=100)
        #: Every trade-or-not evaluation with its full arithmetic, so the strategy page can
        #: show why a signal did not become an order.
        self.recent_evaluations: deque[dict[str, Any]] = deque(maxlen=200)
        #: Closed round trips, as the edge estimator consumed them.
        self.closed_trades: deque[dict[str, Any]] = deque(maxlen=1000)
        self.recent_news: deque[dict[str, Any]] = deque(maxlen=100)
        self.recent_logs: deque[dict[str, Any]] = deque(maxlen=500)
        self.equity_curve: deque[dict[str, Any]] = deque(maxlen=5000)
        self.market_state: dict[str, dict[str, Any]] = {}
        self.peak_equity = config.initial_capital

    # ------------------------------------------------------------------ properties

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def typical_trade_notional_usd(self) -> float:
        """Median dollars-at-work per closed trade — the bps→USD conversion factor."""
        return self._retro.typical_notional_usd

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def execution(self) -> PaperExecutionProvider:
        return self._execution

    @property
    def risk(self) -> RiskEngine:
        return self._risk

    @property
    def context_service(self) -> ContextService:
        return self._context

    @property
    def is_running(self) -> bool:
        return self.state in {RuntimeState.RUNNING, RuntimeState.PAUSED}

    @property
    def progress(self) -> dict[str, int]:
        total = sum(len(s.candles) for s in self._streams.values()) or 1
        done = sum(s.index for s in self._streams.values())
        return {"bars_done": done, "bars_total": total, "percent": int(done / total * 100)}

    def _effective_limits(self):  # type: ignore[no-untyped-def]
        """Apply the scenario's risk overrides, if any.

        Overrides go through :meth:`RiskLimits.propose_change`, which returns a *copy*.
        The limits object itself is immutable, so a scenario cannot mutate the live
        engine's limits — it can only construct different ones before the run starts.
        """
        limits = self._settings.risk
        if not self._scenario.risk_overrides:
            return limits
        return limits.propose_change(**self._scenario.risk_overrides)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Begin the run. An engine that has already run cannot be restarted.

        The clock only moves forward, so replaying a finished engine would either rewind
        time or resume from the end of the previous run. The API creates a fresh engine
        instead, which also gives each run its own run_id and its own ledger.
        """
        if self.is_running:
            return
        if self.state is not RuntimeState.STOPPED:
            raise RuntimeError(
                f"this engine already ran (state={self.state.value}); create a new one"
            )
        self.state = RuntimeState.STARTING
        self._stop_requested = False
        self._pause_requested = False
        self._new_trades_allowed = True

        start_time = SCENARIO_START
        for symbol in self._config.symbols:
            candles = generate_series(
                self._scenario,
                symbol=symbol,
                timeframe=self._config.timeframe,
                start=start_time,
                seed=self._config.seed,
                start_price=_reference_price(symbol),
            )
            self._streams[symbol] = SymbolStream(
                symbol=symbol,
                candles=candles,
                news=(
                    scenario_news(
                        self._scenario,
                        symbol=symbol,
                        candles=candles,
                        seed=self._config.seed,
                    )
                    if self._config.news_enabled
                    else {}
                ),
            )

        self.started_at = datetime.now(UTC_TZ)
        self.state = RuntimeState.RUNNING
        self._log("INFO", "runtime", "system", f"paper trading started ({self._scenario.title})")
        self._emit("runtime.started", {"run_id": self.run_id, "scenario": self._scenario.id.value})

        self._task = asyncio.create_task(self._loop(), name=f"runtime-{self.run_id}")

    async def stop(self) -> None:
        self._stop_requested = True
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(self._task, timeout=10.0)
            self._task = None
        self.state = RuntimeState.STOPPED
        self.stopped_at = datetime.now(UTC_TZ)
        self._log("INFO", "runtime", "system", "paper trading stopped")
        self._emit("runtime.stopped", {"run_id": self.run_id})

    def pause(self) -> None:
        self._pause_requested = True
        self.state = RuntimeState.PAUSED
        self._log("WARNING", "runtime", "system", "strategies paused; no new decisions")

    def resume(self) -> None:
        self._pause_requested = False
        if self.state is RuntimeState.PAUSED:
            self.state = RuntimeState.RUNNING
        self._log("INFO", "runtime", "system", "strategies resumed")

    def stop_new_trades(self) -> None:
        """Keep managing what is open; stop opening anything new."""
        self._new_trades_allowed = False
        self._log("WARNING", "risk", "system", "new trades disabled; existing positions still managed")

    def allow_new_trades(self) -> None:
        self._new_trades_allowed = True
        self._log("INFO", "risk", "system", "new trades re-enabled")

    def kill_switch(self, reason: str = "operator") -> None:
        """Halt all new risk. Reversible only by an explicit, named operator action."""
        self._risk.engage_kill_switch(reason)
        self._new_trades_allowed = False
        self.state = RuntimeState.HALTED
        self._log("ERROR", "risk", "system", f"KILL SWITCH engaged: {reason}")
        self._emit("runtime.kill_switch", {"reason": reason})

    def release_kill_switch(self, approved_by: str) -> None:
        self._risk.resume(approved_by=approved_by)
        self._new_trades_allowed = True
        if self.state is RuntimeState.HALTED:
            self.state = RuntimeState.RUNNING
        self._log("WARNING", "risk", "system", f"kill switch released by {approved_by}")

    # ------------------------------------------------------------------ the loop

    async def _loop(self) -> None:
        try:
            while not self._stop_requested:
                if self._pause_requested:
                    await asyncio.sleep(0.1)
                    continue
                if all(stream.exhausted for stream in self._streams.values()):
                    self.state = RuntimeState.FINISHED
                    self._log("INFO", "runtime", "system", "scenario exhausted; run complete")
                    self._emit("runtime.finished", {"run_id": self.run_id})
                    break

                await self._tick()
                await asyncio.sleep(self._config.bar_interval_seconds)
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            raise
        except Exception as exc:
            self.counters.errors += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.state = RuntimeState.HALTED
            _log.exception("runtime_loop_failed", run_id=self.run_id)
            self._log("ERROR", "runtime", "system", f"runtime halted: {self.last_error}")
            self._emit("runtime.error", {"error": self.last_error})

    async def _tick(self) -> None:
        """Advance every symbol by one bar."""
        for symbol, stream in self._streams.items():
            candle = stream.next_bar()
            if candle is None:
                continue
            self._clock.advance_to(candle.close_time)
            await self._process_bar(symbol, stream, candle)

        self.counters.bars += 1
        self._record_equity()

        if (
            self._config.reconcile_every_bars > 0
            and self.counters.bars % self._config.reconcile_every_bars == 0
        ):
            self._reconcile()

    async def _process_bar(self, symbol: str, stream: SymbolStream, candle: Candle) -> None:
        # 1. Match resting orders against this bar, before anything decides anything.
        fills = self._execution.on_bar(candle)
        for fill in fills:
            self._risk.record_execution(fill.symbol, fill.filled_at)
            self._record_fill(fill)

        if fills:
            await self._sync_protective_stop(symbol)

        self._update_market_state(symbol, candle)
        self._maybe_publish_news(stream, candle)

        window = list(stream.buffer)
        if len(window) < max(self._config.warmup_bars, self._features.min_bars):
            self.counters.warmup_skipped += 1
            return

        # 2. Data quality gate. A hard fail means no decision at all.
        report = self._quality.evaluate(
            symbol=symbol,
            timeframe=self._config.timeframe,
            candles=window,
            now=candle.close_time,
            last_feed_message_at=candle.close_time,
        )
        if report.hard_fail:
            self.counters.quality_skipped += 1
            self._log(
                "WARNING",
                "data",
                symbol,
                f"bar skipped on data quality ({', '.join(f.value for f in report.flags) or 'hard fail'})",
            )
            return

        features = self._features.build(symbol, self._config.timeframe, window)
        regime = self._regimes.classify(features, now=candle.close_time)

        # 3. Context layer. Advisory, bounded in time, and never on the critical path.
        assessment, context_note, context_used = await self._assess(
            symbol, features, regime, report, candle
        )

        signal, _fusion = self._strategies.evaluate(
            features=features,
            regime=regime,
            quality=report,
            context=assessment,
            correlation_id=f"{self.run_id}:{symbol}:{stream.index}",
        )
        self.counters.signals += 1
        if signal.direction is Direction.NO_TRADE:
            self.counters.no_trade += 1

        # 4. Risk Engine. Absolute veto, deterministic, never an LLM.
        decision = self._risk.evaluate(
            signal=signal,
            portfolio=self._execution.portfolio,
            features=features,
            quality=report,
            now=candle.close_time,
        )
        if decision.allows_execution:
            self.counters.approved += 1
        elif signal.direction.is_actionable:
            self.counters.risk_rejected += 1

        # 5. Risk budget and expected value. Only meaningful for an approved, actionable
        #    signal that would open something — an exit is not a discretionary trade and
        #    must never be blocked by an edge calculation.
        position = self._execution.portfolio.positions.get(symbol)
        holding = position is not None and not position.is_flat
        opening = decision.allows_execution and not holding

        budget: RiskBudget | None = None
        evaluation: ExpectedValue | None = None
        if opening:
            self._last_budget_inputs = self._budget_inputs(features)
            budget = self._budget.compute(self._last_budget_inputs)
            evaluation = self._ev.evaluate(
                regime=regime.regime,
                direction=signal.direction,
                confidence=signal.confidence,
                costs=self._costs.estimate(
                    quantity=decision.approved_quantity,
                    conditions=self._market_conditions(candle, features, window),
                ),
            )
            self._record_evaluation(symbol, candle, signal, budget, evaluation)

        self._record_decision(
            symbol, candle, signal, decision, regime, report, features,
            assessment, context_note, context_used, budget, evaluation,
        )

        # 6. Act. An opposing signal flattens; otherwise open, if flat and allowed.
        if not decision.allows_execution:
            return

        if holding:
            # A position already open plus an approved signal in the *opposite*
            # direction is the system changing its mind, and the honest response is to
            # close rather than to hold something it no longer believes in. Same
            # direction means it still believes it, so nothing happens — pyramiding
            # would exceed the size the Risk Engine approved.
            opposing = (position.quantity > 0) != (signal.direction is Direction.LONG)
            if opposing:
                await self._flatten(symbol, "signal reversed", candle)
            else:
                self.counters.suppressed_position_open += 1
            return

        if not self._new_trades_allowed:
            self.counters.suppressed_position_open += 1
            return

        if budget is not None and not budget.allows_new_trades:
            self.counters.budget_rejected += 1
            self._log(
                "INFO", "risk", symbol,
                f"no order: risk budget is zero ({budget.binding_constraint})",
            )
            return

        if evaluation is not None and not evaluation.is_tradeable:
            self.counters.ev_would_reject += 1
            if evaluation.edge_estimate is None:
                self.counters.ev_no_evidence += 1
            if self._config.enforce_expected_value:
                self.counters.ev_rejected += 1
                self._log("INFO", "trading", symbol, f"no order: {evaluation.explain()}")
                return
            # Observing, not enforcing. The trade proceeds and its outcome becomes the
            # evidence that enforcement will later read — see
            # ``RuntimeConfig.enforce_expected_value`` for why this is not a loophole.
            self._log(
                "DEBUG", "trading", symbol,
                f"expected value would refuse this ({evaluation.explain()}), but the EV "
                "engine is observing rather than enforcing; the outcome becomes a sample",
            )

        self._stop_price[symbol] = decision.stop_price or 0.0
        self._entry_beliefs[symbol] = {
            "regime": regime.regime,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "signal_id": signal.signal_id,
            "expected_net_bps": evaluation.net_edge_bps if evaluation else 0.0,
        }
        await self._submit(decision, signal, candle)

    # ------------------------------------------------------------------ economics

    def _market_conditions(
        self, candle: Candle, features: FeatureSet, window: list[Candle]
    ) -> MarketConditions:
        """The inputs the cost model prices against, read from this bar.

        Assembled explicitly rather than reached for, so a stored decision can be
        re-priced later and produce the same number — which is what makes a past
        NO_TRADE auditable rather than merely asserted.
        """
        values = features.finite_values()
        atr_pct = values.get("atr_pct", 0.0)
        per_bar_volatility = max(0.0, atr_pct / 100.0)

        # The paper simulator's configured spread. In a live deployment this comes from
        # the book; here, using the simulator's own number keeps the cost the EV engine
        # subtracts equal to the cost the simulator will charge.
        spread_bps = self._settings.execution.base_slippage_bps

        recent = window[-20:] if len(window) >= 20 else window
        typical_volume = (
            sum(bar.volume for bar in recent) / len(recent) if recent else candle.volume
        )

        return MarketConditions(
            price=max(candle.close, 1e-9),
            spread_bps=spread_bps,
            volatility_per_bar=per_bar_volatility,
            # The simulator caps participation rather than exposing a book, so the
            # available-at-touch quantity is derived from that cap. Stated here because a
            # reader would otherwise assume a real depth reading.
            top_of_book_quantity=typical_volume
            * self._settings.execution.max_participation_rate,
            bar_volume=typical_volume,
            latency_ms=float(
                self._settings.execution.submit_latency_ms
                + self._settings.execution.ack_latency_ms
            ),
            bar_seconds=60.0,
        )

    def _budget_inputs(self, features: FeatureSet) -> BudgetInputs:
        portfolio = self._execution.portfolio
        equity = portfolio.equity
        drawdown = (
            0.0
            if self.peak_equity <= 0
            else max(0.0, (self.peak_equity - equity) / self.peak_equity * 100.0)
        )
        return BudgetInputs(
            equity=equity,
            peak_equity=self.peak_equity,
            drawdown_pct=drawdown,
            realised_annual_volatility=max(
                0.0, features.finite_values().get("realized_vol_20", 0.0)
            ),
            consecutive_losses=self._consecutive_losses,
            trades_today=self._risk.state.trades_today,
            open_gross_exposure_pct=(
                portfolio.gross_exposure / equity * 100.0 if equity > 0 else 0.0
            ),
        )

    def _record_evaluation(
        self,
        symbol: str,
        candle: Candle,
        signal: SignalCandidate,
        budget: RiskBudget,
        evaluation: ExpectedValue,
    ) -> None:
        row = {
            "symbol": symbol,
            "at": self._clock.now(),
            "signal_id": signal.signal_id,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "price": candle.close,
            "budget": budget.as_dict(),
            "expected_value": evaluation.as_dict(),
            "tradeable": evaluation.is_tradeable and budget.allows_new_trades,
        }
        self.recent_evaluations.appendleft(_jsonable(row))
        self._emit("evaluation.created", _jsonable(row))

    def _score_round_trip(self, symbol: str, closed_at: datetime) -> None:
        """Turn a closed position into evidence the edge estimator can use.

        Both legs are volume-weighted. The entry accumulates a VWAP as fills add to the
        position; the exit accumulates one as fills reduce it. An earlier version scored
        the exit at the *last* fill's price alone, which mis-measured every round trip
        that closed in more than one fill — and mis-measured evidence is worse than no
        evidence, because the estimator treats it as fact.

        The realised return is measured **net of the fees actually paid on both legs**,
        because the EV engine subtracts costs again downstream and counting them twice
        would understate every edge. It is expressed in basis points of the entry
        notional, so it is directly comparable to the cost estimate that authorised the
        entry in the first place.
        """
        entry = self._open_trades.pop(symbol, None)
        beliefs = self._entry_beliefs.pop(symbol, None)
        if entry is None or beliefs is None:
            return

        entry_price = float(entry["price"])
        exit_quantity = float(entry.get("exit_quantity", 0.0))
        if entry_price <= 0 or exit_quantity <= 0:
            return
        exit_price = float(entry["exit_value"]) / exit_quantity

        long_side = entry["side"] is Side.BUY
        raw_bps = (exit_price - entry_price) / entry_price * 10_000.0
        gross_bps = raw_bps if long_side else -raw_bps

        notional = entry["quantity"] * entry_price
        fees_bps = (
            (float(entry["fee"]) + float(entry.get("exit_fees", 0.0))) / notional * 10_000.0
            if notional > 0
            else 0.0
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
            closed_at=closed_at,
            signal_id=beliefs["signal_id"],
            symbol=symbol,
            notional_usd=notional,
        )

        # A losing streak shrinks the next budget. It never grows it — see
        # :func:`tia.risk.budget.assert_no_martingale`.
        self._consecutive_losses = 0 if net_bps > 0 else self._consecutive_losses + 1

        row = {
            "symbol": symbol,
            "signal_id": beliefs["signal_id"],
            "regime": beliefs["regime"].value,
            "direction": beliefs["direction"].value,
            "confidence": beliefs["confidence"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": entry["quantity"],
            "gross_bps": gross_bps,
            "fees_bps": fees_bps,
            "net_bps": net_bps,
            "expected_net_bps": beliefs["expected_net_bps"],
            "closed_at": closed_at,
            "samples_now": self._edges.sample_count(
                regime=beliefs["regime"],
                direction=beliefs["direction"],
                confidence=beliefs["confidence"],
            ),
        }
        self.closed_trades.appendleft(_jsonable(row))
        self._emit("trade.closed", _jsonable(row))
        # Persisted with a deterministic id, so a redelivered close upserts rather than
        # double-counting — evidence that arrives twice is still one trade's worth.
        self._save(
            "edge_outcome",
            {
                "outcome_id": deterministic_id(
                    "edge", self.run_id, symbol, beliefs["signal_id"], closed_at
                ),
                "run_id": self.run_id,
                "signal_id": beliefs["signal_id"],
                "symbol": symbol,
                "regime": beliefs["regime"].value,
                "direction": beliefs["direction"].value,
                "confidence": beliefs["confidence"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": entry["quantity"],
                "gross_bps": gross_bps,
                "fees_bps": fees_bps,
                "net_bps": net_bps,
                "expected_net_bps": beliefs["expected_net_bps"],
                "closed_at": closed_at,
                "source": "paper",
            },
        )
        self._log(
            "INFO", "trading", symbol,
            f"round trip closed at {net_bps:+.1f} bps net "
            f"(expected {beliefs['expected_net_bps']:+.1f}); "
            f"{row['samples_now']} samples in this bucket",
        )

    async def _assess(
        self,
        symbol: str,
        features: FeatureSet,
        regime: RegimeAssessment,
        report: Any,
        candle: Candle,
    ) -> tuple[ContextAssessment | None, str, bool]:
        """Fetch a context assessment, bounded by a timeout.

        A timeout yields ``None``, and ``None`` means the fusion layer applies no
        modifier at all. Losing the model costs nothing.
        """
        if not self._config.llm_enabled:
            return (None, "context layer disabled for this run", False)

        equity = self._execution.portfolio.equity
        drawdown = max(0.0, (self.peak_equity - equity) / self.peak_equity * 100.0)
        position = self._execution.portfolio.positions.get(symbol)

        request = ContextRequest(
            symbol=symbol,
            features=features,
            regime=regime,
            quality=report,
            equity=equity,
            drawdown_pct=drawdown,
            open_position_qty=position.quantity if position else 0.0,
        )
        try:
            outcome = await asyncio.wait_for(
                self._context.assess(request), timeout=CONTEXT_TIMEOUT_SECONDS
            )
        except TimeoutError:
            self.counters.context_neutral += 1
            self._log("WARNING", "ai", symbol, "context assessment timed out; proceeding without it")
            return (None, "timeout", False)

        self.counters.context_calls += 1
        if not outcome.used:
            self.counters.context_neutral += 1
        if outcome.assessment.veto:
            self.counters.context_vetoes += 1

        self._record_assessment(symbol, outcome, candle)
        return (outcome.assessment, outcome.reason, outcome.used)

    async def _sync_protective_stop(self, symbol: str) -> None:
        """Keep exactly one protective stop matching the open position.

        Cancelled when flat, replaced when a partial fill changed the quantity it covers.
        A stop that protects the wrong size is worse than none: the dashboard would show
        a bounded loss that was not actually bounded.
        """
        position = self._execution.portfolio.positions.get(symbol)
        existing_id = self._protective.get(symbol)
        stop_price = self._stop_price.get(symbol, 0.0)

        if position is None or position.is_flat or stop_price <= 0:
            if existing_id:
                await self._execution.cancel_order(existing_id)
                self._protective.pop(symbol, None)
            return

        quantity = abs(position.quantity)
        if existing_id:
            existing = await self._execution.get_order(existing_id)
            if existing is not None and not existing.state.is_terminal:
                covered = existing.quantity - existing.filled_quantity
                if abs(covered - quantity) <= max(quantity * 1e-6, 1e-9):
                    return
                await self._execution.cancel_order(existing_id)
            self._protective.pop(symbol, None)

        side = Side.SELL if position.quantity > 0 else Side.BUY
        intent = OrderIntent(
            intent_id=deterministic_id("int", "stop", symbol, quantity, self._clock.now()),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"protective:{symbol}:{self.counters.bars}",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.STOP,
            ),
            signal_id=f"protective:{symbol}",
            risk_decision_id=f"protective:{symbol}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=stop_price,
            time_in_force=TimeInForce.GTC,
            created_at=self._clock.now(),
        )
        order = await self._execution.submit_order(intent)
        if order.state.is_terminal:
            self._log(
                "WARNING", "risk", symbol,
                f"protective stop rejected ({order.reject_reason or order.state.value}); "
                "the position is unprotected",
            )
            return
        self._protective[symbol] = order.order_id
        self._record_order(order)
        self._log("INFO", "risk", symbol, f"protective stop placed at {stop_price:.2f}")

    async def _flatten(self, symbol: str, reason: str, candle: Candle) -> None:
        """Close an open position with a market order, cancelling its protective stop."""
        position = self._execution.portfolio.positions.get(symbol)
        if position is None or position.is_flat:
            return

        existing_id = self._protective.pop(symbol, None)
        if existing_id:
            await self._execution.cancel_order(existing_id)

        quantity = abs(position.quantity)
        side = Side.SELL if position.quantity > 0 else Side.BUY
        intent = OrderIntent(
            intent_id=deterministic_id("int", "flatten", symbol, self._clock.now()),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"flatten:{symbol}:{self.counters.bars}",
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=OrderType.MARKET,
            ),
            signal_id=f"flatten:{symbol}",
            risk_decision_id=f"flatten:{symbol}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            created_at=self._clock.now(),
        )
        order = await self._execution.submit_order(intent)
        self.counters.intents += 1
        self._record_order(order)
        self._log(
            "INFO", "trading", symbol,
            f"closing {quantity:.6f} ({reason}) @ ~{candle.close:.2f}",
        )

    async def _submit(
        self, decision: RiskDecision, signal: SignalCandidate, candle: Candle
    ) -> None:
        side = signal.direction.to_side()
        intent = OrderIntent(
            intent_id=deterministic_id("int", decision.decision_id),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=decision.signal_id,
                symbol=decision.symbol,
                side=side,
                quantity=decision.approved_quantity,
                order_type=OrderType.MARKET,
            ),
            signal_id=decision.signal_id,
            risk_decision_id=decision.decision_id,
            symbol=decision.symbol,
            side=side,
            quantity=decision.approved_quantity,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            created_at=decision.decided_at,
        )
        order = await self._execution.submit_order(intent)
        self.counters.intents += 1
        if order.state.is_terminal:
            self.counters.orders_rejected += 1
            self._log(
                "WARNING", "trading", decision.symbol,
                f"order rejected: {order.reject_reason or order.state.value}",
            )
        else:
            self._log(
                "INFO", "trading", decision.symbol,
                f"{side.value.upper()} {decision.approved_quantity:.6f} submitted "
                f"@ ~{candle.close:.2f} (confidence {signal.confidence:.2f})",
            )
        self._record_order(order)

    # ------------------------------------------------------------------ recording

    def _record_equity(self) -> None:
        portfolio = self._execution.portfolio
        equity = portfolio.equity
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (
            0.0 if self.peak_equity <= 0 else (self.peak_equity - equity) / self.peak_equity * 100.0
        )
        point = {
            "at": self._clock.now(),
            "equity": equity,
            "cash": portfolio.cash,
            "realized_pnl": portfolio.realized_pnl,
            "unrealized_pnl": portfolio.unrealized_pnl,
            "gross_exposure": portfolio.gross_exposure,
            "net_exposure": portfolio.net_exposure,
            "drawdown_pct": drawdown,
            "open_positions": sum(
                1 for p in portfolio.positions.values() if not p.is_flat
            ),
        }
        self.equity_curve.append(point)
        self._save("equity", point)
        self._emit("portfolio.updated", _jsonable(point))

    def _record_decision(
        self,
        symbol: str,
        candle: Candle,
        signal: SignalCandidate,
        decision: RiskDecision,
        regime: RegimeAssessment,
        report: Any,
        features: FeatureSet,
        assessment: ContextAssessment | None,
        context_note: str,
        context_used: bool,
        budget: RiskBudget | None = None,
        evaluation: ExpectedValue | None = None,
    ) -> None:
        row = {
            "decision_id": decision.decision_id,
            "run_id": self.run_id,
            "correlation_id": signal.correlation_id,
            "symbol": symbol,
            "decided_at": decision.decided_at,
            "direction": signal.direction.value,
            "base_confidence": signal.base_confidence,
            "confidence": signal.confidence,
            "verdict": decision.verdict.value,
            "approved_quantity": decision.approved_quantity,
            "requested_quantity": decision.requested_quantity,
            "regime": regime.regime.value,
            "data_quality_score": report.quality_score,
            "data_freshness_score": report.freshness_score,
            "feature_hash": features.feature_hash,
            "signal_id": signal.signal_id,
            "context_modifier": assessment.context_modifier if assessment else 0.0,
            "context_veto": bool(assessment and assessment.veto),
            "context_used": context_used,
            "context_reason": context_note,
            "thesis": assessment.thesis if assessment else "",
            "why_enter": list(signal.why_enter),
            "why_not_enter": list(signal.why_not_enter),
            "risk_checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in decision.checks
            ],
            # Present only when the decision would have opened something. An exit is not
            # priced for edge, so attaching a null here is more honest than attaching a
            # number that was never consulted.
            "risk_budget": budget.as_dict() if budget else None,
            "expected_value": evaluation.as_dict() if evaluation else None,
            "features": dict(list(features.finite_values().items())[:40]),
            "snapshot": {
                "close": candle.close,
                "volume": candle.volume,
                "open_time": candle.open_time.isoformat(),
            },
        }
        self.recent_decisions.appendleft(_jsonable(row))
        self._save("decision", row)
        self._emit("decision.created", _jsonable(row))

    def _record_order(self, order: Order) -> None:
        row = {
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
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }
        self.recent_orders.appendleft(_jsonable(row))
        self._save("order", {"run_id": self.run_id, "order": order})
        self._emit("order.state_changed", _jsonable(row))

    def _record_fill(self, fill: Fill) -> None:
        self.counters.fills += 1
        self._track_round_trip(fill)
        row = {
            "fill_id": fill.fill_id,
            "order_id": fill.order_id,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "quantity": fill.quantity,
            "price": fill.price,
            "fee": fill.fee,
            "slippage_bps": fill.slippage_bps,
            "liquidity": fill.liquidity,
            "filled_at": fill.filled_at,
        }
        self.recent_fills.appendleft(_jsonable(row))
        self._save("fill", {"run_id": self.run_id, "fill": fill})
        self._emit("order.fill_simulated", _jsonable(row))
        self._log(
            "INFO", "trading", fill.symbol,
            f"filled {fill.side.value} {fill.quantity:.6f} @ {fill.price:.2f} "
            f"(slippage {fill.slippage_bps:.1f} bps, fee {fill.fee:.2f})",
        )
        # An order that just changed state must be re-persisted, or the journal shows a
        # filled position attached to an order still recorded as acknowledged.
        order = self._execution._orders.get(fill.order_id)
        if order is not None:
            self._record_order(order)

    def _track_round_trip(self, fill: Fill) -> None:
        """Open or close the round trip this fill belongs to.

        Driven off the *portfolio* rather than off the order, because a position can be
        closed by a protective stop, by a reversal, or by a partial sequence, and only the
        portfolio knows whether the symbol ended up flat. Reading the position after the
        fill has been applied is what makes "did this close?" a fact rather than an
        inference from order metadata.
        """
        position = self._execution.portfolio.positions.get(fill.symbol)
        flat = position is None or position.is_flat
        open_trade = self._open_trades.get(fill.symbol)

        if open_trade is None:
            if not flat:
                self._open_trades[fill.symbol] = {
                    "price": fill.price,
                    "quantity": fill.quantity,
                    "side": fill.side,
                    "fee": fill.fee,
                    "opened_at": fill.filled_at,
                    # The exit leg, accumulated fill by fill. A position can close in
                    # several partial fills, and each one is part of the exit price.
                    "exit_value": 0.0,
                    "exit_quantity": 0.0,
                    "exit_fees": 0.0,
                }
            return

        if fill.side is open_trade["side"]:
            # Adding to the position: the entry becomes a volume-weighted average, so the
            # round trip is scored against what was actually paid rather than against the
            # first fill of several.
            total = open_trade["quantity"] + fill.quantity
            open_trade["price"] = (
                open_trade["price"] * open_trade["quantity"] + fill.price * fill.quantity
            ) / total
            open_trade["quantity"] = total
            open_trade["fee"] += fill.fee
        else:
            # Reducing: accumulate the exit VWAP whether or not this fill finishes the
            # job. Scoring only the final fill's price was defect D1 — a two-fill exit
            # was measured at half its own prices.
            open_trade["exit_value"] += fill.price * fill.quantity
            open_trade["exit_quantity"] += fill.quantity
            open_trade["exit_fees"] += fill.fee
            if flat:
                self._score_round_trip(fill.symbol, fill.filled_at)

    def _record_assessment(self, symbol: str, outcome: Any, candle: Candle) -> None:
        assessment = outcome.assessment
        usage = outcome.usage
        row = {
            "assessment_id": assessment.assessment_id,
            "run_id": self.run_id,
            "correlation_id": "",
            "symbol": symbol,
            "created_at": assessment.created_at,
            "expires_at": assessment.expires_at,
            "used": outcome.used,
            "reason": outcome.reason,
            "provider": self._context.provider_name,
            "model_id": assessment.model_id,
            "prompt_version": assessment.prompt_version,
            "context_modifier": assessment.context_modifier,
            "veto": assessment.veto,
            "leaning": assessment.decision.value,
            "confidence": assessment.confidence,
            "thesis": assessment.thesis,
            "supporting": [e.claim for e in assessment.supporting_evidence],
            "contradicting": [e.claim for e in assessment.contradicting_evidence],
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "latency_ms": usage.latency_ms if usage else 0.0,
            "cost_usd": usage.cost_usd(self._settings.llm) if usage else 0.0,
        }
        self.recent_assessments.appendleft(_jsonable(row))
        self._save("assessment", row)
        self._emit("ai.context_assessed", _jsonable(row))
        del candle

    def _maybe_publish_news(self, stream: SymbolStream, candle: Candle) -> None:
        entry = stream.news.get(stream.index - 1)
        if entry is None:
            return
        headline, sentiment, impact = entry
        item = NewsItem(
            news_id=deterministic_id("news", stream.symbol, stream.index),
            published_at=candle.close_time,
            ingested_at=candle.close_time,
            source="scenario",
            headline=headline,
            body_hash=deterministic_id("body", headline),
            symbols=(stream.symbol,),
        )
        row = {
            "news_id": item.news_id,
            "run_id": self.run_id,
            "published_at": item.published_at,
            "ingested_at": item.ingested_at,
            "source": item.source,
            "headline": item.headline,
            "symbols": list(item.symbols),
            "sentiment": sentiment,
            "relevance": 0.9 if impact == "high" else 0.4,
            "impact": impact,
            "body_hash": item.body_hash,
        }
        self.recent_news.appendleft(_jsonable(row))
        self._save("news", row)
        self._emit("news.received", _jsonable(row))
        self._log("INFO", "data", stream.symbol, f"news: {headline}")

    def _update_market_state(self, symbol: str, candle: Candle) -> None:
        previous = self.market_state.get(symbol, {})
        prior_close = previous.get("price", candle.open)
        self.market_state[symbol] = {
            "symbol": symbol,
            "price": candle.close,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "volume": candle.volume,
            "change_pct": (
                (candle.close - prior_close) / prior_close * 100.0 if prior_close else 0.0
            ),
            "at": candle.close_time.isoformat(),
            "regime": previous.get("regime", MarketRegime.UNKNOWN.value),
        }

    def _reconcile(self) -> None:
        """Compare the runtime's ledger against the execution provider's."""
        self.counters.reconciliations += 1
        now = self._clock.now()
        internal = LedgerSnapshot.of_internal(
            orders=self._execution._orders,
            portfolio=self._execution.portfolio,
            fill_count=self.counters.fills,
            at=now,
        )
        external = LedgerSnapshot.of_provider_snapshot(
            self._execution.snapshot(), at=now, source="paper"
        )
        report = self._reconciler.reconcile(internal, external)
        if report.has_critical:
            self.counters.reconciliation_breaks += 1
            self._reconciler.enforce(report)
            self.state = RuntimeState.HALTED
            self._log("ERROR", "risk", "system", f"reconciliation break: {report.summary()}")
        self._emit(
            "system.reconciliation_completed",
            {"clean": report.is_clean, "summary": report.summary()},
        )

    # ------------------------------------------------------------------ plumbing

    def _log(self, level: str, channel: str, component: str, message: str) -> None:
        entry = {
            "at": datetime.now(UTC_TZ).isoformat(),
            "level": level,
            "channel": channel,
            "component": component,
            "message": message,
            "run_id": self.run_id,
        }
        self.recent_logs.appendleft(entry)
        self._emit("log", entry)
        self._save("log", {**entry, "at": datetime.now(UTC_TZ), "context": {}})

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._on_event({"type": event_type, "data": payload})
        except Exception as exc:
            _log.warning("event_subscriber_failed", error=str(exc)[:200])

    def _save(self, kind: str, payload: Any) -> None:
        if self._persist is None:
            return
        try:
            result = self._persist(kind, payload)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                task.add_done_callback(_swallow_task_error)
        except Exception as exc:
            _log.warning("persist_failed", kind=kind, error=str(exc)[:200])

    def snapshot(self) -> dict[str, Any]:
        """Everything the dashboard needs in one object."""
        portfolio = self._execution.portfolio
        equity = portfolio.equity
        drawdown = (
            0.0 if self.peak_equity <= 0 else (self.peak_equity - equity) / self.peak_equity * 100.0
        )
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "mode": "paper",
            "simulated": True,
            "scenario": {
                "id": self._scenario.id.value,
                "title": self._scenario.title,
                "demonstrates": self._scenario.demonstrates,
                "expected_outcome": self._scenario.expected_outcome,
            },
            "symbols": list(self._config.symbols),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "progress": self.progress,
            "capital": {
                "starting": self._config.initial_capital,
                "equity": equity,
                "cash": portfolio.cash,
                "invested": portfolio.gross_exposure,
                "unrealized_pnl": portfolio.unrealized_pnl,
                "realized_pnl": portfolio.realized_pnl,
                "fees_paid": portfolio.fees_paid,
                "total_pnl": equity - self._config.initial_capital,
                "return_pct": (
                    (equity / self._config.initial_capital - 1.0) * 100.0
                    if self._config.initial_capital
                    else 0.0
                ),
                "max_drawdown_pct": drawdown,
                "peak_equity": self.peak_equity,
            },
            "risk": {
                "mode": self._risk.state.mode.value,
                "kill_switch_reason": self._risk.state.kill_switch_reason,
                "trades_today": self._risk.state.trades_today,
                "new_trades_allowed": self._new_trades_allowed,
                "gross_exposure_pct": (
                    portfolio.gross_exposure / equity * 100.0 if equity > 0 else 0.0
                ),
                "net_exposure_pct": (
                    portfolio.net_exposure / equity * 100.0 if equity > 0 else 0.0
                ),
                "limits": self._risk.limits.model_dump(mode="json"),
            },
            "ai": {
                "provider": self._context.provider_name,
                "enabled": self._config.llm_enabled,
                "assessments": self._context.assessments,
                "neutral": self._context.neutral_assessments,
                "rejections": self._context.rejections,
                "budget": self._context.governor.snapshot().as_dict(),
            },
            "economics": self.economics_snapshot(),
            "counters": self.counters.as_dict(),
            "last_error": self.last_error,
        }

    def learning_report(self) -> dict[str, Any]:
        """What the system has learned from its own closed trades, for the Learning view.

        Observe-only in the demo: it reflects the lessons read from this run's trades but
        does not gate them. ``applies_guardrails`` says so, so the dashboard never implies
        the demo is acting on what it learns.
        """
        report = self._retro.report()
        report["applies_guardrails"] = False
        report["source"] = "demo"
        return report

    def economics_snapshot(self) -> dict[str, Any]:
        """The trade-or-not machinery, as the strategy page shows it.

        Split out from :meth:`snapshot` because the strategy page polls it on its own and
        has no use for the equity curve.
        """
        latest = self.recent_evaluations[0] if self.recent_evaluations else None
        closed = [row["net_bps"] for row in self.closed_trades]
        # The same inputs the decision path last used — never a parallel recomputation.
        # Before any decision has run, the honest inputs are the current portfolio state
        # with volatility unknown, and the snapshot says so via `inputs_from_decision`.
        inputs = self._last_budget_inputs or BudgetInputs(
            equity=self._execution.portfolio.equity,
            peak_equity=self.peak_equity,
            drawdown_pct=(
                0.0
                if self.peak_equity <= 0
                else max(
                    0.0,
                    (self.peak_equity - self._execution.portfolio.equity)
                    / self.peak_equity
                    * 100.0,
                )
            ),
            realised_annual_volatility=0.0,
            consecutive_losses=self._consecutive_losses,
            trades_today=self._risk.state.trades_today,
            open_gross_exposure_pct=0.0,
        )
        budget = self._budget.compute(inputs)
        return {
            "profile": self._budget.profile.model_dump(mode="json"),
            "budget": budget.as_dict(),
            "budget_inputs": {
                "equity": inputs.equity,
                "drawdown_pct": inputs.drawdown_pct,
                "realised_annual_volatility": inputs.realised_annual_volatility,
                "consecutive_losses": inputs.consecutive_losses,
                "trades_today": inputs.trades_today,
                "open_gross_exposure_pct": inputs.open_gross_exposure_pct,
                "inputs_from_decision": self._last_budget_inputs is not None,
            },
            "consecutive_losses": self._consecutive_losses,
            "fees": {
                "maker_bps": self._costs.fees.maker_bps,
                "taker_bps": self._costs.fees.taker_bps,
                "round_trip_taker_bps": self._costs.fees.taker_bps * 2,
                "verified_at_source": self._costs.fees.verified_at_source,
                "source": self._costs.fees.source,
                # Surfaced rather than buried: an unverified fee schedule is the single
                # assumption most able to turn a losing strategy into a winning-looking
                # one, and the activation gate refuses to arm while this is True.
                "requires_verification": self._costs.requires_verification,
            },
            "expected_value": {
                "enforcing": self._config.enforce_expected_value,
                "mode_explanation": (
                    "Enforcing: a signal without a measured edge that clears its costs "
                    "does not become an order."
                    if self._config.enforce_expected_value
                    else "Observing: every decision is priced and recorded, but the trade "
                    "proceeds so its outcome becomes evidence. Paper trading is how the "
                    "edge is measured; enforcing here would deadlock — no trades, so no "
                    "evidence, so no trades. Watch would_reject to see what enforcing "
                    "would cost."
                ),
                "threshold_bps": self._ev.threshold_bps,
                "max_cost_ratio": self._ev.max_cost_ratio,
                "evaluations": self._ev.evaluations,
                "acceptance_rate": round(self._ev.acceptance_rate(), 4),
                "would_reject": self.counters.ev_would_reject,
                "rejected": self.counters.ev_rejected,
                "no_evidence": self.counters.ev_no_evidence,
                "min_samples": self._edges.min_samples,
                "coverage": self._edges.coverage(),
                "latest": latest,
            },
            "closed_trades": {
                "count": len(closed),
                "prior_evidence": self._prior_outcome_count,
                "mean_net_bps": round(sum(closed) / len(closed), 4) if closed else None,
                "wins": sum(1 for value in closed if value > 0),
                "losses": sum(1 for value in closed if value <= 0),
                "recent": list(self.closed_trades)[:20],
            },
        }


def _reference_price(symbol: str) -> float:
    """A plausible starting price per symbol, so the demo does not show every asset at 50k."""
    return {"BTC-USD": 50_000.0, "ETH-USD": 3_000.0, "SPX-IDX": 5_200.0}.get(symbol, 100.0)


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert datetimes so the value can go straight out over SSE as JSON."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
        elif isinstance(value, timedelta):
            out[key] = value.total_seconds()
        else:
            out[key] = value
    return out


def _swallow_task_error(task: asyncio.Task[Any]) -> None:
    """Persistence failures are logged, never raised into the trading loop."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _log.warning("persist_task_failed", error=str(exc)[:300])


__all__ = [
    "CONTEXT_TIMEOUT_SECONDS",
    "Counters",
    "RuntimeConfig",
    "RuntimeEngine",
    "RuntimeState",
    "SymbolStream",
]
