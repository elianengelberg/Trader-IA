"""The inference the experiment's verdicts rest on: intervals that respect dependence,
a level adjusted for how many candidates were compared, and a verdict rule whose every
branch is a boundary that can be hit on purpose."""

from __future__ import annotations

import math
import random
import statistics

import pytest

from tia.backtest.inference import (
    CRITERIA,
    Verdict,
    adjusted_level,
    block_bootstrap_ci,
    block_length,
    iid_bootstrap_ci,
    verdict,
)


def _ar1(n: int, *, phi: float, seed: int, mean: float = 0.0, sigma: float = 10.0) -> list[float]:
    rng = random.Random(seed)
    out = [mean]
    for _ in range(n - 1):
        out.append(mean + phi * (out[-1] - mean) + rng.gauss(0.0, sigma))
    return out


# -------------------------------------------------------------------------- intervals


def test_block_length_follows_the_cube_root_rule_within_bounds() -> None:
    assert block_length(0) == 1
    assert block_length(1) == 1
    assert block_length(8) == 2
    assert block_length(27) == 3
    assert block_length(60) == 4
    assert block_length(1000) == 10


def test_the_interval_is_reproducible_for_a_seed_and_moves_with_it() -> None:
    values = _ar1(80, phi=0.0, seed=3, mean=2.0)
    assert block_bootstrap_ci(values, seed=11) == block_bootstrap_ci(values, seed=11)
    assert block_bootstrap_ci(values, seed=11) != block_bootstrap_ci(values, seed=12)
    assert iid_bootstrap_ci(values, seed=11) == iid_bootstrap_ci(values, seed=11)


def test_an_independent_series_gives_similar_block_and_iid_intervals_around_the_truth() -> None:
    """With no dependence the block bootstrap loses little: both intervals contain the
    true mean on a well-sized sample and their widths agree within a modest factor."""
    values = _ar1(400, phi=0.0, seed=5, mean=3.0, sigma=10.0)
    block = block_bootstrap_ci(values, seed=1)
    iid = iid_bootstrap_ci(values, seed=1)
    assert block is not None and iid is not None
    assert block[0] < 3.0 < block[1] and iid[0] < 3.0 < iid[1]
    width_ratio = (block[1] - block[0]) / (iid[1] - iid[0])
    assert 0.7 < width_ratio < 1.5


def test_a_positively_autocorrelated_series_gets_a_wider_interval_from_the_block_bootstrap() -> None:
    """The point of the method: dependence the i.i.d. bootstrap cannot see. Averaged over
    seeds so one draw's luck does not decide the test."""
    ratios = []
    for seed in range(8):
        values = _ar1(300, phi=0.7, seed=seed, mean=0.0, sigma=10.0)
        block = block_bootstrap_ci(values, seed=seed, resamples=800)
        iid = iid_bootstrap_ci(values, seed=seed, resamples=800)
        assert block is not None and iid is not None
        ratios.append((block[1] - block[0]) / (iid[1] - iid[0]))
    assert statistics.fmean(ratios) > 1.25, ratios


def test_too_few_values_give_no_interval() -> None:
    assert block_bootstrap_ci([], seed=1) is None
    assert block_bootstrap_ci([1.0], seed=1) is None
    assert iid_bootstrap_ci([1.0], seed=1) is None


def test_a_constant_series_has_a_degenerate_interval_at_the_constant() -> None:
    assert block_bootstrap_ci([2.5] * 40, seed=1) == (2.5, 2.5)


def test_the_block_bootstrap_uses_every_position_of_the_wrapped_series() -> None:
    """A series whose mean is zero but whose halves differ: resampled means must cover
    both signs, which a method stuck at one position could not do."""
    values = [10.0] * 30 + [-10.0] * 30
    lo, hi = block_bootstrap_ci(values, seed=2)  # type: ignore[misc]
    assert lo < 0.0 < hi


# ------------------------------------------------------------------------ multiplicity


def test_the_adjusted_level_is_bonferroni_and_degenerates_to_nominal_for_one_candidate() -> None:
    assert adjusted_level(0.90, 1) == pytest.approx(0.90)
    assert adjusted_level(0.90, 2) == pytest.approx(0.95)
    assert adjusted_level(0.90, 9) == pytest.approx(1 - 0.1 / 9)
    assert adjusted_level(0.90, 0) == pytest.approx(0.90), "k below one is one"
    with pytest.raises(ValueError):
        adjusted_level(1.0, 3)


def test_the_adjusted_interval_is_never_narrower_than_the_nominal_one() -> None:
    values = _ar1(120, phi=0.3, seed=9, mean=1.0)
    nominal = block_bootstrap_ci(values, seed=4, level=0.90)
    adjusted = block_bootstrap_ci(values, seed=4, level=adjusted_level(0.90, 9))
    assert nominal is not None and adjusted is not None
    assert adjusted[0] <= nominal[0] and adjusted[1] >= nominal[1]


# ---------------------------------------------------------------------------- verdicts

OK = {"trades": 60, "profit_factor": 1.5, "max_drawdown_pct": 0.5, "stressed_mean_bps": 1.0}


def test_the_pre_registered_criteria_are_the_documented_ones() -> None:
    assert CRITERIA["min_trades"] == 30
    assert CRITERIA["ci_level"] == 0.90
    assert CRITERIA["ci_lower_min_bps"] == 0.0
    assert CRITERIA["min_profit_factor"] == 1.2
    assert CRITERIA["max_drawdown_pct"] == 1.0
    assert CRITERIA["fee_stress_multiplier"] == 1.5


def test_an_interval_entirely_above_zero_may_continue_to_the_other_filters() -> None:
    result = verdict(ci=(0.01, 5.0), **OK)
    assert result.verdict is Verdict.PROMISING_ON_VALIDATION
    assert "not a claim of profitability" in result.reason


def test_an_interval_that_crosses_zero_is_never_promising() -> None:
    assert verdict(ci=(-0.5, 5.0), **OK).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(-4.9, 5.0), **OK).verdict is Verdict.INCONCLUSIVE, "the old -5 floor is gone"


def test_a_lower_bound_of_exactly_zero_is_not_promising() -> None:
    assert verdict(ci=(0.0, 5.0), **OK).verdict is Verdict.INCONCLUSIVE


def test_an_interval_entirely_below_zero_is_unfavourable() -> None:
    assert verdict(ci=(-8.0, -0.1), **OK).verdict is Verdict.UNFAVOURABLE


def test_an_upper_bound_of_exactly_zero_is_inconclusive_not_unfavourable() -> None:
    assert verdict(ci=(-8.0, 0.0), **OK).verdict is Verdict.INCONCLUSIVE


def test_too_few_trades_are_insufficient_whatever_the_interval() -> None:
    assert verdict(ci=(2.0, 5.0), **{**OK, "trades": 29}).verdict is Verdict.INSUFFICIENT
    assert verdict(ci=None, **OK).verdict is Verdict.INSUFFICIENT


def test_profit_factor_and_drawdown_each_block_the_label() -> None:
    assert verdict(ci=(1.0, 5.0), **{**OK, "profit_factor": 1.2}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 5.0), **{**OK, "profit_factor": None}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 5.0), **{**OK, "max_drawdown_pct": 1.0}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 5.0), **{**OK, "profit_factor": math.inf}).verdict is Verdict.PROMISING_ON_VALIDATION


def test_a_positive_base_that_fails_under_cost_stress_is_fragile() -> None:
    assert verdict(ci=(1.0, 5.0), **{**OK, "stressed_mean_bps": 0.0}).verdict is Verdict.FRAGILE
    assert verdict(ci=(1.0, 5.0), **{**OK, "stressed_mean_bps": -2.0}).verdict is Verdict.FRAGILE


def test_without_the_cost_stress_nothing_is_promising() -> None:
    result = verdict(ci=(1.0, 5.0), **{**OK, "stressed_mean_bps": None})
    assert result.verdict is Verdict.INCONCLUSIVE and "stress" in result.reason


def test_the_order_of_the_rules_is_fixed() -> None:
    """Insufficient beats everything; unfavourable beats inconclusive; the interval beats
    the quality filters; the quality filters beat the stress."""
    assert verdict(ci=(-8.0, -1.0), **{**OK, "trades": 10}).verdict is Verdict.INSUFFICIENT
    assert verdict(ci=(-8.0, -1.0), **{**OK, "profit_factor": 0.1}).verdict is Verdict.UNFAVOURABLE
    assert verdict(ci=(-1.0, 1.0), **{**OK, "stressed_mean_bps": -1.0}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 2.0), **{**OK, "profit_factor": 1.0, "stressed_mean_bps": -1.0}).verdict is Verdict.INCONCLUSIVE


def test_numerical_edge_cases_do_not_crash_and_never_promise() -> None:
    """NaN compares False to every bound; without explicit guards a NaN interval would
    slide past every rule and come out PROMISING. It must not."""
    nan = float("nan")
    assert verdict(ci=(nan, nan), **OK).verdict is Verdict.INSUFFICIENT
    assert verdict(ci=(nan, 5.0), **OK).verdict is Verdict.INSUFFICIENT
    assert verdict(ci=(1.0, 5.0), **{**OK, "max_drawdown_pct": nan}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 5.0), **{**OK, "profit_factor": nan}).verdict is Verdict.INCONCLUSIVE
    assert verdict(ci=(1.0, 5.0), **{**OK, "stressed_mean_bps": nan}).verdict is Verdict.FRAGILE
    assert verdict(ci=(math.inf, math.inf), **OK).verdict is Verdict.INSUFFICIENT
    assert verdict(ci=(1.0, 5.0), **{**OK, "stressed_mean_bps": -math.inf}).verdict is Verdict.FRAGILE


def test_empty_data_and_zero_losses_are_handled() -> None:
    assert verdict(trades=0, ci=None, profit_factor=None, max_drawdown_pct=0.0, stressed_mean_bps=None).verdict is Verdict.INSUFFICIENT
    # No losses at all: an infinite profit factor passes the quality filter, the interval still decides.
    assert verdict(ci=(0.5, 3.0), **{**OK, "profit_factor": math.inf}).verdict is Verdict.PROMISING_ON_VALIDATION
    assert verdict(ci=(-0.5, 3.0), **{**OK, "profit_factor": math.inf}).verdict is Verdict.INCONCLUSIVE
