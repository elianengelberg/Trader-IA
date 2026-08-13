"""The asymmetry rule.

This is the single most important safety property in the platform:

    **The language model can only reduce risk-taking. It can never increase it.**

The consequence is that the worst case of a hallucination, a prompt injection buried in a
news article, a compromised news source, or a total LLM outage is *fewer trades* — never
a trade the deterministic layer did not already want to take, and never a larger one.

These tests attack that property directly: they feed the fusion layer adversarial context
assessments and assert that none of them can raise a confidence, flip a direction, or
produce an actionable signal where the deterministic layer produced none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tia.core.errors import RiskError
from tia.domain.enums import Direction, MarketRegime
from tia.domain.quality import DataQualityReport
from tia.domain.signals import (
    ContextAssessment,
    DataQualityAnnotation,
    Evidence,
    StrategyOpinion,
)
from tia.regime.classifier import RegimeAssessment
from tia.strategy.fusion import FusionWeights, context_factor, fuse

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
WEIGHTS = FusionWeights(weights={"trend_following": 1.0, "mean_reversion": 1.0}, min_agreement=0.0)


def opinion(
    direction: Direction = Direction.LONG,
    strength: float = 0.8,
    strategy_id: str = "trend_following",
) -> StrategyOpinion:
    entry = 100.0
    stop = 95.0 if direction is Direction.LONG else 105.0
    return StrategyOpinion(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        symbol="BTC-USD",
        direction=direction,
        strength=strength,
        entry_reference=entry,
        stop_reference=stop if direction.is_actionable else None,
        evidence=(Evidence(claim="test evidence", weight=0.5),),
    )


def regime(kind: MarketRegime = MarketRegime.TRENDING_UP) -> RegimeAssessment:
    return RegimeAssessment(symbol="BTC-USD", regime=kind, confidence=0.8, assessed_at=NOW)


def quality(score: float = 1.0, hard_fail: bool = False) -> DataQualityReport:
    return DataQualityReport(
        report_id="dq_test",
        symbol="BTC-USD",
        timeframe="1m",
        evaluated_at=NOW,
        quality_score=score,
        freshness_score=score,
        hard_fail=hard_fail,
    )


def assessment(
    *,
    modifier: float = 0.0,
    veto: bool = False,
    decision: Direction = Direction.NO_TRADE,
    confidence: float = 0.0,
    expires_in: int = 900,
) -> ContextAssessment:
    return ContextAssessment(
        assessment_id="ctx_test",
        symbol="BTC-USD",
        created_at=NOW,
        expires_at=NOW + timedelta(seconds=expires_in),
        decision=decision,
        confidence=confidence,
        context_modifier=ContextAssessment.clamp_modifier(modifier),
        veto=veto,
        thesis="test thesis",
        data_quality=DataQualityAnnotation(score=1.0, freshness=1.0),
    )


class TestTheModelCannotAmplify:
    def test_baseline_without_context_is_the_ceiling(self) -> None:
        no_context = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=quality(), context=None, now=NOW
        )
        assert no_context.final_confidence == pytest.approx(no_context.base_confidence)

    def test_maximally_enthusiastic_context_changes_nothing(self) -> None:
        """A model returning a positive modifier gets exactly zero influence."""
        baseline = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=quality(), context=None, now=NOW
        )
        enthusiastic = fuse(
            [opinion()],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(modifier=0.9, decision=Direction.LONG, confidence=1.0),
            now=NOW,
        )
        assert enthusiastic.final_confidence == pytest.approx(baseline.final_confidence)

    def test_clamp_neutralises_any_positive_modifier(self) -> None:
        for raw in (0.01, 0.5, 1.0, 99.0, float("inf")):
            assert ContextAssessment.clamp_modifier(raw) == 0.0

    def test_clamp_bounds_negative_modifiers_at_minus_one(self) -> None:
        assert ContextAssessment.clamp_modifier(-5.0) == -1.0
        assert ContextAssessment.clamp_modifier(float("nan")) == 0.0

    def test_negative_modifier_reduces_confidence(self) -> None:
        baseline = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=quality(), context=None, now=NOW
        )
        dampened = fuse(
            [opinion()],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(modifier=-0.5),
            now=NOW,
        )
        assert dampened.final_confidence == pytest.approx(baseline.final_confidence * 0.5)

    def test_veto_forces_no_trade(self) -> None:
        result = fuse(
            [opinion(strength=1.0)],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(veto=True),
            now=NOW,
        )
        assert result.direction is Direction.NO_TRADE
        assert result.final_confidence == 0.0
        assert result.vetoed is True
        assert "llm_veto" in (result.veto_reason or "")

    def test_model_cannot_create_a_signal_from_nothing(self) -> None:
        """The deterministic layer abstained. No amount of model enthusiasm changes that."""
        result = fuse(
            [opinion(direction=Direction.NO_TRADE, strength=0.0)],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(modifier=-0.0, decision=Direction.LONG, confidence=1.0),
            now=NOW,
        )
        assert result.direction is Direction.NO_TRADE

    def test_model_cannot_flip_direction(self) -> None:
        """Deterministic layer says LONG; the model says SHORT with full confidence."""
        result = fuse(
            [opinion(direction=Direction.LONG, strength=0.9)],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(decision=Direction.SHORT, confidence=1.0),
            now=NOW,
        )
        assert result.direction is Direction.LONG

    def test_expired_assessment_is_neutral_not_trusted(self) -> None:
        """An expired assessment describes a market that no longer exists."""
        stale = assessment(modifier=-0.9, expires_in=60)
        factor, modifier, veto = context_factor(stale, now=NOW + timedelta(seconds=120))
        assert factor == 1.0
        assert modifier == 0.0
        assert veto is None

    def test_expired_veto_does_not_persist(self) -> None:
        """A veto is also an opinion about a moment, and it expires with the rest."""
        result = fuse(
            [opinion()],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=assessment(veto=True, expires_in=60),
            now=NOW + timedelta(seconds=300),
        )
        assert result.direction is Direction.LONG

    def test_missing_context_degrades_to_neutral(self) -> None:
        """An LLM outage must not stop the deterministic pipeline."""
        result = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=quality(), context=None, now=NOW
        )
        assert result.is_actionable
        assert result.context_factor == 1.0


class TestDataQualityIsAlsoDampeningOnly:
    def test_perfect_quality_is_neutral(self) -> None:
        result = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=quality(1.0), context=None, now=NOW
        )
        assert result.data_quality_factor == pytest.approx(1.0)

    def test_hard_fail_forces_no_trade_regardless_of_conviction(self) -> None:
        result = fuse(
            [opinion(strength=1.0)],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(0.9, hard_fail=True),
            context=None,
            now=NOW,
        )
        assert result.direction is Direction.NO_TRADE
        assert result.data_quality_factor == 0.0

    def test_absent_report_is_treated_as_poor_quality(self) -> None:
        """Unknown data quality is not good data quality."""
        result = fuse(
            [opinion()], weights=WEIGHTS, regime=regime(), quality=None, context=None, now=NOW
        )
        assert result.data_quality_factor == 0.5
        assert result.final_confidence < result.base_confidence


class TestHostileRegimes:
    @pytest.mark.parametrize("kind", [MarketRegime.CRISIS, MarketRegime.ANOMALOUS])
    def test_hostile_regime_blocks_everything(self, kind: MarketRegime) -> None:
        result = fuse(
            [opinion(strength=1.0)],
            weights=WEIGHTS,
            regime=regime(kind),
            quality=quality(),
            context=None,
            now=NOW,
        )
        assert result.direction is Direction.NO_TRADE
        assert result.vetoed is True
        assert kind.value in (result.veto_reason or "")


class TestInvariantUnderAdversarialInput:
    @settings(max_examples=300, deadline=None)
    @given(
        strength=st.floats(min_value=0.0, max_value=1.0),
        # NaN and the infinities are included explicitly: a model returning one of them
        # is exactly the adversarial case this property is meant to survive.
        raw_modifier=st.one_of(
            st.floats(min_value=-100.0, max_value=100.0),
            st.sampled_from([float("nan"), float("inf"), float("-inf")]),
        ),
        veto=st.booleans(),
        quality_score=st.floats(min_value=0.0, max_value=1.0),
        hard_fail=st.booleans(),
        model_confidence=st.floats(min_value=0.0, max_value=1.0),
        model_decision=st.sampled_from(list(Direction)),
    )
    def test_final_confidence_never_exceeds_base(
        self,
        strength: float,
        raw_modifier: float,
        veto: bool,
        quality_score: float,
        hard_fail: bool,
        model_confidence: float,
        model_decision: Direction,
    ) -> None:
        """Property: over any adversarial context the model could produce, the final
        confidence is bounded above by the deterministic base confidence."""
        ctx = assessment(
            modifier=raw_modifier,
            veto=veto,
            decision=model_decision,
            confidence=model_confidence,
        )
        result = fuse(
            [opinion(strength=strength)],
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(quality_score, hard_fail),
            context=ctx,
            now=NOW,
        )
        assert result.final_confidence <= result.base_confidence + 1e-12
        assert 0.0 <= result.final_confidence <= 1.0
        assert 0.0 <= result.context_factor <= 1.0
        assert 0.0 <= result.data_quality_factor <= 1.0

    @settings(max_examples=200, deadline=None)
    @given(
        directions=st.lists(
            st.sampled_from([Direction.LONG, Direction.SHORT, Direction.NO_TRADE]),
            min_size=1,
            max_size=4,
        ),
        strengths=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=1, max_size=4),
    )
    def test_fusion_output_is_always_well_formed(
        self, directions: list[Direction], strengths: list[float]
    ) -> None:
        opinions = [
            opinion(direction=d, strength=s, strategy_id="trend_following")
            for d, s in zip(directions, strengths, strict=False)
        ]
        result = fuse(
            opinions,
            weights=WEIGHTS,
            regime=regime(),
            quality=quality(),
            context=None,
            now=NOW,
        )
        assert result.direction in set(Direction)
        assert -1.0 <= result.net_score <= 1.0
        if result.direction is Direction.NO_TRADE:
            assert result.final_confidence == 0.0


class TestInvariantIsActuallyEnforced:
    def test_an_amplifying_modifier_would_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Proves the assertion in fuse() can fire — a guard that cannot fail proves
        nothing. Here the clamp is sabotaged to simulate a future refactor breaking it."""
        import tia.strategy.fusion as fusion_module

        monkeypatch.setattr(fusion_module, "context_factor", lambda a, *, now: (1.5, 0.5, None))
        with pytest.raises(RiskError, match="amplified"):
            fusion_module.fuse(
                [opinion()],
                weights=WEIGHTS,
                regime=regime(),
                quality=quality(),
                context=assessment(),
                now=NOW,
            )
