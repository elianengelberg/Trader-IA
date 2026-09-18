"""Conviction sizing: follows the evidence, never exceeds the approved size."""

from __future__ import annotations

import pytest

from tia.domain.enums import Direction, MarketRegime
from tia.economics.conviction import conviction_fraction
from tia.economics.expected_value import EdgeEstimate

CFG = {"min_fraction": 0.35, "exploration_fraction": 0.25, "pooled_cap": 0.6}


def _estimate(mean: float, se: float, *, samples: int = 60, level: str = "bucket") -> EdgeEstimate:
    return EdgeEstimate(
        mean_bps=mean, adjusted_bps=max(0.0, mean - se), standard_error_bps=se, samples=samples,
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence_band=(0.55, 0.70),
        level=level,
    )


def test_strong_evidence_takes_the_full_approved_size() -> None:
    assert conviction_fraction(_estimate(30.0, 5.0), exploring=False, **CFG).fraction == 1.0


def test_barely_significant_evidence_takes_the_floor() -> None:
    assert conviction_fraction(_estimate(10.0, 10.0), exploring=False, **CFG).fraction == 0.35


def test_between_the_two_the_fraction_is_linear_in_the_t_statistic() -> None:
    assert conviction_fraction(_estimate(20.0, 10.0), exploring=False, **CFG).fraction == pytest.approx(0.675)


def test_pooled_evidence_is_capped_however_sure_it_looks() -> None:
    result = conviction_fraction(_estimate(50.0, 2.0, level="regime"), exploring=False, **CFG)
    assert result.fraction == 0.6
    assert "capped" in result.reason


def test_an_exploration_trade_is_a_cheap_lesson() -> None:
    result = conviction_fraction(None, exploring=True, **CFG)
    assert result.fraction == 0.25
    assert "exploration" in result.reason


def test_no_estimate_means_the_floor_not_zero_and_not_full() -> None:
    assert conviction_fraction(None, exploring=False, **CFG).fraction == 0.35


@pytest.mark.parametrize("bad", [{"min_fraction": 5.0}, {"pooled_cap": 9.0}, {"exploration_fraction": 3.0}])
def test_the_fraction_can_never_exceed_one_whatever_the_configuration(bad: dict) -> None:  # type: ignore[type-arg]
    cfg = {**CFG, **bad}
    for estimate in (None, _estimate(100.0, 1.0), _estimate(100.0, 1.0, level="regime")):
        for exploring in (False, True):
            assert 0.0 < conviction_fraction(estimate, exploring=exploring, **cfg).fraction <= 1.0
