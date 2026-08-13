"""The paper-trading runtime.

This is the pipeline the whole project exists to run, as one loop:

    bar → data quality → features → regime → strategies → fusion
        → context (LLM, advisory only) → Risk Engine → order intent
        → paper execution → fill → position → P&L → persistence → broadcast

Two properties are worth stating because they are what make the loop trustworthy rather
than merely working.

**The fast loop never waits on the slow loop.** The context assessment is fetched with a
timeout, and a timeout produces a neutral assessment rather than a delay. A language model
having a bad minute cannot stall the deterministic pipeline, and cannot change what it
decides beyond removing risk.

**Every refusal is recorded as loudly as every action.** Bars skipped for data quality,
signals that produced NO_TRADE, risk vetoes, orders rejected by the simulator — all of them
are counted, persisted and shown. A dashboard that only displays trades cannot distinguish
a system that is working carefully from one that is broken and silent.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Callable
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
from tia.execution.paper import PaperExecutionProvider
from tia.execution.reconciliation import LedgerSnapshot, ReconciliationEngine
from tia.llm.context import ContextRequest, ContextService
from tia.llm.governance import LLMGovernor
from tia.llm.provider import MockLLMProvider, build_provider
from tia.quant.features import FeatureBuilder, FeatureSet
from tia.regime.classifier import RegimeAssessment, RegimeClassifier
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

        self._record_decision(
            symbol, candle, signal, decision, regime, report, features,
            assessment, context_note, context_used,
        )

        # 5. Act. An opposing signal flattens; otherwise open, if flat and allowed.
        if not decision.allows_execution:
            return

        position = self._execution.portfolio.positions.get(symbol)
        holding = position is not None and not position.is_flat

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

        self._stop_price[symbol] = decision.stop_price or 0.0
        await self._submit(decision, signal, candle)

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
            "counters": self.counters.as_dict(),
            "last_error": self.last_error,
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
