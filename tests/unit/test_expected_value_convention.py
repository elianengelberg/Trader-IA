"""The one cost convention: the estimator samples the GROSS edge, the engine subtracts the
costs of the trade under consideration exactly once.

Every number here is worked by hand. The bucket is seeded with identical outcomes so the
standard error is zero and the shrink leaves the mean untouched; what remains is the
arithmetic the gate actually applies.
"""

from __future__ import annotations

import math

import pytest

from tia.domain.enums import Direction, MarketRegime
from tia.economics.costs import CostModel, FeeSchedule, MarketConditions, TradeCosts
from tia.economics.expected_value import (
    MIN_SAMPLES_FOR_EDGE,
    EdgeEstimator,
    ExpectedValueEngine,
    Outcome,
)

REGIME = MarketRegime.TRENDING_DOWN


def _costs(total_bps: float, *, notional: float = 1_000.0) -> TradeCosts:
    """Costs with exactly ``total_bps`` of fees and nothing else — no model, no rounding."""
    return TradeCosts(
        fee_bps=total_bps, spread_bps=0.0, slippage_bps=0.0, latency_bps=0.0, impact_bps=0.0,
        notional=notional,
    )


def _seeded(
    *,
    gross_bps: float,
    fees_bps: float,
    direction: Direction = Direction.SHORT,
    count: int = MIN_SAMPLES_FOR_EDGE,
    confidence: float = 0.9,
) -> EdgeEstimator:
    estimator = EdgeEstimator()
    estimator.record_many(
        [
            Outcome(
                regime=REGIME,
                direction=direction,
                confidence=confidence,
                net_return_bps=gross_bps - fees_bps,
                fees_bps=fees_bps,
                gross_return_bps=gross_bps,
            )
            for _ in range(count)
        ]
    )
    return estimator


def _evaluate(estimator: EdgeEstimator, costs: TradeCosts, *, threshold: float = 5.0,
              direction: Direction = Direction.SHORT, max_cost_ratio: float = 0.6):  # type: ignore[no-untyped-def]
    return ExpectedValueEngine(
        estimator, threshold_bps=threshold, max_cost_ratio=max_cost_ratio
    ).evaluate(regime=REGIME, direction=direction, confidence=0.9, costs=costs)


# --------------------------------------------------------------- gross minus costs, once


def test_the_sample_is_the_gross_return_so_costs_are_subtracted_exactly_once() -> None:
    """Past trades: +20 gross, 10 paid in fees, +10 net. Next trade costs 10.

    Economically: expect +20 - 10 = +10 net. Before this convention the engine computed
    +10 (net sample) - 10 = 0 and refused — the same costs charged twice."""
    estimator = _seeded(gross_bps=20.0, fees_bps=10.0)
    ev = _evaluate(estimator, _costs(10.0))

    assert ev.edge_estimate is not None
    assert ev.edge_estimate.mean_bps == pytest.approx(20.0)
    assert ev.gross_edge_bps == pytest.approx(20.0)
    assert ev.net_edge_bps == pytest.approx(10.0)
    assert ev.is_tradeable is True


def test_a_net_only_outcome_is_treated_as_cost_free_not_as_already_charged() -> None:
    """Rows that recorded no fees carry ``fees_bps == 0``: their net *is* their gross.
    The convention is explicit — zero means "none recorded" — so a legacy row can never
    smuggle a second discount back in."""
    legacy = Outcome(REGIME, Direction.SHORT, 0.9, net_return_bps=10.0)
    assert legacy.fees_bps == 0.0
    assert legacy.gross_return_bps is None
    assert legacy.edge_sample_bps == pytest.approx(10.0)

    derived = Outcome(REGIME, Direction.SHORT, 0.9, net_return_bps=10.0, fees_bps=10.0)
    assert derived.edge_sample_bps == pytest.approx(20.0)

    explicit = Outcome(
        REGIME, Direction.SHORT, 0.9, net_return_bps=10.0, fees_bps=10.0, gross_return_bps=19.5
    )
    assert explicit.edge_sample_bps == pytest.approx(19.5), "an explicit gross wins"


def test_zero_costs_leave_the_gross_edge_as_the_net_edge() -> None:
    estimator = _seeded(gross_bps=12.0, fees_bps=0.0)
    ev = _evaluate(estimator, _costs(0.0))
    assert ev.net_edge_bps == pytest.approx(12.0)
    assert ev.is_tradeable is True
    assert math.isinf(ev.cost_ratio) is False and ev.cost_ratio == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("gross", "costs", "expected_net", "tradeable"),
    [
        (10.0, 5.0, 5.0, True),   # exactly at the 5 bps threshold: ≥ holds
        (9.99, 5.0, 4.99, False),  # one hundredth below: refused
        (10.01, 5.0, 5.01, True),  # one hundredth above: taken
        (30.0, 10.0, 20.0, True),  # comfortably above
        (12.0, 10.0, 2.0, False),  # positive but below the margin of safety
        (-5.0, 5.0, -10.0, False),  # a losing bucket never trades
    ],
)
def test_the_threshold_is_applied_to_gross_minus_current_costs(
    gross: float, costs: float, expected_net: float, tradeable: bool
) -> None:
    # Costs are kept at half the gross so the cost-ratio ceiling (0.6) never decides.
    estimator = _seeded(gross_bps=gross, fees_bps=0.0)
    ev = _evaluate(estimator, _costs(costs))
    assert ev.net_edge_bps == pytest.approx(expected_net)
    assert ev.is_tradeable is tradeable


def test_variable_costs_move_the_verdict_not_the_estimate() -> None:
    """The estimate is a property of the evidence; the costs are a property of the trade
    about to be taken. Only the second changes between two evaluations of one bucket."""
    estimator = _seeded(gross_bps=20.0, fees_bps=10.0)
    cheap = _evaluate(estimator, _costs(4.0))
    dear = _evaluate(estimator, _costs(16.0))
    assert cheap.gross_edge_bps == dear.gross_edge_bps == pytest.approx(20.0)
    assert cheap.net_edge_bps == pytest.approx(16.0) and cheap.is_tradeable
    assert dear.net_edge_bps == pytest.approx(4.0) and not dear.is_tradeable


def test_the_cost_ratio_ceiling_still_applies_on_top_of_the_threshold() -> None:
    """Net +8 clears a 5 bps threshold, but 12 of costs against 20 of gross is 60 % —
    at the ceiling — and 12.5 is over it. The ceiling is a separate, documented rule."""
    estimator = _seeded(gross_bps=20.0, fees_bps=10.0)
    at_ceiling = _evaluate(estimator, _costs(12.0))
    assert at_ceiling.cost_ratio == pytest.approx(0.6)
    assert at_ceiling.is_tradeable is True
    over = _evaluate(estimator, _costs(12.5))
    assert over.net_edge_bps == pytest.approx(7.5)
    assert over.is_tradeable is False
    assert "ceiling" in over.reason


# ----------------------------------------------------------------------- directions


def test_long_and_short_outcomes_follow_the_same_sign_convention() -> None:
    """A short that captured +20 bps and a long that captured +20 bps are the same edge:
    the producers already orient ``gross`` by direction before it reaches the estimator."""
    longs = _seeded(gross_bps=20.0, fees_bps=10.0, direction=Direction.LONG)
    shorts = _seeded(gross_bps=20.0, fees_bps=10.0, direction=Direction.SHORT)
    long_ev = _evaluate(longs, _costs(10.0), direction=Direction.LONG)
    short_ev = _evaluate(shorts, _costs(10.0), direction=Direction.SHORT)
    assert long_ev.net_edge_bps == pytest.approx(short_ev.net_edge_bps) == pytest.approx(10.0)
    assert long_ev.is_tradeable and short_ev.is_tradeable


def test_the_producers_arithmetic_matches_the_sample_the_estimator_expects() -> None:
    """The live runtime and the scenario engine compute gross as the oriented price move
    and net as gross minus fees; both must land in the estimator as gross."""
    entry, exit_price, quantity = 83_026.0, 83_116.49, 0.012043
    raw = (exit_price - entry) / entry * 10_000.0
    gross_short = -raw
    notional = quantity * entry
    fees_bps = (0.25 + 0.7507) / notional * 10_000.0
    net = gross_short - fees_bps
    outcome = Outcome(
        REGIME, Direction.SHORT, 0.89, net_return_bps=net, fees_bps=fees_bps,
        gross_return_bps=gross_short,
    )
    assert outcome.edge_sample_bps == pytest.approx(-10.899, abs=1e-3)
    assert net == pytest.approx(-20.907, abs=1e-3)


# -------------------------------------------------------------- units and conversions


def test_units_are_basis_points_of_entry_notional_and_currency_agrees() -> None:
    estimator = _seeded(gross_bps=20.0, fees_bps=10.0)
    ev = _evaluate(estimator, _costs(10.0, notional=2_000.0))
    assert ev.net_edge_bps == pytest.approx(10.0)
    assert ev.net_edge_currency == pytest.approx(2_000.0 * 10.0 / 10_000.0)  # $2.00
    assert "+$2.00" in ev.explain()


def test_the_cost_model_prices_a_maker_entry_at_the_configured_fee_schedule() -> None:
    """With the production schedule (2.5 maker, 7.5 taker) a resting entry and a taker
    exit cost 10.0 bps in fees; the other components are zero when the book is deep,
    the spread is nil and nothing moves between decision and fill."""
    model = CostModel(FeeSchedule(maker_bps=2.5, taker_bps=7.5))
    conditions = MarketConditions(
        price=83_000.0, spread_bps=0.0, volatility_per_bar=0.0, top_of_book_quantity=1.0,
        bar_volume=0.0, latency_ms=0.0, bar_seconds=60.0,
    )
    costs = model.estimate(quantity=0.012, conditions=conditions, entry_maker=True)
    assert costs.fee_bps == pytest.approx(10.0)
    assert costs.total_bps == pytest.approx(10.0)


# ------------------------------------------------------------ extremes and bad inputs


def test_a_single_extreme_outcome_is_shrunk_by_its_own_uncertainty() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(
        [Outcome(REGIME, Direction.SHORT, 0.9, net_return_bps=-10.0) for _ in range(29)]
        + [Outcome(REGIME, Direction.SHORT, 0.9, net_return_bps=1_000_000.0)]
    )
    estimate = estimator.estimate(regime=REGIME, direction=Direction.SHORT, confidence=0.9)
    assert estimate is not None
    assert estimate.standard_error_bps > 0.0
    assert estimate.adjusted_bps < estimate.mean_bps


def test_a_non_finite_sample_can_never_make_a_bucket_tradeable() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(
        [Outcome(REGIME, Direction.SHORT, 0.9, net_return_bps=float("nan")) for _ in range(30)]
    )
    ev = _evaluate(estimator, _costs(1.0))
    assert ev.is_tradeable is False


def test_a_non_actionable_direction_is_refused_before_any_arithmetic() -> None:
    estimator = _seeded(gross_bps=50.0, fees_bps=0.0)
    ev = ExpectedValueEngine(estimator).evaluate(
        regime=REGIME, direction=Direction.HOLD, confidence=0.9, costs=_costs(1.0)
    )
    assert ev.edge_estimate is None and ev.is_tradeable is False
    assert "hold" in ev.reason
