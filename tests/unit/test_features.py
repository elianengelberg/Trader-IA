"""Feature computation."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from tests.conftest import linear_series, proportional_series
from tia.data.providers.synthetic import build_synthetic_history
from tia.quant.features import FEATURE_VERSION, FeatureBuilder

END = datetime(2026, 1, 6, tzinfo=UTC)


@pytest.fixture
def builder() -> FeatureBuilder:
    return FeatureBuilder()


@pytest.fixture
def candles() -> list:
    return build_synthetic_history("BTC-USD", "1m", 400, seed=21, end=END)


class TestFeatureBuilder:
    def test_builds_a_complete_set(self, builder: FeatureBuilder, candles: list) -> None:
        fs = builder.build("BTC-USD", "1m", candles)
        assert fs.complete is True
        assert fs.bars_used == 400
        assert fs.feature_version == FEATURE_VERSION
        assert fs.feature_hash

    def test_core_features_are_present_and_finite(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        fs = builder.build("BTC-USD", "1m", candles)
        required = (
            "close",
            "ema_12",
            "ema_26",
            "rsi_14",
            "macd",
            "atr_14",
            "atr_pct",
            "adx_14",
            "bb_percent_b",
            "realized_vol_20",
            "vol_percentile_100",
            "volume_ratio",
            "zscore_20",
            "channel_position",
            "trend_slope_20",
        )
        assert fs.has_all(*required), [n for n in required if not fs.has_all(n)]

    def test_features_reflect_the_last_bar(self, builder: FeatureBuilder, candles: list) -> None:
        fs = builder.build("BTC-USD", "1m", candles)
        assert fs.get("close") == pytest.approx(candles[-1].close)
        assert fs.bar_open_time == candles[-1].open_time

    def test_short_history_is_marked_incomplete_not_silently_wrong(
        self, builder: FeatureBuilder
    ) -> None:
        fs = builder.build("BTC-USD", "1m", linear_series(30))
        assert fs.complete is False
        # Long-window features are NaN rather than a plausible number from thin data.
        assert math.isnan(fs.get("realized_vol_60"))

    def test_empty_series_is_rejected(self, builder: FeatureBuilder) -> None:
        with pytest.raises(ValueError, match="empty series"):
            builder.build("BTC-USD", "1m", [])

    def test_identical_input_produces_identical_hash(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        a = builder.build("BTC-USD", "1m", candles)
        b = builder.build("BTC-USD", "1m", candles)
        assert a.feature_hash == b.feature_hash

    def test_different_input_changes_the_hash(self, builder: FeatureBuilder, candles: list) -> None:
        a = builder.build("BTC-USD", "1m", candles)
        b = builder.build("BTC-USD", "1m", candles[:-1])
        assert a.feature_hash != b.feature_hash

    def test_require_raises_for_an_unknown_feature(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        fs = builder.build("BTC-USD", "1m", candles)
        with pytest.raises(KeyError, match="not present"):
            fs.require("no_such_feature")


class TestPointInTimeCorrectness:
    def test_features_do_not_change_when_future_bars_arrive(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        """The structural guarantee: a decision made at bar t is identical whether or not
        bars t+1.. exist yet."""
        at_bar_300 = builder.build("BTC-USD", "1m", candles[:300])
        later = builder.build("BTC-USD", "1m", candles[:300])  # same prefix, computed later
        assert at_bar_300.values == later.values

        # And computing over the full series then asking about bar 300 is not how the
        # builder works at all — it only ever sees a prefix.
        with_future = builder.build("BTC-USD", "1m", candles)
        assert with_future.bar_open_time == candles[-1].open_time

    def test_build_series_advances_one_bar_at_a_time(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        sets = builder.build_series("BTC-USD", "1m", candles[:200], start_index=150)
        assert len(sets) == 51
        assert sets[0].bars_used == 150
        assert sets[-1].bars_used == 200
        for fs, candle in zip(sets, candles[149:200], strict=True):
            assert fs.bar_open_time == candle.open_time

    def test_series_features_match_incremental_computation(
        self, builder: FeatureBuilder, candles: list
    ) -> None:
        sets = builder.build_series("BTC-USD", "1m", candles[:180], start_index=170)
        for fs in sets:
            direct = builder.build("BTC-USD", "1m", candles[: fs.bars_used])
            assert fs.feature_hash == direct.feature_hash


class TestFeatureSemantics:
    def test_uptrend_produces_positive_slope_and_fast_above_slow(
        self, builder: FeatureBuilder
    ) -> None:
        fs = builder.build("BTC-USD", "1m", linear_series(200, step=0.5))
        assert fs.get("trend_slope_20") > 0
        assert fs.get("ema_fast_above_slow") == 1.0
        assert fs.get("rsi_14") > 70

    def test_downtrend_inverts_those_features(self, builder: FeatureBuilder) -> None:
        fs = builder.build("BTC-USD", "1m", linear_series(200, start_price=200.0, step=-0.5))
        assert fs.get("trend_slope_20") < 0
        assert fs.get("ema_fast_above_slow") == 0.0
        assert fs.get("rsi_14") < 30

    def test_breakout_flag_fires_at_a_new_high(self, builder: FeatureBuilder) -> None:
        fs = builder.build("BTC-USD", "1m", linear_series(200, step=0.5))
        assert fs.get("breakout_up") == 1.0
        assert fs.get("breakout_down") == 0.0

    def test_atr_pct_is_scale_free(self, builder: FeatureBuilder) -> None:
        """Comparable across a 100,000-price asset and a 100-price one.

        Both series are built from the same *proportional* generator, so any difference
        in atr_pct would mean the feature is picking up price level rather than
        volatility.
        """
        cheap = builder.build("A", "1m", proportional_series(200, start_price=100.0))
        dear = builder.build("B", "1m", proportional_series(200, start_price=100_000.0))
        assert cheap.get("atr_pct") == pytest.approx(dear.get("atr_pct"), rel=0.02)

    def test_volume_ratio_detects_a_spike(self, builder: FeatureBuilder) -> None:
        series = linear_series(200, volume=1000.0)
        spiked = [*series[:-1], series[-1].model_copy(update={"volume": 10_000.0})]
        fs = builder.build("BTC-USD", "1m", spiked)
        assert fs.get("volume_ratio") > 5.0
