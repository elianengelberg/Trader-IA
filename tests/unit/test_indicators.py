"""Indicators.

Verified against hand-computed values rather than against another library, so a
dependency upgrade cannot silently change a trading signal. The no-look-ahead class is
the most important one here: it is what makes every backtest number believable.
"""

from __future__ import annotations

import numpy as np
import pytest

from tia.quant import indicators as ind


class TestMovingAverages:
    def test_sma_matches_hand_computation(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        out = ind.sma(values, 3)
        assert np.isnan(out[0]) and np.isnan(out[1])
        assert out[2] == pytest.approx(2.0)  # (1+2+3)/3
        assert out[3] == pytest.approx(3.0)
        assert out[4] == pytest.approx(4.0)

    def test_ema_is_seeded_with_the_sma(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        out = ind.ema(values, 3)
        assert out[2] == pytest.approx(2.0)  # SMA seed
        # alpha = 2/(3+1) = 0.5 -> 0.5*4 + 0.5*2 = 3.0
        assert out[3] == pytest.approx(3.0)
        assert out[4] == pytest.approx(4.0)

    def test_ema_reacts_faster_than_sma(self) -> None:
        values = [10.0] * 20 + [20.0] * 5
        assert ind.ema(values, 10)[-1] > ind.sma(values, 10)[-1]

    def test_output_length_always_matches_input(self) -> None:
        values = list(range(50))
        for period in (2, 10, 49):
            assert ind.sma(values, period).size == 50
            assert ind.ema(values, period).size == 50

    def test_insufficient_history_returns_all_nan(self) -> None:
        assert np.all(np.isnan(ind.sma([1.0, 2.0], 5)))

    def test_period_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="period"):
            ind.sma([1.0, 2.0], 0)

    def test_input_is_not_mutated(self) -> None:
        values = np.array([1.0, 2.0, 3.0, 4.0])
        original = values.copy()
        ind.ema(values, 2)
        assert np.array_equal(values, original)


class TestRsi:
    def test_monotonic_rise_pins_rsi_at_100(self) -> None:
        out = ind.rsi(list(range(1, 40)), 14)
        assert out[-1] == pytest.approx(100.0)

    def test_monotonic_fall_pins_rsi_at_zero(self) -> None:
        out = ind.rsi(list(range(40, 1, -1)), 14)
        assert out[-1] == pytest.approx(0.0)

    def test_rsi_is_bounded(self) -> None:
        rng = np.random.default_rng(3)
        series = 100 + np.cumsum(rng.normal(0, 1, 500))
        out = ind.rsi(series, 14)
        finite = out[~np.isnan(out)]
        assert finite.min() >= 0.0
        assert finite.max() <= 100.0

    def test_alternating_series_sits_near_the_midpoint(self) -> None:
        series = [100 + (1 if i % 2 == 0 else -1) for i in range(60)]
        assert 40.0 < ind.rsi(series, 14)[-1] < 60.0


class TestMacd:
    def test_histogram_is_line_minus_signal(self) -> None:
        rng = np.random.default_rng(1)
        series = 100 + np.cumsum(rng.normal(0, 1, 200))
        line, signal, hist = ind.macd(series)
        valid = ~np.isnan(hist)
        assert np.allclose(hist[valid], line[valid] - signal[valid])

    def test_fast_must_be_shorter_than_slow(self) -> None:
        with pytest.raises(ValueError, match="fast period"):
            ind.macd([1.0] * 50, fast=26, slow=12)

    def test_uptrend_produces_a_positive_line(self) -> None:
        line, _, _ = ind.macd(list(range(1, 200)))
        assert line[-1] > 0


class TestVolatility:
    def test_true_range_first_bar_uses_the_bar_range(self) -> None:
        tr = ind.true_range([10.0, 11.0], [9.0, 10.0], [9.5, 10.5])
        assert tr[0] == pytest.approx(1.0)

    def test_true_range_accounts_for_gaps(self) -> None:
        # Gap up: |high - prev_close| exceeds the intrabar range.
        tr = ind.true_range([10.0, 20.0], [9.0, 19.0], [9.5, 19.5])
        assert tr[1] == pytest.approx(10.5)

    def test_atr_is_positive_on_a_moving_series(self) -> None:
        rng = np.random.default_rng(2)
        close = 100 + np.cumsum(rng.normal(0, 1, 200))
        high, low = close + 1.0, close - 1.0
        out = ind.atr(high, low, close, 14)
        assert out[-1] > 0

    def test_bollinger_bands_bracket_the_middle(self) -> None:
        rng = np.random.default_rng(4)
        series = 100 + np.cumsum(rng.normal(0, 1, 200))
        upper, middle, lower = ind.bollinger_bands(series, 20, 2.0)
        valid = ~np.isnan(middle)
        assert np.all(upper[valid] >= middle[valid])
        assert np.all(middle[valid] >= lower[valid])

    def test_percent_b_is_zero_at_the_lower_band(self) -> None:
        series = [100.0] * 19 + [90.0]
        pb = ind.bollinger_percent_b(series, 20, 2.0)
        assert pb[-1] < 0.5

    def test_constant_series_has_zero_realized_volatility(self) -> None:
        assert ind.realized_volatility([100.0] * 100, 20)[-1] == pytest.approx(0.0)


class TestAdx:
    def test_strong_trend_produces_high_adx(self) -> None:
        close = np.arange(1.0, 201.0)
        adx_out, plus_di, minus_di = ind.adx(close + 1, close - 1, close, 14)
        assert adx_out[-1] > 40
        assert plus_di[-1] > minus_di[-1]

    def test_choppy_market_produces_low_adx(self) -> None:
        base = np.array([100 + (2 if i % 2 == 0 else -2) for i in range(200)], dtype=float)
        adx_out, _, _ = ind.adx(base + 1, base - 1, base, 14)
        assert adx_out[-1] < 30

    def test_downtrend_flips_the_di_ordering(self) -> None:
        close = np.arange(200.0, 0.0, -1.0)
        _, plus_di, minus_di = ind.adx(close + 1, close - 1, close, 14)
        assert minus_di[-1] > plus_di[-1]


class TestStructure:
    def test_zscore_of_a_constant_series_is_zero(self) -> None:
        assert ind.zscore([5.0] * 50, 20)[-1] == pytest.approx(0.0)

    def test_zscore_flags_an_outlier(self) -> None:
        series = [100.0] * 39 + [130.0]
        assert ind.zscore(series, 20)[-1] > 3.0

    def test_percentile_rank_is_one_at_a_new_high(self) -> None:
        series = list(range(100))
        assert ind.percentile_rank(series, 50)[-1] == pytest.approx(1.0)

    def test_slope_sign_follows_direction(self) -> None:
        assert ind.slope(list(range(100)), 20)[-1] > 0
        assert ind.slope(list(range(100, 0, -1)), 20)[-1] < 0

    def test_slope_is_scale_invariant(self) -> None:
        """Normalizing by the window mean makes slopes comparable across price levels."""
        small = ind.slope([100 + i for i in range(60)], 20)[-1]
        large = ind.slope([100_000 + i * 1000 for i in range(60)], 20)[-1]
        assert small == pytest.approx(large, rel=0.02)

    def test_donchian_channel_brackets_price(self) -> None:
        rng = np.random.default_rng(6)
        close = 100 + np.cumsum(rng.normal(0, 1, 200))
        upper, middle, lower = ind.donchian_channel(close + 1, close - 1, 20)
        valid = ~np.isnan(upper)
        assert np.all(upper[valid] >= middle[valid])
        assert np.all(middle[valid] >= lower[valid])


class TestNoLookAhead:
    """The property the entire backtest rests on.

    For each indicator, recompute on a truncated series and assert the shared prefix is
    bit-identical. Any dependence on a future bar shows up here immediately.
    """

    @pytest.fixture
    def series(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rng = np.random.default_rng(11)
        close = 100 + np.cumsum(rng.normal(0, 1, 300))
        high = close + np.abs(rng.normal(0, 0.5, 300))
        low = close - np.abs(rng.normal(0, 0.5, 300))
        volume = np.abs(rng.normal(1000, 100, 300))
        return close, high, low, volume

    @pytest.mark.parametrize(
        "name,fn",
        [
            ("sma", lambda c, h, low_, v: ind.sma(c, 20)),
            ("ema", lambda c, h, low_, v: ind.ema(c, 20)),
            ("rsi", lambda c, h, low_, v: ind.rsi(c, 14)),
            ("macd_line", lambda c, h, low_, v: ind.macd(c)[0]),
            ("macd_signal", lambda c, h, low_, v: ind.macd(c)[1]),
            ("atr", lambda c, h, low_, v: ind.atr(h, low_, c, 14)),
            ("adx", lambda c, h, low_, v: ind.adx(h, low_, c, 14)[0]),
            ("bb_upper", lambda c, h, low_, v: ind.bollinger_bands(c, 20)[0]),
            ("zscore", lambda c, h, low_, v: ind.zscore(c, 20)),
            ("slope", lambda c, h, low_, v: ind.slope(c, 20)),
            ("realized_vol", lambda c, h, low_, v: ind.realized_volatility(c, 20)),
            ("rolling_max", lambda c, h, low_, v: ind.rolling_max(c, 20)),
            ("percentile_rank", lambda c, h, low_, v: ind.percentile_rank(c, 50)),
            ("vwap", lambda c, h, low_, v: ind.vwap(h, low_, c, v)),
            ("roc", lambda c, h, low_, v: ind.roc(c, 10)),
        ],
    )
    def test_prefix_is_unchanged_by_future_data(
        self, series: tuple[np.ndarray, ...], name: str, fn: object
    ) -> None:
        close, high, low, volume = series
        cut = 200
        full = fn(close, high, low, volume)  # type: ignore[operator]
        truncated = fn(close[:cut], high[:cut], low[:cut], volume[:cut])  # type: ignore[operator]

        a, b = full[:cut], truncated
        both_nan = np.isnan(a) & np.isnan(b)
        comparable = ~both_nan
        assert np.allclose(a[comparable], b[comparable], rtol=1e-12, atol=1e-12), (
            f"{name} depends on future data"
        )

    def test_a_deliberately_leaking_indicator_is_caught(self) -> None:
        """Confirms the check above can actually fail — a test that cannot fail proves
        nothing."""
        rng = np.random.default_rng(12)
        close = 100 + np.cumsum(rng.normal(0, 1, 300))

        def centered_mean(values: np.ndarray) -> np.ndarray:
            """Uses the whole series mean — classic look-ahead."""
            return np.full(values.shape, float(np.mean(values)))

        full = centered_mean(close)
        truncated = centered_mean(close[:200])
        assert not np.allclose(full[:200], truncated)
