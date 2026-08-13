"""The backtest engine.

**The backtester is the runtime.** It feeds historical bars through the same data-quality
gate, the same feature builder, the same regime classifier, the same strategy engine, the
same Risk Engine and the same execution simulator that a paper run uses. There is no
"backtest version" of any of those components, because a second implementation is a
second set of behaviours that will silently diverge from the first.

The bar loop, in the order that makes look-ahead structurally impossible:

1. Advance the clock to bar *t*'s close. Nothing has seen bar *t* yet.
2. Match resting orders against bar *t*. An order created at bar *t-1*'s close fills at
   bar *t*'s **open** — the first price available after the decision.
3. Build features from ``candles[:t+1]``, a strictly truncated prefix. A feature computed
   at bar *t* cannot reference bar *t+1* because bar *t+1* is not in the list.
4. Quality gate, regime classification, strategies, fusion.
5. Risk Engine. Only it may authorise size.
6. Submit an intent that cannot be matched until bar *t+1*.

Step 3 is the one that matters, and it holds by construction rather than by discipline:
the loop slices its input, so there is no code path in which future data is in scope.

**What this engine does not model.** One symbol at a time and one leg at a time, so
portfolio-level interactions between concurrent positions are out of scope here. Exits
are a protective stop plus the sample-boundary liquidation; there is no take-profit,
trailing stop or time-based exit, because inventing one would be a strategy decision this
engine has no mandate to make. Every cost the paper simulator does not model
(see ``docs/ARCHITECTURE.md`` §12.1) is equally absent from these results.
"""

from __future__ import annotations

from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any, TypeVar

from tia.core.clock import SimulatedClock
from tia.core.config import DataQualityConfig, ExecutionSimConfig, RiskLimits, StrategyConfig
from tia.core.errors import BacktestError, TiaError
from tia.core.ids import content_hash, deterministic_id
from tia.core.logging import get_logger
from tia.core.rng import RngRegistry
from tia.data.quality import DataQualityEngine
from tia.domain.enums import Direction, MarketRegime, OrderType, Side, TimeInForce
from tia.domain.instruments import InstrumentUniverse, Timeframe
from tia.domain.market import Candle, MarketSnapshot
from tia.domain.orders import Fill, OrderIntent
from tia.domain.quality import DataQualityReport
from tia.domain.risk import RiskDecision
from tia.execution.paper import PaperExecutionProvider
from tia.quant.features import FEATURE_VERSION, FeatureBuilder, FeatureSet
from tia.quant.statistics import compute_metrics
from tia.regime.classifier import RegimeAssessment, RegimeClassifier
from tia.risk.engine import RiskEngine
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import build_strategies

from tia.backtest.result import (  # isort: skip
    BacktestConditions,
    BacktestResult,
    ClosedTrade,
    DecisionCounts,
    DecisionRecord,
)

_log = get_logger("backtest.engine")

T = TypeVar("T")

#: Below this, a closed-trade sample cannot separate skill from chance at any confidence
#: worth quoting. Results are still reported — with the caveat attached.
MIN_TRADES_FOR_INFERENCE = 30


@dataclass
class BacktestConfig:
    """Everything that changes what a run produces.

    Hashed into the result's conditions, so two results can be compared for "were these
    the same experiment?" without having to trust a filename.
    """

    dataset: str = "unnamed"
    timeframe: str = "1m"
    initial_capital: float = 100_000.0
    seed: int = 20260812
    warmup_bars: int = 120
    #: Size of the rolling buffer handed to the feature builder and the quality gate.
    #: A live runtime keeps a bounded buffer, not the entire history, so passing the whole
    #: prefix here would make the backtest differ from the thing it is meant to simulate —
    #: and would make the loop quadratic in the number of bars. The longest lookback any
    #: feature uses is the 200-bar SMA, so 300 leaves 100 bars of margin. The indicators
    #: recompute over the whole buffer on every bar, so this value is also the main lever
    #: on how long a run takes.
    lookback_bars: int = 300
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskLimits = field(default_factory=RiskLimits)
    execution: ExecutionSimConfig = field(default_factory=ExecutionSimConfig)
    data_quality: DataQualityConfig = field(default_factory=DataQualityConfig)
    #: Attach a protective stop when an entry fills. Without one, losses are unbounded
    #: and every drawdown figure in the report is an artefact of where the sample ended.
    use_protective_stops: bool = True
    #: Close any position still open at the end of the sample, so the headline result is
    #: realised rather than a mark at an arbitrary cut-off.
    liquidate_at_end: bool = True
    is_out_of_sample: bool = False

    def digest(self) -> str:
        return content_hash(
            {
                "timeframe": self.timeframe,
                "capital": self.initial_capital,
                "seed": self.seed,
                "warmup": self.warmup_bars,
                "lookback": self.lookback_bars,
                "stops": self.use_protective_stops,
                "strategy": self.strategy.model_dump(mode="json"),
                "risk": self.risk.model_dump(mode="json"),
                "execution": self.execution.model_dump(mode="json"),
                "quality": self.data_quality.model_dump(mode="json"),
            }
        )


@dataclass
class _PendingEntry:
    """The decision behind an intent, held until its fill arrives.

    Kept so a closed trade can be traced back to the signal, regime and confidence that
    produced it. A trade list without that provenance can show *what* happened but never
    *why*, which makes it useless for improving anything.
    """

    signal_id: str
    confidence: float
    regime: MarketRegime
    stop_price: float | None
    direction: Direction


@dataclass
class _OpenLeg:
    """The entry side of a round trip, held until the position returns to flat."""

    symbol: str
    direction: Direction
    quantity: float
    entry_price: float
    entry_at: datetime
    entry_bar: int
    fees: float
    signal_id: str
    confidence: float
    regime: MarketRegime
    stop_price: float | None


class BacktestEngine:
    """Runs one experiment over one symbol's bars."""

    def __init__(
        self,
        config: BacktestConfig,
        universe: InstrumentUniverse,
        *,
        strategies: Sequence[str] | None = None,
    ) -> None:
        self._config = config
        self._universe = universe
        self._strategy_names = tuple(strategies or config.strategy.enabled)

    @property
    def config(self) -> BacktestConfig:
        return self._config

    def run(self, candles: Sequence[Candle], *, symbol: str | None = None) -> BacktestResult:
        """Execute the bar loop and return the complete record."""
        bars = list(candles)
        if len(bars) < 2:
            raise BacktestError("a backtest needs at least two bars", bars=len(bars))

        resolved = symbol or bars[0].symbol
        if any(candle.symbol != resolved for candle in bars):
            raise BacktestError(
                "this engine runs one symbol at a time; the input mixes several",
                symbol=resolved,
            )
        _assert_chronological(bars)

        cfg = self._config
        timeframe = Timeframe.parse(cfg.timeframe)
        clock = SimulatedClock(bars[0].open_time)
        rng = RngRegistry(cfg.seed)

        quality_engine = DataQualityEngine(cfg.data_quality)
        feature_builder = FeatureBuilder()
        regime_classifier = RegimeClassifier()
        strategy_engine = StrategyEngine(
            build_strategies(self._strategy_names), cfg.strategy, clock
        )
        risk_engine = RiskEngine(cfg.risk, self._universe, clock)
        provider = PaperExecutionProvider(
            cfg.execution, self._universe, clock, rng, initial_capital=cfg.initial_capital
        )

        counts = _MutableCounts()
        equity: list[float] = []
        stamps: list[datetime] = []
        closed: list[ClosedTrade] = []
        decision_log: list[DecisionRecord] = []
        warnings: list[str] = []

        leg: _OpenLeg | None = None
        pending: _PendingEntry | None = None
        stop_order_id: str | None = None
        bars_in_market = 0
        warmup = max(cfg.warmup_bars, feature_builder.min_bars)

        for index, candle in enumerate(bars):
            clock.advance_to(candle.close_time)
            counts.bars_processed += 1

            # --- 2. match what was already resting ---------------------------
            fills = provider.on_bar(candle)
            counts.fills += len(fills)
            for fill in fills:
                risk_engine.record_execution(fill.symbol, fill.filled_at)

            portfolio = provider.portfolio
            position = portfolio.positions.get(resolved)
            flat = position is None or position.is_flat

            if fills:
                leg, finished = _fold_fills(fills, leg, index, pending)
                closed.extend(finished)
                if flat:
                    leg = None
                    pending = None

            # Keep the protective stop in step with the position: cancelled when flat,
            # resized when a partial fill changed the quantity it is meant to cover.
            if cfg.use_protective_stops:
                stop_order_id = self._sync_protective_stop(
                    provider, leg, stop_order_id, counts
                )

            if not flat:
                bars_in_market += 1

            equity.append(portfolio.equity)
            stamps.append(candle.close_time)

            # --- 3. decide, using only bars up to and including this one -----
            if index + 1 < warmup:
                counts.bars_skipped_insufficient_history += 1
                continue
            if index == len(bars) - 1:
                # No bar remains to execute against, so a decision here could only
                # inflate the signal counts with proposals nothing could act on.
                continue

            # A bounded, backward-looking slice: the same buffer a live runtime holds.
            window = bars[max(0, index + 1 - cfg.lookback_bars) : index + 1]
            report = quality_engine.evaluate(
                symbol=resolved,
                timeframe=cfg.timeframe,
                candles=window,
                now=candle.close_time,
                last_feed_message_at=candle.close_time,
            )
            if report.hard_fail:
                counts.bars_skipped_data_quality += 1
                continue

            features = feature_builder.build(resolved, cfg.timeframe, window)
            regime = regime_classifier.classify(features, now=candle.close_time)

            signal, _fusion = strategy_engine.evaluate(
                features=features,
                regime=regime,
                quality=report,
                snapshot=self._snapshot(candle, features, regime, provider, report),
                correlation_id=f"bt-{index:06d}",
            )
            counts.signals_generated += 1
            counts.count_direction(signal.direction.value)

            decision = risk_engine.evaluate(
                signal=signal,
                portfolio=portfolio,
                features=features,
                quality=report,
                now=candle.close_time,
            )
            counts.count_verdict(decision)
            decision_log.append(
                DecisionRecord(
                    bar_close_time=candle.close_time,
                    direction=signal.direction,
                    confidence=signal.confidence,
                    verdict=decision.verdict,
                    approved_quantity=decision.approved_quantity,
                    regime=regime.regime,
                    feature_hash=features.feature_hash,
                    signal_id=signal.signal_id,
                )
            )

            if not decision.allows_execution:
                continue
            if not flat:
                # An approved entry while already positioned would pyramid. The Risk
                # Engine's position limits govern that in general; this engine trades one
                # leg at a time so every round trip in the report is unambiguous. Counted
                # because the gap between "approved" and "submitted" is otherwise
                # invisible, and it is usually large.
                counts.approvals_suppressed_position_open += 1
                continue

            pending = _PendingEntry(
                signal_id=signal.signal_id,
                confidence=signal.confidence,
                regime=regime.regime,
                stop_price=decision.stop_price,
                direction=signal.direction,
            )
            order = _sync(provider.submit_order(self._to_intent(decision, signal.direction)))
            counts.intents_submitted += 1
            if order.state.is_terminal:
                counts.orders_rejected += 1
                pending = None

        # --- close the book ---------------------------------------------------
        if cfg.liquidate_at_end and leg is not None:
            if stop_order_id is not None:
                _sync(provider.cancel_order(stop_order_id))
                stop_order_id = None
            trade, note = self._liquidate(provider, bars[-1], leg, len(bars) - 1)
            closed.append(trade)
            warnings.append(note)
            leg = None
            equity[-1] = provider.portfolio.equity

        open_at_end = {
            s: p.quantity for s, p in provider.portfolio.positions.items() if not p.is_flat
        }
        if open_at_end:
            warnings.append(
                "positions were still open when the sample ended; the final equity "
                "includes an unrealised mark, not a realised result"
            )

        metrics = compute_metrics(
            equity_curve=equity,
            trades=[t.to_record() for t in closed],
            periods_per_year=timeframe.bars_per_year(),
            bars_in_market=bars_in_market,
        )
        warnings.extend(_sample_warnings(closed, bars))

        conditions = BacktestConditions(
            run_id=deterministic_id("bt", cfg.dataset, resolved, cfg.digest()),
            dataset=cfg.dataset,
            symbols=(resolved,),
            timeframe=cfg.timeframe,
            start=bars[0].open_time,
            end=bars[-1].close_time,
            bars=len(bars),
            initial_capital=cfg.initial_capital,
            seed=cfg.seed,
            strategy_versions=strategy_engine.strategy_versions(),
            feature_version=FEATURE_VERSION,
            risk_limits_digest=content_hash(cfg.risk.model_dump(mode="json")),
            execution_config=cfg.execution.model_dump(mode="json"),
            is_out_of_sample=cfg.is_out_of_sample,
        )

        _log.info(
            "backtest_complete",
            run_id=conditions.run_id,
            bars=len(bars),
            trades=len(closed),
            final_equity=round(equity[-1], 2) if equity else 0.0,
        )

        return BacktestResult(
            conditions=conditions,
            metrics=metrics,
            equity_curve=tuple(equity),
            equity_timestamps=tuple(stamps),
            trades=tuple(closed),
            decisions=counts.freeze(),
            decision_log=tuple(decision_log),
            open_positions_at_end=open_at_end,
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------ helpers

    def _snapshot(
        self,
        candle: Candle,
        features: FeatureSet,
        regime: RegimeAssessment,
        provider: PaperExecutionProvider,
        report: DataQualityReport,
    ) -> MarketSnapshot:
        portfolio = provider.portfolio
        return MarketSnapshot(
            taken_at=candle.close_time,
            symbol=candle.symbol,
            timeframe=self._config.timeframe,
            last_close=candle.close,
            last_candle_open_time=candle.open_time,
            features=dict(features.values),
            regime=regime.regime,
            volatility=features.get("atr_pct", 0.0),
            data_quality_score=report.quality_score,
            data_freshness_score=report.freshness_score,
            open_positions=portfolio.snapshot_exposures(),
            gross_exposure=portfolio.gross_exposure,
            net_exposure=portfolio.net_exposure,
            available_capital=portfolio.available_capital(),
            equity=portfolio.equity,
        )

    @staticmethod
    def _to_intent(decision: RiskDecision, direction: Direction) -> OrderIntent:
        side = direction.to_side()
        return OrderIntent(
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

    def _sync_protective_stop(
        self,
        provider: PaperExecutionProvider,
        leg: _OpenLeg | None,
        current_id: str | None,
        counts: _MutableCounts,
    ) -> str | None:
        """Keep exactly one protective stop matching the open leg.

        Cancelled when the position is flat, replaced when a partial fill changed the
        quantity it covers. A stop that protects the wrong size is worse than none,
        because the report will show a bounded loss that was not actually bounded.
        """
        if leg is None or leg.stop_price is None:
            if current_id is not None:
                _sync(provider.cancel_order(current_id))
            return None

        existing = _sync(provider.get_order(current_id)) if current_id else None
        if existing is not None and not existing.state.is_terminal:
            covered = existing.quantity - existing.filled_quantity
            if abs(covered - leg.quantity) <= max(leg.quantity * 1e-6, 1e-9):
                return current_id
            _sync(provider.cancel_order(current_id))

        side = Side.SELL if leg.direction is Direction.LONG else Side.BUY
        intent = OrderIntent(
            intent_id=deterministic_id("int", "stop", leg.signal_id, leg.quantity),
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"{leg.signal_id}:protective",
                symbol=leg.symbol,
                side=side,
                quantity=leg.quantity,
                order_type=OrderType.STOP,
            ),
            signal_id=leg.signal_id,
            risk_decision_id=f"protective:{leg.signal_id}",
            symbol=leg.symbol,
            side=side,
            quantity=leg.quantity,
            order_type=OrderType.STOP,
            stop_price=leg.stop_price,
            time_in_force=TimeInForce.GTC,
            created_at=leg.entry_at,
        )
        try:
            order = _sync(provider.submit_order(intent))
        except (TiaError, ValueError) as exc:
            # A stop the venue will not accept is a real outcome, and the honest
            # response is to record that the position is unprotected rather than to
            # pretend the order exists.
            _log.warning(
                "protective_stop_rejected", symbol=leg.symbol, error=str(exc)
            )
            counts.protective_stops_unplaced += 1
            return None
        if order.state.is_terminal:
            counts.protective_stops_unplaced += 1
            return None
        return order.order_id

    def _liquidate(
        self,
        provider: PaperExecutionProvider,
        last: Candle,
        leg: _OpenLeg,
        bar_index: int,
    ) -> tuple[ClosedTrade, str]:
        """Close the open leg at the last bar's close, marked as a forced exit.

        Reporting an open position's mark as though it were a result lets a losing trade
        sit unrealised at the edge of the sample and quietly improve every metric that
        depends on realised P&L. Closing it costs a taker fee and the base slippage,
        charged here because a forced exit is never a maker and never free.

        This is still an assumption: the strategy did not choose this exit, and in a real
        session the close is not a price you can reliably transact at.
        """
        costs = self._config.execution
        direction_sign = 1.0 if leg.direction is Direction.LONG else -1.0
        exit_price = last.close * (1.0 - direction_sign * costs.base_slippage_bps / 10_000.0)
        exit_price = max(last.low, min(last.high, exit_price))

        gross = direction_sign * leg.quantity * (exit_price - leg.entry_price)
        fee = abs(leg.quantity * exit_price) * costs.taker_fee_bps / 10_000.0
        notional = leg.entry_price * leg.quantity

        closing_fill = Fill(
            fill_id=deterministic_id("fill", "liquidation", leg.signal_id, last.close_time),
            order_id=deterministic_id("ord", "liquidation", leg.signal_id),
            sequence=0,
            symbol=leg.symbol,
            side=Side.SELL if leg.direction is Direction.LONG else Side.BUY,
            quantity=leg.quantity,
            price=exit_price,
            fee=fee,
            liquidity="taker",
            filled_at=last.close_time,
        )
        provider.portfolio.apply_fill(closing_fill)

        trade = ClosedTrade(
            trade_id=deterministic_id("trade", closing_fill.fill_id),
            symbol=leg.symbol,
            direction=leg.direction,
            quantity=leg.quantity,
            entry_price=leg.entry_price,
            exit_price=exit_price,
            entry_at=leg.entry_at,
            exit_at=closing_fill.filled_at,
            gross_pnl=gross,
            fees=leg.fees + fee,
            net_pnl=gross - leg.fees - fee,
            return_pct=((gross - leg.fees - fee) / notional * 100.0) if notional > 0 else 0.0,
            bars_held=max(0, bar_index - leg.entry_bar),
            exit_reason="forced liquidation at end of sample",
            regime_at_entry=leg.regime,
            signal_id=leg.signal_id,
            confidence=leg.confidence,
        )
        return (
            trade,
            "an open position was force-closed at the final bar's close; that exit was "
            "chosen by the sample boundary, not by the strategy",
        )


# --------------------------------------------------------------------------- free helpers


def _assert_chronological(bars: list[Candle]) -> None:
    """Out-of-order bars would let a "past" bar carry future information.

    Checked rather than assumed: a CSV sorted as strings, or a provider that pages
    backwards, produces exactly this, and the resulting backtest looks entirely fine.
    """
    for previous, current in pairwise(bars):
        if current.open_time <= previous.open_time:
            raise BacktestError(
                "bars are not strictly chronological",
                previous=previous.open_time.isoformat(),
                current=current.open_time.isoformat(),
            )


def _fold_fills(
    fills: list[Fill],
    leg: _OpenLeg | None,
    bar_index: int,
    pending: _PendingEntry | None,
) -> tuple[_OpenLeg | None, list[ClosedTrade]]:
    """Turn a bar's fills into an open leg and any completed round trips."""
    finished: list[ClosedTrade] = []
    for fill in fills:
        if leg is None:
            leg = _OpenLeg(
                symbol=fill.symbol,
                direction=Direction.LONG if fill.side is Side.BUY else Direction.SHORT,
                quantity=fill.quantity,
                entry_price=fill.price,
                entry_at=fill.filled_at,
                entry_bar=bar_index,
                fees=fill.fee,
                signal_id=pending.signal_id if pending else "",
                confidence=pending.confidence if pending else 0.0,
                regime=pending.regime if pending else MarketRegime.UNKNOWN,
                stop_price=pending.stop_price if pending else None,
            )
            continue

        adding = (leg.direction is Direction.LONG) == (fill.side is Side.BUY)
        if adding:
            total = leg.quantity + fill.quantity
            leg.entry_price = (
                leg.entry_price * leg.quantity + fill.price * fill.quantity
            ) / total
            leg.quantity = total
            leg.fees += fill.fee
            continue

        closing = min(fill.quantity, leg.quantity)
        direction_sign = 1.0 if leg.direction is Direction.LONG else -1.0
        gross = direction_sign * closing * (fill.price - leg.entry_price)
        entry_fee_share = leg.fees * (closing / leg.quantity) if leg.quantity > 0 else 0.0
        fees = entry_fee_share + fill.fee * (closing / fill.quantity)
        notional = leg.entry_price * closing

        finished.append(
            ClosedTrade(
                trade_id=deterministic_id("trade", fill.fill_id, closing),
                symbol=leg.symbol,
                direction=leg.direction,
                quantity=closing,
                entry_price=leg.entry_price,
                exit_price=fill.price,
                entry_at=leg.entry_at,
                exit_at=fill.filled_at,
                gross_pnl=gross,
                fees=fees,
                net_pnl=gross - fees,
                return_pct=((gross - fees) / notional * 100.0) if notional > 0 else 0.0,
                bars_held=max(0, bar_index - leg.entry_bar),
                exit_reason="protective stop or reversing fill",
                regime_at_entry=leg.regime,
                signal_id=leg.signal_id,
                confidence=leg.confidence,
            )
        )
        leg.quantity -= closing
        leg.fees -= entry_fee_share
        if leg.quantity <= max(leg.quantity * 1e-9, 1e-12):
            leg = None

    return leg, finished


def _sample_warnings(trades: list[ClosedTrade], bars: list[Candle]) -> list[str]:
    """Say plainly when the experiment cannot support a conclusion."""
    out: list[str] = []
    if len(trades) < MIN_TRADES_FOR_INFERENCE:
        out.append(
            f"only {len(trades)} closed trades; too few to separate skill from chance "
            "at any confidence worth quoting"
        )
    span = bars[-1].close_time - bars[0].open_time
    if span < timedelta(days=30):
        out.append(
            f"the sample covers {span.days} days, which is unlikely to contain more "
            "than one market regime"
        )
    return out


def _sync(coroutine: Coroutine[Any, Any, T]) -> T:
    """Drive a non-awaiting coroutine to completion from the synchronous bar loop.

    The execution provider's methods are ``async`` because the interface they implement
    is, not because they wait for anything: the paper simulator performs no I/O. Stepping
    the coroutine directly keeps the backtest an ordinary loop instead of dragging an
    event loop into a computation with nothing to await — and if an implementation ever
    does suspend, this raises rather than silently returning a half-finished result.
    """
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value  # type: ignore[no-any-return]
    coroutine.close()
    raise BacktestError(
        "the execution provider suspended on a real await; the backtest loop requires "
        "simulated submission to complete synchronously"
    )


@dataclass
class _MutableCounts:
    """Accumulator for the frozen :class:`DecisionCounts`."""

    bars_processed: int = 0
    bars_skipped_insufficient_history: int = 0
    bars_skipped_data_quality: int = 0
    signals_generated: int = 0
    signals_by_direction: dict[str, int] = field(default_factory=dict)
    risk_verdicts: dict[str, int] = field(default_factory=dict)
    risk_rejection_reasons: dict[str, int] = field(default_factory=dict)
    intents_submitted: int = 0
    orders_rejected: int = 0
    orders_expired: int = 0
    fills: int = 0
    protective_stops_unplaced: int = 0
    approvals_suppressed_position_open: int = 0

    def count_direction(self, direction: str) -> None:
        self.signals_by_direction[direction] = self.signals_by_direction.get(direction, 0) + 1

    def count_verdict(self, decision: RiskDecision) -> None:
        verdict = decision.verdict.value
        self.risk_verdicts[verdict] = self.risk_verdicts.get(verdict, 0) + 1
        # Bucketed by failed *check name*, not by the free-text reason: the reasons embed
        # the actual numbers ("confidence 0.182 below minimum 0.550"), so counting them
        # produces one bucket per bar and tells you nothing about which gate is binding.
        for check in decision.failed_checks():
            self.risk_rejection_reasons[check.name] = (
                self.risk_rejection_reasons.get(check.name, 0) + 1
            )

    def freeze(self) -> DecisionCounts:
        return DecisionCounts(
            bars_processed=self.bars_processed,
            bars_skipped_insufficient_history=self.bars_skipped_insufficient_history,
            bars_skipped_data_quality=self.bars_skipped_data_quality,
            signals_generated=self.signals_generated,
            signals_by_direction=dict(self.signals_by_direction),
            risk_verdicts=dict(self.risk_verdicts),
            risk_rejection_reasons=dict(self.risk_rejection_reasons),
            intents_submitted=self.intents_submitted,
            orders_rejected=self.orders_rejected,
            orders_expired=self.orders_expired,
            fills=self.fills,
            protective_stops_unplaced=self.protective_stops_unplaced,
            approvals_suppressed_position_open=self.approvals_suppressed_position_open,
        )


__all__ = ["MIN_TRADES_FOR_INFERENCE", "BacktestConfig", "BacktestEngine"]
