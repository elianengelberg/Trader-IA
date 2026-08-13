"""The strategy engine — turns features into a signal candidate.

Responsibilities, in order: consult each strategy that applies in the current regime,
fuse their opinions, apply dampening modifiers, and emit a :class:`SignalCandidate` that
carries everything needed to audit the decision later — the snapshot it was made from,
the versions of every component involved, and both sides of the argument.

The engine never sizes a position and never places an order. It proposes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tia.core.clock import Clock, ensure_utc
from tia.core.config import StrategyConfig
from tia.core.ids import deterministic_id
from tia.core.logging import get_logger
from tia.domain.enums import Direction
from tia.domain.market import MarketSnapshot
from tia.domain.quality import DataQualityReport
from tia.domain.signals import AgentFinding, ContextAssessment, SignalCandidate
from tia.quant.features import FEATURE_VERSION, FeatureSet
from tia.regime.classifier import RegimeAssessment
from tia.strategy.base import Strategy
from tia.strategy.fusion import FusionResult, FusionWeights, fuse, regime_alignment_penalty

_log = get_logger("strategy.engine")


class StrategyEngine:
    """Runs the configured strategies and produces a signal candidate."""

    def __init__(
        self,
        strategies: list[Strategy],
        config: StrategyConfig,
        clock: Clock,
        *,
        apply_regime_alignment: bool = True,
    ) -> None:
        self._strategies = strategies
        self._config = config
        self._clock = clock
        self._weights = FusionWeights(
            weights=dict(config.weights), min_agreement=config.min_agreement
        )
        self._apply_alignment = apply_regime_alignment

    @property
    def strategies(self) -> list[Strategy]:
        return list(self._strategies)

    def strategy_versions(self) -> dict[str, str]:
        """Recorded on every signal so a decision can be tied to exact logic."""
        return {s.strategy_id: s.version for s in self._strategies}

    def evaluate(
        self,
        *,
        features: FeatureSet,
        regime: RegimeAssessment,
        quality: DataQualityReport | None,
        context: ContextAssessment | None = None,
        snapshot: MarketSnapshot | None = None,
        findings: tuple[AgentFinding, ...] = (),
        correlation_id: str = "",
    ) -> tuple[SignalCandidate, FusionResult]:
        """Produce a signal candidate for the current bar.

        Always returns a candidate — including a ``NO_TRADE`` one. Recording *why* the
        system declined is as valuable as recording why it acted, and a pipeline that
        returns ``None`` for "no trade" loses that information entirely.
        """
        now = self._clock.now()

        opinions = []
        for strategy in self._strategies:
            if not strategy.applies_in(regime.regime):
                continue
            try:
                opinions.append(strategy.evaluate(features, regime))
            except Exception as exc:
                _log.error(
                    "strategy_evaluation_failed",
                    strategy=strategy.strategy_id,
                    symbol=features.symbol,
                    error=str(exc),
                )

        result = fuse(
            opinions,
            weights=self._weights,
            regime=regime,
            quality=quality,
            context=context,
            now=now,
        )

        # Fighting the prevailing regime is allowed but must clear a higher bar. Applied
        # here rather than inside a strategy so it is visible in one place and shows up
        # in the audit trail.
        if self._apply_alignment and result.is_actionable:
            penalty = regime_alignment_penalty(result.direction, regime.regime)
            if penalty < 1.0:
                result.final_confidence *= penalty
                result.why_not_enter.append(
                    f"direction {result.direction.value} opposes the {regime.regime.value} "
                    f"regime; confidence dampened by {(1 - penalty) * 100:.0f}%"
                )

        return self._build_candidate(
            features=features,
            regime=regime,
            quality=quality,
            context=context,
            snapshot=snapshot,
            findings=findings,
            result=result,
            opinions=opinions,
            now=now,
            correlation_id=correlation_id,
        )

    def _build_candidate(
        self,
        *,
        features: FeatureSet,
        regime: RegimeAssessment,
        quality: DataQualityReport | None,
        context: ContextAssessment | None,
        snapshot: MarketSnapshot | None,
        findings: tuple[AgentFinding, ...],
        result: FusionResult,
        opinions: list,
        now: datetime,
        correlation_id: str,
    ) -> tuple[SignalCandidate, FusionResult]:
        ttl = timedelta(seconds=self._config.signal_ttl_seconds)
        entry = result.entry_reference or features.get("close", 1.0)

        # A deterministic signal id: the same market state evaluated twice produces the
        # same id, which makes the whole pipeline replay-safe rather than generating a
        # fresh id (and a fresh order) on every retry.
        signal_id = deterministic_id(
            "sig",
            features.symbol,
            features.bar_open_time,
            features.feature_hash,
            result.direction.value,
            round(result.final_confidence, 6),
        )

        strategy_version = "+".join(
            f"{s.strategy_id}@{s.version}" for s in sorted(self._strategies, key=lambda x: x.strategy_id)
        )

        candidate = SignalCandidate(
            signal_id=signal_id,
            symbol=features.symbol,
            direction=result.direction,
            confidence=result.final_confidence,
            base_confidence=max(result.base_confidence, result.final_confidence),
            created_at=ensure_utc(now),
            expires_at=ensure_utc(now) + ttl,
            market_snapshot_id=snapshot.snapshot_id if snapshot else "",
            entry_reference=entry,
            stop_reference=result.stop_reference,
            target_reference=result.target_reference,
            strategy_id=(
                result.contributing[0].strategy_id if result.contributing else "fusion"
            ),
            strategy_version=strategy_version,
            model_version=context.model_id if context else "",
            prompt_version=context.prompt_version if context else "",
            feature_version=FEATURE_VERSION,
            regime=regime.regime,
            data_quality_score=quality.quality_score if quality else 0.5,
            data_freshness_score=quality.freshness_score if quality else 0.5,
            opinions=tuple(opinions),
            findings=findings,
            context_assessment_id=result.context_assessment_id,
            context_modifier_applied=result.context_modifier_applied,
            why_enter=tuple(result.why_enter[:12]),
            why_not_enter=tuple(result.why_not_enter[:12]),
            supporting_factors=tuple(result.supporting[:10]),
            contradicting_factors=tuple(result.contradicting[:10]),
            invalidation_conditions=tuple(result.invalidation_conditions[:10]),
            correlation_id=correlation_id,
        )
        return candidate, result

    def no_trade_candidate(
        self,
        *,
        symbol: str,
        reason: str,
        now: datetime | None = None,
        correlation_id: str = "",
        reference_price: float = 1.0,
    ) -> SignalCandidate:
        """A NO_TRADE candidate for cases that never reach strategy evaluation.

        Used when data quality hard-fails or the feed is down: the system still records
        that it looked and declined, with the reason attached.
        """
        moment = ensure_utc(now) if now else self._clock.now()
        return SignalCandidate(
            signal_id=deterministic_id("sig", symbol, moment, reason),
            symbol=symbol,
            direction=Direction.NO_TRADE,
            confidence=0.0,
            base_confidence=0.0,
            created_at=moment,
            expires_at=moment + timedelta(seconds=self._config.signal_ttl_seconds),
            market_snapshot_id="",
            entry_reference=reference_price,
            strategy_id="none",
            strategy_version="n/a",
            feature_version=FEATURE_VERSION,
            why_not_enter=(reason,),
            correlation_id=correlation_id,
        )


__all__ = ["StrategyEngine"]
