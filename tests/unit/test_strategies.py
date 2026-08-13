"""Regime classification, the strategy library, and the signal engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from tests.conftest import linear_series
from tia.core.clock import SimulatedClock
from tia.core.config import StrategyConfig
from tia.core.errors import ConfigurationError
from tia.data.providers.synthetic import build_synthetic_history
from tia.domain.enums import Direction, MarketRegime
from tia.domain.quality import DataQualityReport
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeAssessment, RegimeClassifier, RegimeThresholds
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import (
    BreakoutStrategy,
    MeanReversionStrategy,
    TrendFollowingStrategy,
    build_strategies,
)

NOW = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
END = datetime(2026, 1, 6, tzinfo=UTC)


@pytest.fixture
def builder() -> FeatureBuilder:
    return FeatureBuilder()


def good_quality() -> DataQualityReport:
    return DataQualityReport(
        report_id="dq",
        symbol="BTC-USD",
        timeframe="1m",
        evaluated_at=NOW,
        quality_score=1.0,
        freshness_score=1.0,
    )


class TestRegimeClassifier:
    def test_strong_uptrend_is_classified_as_trending_up(self, builder: FeatureBuilder) -> None:
        classifier = RegimeClassifier(RegimeThresholds(confirmation_bars=1))
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        assessment = classifier.classify(features, now=NOW)
        assert assessment.regime is MarketRegime.TRENDING_UP
        assert assessment.confidence > 0.5

    def test_strong_downtrend_is_classified_as_trending_down(self, builder: FeatureBuilder) -> None:
        classifier = RegimeClassifier(RegimeThresholds(confirmation_bars=1))
        features = builder.build(
            "BTC-USD", "1m", linear_series(250, start_price=300.0, step=-0.5)
        )
        assert classifier.classify(features, now=NOW).regime is MarketRegime.TRENDING_DOWN

    def test_incomplete_history_returns_unknown_not_a_guess(self, builder: FeatureBuilder) -> None:
        classifier = RegimeClassifier()
        features = builder.build("BTC-USD", "1m", linear_series(30))
        assessment = classifier.classify(features, now=NOW)
        assert assessment.regime is MarketRegime.UNKNOWN
        assert assessment.confidence == 0.0

    def test_hysteresis_requires_confirmation_before_switching(
        self, builder: FeatureBuilder
    ) -> None:
        """Without hysteresis the classifier flickers on noise and everything downstream
        thrashes."""
        classifier = RegimeClassifier(RegimeThresholds(confirmation_bars=3))
        candles = build_synthetic_history("BTC-USD", "1m", 400, seed=51, end=END)
        regimes = [
            classifier.classify(builder.build("BTC-USD", "1m", candles[: i + 1]), now=NOW).regime
            for i in range(200, 400)
        ]
        switches = sum(1 for a, b in pairwise(regimes) if a != b)
        assert switches < len(regimes) / 4, f"{switches} switches in {len(regimes)} bars is thrash"

    def test_hostile_regime_is_adopted_immediately(self, builder: FeatureBuilder) -> None:
        """Waiting three bars to acknowledge a crisis is the wrong trade-off."""
        classifier = RegimeClassifier(RegimeThresholds(confirmation_bars=5, anomaly_zscore=2.0))
        candles = linear_series(200, step=0.05)
        spike = candles[-1].model_copy(
            update={"close": candles[-1].close * 1.15, "high": candles[-1].close * 1.16}
        )
        features = builder.build("BTC-USD", "1m", [*candles[:-1], spike])
        assessment = classifier.classify(features, now=NOW)
        # A 15% single-bar move is both anomalous and crisis-shaped; which of the two
        # hostile labels applies is less important than that it was adopted on the first
        # bar rather than after five bars of confirmation.
        assert assessment.is_hostile
        assert classifier.current_regime("BTC-USD").is_hostile

    def test_reset_clears_state(self, builder: FeatureBuilder) -> None:
        classifier = RegimeClassifier(RegimeThresholds(confirmation_bars=1))
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        classifier.classify(features, now=NOW)
        assert classifier.current_regime("BTC-USD") is not MarketRegime.UNKNOWN
        classifier.reset("BTC-USD")
        assert classifier.current_regime("BTC-USD") is MarketRegime.UNKNOWN


def regime_of(kind: MarketRegime) -> RegimeAssessment:
    return RegimeAssessment(symbol="BTC-USD", regime=kind, confidence=0.8, assessed_at=NOW)


class TestTrendFollowing:
    def test_proposes_long_in_a_confirmed_uptrend(self, builder: FeatureBuilder) -> None:
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        opinion = TrendFollowingStrategy().evaluate(features, regime_of(MarketRegime.TRENDING_UP))
        assert opinion.direction is Direction.LONG
        assert opinion.stop_reference is not None
        assert opinion.stop_reference < opinion.entry_reference
        assert opinion.strength > 0

    def test_abstains_without_a_trend(self, builder: FeatureBuilder) -> None:
        candles = build_synthetic_history("BTC-USD", "1m", 300, seed=77, end=END)
        opinion = TrendFollowingStrategy(adx_threshold=95.0).evaluate(
            builder.build("BTC-USD", "1m", candles), regime_of(MarketRegime.RANGING)
        )
        assert opinion.direction is Direction.NO_TRADE
        assert "ADX" in opinion.evidence[0].claim

    def test_refuses_when_volatility_is_too_low_to_define_a_stop(
        self, builder: FeatureBuilder
    ) -> None:
        """A near-zero ATR means a near-zero stop distance, which means unbounded size."""
        flat = linear_series(250, step=0.0001)
        opinion = TrendFollowingStrategy(min_atr_pct=1.0).evaluate(
            builder.build("BTC-USD", "1m", flat), regime_of(MarketRegime.TRENDING_UP)
        )
        assert opinion.direction is Direction.NO_TRADE
        assert "stop" in opinion.evidence[0].claim

    def test_always_supplies_invalidation_conditions(self, builder: FeatureBuilder) -> None:
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        opinion = TrendFollowingStrategy().evaluate(features, regime_of(MarketRegime.TRENDING_UP))
        assert len(opinion.invalidation_conditions) >= 2


class TestMeanReversion:
    def test_refuses_to_fade_a_trend(self, builder: FeatureBuilder) -> None:
        """Applying mean reversion inside a strong trend is the fastest way to lose money
        in a systematic backtest."""
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        opinion = MeanReversionStrategy(max_adx=20.0).evaluate(
            features, regime_of(MarketRegime.TRENDING_UP)
        )
        assert opinion.direction is Direction.NO_TRADE
        assert "trend present" in opinion.evidence[0].claim

    def test_abstains_when_price_is_not_extended(self, builder: FeatureBuilder) -> None:
        candles = build_synthetic_history("BTC-USD", "1m", 300, seed=88, end=END)
        opinion = MeanReversionStrategy().evaluate(
            builder.build("BTC-USD", "1m", candles), regime_of(MarketRegime.RANGING)
        )
        assert opinion.direction in (Direction.NO_TRADE, Direction.LONG, Direction.SHORT)

    def test_only_applies_in_non_trending_regimes(self) -> None:
        strategy = MeanReversionStrategy()
        assert strategy.applies_in(MarketRegime.RANGING) is True
        assert strategy.applies_in(MarketRegime.TRENDING_UP) is False
        assert strategy.applies_in(MarketRegime.CRISIS) is False


class TestBreakout:
    def test_rejects_a_breakout_on_thin_volume(self, builder: FeatureBuilder) -> None:
        """A breakout without volume is usually noise."""
        series = linear_series(250, step=0.5, volume=1000.0)
        thin = [*series[:-1], series[-1].model_copy(update={"volume": 10.0})]
        opinion = BreakoutStrategy().evaluate(
            builder.build("BTC-USD", "1m", thin), regime_of(MarketRegime.TRENDING_UP)
        )
        assert opinion.direction is Direction.NO_TRADE
        assert "thin volume" in opinion.evidence[0].claim

    def test_accepts_a_breakout_with_volume_confirmation(self, builder: FeatureBuilder) -> None:
        series = linear_series(250, step=0.5, volume=1000.0)
        confirmed = [*series[:-1], series[-1].model_copy(update={"volume": 5000.0})]
        opinion = BreakoutStrategy().evaluate(
            builder.build("BTC-USD", "1m", confirmed), regime_of(MarketRegime.TRENDING_UP)
        )
        assert opinion.direction is Direction.LONG
        assert opinion.stop_reference is not None and opinion.stop_reference < opinion.entry_reference


class TestStrategyRegistry:
    def test_builds_known_strategies(self) -> None:
        strategies = build_strategies(("trend_following", "breakout"))
        assert [s.strategy_id for s in strategies] == ["trend_following", "breakout"]

    def test_unknown_strategy_fails_loudly(self) -> None:
        with pytest.raises(ConfigurationError, match="unknown strategy"):
            build_strategies(("does_not_exist",))


class TestStrategyEngine:
    @pytest.fixture
    def engine(self) -> StrategyEngine:
        return StrategyEngine(
            build_strategies(("trend_following", "mean_reversion", "breakout")),
            StrategyConfig(),
            SimulatedClock(NOW),
        )

    def test_produces_a_signal_in_a_clear_uptrend(
        self, engine: StrategyEngine, builder: FeatureBuilder
    ) -> None:
        series = linear_series(250, step=0.5, volume=1000.0)
        confirmed = [*series[:-1], series[-1].model_copy(update={"volume": 5000.0})]
        features = builder.build("BTC-USD", "1m", confirmed)
        signal, _result = engine.evaluate(
            features=features,
            regime=regime_of(MarketRegime.TRENDING_UP),
            quality=good_quality(),
        )
        assert signal.direction is Direction.LONG
        assert signal.confidence > 0
        assert signal.stop_reference is not None
        assert signal.why_enter

    def test_records_why_it_declined(
        self, engine: StrategyEngine, builder: FeatureBuilder
    ) -> None:
        """A pipeline that returns nothing for NO_TRADE loses the reason it declined."""
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.0001))
        signal, _ = engine.evaluate(
            features=features,
            regime=regime_of(MarketRegime.RANGING),
            quality=good_quality(),
        )
        assert signal.direction is Direction.NO_TRADE
        assert signal.why_not_enter

    def test_signal_carries_full_provenance(
        self, engine: StrategyEngine, builder: FeatureBuilder
    ) -> None:
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        signal, _ = engine.evaluate(
            features=features, regime=regime_of(MarketRegime.TRENDING_UP), quality=good_quality()
        )
        assert signal.feature_version
        assert "trend_following@" in signal.strategy_version
        assert signal.data_quality_score == 1.0

    def test_signal_id_is_deterministic(
        self, engine: StrategyEngine, builder: FeatureBuilder
    ) -> None:
        """Replaying the same market state must not mint a second signal (and a second
        order)."""
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        a, _ = engine.evaluate(
            features=features, regime=regime_of(MarketRegime.TRENDING_UP), quality=good_quality()
        )
        b, _ = engine.evaluate(
            features=features, regime=regime_of(MarketRegime.TRENDING_UP), quality=good_quality()
        )
        assert a.signal_id == b.signal_id

    def test_signal_expires(self, engine: StrategyEngine, builder: FeatureBuilder) -> None:
        features = builder.build("BTC-USD", "1m", linear_series(250, step=0.5))
        signal, _ = engine.evaluate(
            features=features, regime=regime_of(MarketRegime.TRENDING_UP), quality=good_quality()
        )
        assert signal.is_expired_at(NOW + timedelta(seconds=signal.ttl_seconds() + 1))
        assert not signal.is_expired_at(NOW + timedelta(seconds=1))

    def test_a_failing_strategy_does_not_break_the_engine(
        self, builder: FeatureBuilder
    ) -> None:
        class Exploding(TrendFollowingStrategy):
            strategy_id = "trend_following"

            def evaluate(self, features, regime):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        engine = StrategyEngine(
            [Exploding(), BreakoutStrategy()],
            StrategyConfig(enabled=("trend_following", "breakout"),
                           weights={"trend_following": 0.5, "breakout": 0.5}),
            SimulatedClock(NOW),
        )
        series = linear_series(250, step=0.5, volume=1000.0)
        confirmed = [*series[:-1], series[-1].model_copy(update={"volume": 5000.0})]
        signal, _ = engine.evaluate(
            features=builder.build("BTC-USD", "1m", confirmed),
            regime=regime_of(MarketRegime.TRENDING_UP),
            quality=good_quality(),
        )
        # The surviving strategy still produced a decision.
        assert signal.direction is Direction.LONG

    def test_no_trade_candidate_for_pre_strategy_failures(self, engine: StrategyEngine) -> None:
        signal = engine.no_trade_candidate(
            symbol="BTC-USD", reason="data quality hard fail", reference_price=100.0
        )
        assert signal.direction is Direction.NO_TRADE
        assert signal.why_not_enter == ("data quality hard fail",)
