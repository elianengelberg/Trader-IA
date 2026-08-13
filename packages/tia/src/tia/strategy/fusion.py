"""Signal fusion — where the asymmetry rule is enforced.

This module combines deterministic strategy opinions into a single direction and
confidence, then applies two *dampening-only* modifiers: data quality and LLM context.

**The invariant this file exists to guarantee:**

    final_confidence <= base_confidence,  always.

Every modifier is a multiplier in ``[0, 1]``. There is no code path that can raise a
confidence, flip a direction, or enlarge a position on the strength of a language-model
output. The consequence is that the worst case of a hallucination, a prompt injection
buried in a news article, or an LLM outage is *fewer trades* — never a trade the
deterministic layer did not already want to take, and never a bigger one.

The invariant is enforced three times over, deliberately:

1. Structurally — every modifier is clamped to ``[0, 1]`` before use.
2. By assertion — :func:`fuse` checks the result and raises if it were ever violated.
3. By the domain model — :class:`~tia.domain.signals.SignalCandidate` rejects a signal
   whose final confidence exceeds its base.

Defence in depth is warranted here because this is the single place where a
non-deterministic component touches a decision that moves (simulated) money.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tia.core.errors import RiskError
from tia.domain.enums import Direction, MarketRegime
from tia.domain.quality import DataQualityReport
from tia.domain.signals import ContextAssessment, Evidence, StrategyOpinion
from tia.regime.classifier import RegimeAssessment


@dataclass(frozen=True)
class FusionWeights:
    """Per-strategy weights. Configuration, never learned at runtime."""

    weights: dict[str, float]
    min_agreement: float = 0.0

    def weight_for(self, strategy_id: str) -> float:
        return self.weights.get(strategy_id, 0.0)


@dataclass
class FusionResult:
    """The fused view, with a complete audit of how it got there."""

    direction: Direction
    base_confidence: float
    final_confidence: float
    net_score: float
    data_quality_factor: float
    context_factor: float
    vetoed: bool
    veto_reason: str | None
    contributing: list[StrategyOpinion] = field(default_factory=list)
    dissenting: list[StrategyOpinion] = field(default_factory=list)
    why_enter: list[str] = field(default_factory=list)
    why_not_enter: list[str] = field(default_factory=list)
    supporting: list[Evidence] = field(default_factory=list)
    contradicting: list[Evidence] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    entry_reference: float = 0.0
    stop_reference: float | None = None
    target_reference: float | None = None
    context_modifier_applied: float = 0.0
    context_assessment_id: str | None = None

    @property
    def is_actionable(self) -> bool:
        return self.direction.is_actionable and self.final_confidence > 0.0


def _clamp_factor(value: float) -> float:
    """Clamp a modifier into ``[0, 1]``.

    A modifier above 1 would amplify. Rather than raise on a caller's arithmetic slip,
    clamp — a modifier that was going to amplify becomes neutral, which is the safe
    direction to fail in.
    """
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(1.0, value))


def data_quality_factor(report: DataQualityReport | None) -> float:
    """Map a data-quality report to a dampening factor in ``[0, 1]``.

    A hard fail returns 0.0, which forces NO_TRADE regardless of how strong the
    deterministic signal is. Degraded-but-usable data scales confidence down smoothly,
    so a marginal signal on marginal data does not survive the confidence threshold.
    """
    if report is None:
        # No report is not "fine" — it is an unknown, and unknown data quality is
        # treated as poor quality.
        return 0.5
    if report.hard_fail:
        return 0.0
    return _clamp_factor(report.composite_score)


def context_factor(
    assessment: ContextAssessment | None, *, now: datetime
) -> tuple[float, float, str | None]:
    """Map an LLM context assessment to ``(factor, modifier_applied, veto_reason)``.

    The modifier is clamped into ``[-1, 0]`` before use, so ``factor = 1 + modifier``
    always lands in ``[0, 1]``. A model that returns ``+0.9`` — attempting to amplify —
    contributes exactly nothing rather than being rejected outright, because a failed
    assessment should degrade gracefully into "no context", not into a pipeline error.
    """
    if assessment is None:
        return (1.0, 0.0, None)
    if not assessment.is_valid_at(now):
        # An expired assessment describes a market that no longer exists. Neutral, not
        # trusted.
        return (1.0, 0.0, None)
    if assessment.veto:
        return (0.0, -1.0, f"llm_veto: {assessment.thesis[:200] or 'no reason supplied'}")

    modifier = ContextAssessment.clamp_modifier(assessment.context_modifier)
    return (_clamp_factor(1.0 + modifier), modifier, None)


def fuse(
    opinions: list[StrategyOpinion],
    *,
    weights: FusionWeights,
    regime: RegimeAssessment,
    quality: DataQualityReport | None,
    context: ContextAssessment | None,
    now: datetime,
) -> FusionResult:
    """Combine opinions and dampening modifiers into a single fused view."""
    actionable = [o for o in opinions if o.direction.is_actionable]
    abstained = [o for o in opinions if not o.direction.is_actionable]

    why_not: list[str] = []
    supporting: list[Evidence] = []
    contradicting: list[Evidence] = []

    for opinion in abstained:
        for ev in opinion.evidence:
            why_not.append(f"{opinion.strategy_id}: {ev.claim}")

    # A hostile regime is a hard stop before anything else is considered. Anomalous and
    # crisis regimes are precisely where historical relationships stop holding, which is
    # to say precisely where a systematic strategy's edge is least reliable.
    if regime.regime.is_hostile:
        return FusionResult(
            direction=Direction.NO_TRADE,
            base_confidence=0.0,
            final_confidence=0.0,
            net_score=0.0,
            data_quality_factor=data_quality_factor(quality),
            context_factor=1.0,
            vetoed=True,
            veto_reason=f"hostile regime: {regime.regime.value}",
            dissenting=list(opinions),
            why_not_enter=[f"market regime is {regime.regime.value}", *why_not],
        )

    if not actionable:
        return FusionResult(
            direction=Direction.NO_TRADE,
            base_confidence=0.0,
            final_confidence=0.0,
            net_score=0.0,
            data_quality_factor=data_quality_factor(quality),
            context_factor=1.0,
            vetoed=False,
            veto_reason=None,
            dissenting=abstained,
            why_not_enter=why_not or ["no strategy proposed a direction"],
        )

    # Signed, weighted vote. Longs are positive, shorts negative; the sign of the sum is
    # the direction and its magnitude relative to the total weight is the conviction.
    net = 0.0
    total_weight = 0.0
    for opinion in actionable:
        weight = weights.weight_for(opinion.strategy_id)
        if weight <= 0:
            continue
        sign = 1.0 if opinion.direction is Direction.LONG else -1.0
        net += sign * opinion.strength * weight
        total_weight += weight

    if total_weight <= 0:
        return FusionResult(
            direction=Direction.NO_TRADE,
            base_confidence=0.0,
            final_confidence=0.0,
            net_score=0.0,
            data_quality_factor=data_quality_factor(quality),
            context_factor=1.0,
            vetoed=False,
            veto_reason=None,
            dissenting=list(opinions),
            why_not_enter=["no enabled strategy carries a positive fusion weight", *why_not],
        )

    net_score = net / total_weight
    base_confidence = _clamp_factor(abs(net_score))

    # A net score of zero means the vote is balanced — either strategies cancelled each
    # other out, or every actionable opinion carried zero strength. Either way there is
    # no conviction, and picking a direction from the sign of 0.0 would be arbitrary.
    if base_confidence <= 0.0:
        return FusionResult(
            direction=Direction.NO_TRADE,
            base_confidence=0.0,
            final_confidence=0.0,
            net_score=net_score,
            data_quality_factor=data_quality_factor(quality),
            context_factor=1.0,
            vetoed=False,
            veto_reason=None,
            contributing=[],
            dissenting=list(opinions),
            why_not_enter=[
                "strategies produced no net conviction in either direction",
                *why_not,
            ],
        )

    direction = Direction.LONG if net_score > 0 else Direction.SHORT

    if base_confidence < weights.min_agreement:
        return FusionResult(
            direction=Direction.NO_TRADE,
            base_confidence=base_confidence,
            final_confidence=0.0,
            net_score=net_score,
            data_quality_factor=data_quality_factor(quality),
            context_factor=1.0,
            vetoed=False,
            veto_reason=None,
            contributing=actionable,
            dissenting=abstained,
            why_not_enter=[
                f"strategy agreement {base_confidence:.2f} below the minimum "
                f"{weights.min_agreement:.2f}",
                *why_not,
            ],
        )

    agreeing = [o for o in actionable if o.direction is direction]
    disagreeing = [o for o in actionable if o.direction is not direction]

    why_enter: list[str] = []
    invalidation: list[str] = []
    for opinion in agreeing:
        why_enter.extend(f"{opinion.strategy_id}: {ev.claim}" for ev in opinion.evidence)
        supporting.extend(opinion.evidence)
        invalidation.extend(opinion.invalidation_conditions)
    for opinion in disagreeing:
        why_not.extend(f"{opinion.strategy_id} disagrees: {ev.claim}" for ev in opinion.evidence)
        contradicting.extend(opinion.evidence)

    # Entry, stop and target come from the highest-conviction agreeing strategy rather
    # than from an average. Averaging two different stop theses produces a level neither
    # strategy would have chosen and that neither thesis invalidates at.
    primary = max(agreeing, key=lambda o: o.strength)

    dq_factor = data_quality_factor(quality)
    ctx_factor, modifier_applied, veto_reason = context_factor(context, now=now)

    if quality is not None and quality.hard_fail:
        why_not.append(f"data quality hard fail: {quality.reason()}")
    if veto_reason:
        why_not.append(veto_reason)

    final_confidence = base_confidence * dq_factor * ctx_factor

    # The invariant, checked rather than assumed. If this ever fires, a modifier escaped
    # its clamp and the decision path is not trustworthy — refuse to produce a signal.
    if final_confidence > base_confidence + 1e-12:
        raise RiskError(
            "fusion produced a confidence above the deterministic base; a dampening "
            "modifier amplified, which must be impossible",
            base_confidence=base_confidence,
            final_confidence=final_confidence,
            data_quality_factor=dq_factor,
            context_factor=ctx_factor,
        )

    vetoed = veto_reason is not None or dq_factor == 0.0
    resolved_direction = Direction.NO_TRADE if vetoed or final_confidence <= 0.0 else direction

    return FusionResult(
        direction=resolved_direction,
        base_confidence=base_confidence,
        final_confidence=0.0 if resolved_direction is Direction.NO_TRADE else final_confidence,
        net_score=net_score,
        data_quality_factor=dq_factor,
        context_factor=ctx_factor,
        vetoed=vetoed,
        veto_reason=veto_reason
        or ("data quality hard fail" if dq_factor == 0.0 else None),
        contributing=agreeing,
        dissenting=[*disagreeing, *abstained],
        why_enter=why_enter,
        why_not_enter=why_not,
        supporting=supporting,
        contradicting=contradicting,
        invalidation_conditions=sorted(set(invalidation)),
        entry_reference=primary.entry_reference,
        stop_reference=primary.stop_reference,
        target_reference=primary.target_reference,
        context_modifier_applied=modifier_applied,
        context_assessment_id=context.assessment_id if context else None,
    )


def regime_alignment_penalty(direction: Direction, regime: MarketRegime) -> float:
    """A dampening factor for a direction that fights the prevailing regime.

    Shorting into a confirmed uptrend is not forbidden — sometimes it is right — but it
    should require more conviction than going with the trend, and this expresses that as
    a multiplier rather than as a hidden rule inside a strategy.
    """
    if regime is MarketRegime.TRENDING_UP and direction is Direction.SHORT:
        return 0.7
    if regime is MarketRegime.TRENDING_DOWN and direction is Direction.LONG:
        return 0.7
    return 1.0


__all__ = [
    "FusionResult",
    "FusionWeights",
    "context_factor",
    "data_quality_factor",
    "fuse",
    "regime_alignment_penalty",
]
