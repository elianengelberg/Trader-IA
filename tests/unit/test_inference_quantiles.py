"""Bootstrap interval ends by interpolation, and no interval from non-finite data (Phase 1.3)."""

from __future__ import annotations

import math
import statistics

import pytest

from tia.backtest.inference import _percentiles, _quantile, block_bootstrap_ci, iid_bootstrap_ci


def test_quantiles_interpolate_between_order_statistics_like_the_inclusive_method() -> None:
    values = [float(v) for v in range(10)]  # 0..9
    assert _quantile(values, 0.0) == 0.0 and _quantile(values, 1.0) == 9.0
    assert _quantile(values, 0.5) == 4.5
    assert _quantile(values, 0.05) == pytest.approx(0.45) and _quantile(values, 0.95) == pytest.approx(8.55)
    # The same answer statistics.quantiles gives with method="inclusive" (Hyndman-Fan 7).
    inclusive = statistics.quantiles(values, n=20, method="inclusive")
    assert _quantile(values, 0.05) == pytest.approx(inclusive[0]) and _quantile(values, 0.95) == pytest.approx(inclusive[-1])


def test_truncation_bias_is_gone_at_the_ends() -> None:
    """With 2 000 resampled means the 5 % end sits at position 99.95, not at the 99th
    mean: the old integer index read one order statistic too far toward the centre."""
    means = [float(i) for i in range(2_000)]
    lo, hi = _percentiles(means, 0.90)
    assert lo == pytest.approx(99.95) and hi == pytest.approx(1_899.05)
    assert lo < means[100] and hi > means[1_899]


def test_a_constant_series_is_still_degenerate_and_a_wider_level_is_never_narrower() -> None:
    assert _percentiles([2.5] * 40, 0.90) == (2.5, 2.5)
    means = [math.sin(i / 7.0) for i in range(500)]
    lo90, hi90 = _percentiles(means, 0.90)
    lo95, hi95 = _percentiles(means, 0.95)
    assert lo95 <= lo90 and hi95 >= hi90


def test_non_finite_returns_give_no_interval_rather_than_a_bound() -> None:
    clean = [1.0, -2.0, 3.0, 0.5, -1.0, 2.0, 1.5, -0.5] * 4
    assert block_bootstrap_ci(clean, seed=1) is not None
    for poison in (math.nan, math.inf, -math.inf):
        assert block_bootstrap_ci([*clean, poison], seed=1) is None
        assert iid_bootstrap_ci([*clean, poison], seed=1) is None
