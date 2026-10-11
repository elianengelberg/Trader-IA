"""A signal is credited to the strategy that set its levels — the strongest agreeing
opinion — never to whichever strategy happened to be evaluated first."""

from __future__ import annotations

from datetime import UTC, datetime

from tia.domain.enums import Direction, MarketRegime
from tia.domain.signals import StrategyOpinion
from tia.regime.classifier import RegimeAssessment
from tia.strategy.fusion import FusionWeights, fuse

NOW = datetime(2026, 10, 10, tzinfo=UTC)
REGIME = RegimeAssessment(
    symbol="BTC-USD", regime=MarketRegime.TRENDING_DOWN, confidence=0.8, assessed_at=NOW
)
WEIGHTS = FusionWeights(
    weights={"trend_following": 0.45, "mean_reversion": 0.30, "breakout": 0.25},
    min_agreement=0.0,
)


def opinion(strategy_id: str, strength: float, *, stop: float = 101.0) -> StrategyOpinion:
    return StrategyOpinion(
        strategy_id=strategy_id,
        strategy_version="1.1.0",
        symbol="BTC-USD",
        direction=Direction.SHORT,
        strength=strength,
        entry_reference=100.0,
        stop_reference=stop,
        target_reference=97.0,
    )


def test_the_primary_is_the_strongest_agreeing_opinion_not_the_first_listed() -> None:
    weak_first = opinion("trend_following", 0.3, stop=100.5)
    strong_second = opinion("breakout", 0.9, stop=101.5)
    result = fuse([weak_first, strong_second], weights=WEIGHTS, regime=REGIME, quality=None, context=None, now=NOW)

    assert result.is_actionable
    assert result.primary is not None
    assert result.primary.strategy_id == "breakout"
    # The levels the signal carries are the primary's, so attribution and levels agree.
    assert result.stop_reference == 101.5
    assert [o.strategy_id for o in result.contributing] == ["trend_following", "breakout"]


def test_a_lone_opinion_is_its_own_primary() -> None:
    only = opinion("mean_reversion", 0.5)
    result = fuse([only], weights=WEIGHTS, regime=REGIME, quality=None, context=None, now=NOW)
    assert result.primary is not None and result.primary.strategy_id == "mean_reversion"


def test_no_conviction_means_no_primary() -> None:
    result = fuse([], weights=WEIGHTS, regime=REGIME, quality=None, context=None, now=NOW)
    assert result.direction is Direction.NO_TRADE
    assert result.primary is None
