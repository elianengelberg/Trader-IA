"""The Risk Engine.

Deterministic, pure where it can be, and holding **absolute veto**. Nothing downstream
may override it, and nothing upstream — including any language model — may raise a limit,
increase a size, or bypass a check. The engine's only powers are to approve, to shrink,
or to refuse.

Three properties the tests enforce mechanically:

1. **It may only shrink.** ``approved_quantity <= requested_quantity``, always. An engine
   that could grow a request would be a second, unreviewed sizing model.
2. **Every check is recorded**, passed or failed, with observed value and limit. A
   rejection that says only "risk limit" is unauditable six months later; one that says
   "gross exposure 118% against a 100% limit" is actionable.
3. **Checks run in a fixed order**, cheapest and most absolute first, so a kill switch or
   a data-quality failure short-circuits before any arithmetic happens.

The engine keeps a small amount of state — trade counts, cooldowns, the kill switch —
because frequency limits and circuit breakers are inherently stateful. That state is
explicit and inspectable rather than hidden in a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tia.core.clock import Clock, ensure_utc
from tia.core.config import RiskLimits
from tia.core.ids import deterministic_id
from tia.core.logging import get_logger
from tia.domain.enums import Direction, RiskVerdict, SystemMode
from tia.domain.instruments import InstrumentUniverse
from tia.domain.portfolio import PortfolioState
from tia.domain.quality import DataQualityReport
from tia.domain.risk import PositionSizing, RiskCheck, RiskDecision
from tia.domain.signals import SignalCandidate
from tia.quant.features import FeatureSet
from tia.risk.sizing import compute_size

_log = get_logger("risk.engine")


@dataclass
class RiskState:
    """Mutable state the engine needs: counters, cooldowns and breakers."""

    mode: SystemMode = SystemMode.NORMAL
    kill_switch_reason: str = ""
    current_day: str = ""
    trades_today: int = 0
    trades_today_by_symbol: dict[str, int] = field(default_factory=dict)
    last_trade_at: dict[str, datetime] = field(default_factory=dict)
    breaker_tripped_at: datetime | None = None
    breaker_reason: str = ""

    def roll_day(self, moment: datetime) -> None:
        day = moment.date().isoformat()
        if day != self.current_day:
            self.current_day = day
            self.trades_today = 0
            self.trades_today_by_symbol.clear()

    def record_trade(self, symbol: str, moment: datetime) -> None:
        self.roll_day(moment)
        self.trades_today += 1
        self.trades_today_by_symbol[symbol] = self.trades_today_by_symbol.get(symbol, 0) + 1
        self.last_trade_at[symbol] = moment

    @property
    def is_halted(self) -> bool:
        return self.mode in {SystemMode.SAFE_MODE, SystemMode.HALTED}


class RiskEngine:
    """Evaluates a signal against every configured limit."""

    def __init__(
        self,
        limits: RiskLimits,
        universe: InstrumentUniverse,
        clock: Clock,
        *,
        state: RiskState | None = None,
    ) -> None:
        self._limits = limits
        self._universe = universe
        self._clock = clock
        self._state = state or RiskState()

    @property
    def limits(self) -> RiskLimits:
        """Read-only. ``RiskLimits`` raises on any attempt to mutate it."""
        return self._limits

    @property
    def state(self) -> RiskState:
        return self._state

    # ------------------------------------------------------------------ control

    def engage_kill_switch(self, reason: str) -> None:
        """Halt all new risk. Reversible only by an explicit operator action."""
        self._state.mode = SystemMode.HALTED
        self._state.kill_switch_reason = reason
        _log.critical("kill_switch_engaged", reason=reason)

    def enter_safe_mode(self, reason: str) -> None:
        self._state.mode = SystemMode.SAFE_MODE
        self._state.kill_switch_reason = reason
        _log.error("safe_mode_entered", reason=reason)

    def resume(self, *, approved_by: str) -> None:
        """Return to normal operation. Deliberately requires naming who approved it."""
        _log.warning(
            "risk_engine_resumed",
            previous_mode=self._state.mode.value,
            previous_reason=self._state.kill_switch_reason,
            approved_by=approved_by,
        )
        self._state.mode = SystemMode.NORMAL
        self._state.kill_switch_reason = ""
        self._state.breaker_tripped_at = None
        self._state.breaker_reason = ""

    def record_execution(self, symbol: str, at: datetime) -> None:
        """Called after a fill so frequency limits and cooldowns stay accurate."""
        self._state.record_trade(symbol, ensure_utc(at))

    # ------------------------------------------------------------------ evaluation

    def evaluate(
        self,
        *,
        signal: SignalCandidate,
        portfolio: PortfolioState,
        features: FeatureSet | None = None,
        quality: DataQualityReport | None = None,
        spread_bps: float | None = None,
        correlations: dict[tuple[str, str], float] | None = None,
        now: datetime | None = None,
    ) -> RiskDecision:
        moment = ensure_utc(now) if now else self._clock.now()
        self._state.roll_day(moment)

        checks: list[RiskCheck] = []
        reasons: list[str] = []
        sizing: PositionSizing | None = None

        def decide(verdict: RiskVerdict, quantity: float = 0.0) -> RiskDecision:
            return RiskDecision(
                decision_id=deterministic_id("rd", signal.signal_id, moment, verdict.value),
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                verdict=verdict,
                approved_quantity=quantity,
                requested_quantity=sizing.raw_quantity if sizing else 0.0,
                decided_at=moment,
                checks=tuple(checks),
                sizing=sizing,
                reasons=tuple(reasons),
                stop_price=signal.stop_reference,
                target_price=signal.target_reference,
                correlation_id=signal.correlation_id,
            )

        # --- 1. system state -------------------------------------------------
        halted = self._state.is_halted
        checks.append(
            RiskCheck(
                name="system_mode",
                passed=not halted,
                detail=self._state.kill_switch_reason if halted else self._state.mode.value,
                action="reject_all" if halted else "",
            )
        )
        if halted:
            reasons.append(f"system halted: {self._state.kill_switch_reason}")
            return decide(RiskVerdict.NO_TRADE)

        # --- 2. is there anything to approve? --------------------------------
        actionable = signal.direction.is_actionable
        checks.append(
            RiskCheck(
                name="signal_actionable",
                passed=actionable,
                detail=signal.direction.value,
            )
        )
        if not actionable:
            reasons.append(f"signal direction is {signal.direction.value}")
            return decide(RiskVerdict.NO_TRADE)

        # --- 3. signal freshness ---------------------------------------------
        expired = signal.is_expired_at(moment)
        age = (moment - signal.created_at).total_seconds()
        checks.append(
            RiskCheck(
                name="signal_ttl",
                passed=not expired,
                observed=age,
                limit=signal.ttl_seconds(),
                action="reject" if expired else "",
                detail="acting on an expired signal means acting on a market that has moved",
            )
        )
        if expired:
            reasons.append(f"signal expired {age - signal.ttl_seconds():.0f}s ago")
            return decide(RiskVerdict.NO_TRADE)

        # --- 4. data quality --------------------------------------------------
        dq_ok = self._check_data_quality(checks, quality, signal)
        if not dq_ok:
            reasons.append("data quality below the threshold required to take risk")
            return decide(RiskVerdict.NO_TRADE)

        # --- 5. confidence ----------------------------------------------------
        confident = signal.confidence >= self._limits.min_confidence
        checks.append(
            RiskCheck(
                name="min_confidence",
                passed=confident,
                observed=signal.confidence,
                limit=self._limits.min_confidence,
            )
        )
        if not confident:
            reasons.append(
                f"confidence {signal.confidence:.3f} below minimum {self._limits.min_confidence:.3f}"
            )
            return decide(RiskVerdict.REJECTED)

        # --- 6. instrument ----------------------------------------------------
        instrument = self._universe.get(signal.symbol)
        checks.append(
            RiskCheck(
                name="instrument_known",
                passed=instrument is not None,
                detail=signal.symbol,
            )
        )
        if instrument is None:
            reasons.append(f"unknown instrument {signal.symbol}")
            return decide(RiskVerdict.REJECTED)

        if signal.direction is Direction.SHORT:
            checks.append(
                RiskCheck(name="shortable", passed=instrument.shortable, detail=signal.symbol)
            )
            if not instrument.shortable:
                reasons.append(f"{signal.symbol} may not be sold short")
                return decide(RiskVerdict.REJECTED)

        # --- 7. circuit breakers ---------------------------------------------
        if not self._check_breakers(checks, portfolio, moment, reasons):
            return decide(RiskVerdict.NO_TRADE)

        # --- 8. market conditions --------------------------------------------
        if not self._check_market_conditions(checks, features, spread_bps, reasons):
            return decide(RiskVerdict.REJECTED)

        # --- 9. frequency -----------------------------------------------------
        if not self._check_frequency(checks, signal.symbol, moment, reasons):
            return decide(RiskVerdict.REJECTED)

        # --- 10. sizing --------------------------------------------------------
        sizing = compute_size(
            equity=portfolio.equity,
            entry_price=signal.entry_reference,
            stop_price=signal.stop_reference,
            direction=signal.direction,
            instrument=instrument,
            risk_per_trade_pct=self._limits.max_risk_per_trade_pct,
            max_position_notional_pct=self._limits.max_position_notional_pct,
            available_capital=portfolio.available_capital(),
        )
        sized = sizing.quantity_after_limits > 0
        checks.append(
            RiskCheck(
                name="position_sizing",
                passed=sized,
                observed=sizing.quantity_after_limits,
                limit=sizing.raw_quantity,
                action=sizing.limiting_constraint,
                detail=f"risk budget {sizing.risk_budget_currency:.2f} over stop distance "
                f"{sizing.stop_distance:.6f}",
            )
        )
        if not sized:
            reasons.append(f"position cannot be sized: {sizing.limiting_constraint}")
            return decide(RiskVerdict.REJECTED)

        # --- 11. portfolio limits ---------------------------------------------
        quantity = sizing.quantity_after_limits
        quantity, reduced = self._apply_portfolio_limits(
            checks=checks,
            reasons=reasons,
            quantity=quantity,
            price=signal.entry_reference,
            direction=signal.direction,
            symbol=signal.symbol,
            portfolio=portfolio,
            correlations=correlations or {},
        )

        if quantity <= 0:
            return decide(RiskVerdict.REJECTED)

        quantity = instrument.round_quantity(quantity)
        if quantity <= 0 or quantity * signal.entry_reference < instrument.min_notional:
            checks.append(
                RiskCheck(
                    name="min_notional_after_limits",
                    passed=False,
                    observed=quantity * signal.entry_reference,
                    limit=instrument.min_notional,
                    action="reject",
                )
            )
            reasons.append("size after limits falls below the instrument's minimum notional")
            return decide(RiskVerdict.REJECTED)

        # The engine may only shrink. Asserted here rather than assumed, because a bug
        # that grew a size would be both silent and expensive.
        if quantity > sizing.raw_quantity + 1e-9:
            _log.critical(
                "risk_engine_would_have_grown_a_position",
                requested=sizing.raw_quantity,
                approved=quantity,
            )
            reasons.append("internal error: approved size exceeded the requested size")
            return decide(RiskVerdict.REJECTED)

        verdict = RiskVerdict.REDUCED_SIZE if reduced else RiskVerdict.APPROVED
        if reduced:
            reasons.append(
                f"size reduced from {sizing.quantity_after_limits:.8f} to {quantity:.8f} "
                "by portfolio limits"
            )
        return decide(verdict, quantity)

    # ------------------------------------------------------------------ checks

    def _check_data_quality(
        self, checks: list[RiskCheck], quality: DataQualityReport | None, signal: SignalCandidate
    ) -> bool:
        if quality is None:
            # The signal carries its own copies; use them rather than assuming the data
            # was fine because no report was supplied.
            score, freshness, hard_fail = (
                signal.data_quality_score,
                signal.data_freshness_score,
                False,
            )
        else:
            score, freshness, hard_fail = (
                quality.quality_score,
                quality.freshness_score,
                quality.hard_fail,
            )

        checks.append(
            RiskCheck(
                name="data_quality_hard_fail",
                passed=not hard_fail,
                detail=quality.reason() if quality else "no report supplied",
                action="reject" if hard_fail else "",
            )
        )
        quality_ok = score >= self._limits.min_data_quality_score
        checks.append(
            RiskCheck(
                name="data_quality_score",
                passed=quality_ok,
                observed=score,
                limit=self._limits.min_data_quality_score,
            )
        )
        freshness_ok = freshness >= self._limits.min_freshness_score
        checks.append(
            RiskCheck(
                name="data_freshness_score",
                passed=freshness_ok,
                observed=freshness,
                limit=self._limits.min_freshness_score,
            )
        )
        return not hard_fail and quality_ok and freshness_ok

    def _check_breakers(
        self,
        checks: list[RiskCheck],
        portfolio: PortfolioState,
        moment: datetime,
        reasons: list[str],
    ) -> bool:
        drawdown = portfolio.drawdown_pct
        dd_ok = drawdown < self._limits.max_drawdown_pct
        checks.append(
            RiskCheck(
                name="max_drawdown_breaker",
                passed=dd_ok,
                observed=drawdown,
                limit=self._limits.max_drawdown_pct,
                action="halt" if not dd_ok else "",
            )
        )
        if not dd_ok:
            # A drawdown breach is not a per-signal rejection: it stops the system. The
            # next signal must not be evaluated as though nothing happened.
            self._state.breaker_tripped_at = moment
            self._state.breaker_reason = (
                f"max drawdown {drawdown:.2f}% >= {self._limits.max_drawdown_pct:.2f}%"
            )
            self.enter_safe_mode(self._state.breaker_reason)
            reasons.append(self._state.breaker_reason)
            return False

        day_pnl = portfolio.day_pnl_pct
        daily_ok = day_pnl > -self._limits.daily_loss_limit_pct
        checks.append(
            RiskCheck(
                name="daily_loss_limit",
                passed=daily_ok,
                observed=day_pnl,
                limit=-self._limits.daily_loss_limit_pct,
                action="no_new_risk_today" if not daily_ok else "",
            )
        )
        if not daily_ok:
            reasons.append(
                f"daily loss {day_pnl:.2f}% breached the {self._limits.daily_loss_limit_pct:.2f}% limit"
            )
            return False
        return True

    def _check_market_conditions(
        self,
        checks: list[RiskCheck],
        features: FeatureSet | None,
        spread_bps: float | None,
        reasons: list[str],
    ) -> bool:
        if spread_bps is not None:
            ok = spread_bps <= self._limits.max_spread_bps
            checks.append(
                RiskCheck(
                    name="max_spread",
                    passed=ok,
                    observed=spread_bps,
                    limit=self._limits.max_spread_bps,
                )
            )
            if not ok:
                reasons.append(f"spread {spread_bps:.1f} bps exceeds the limit")
                return False

        if features is None:
            return True

        volume = features.get("volume")
        if self._limits.min_bar_volume > 0 and volume == volume:  # not NaN
            ok = volume >= self._limits.min_bar_volume
            checks.append(
                RiskCheck(
                    name="min_liquidity",
                    passed=ok,
                    observed=volume,
                    limit=self._limits.min_bar_volume,
                )
            )
            if not ok:
                reasons.append(f"bar volume {volume:.2f} below the liquidity floor")
                return False

        vol_pct = features.get("vol_percentile_100")
        if vol_pct == vol_pct:  # not NaN
            ok = vol_pct <= self._limits.max_volatility_percentile
            checks.append(
                RiskCheck(
                    name="max_volatility_percentile",
                    passed=ok,
                    observed=vol_pct,
                    limit=self._limits.max_volatility_percentile,
                )
            )
            if not ok:
                reasons.append(
                    f"volatility at the {vol_pct:.1%} percentile exceeds the "
                    f"{self._limits.max_volatility_percentile:.1%} limit"
                )
                return False
        return True

    def _check_frequency(
        self, checks: list[RiskCheck], symbol: str, moment: datetime, reasons: list[str]
    ) -> bool:
        daily_ok = self._state.trades_today < self._limits.max_trades_per_day
        checks.append(
            RiskCheck(
                name="max_trades_per_day",
                passed=daily_ok,
                observed=float(self._state.trades_today),
                limit=float(self._limits.max_trades_per_day),
            )
        )
        if not daily_ok:
            reasons.append("daily trade count limit reached")
            return False

        symbol_count = self._state.trades_today_by_symbol.get(symbol, 0)
        symbol_ok = symbol_count < self._limits.max_trades_per_symbol_per_day
        checks.append(
            RiskCheck(
                name="max_trades_per_symbol_per_day",
                passed=symbol_ok,
                observed=float(symbol_count),
                limit=float(self._limits.max_trades_per_symbol_per_day),
            )
        )
        if not symbol_ok:
            reasons.append(f"per-symbol daily trade limit reached for {symbol}")
            return False

        last = self._state.last_trade_at.get(symbol)
        if last is not None and self._limits.trade_cooldown_seconds > 0:
            elapsed = (moment - last).total_seconds()
            cooldown_ok = elapsed >= self._limits.trade_cooldown_seconds
            checks.append(
                RiskCheck(
                    name="trade_cooldown",
                    passed=cooldown_ok,
                    observed=elapsed,
                    limit=float(self._limits.trade_cooldown_seconds),
                )
            )
            if not cooldown_ok:
                reasons.append(
                    f"cooldown active on {symbol}: {elapsed:.0f}s of "
                    f"{self._limits.trade_cooldown_seconds}s elapsed"
                )
                return False
        return True

    def _apply_portfolio_limits(
        self,
        *,
        checks: list[RiskCheck],
        reasons: list[str],
        quantity: float,
        price: float,
        direction: Direction,
        symbol: str,
        portfolio: PortfolioState,
        correlations: dict[tuple[str, str], float],
    ) -> tuple[float, bool]:
        """Shrink ``quantity`` until it fits every portfolio-level limit.

        Returns ``(quantity, was_reduced)``. Each limit either passes, shrinks the size,
        or zeroes it — none of them can increase it.
        """
        equity = portfolio.equity
        original = quantity
        reduced = False
        signed = 1.0 if direction is Direction.LONG else -1.0

        # --- concurrent positions ---
        existing = portfolio.positions.get(symbol)
        is_new_position = existing is None or existing.is_flat
        open_count = portfolio.open_position_count
        slots_ok = not is_new_position or open_count < self._limits.max_concurrent_positions
        checks.append(
            RiskCheck(
                name="max_concurrent_positions",
                passed=slots_ok,
                observed=float(open_count),
                limit=float(self._limits.max_concurrent_positions),
            )
        )
        if not slots_ok:
            reasons.append("maximum concurrent positions already open")
            return (0.0, False)

        # --- gross exposure ---
        max_gross = equity * self._limits.max_gross_exposure_pct / 100.0
        headroom = max_gross - portfolio.gross_exposure
        gross_ok = quantity * price <= headroom
        checks.append(
            RiskCheck(
                name="max_gross_exposure",
                passed=gross_ok,
                observed=portfolio.gross_exposure + quantity * price,
                limit=max_gross,
                action="" if gross_ok else "reduce",
            )
        )
        if not gross_ok:
            quantity = max(0.0, headroom / price) if price > 0 else 0.0
            reduced = True
            if quantity <= 0:
                reasons.append("no gross exposure headroom remaining")
                return (0.0, False)

        # --- net exposure ---
        max_net = equity * self._limits.max_net_exposure_pct / 100.0
        prospective_net = abs(portfolio.net_exposure + signed * quantity * price)
        net_ok = prospective_net <= max_net
        checks.append(
            RiskCheck(
                name="max_net_exposure",
                passed=net_ok,
                observed=prospective_net,
                limit=max_net,
                action="" if net_ok else "reduce",
            )
        )
        if not net_ok:
            net_headroom = max_net - abs(portfolio.net_exposure)
            quantity = max(0.0, min(quantity, net_headroom / price)) if price > 0 else 0.0
            reduced = True
            if quantity <= 0:
                reasons.append("no net exposure headroom remaining")
                return (0.0, False)

        # --- correlated / cluster exposure ---
        instrument = self._universe.get(symbol)
        cluster = instrument.correlation_cluster if instrument else "default"
        cluster_symbols = {
            i.symbol
            for i in self._universe.instruments
            if i.correlation_cluster == cluster and i.symbol != symbol
        }
        cluster_exposure = sum(
            p.notional for s, p in portfolio.positions.items() if s in cluster_symbols
        )
        cluster_positions = sum(
            1 for s, p in portfolio.positions.items() if s in cluster_symbols and not p.is_flat
        )

        cluster_slots_ok = (
            not is_new_position or cluster_positions < self._limits.max_positions_per_cluster
        )
        checks.append(
            RiskCheck(
                name="max_positions_per_cluster",
                passed=cluster_slots_ok,
                observed=float(cluster_positions),
                limit=float(self._limits.max_positions_per_cluster),
                detail=f"cluster={cluster}",
            )
        )
        if not cluster_slots_ok:
            reasons.append(f"correlation cluster {cluster!r} already at its position limit")
            return (0.0, False)

        max_cluster = equity * self._limits.max_cluster_exposure_pct / 100.0
        cluster_headroom = max_cluster - cluster_exposure
        cluster_ok = quantity * price <= cluster_headroom
        checks.append(
            RiskCheck(
                name="max_cluster_exposure",
                passed=cluster_ok,
                observed=cluster_exposure + quantity * price,
                limit=max_cluster,
                detail=f"cluster={cluster}",
                action="" if cluster_ok else "reduce",
            )
        )
        if not cluster_ok:
            quantity = max(0.0, min(quantity, cluster_headroom / price)) if price > 0 else 0.0
            reduced = True
            if quantity <= 0:
                reasons.append(f"no exposure headroom in correlation cluster {cluster!r}")
                return (0.0, False)

        # --- realized correlation with existing positions ---
        # Cluster membership is a static approximation; measured correlation catches the
        # case where two nominally unrelated instruments have started moving together.
        if correlations and is_new_position:
            worst_symbol, worst_corr = "", 0.0
            for other, position in portfolio.positions.items():
                if position.is_flat or other == symbol:
                    continue
                corr = abs(correlations.get((symbol, other), 0.0))
                if corr > worst_corr:
                    worst_symbol, worst_corr = other, corr
            corr_ok = worst_corr <= self._limits.max_correlation_for_new_position
            checks.append(
                RiskCheck(
                    name="max_correlation_for_new_position",
                    passed=corr_ok,
                    observed=worst_corr,
                    limit=self._limits.max_correlation_for_new_position,
                    detail=f"most correlated open position: {worst_symbol or 'none'}",
                )
            )
            if not corr_ok:
                reasons.append(
                    f"correlation {worst_corr:.2f} with open position {worst_symbol} "
                    "exceeds the limit for a new position"
                )
                return (0.0, False)

        return (quantity, reduced or quantity < original - 1e-12)


__all__ = ["RiskEngine", "RiskState"]
