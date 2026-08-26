"""Costs and expected value — the arithmetic that decides whether a signal is a trade.

The claim these tests defend is narrow and easy to state: **the system may not act on an
edge it has not measured.** A confidence is not a probability, a bucket of eleven trades is
not an expectation, and a gross edge is not a return until the costs come out of it.

The most important test in this file is
:func:`test_a_fresh_system_refuses_to_trade_because_it_has_no_evidence`, because it asserts
the behaviour every trading system is tempted to skip.
"""

from __future__ import annotations

import math

import pytest

from tia.domain.enums import Direction, MarketRegime
from tia.economics.costs import BPS, CostModel, FeeSchedule, MarketConditions, TradeCosts
from tia.economics.expected_value import (
    MIN_SAMPLES_FOR_EDGE,
    EdgeEstimator,
    ExpectedValueEngine,
    Outcome,
    band_of,
)

CONDITIONS = MarketConditions(
    price=50_000.0,
    spread_bps=1.5,
    volatility_per_bar=0.0008,
    top_of_book_quantity=2.0,
    bar_volume=120.0,
    latency_ms=250.0,
    bar_seconds=60.0,
)


def outcomes(count: int, net_bps: float, *, confidence: float = 0.75) -> list[Outcome]:
    return [
        Outcome(
            regime=MarketRegime.TRENDING_UP,
            direction=Direction.LONG,
            confidence=confidence,
            net_return_bps=net_bps,
        )
        for _ in range(count)
    ]


# --------------------------------------------------------------------------- costs


def test_a_round_trip_is_priced_not_a_single_leg() -> None:
    """A one-way cost estimate flatters every strategy that has to get out again."""
    model = CostModel(FeeSchedule(maker_bps=10.0, taker_bps=10.0))
    costs = model.estimate(quantity=0.1, conditions=CONDITIONS)

    assert costs.fee_bps == pytest.approx(20.0)


def test_maker_legs_pay_less_and_do_not_cross_the_spread() -> None:
    model = CostModel(FeeSchedule(maker_bps=2.0, taker_bps=10.0))
    taker = model.estimate(quantity=0.1, conditions=CONDITIONS)
    maker = model.estimate(quantity=0.1, conditions=CONDITIONS, entry_maker=True, exit_maker=True)

    assert maker.fee_bps < taker.fee_bps
    assert maker.spread_bps == 0.0
    assert taker.spread_bps == pytest.approx(CONDITIONS.spread_bps)


def test_unknown_book_depth_is_priced_as_a_cost_not_as_infinite_liquidity() -> None:
    """"We could not see the book" is a reason for more caution, not less.

    The optimistic reading — no depth data, therefore no slippage — is what makes a
    backtest on daily bars look tradeable.
    """
    model = CostModel()
    blind = model.estimate(
        quantity=0.1,
        conditions=CONDITIONS.model_copy(update={"top_of_book_quantity": 0.0}),
    )
    assert blind.slippage_bps > 0.0


def test_slippage_grows_when_the_order_is_bigger_than_the_touch() -> None:
    model = CostModel()
    small = model.estimate(quantity=1.0, conditions=CONDITIONS)
    large = model.estimate(quantity=20.0, conditions=CONDITIONS)

    assert small.slippage_bps == 0.0  # fits inside top_of_book_quantity=2.0
    assert large.slippage_bps > 0.0


def test_latency_is_priced_from_measured_delay_and_scales_with_volatility() -> None:
    model = CostModel()
    calm = model.estimate(
        quantity=0.1, conditions=CONDITIONS.model_copy(update={"volatility_per_bar": 0.0002})
    )
    wild = model.estimate(
        quantity=0.1, conditions=CONDITIONS.model_copy(update={"volatility_per_bar": 0.0032})
    )

    assert wild.latency_bps > calm.latency_bps
    instant = model.estimate(
        quantity=0.1, conditions=CONDITIONS.model_copy(update={"latency_ms": 0.0})
    )
    assert instant.latency_bps == 0.0


def test_the_dominant_component_is_reported_so_a_no_trade_has_a_reason() -> None:
    model = CostModel(FeeSchedule(taker_bps=10.0))
    costs = model.estimate(quantity=0.1, conditions=CONDITIONS)

    assert costs.dominant_component == "fees"
    assert costs.as_dict()["dominant"] == "fees"


def test_costs_in_currency_agree_with_costs_in_basis_points() -> None:
    costs = TradeCosts(
        fee_bps=20.0, spread_bps=1.0, slippage_bps=0.0, latency_bps=0.5,
        impact_bps=0.5, notional=10_000.0,
    )
    assert costs.total_bps == pytest.approx(22.0)
    assert costs.total_currency == pytest.approx(10_000.0 * 22.0 * BPS)


def test_a_configured_fee_schedule_is_flagged_as_unverified() -> None:
    """A fee tier guessed 5 bps low turns a losing strategy into a winning-looking one.

    The default is a published standard tier, not a fact about anyone's account, and the
    activation gate refuses to arm while this is True.
    """
    assert CostModel().requires_verification is True
    verified = CostModel(FeeSchedule(verified_at_source=True, source="account endpoint"))
    assert verified.requires_verification is False


# --------------------------------------------------------------------------- edge


def test_a_fresh_system_refuses_to_trade_because_it_has_no_evidence() -> None:
    """The behaviour every trading system is tempted to skip.

    With no closed trades there is no expectation, and the honest output is NO_TRADE with
    the sample count attached — not a guess derived from the confidence score.
    """
    engine = ExpectedValueEngine(EdgeEstimator())
    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.9,
        costs=CostModel().estimate(quantity=0.1, conditions=CONDITIONS),
    )

    assert not result.is_tradeable
    assert result.edge_estimate is None
    assert "0 closed trades" in result.reason
    assert str(MIN_SAMPLES_FOR_EDGE) in result.reason


def test_the_estimator_refuses_one_trade_below_the_sample_floor() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(MIN_SAMPLES_FOR_EDGE - 1, 40.0))
    key = {
        "regime": MarketRegime.TRENDING_UP,
        "direction": Direction.LONG,
        "confidence": 0.75,
    }
    assert estimator.estimate(**key) is None

    estimator.record(outcomes(1, 40.0)[0])
    assert estimator.estimate(**key) is not None


def test_confidence_is_never_used_as_a_probability() -> None:
    """Two buckets with identical realised outcomes must produce identical edges, even
    when their confidences differ wildly. A system that multiplies confidence by a target
    is a random number generator with an equals sign in front of it.
    """
    low = EdgeEstimator()
    low.record_many(outcomes(50, 30.0, confidence=0.56))
    high = EdgeEstimator()
    high.record_many(outcomes(50, 30.0, confidence=0.99))

    low_edge = low.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.56
    )
    high_edge = high.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.99
    )

    assert low_edge is not None and high_edge is not None
    assert low_edge.adjusted_bps == pytest.approx(high_edge.adjusted_bps)


def test_a_noisy_bucket_is_shrunk_toward_zero_by_its_own_standard_error() -> None:
    """A bucket whose mean sits inside its own noise gets no credit for it."""
    noisy = EdgeEstimator()
    for index in range(60):
        noisy.record(
            Outcome(
                regime=MarketRegime.TRENDING_UP,
                direction=Direction.LONG,
                confidence=0.75,
                net_return_bps=200.0 if index % 2 else -190.0,
            )
        )
    estimate = noisy.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
    )

    assert estimate is not None
    assert estimate.mean_bps > 0
    assert estimate.adjusted_bps < estimate.mean_bps
    assert estimate.adjusted_bps == 0.0  # entirely inside the noise


def test_a_negative_bucket_is_shrunk_toward_zero_from_below() -> None:
    """Symmetry matters: shrinking only positive means would bias every estimate up."""
    estimator = EdgeEstimator()
    for index in range(60):
        estimator.record(
            Outcome(
                regime=MarketRegime.RANGING,
                direction=Direction.SHORT,
                confidence=0.6,
                net_return_bps=-50.0 if index % 2 else -30.0,
            )
        )
    estimate = estimator.estimate(
        regime=MarketRegime.RANGING, direction=Direction.SHORT, confidence=0.6
    )

    assert estimate is not None
    assert estimate.mean_bps < 0
    assert estimate.adjusted_bps > estimate.mean_bps
    assert estimate.adjusted_bps <= 0.0


def test_buckets_do_not_leak_across_regime_direction_or_confidence_band() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(50, 40.0))

    assert estimator.estimate(
        regime=MarketRegime.RANGING, direction=Direction.LONG, confidence=0.75
    ) is None
    assert estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.SHORT, confidence=0.75
    ) is None
    assert estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.5
    ) is None


def test_bands_cover_the_whole_confidence_range_without_a_gap() -> None:
    for value in (0.0, 0.3, 0.549, 0.55, 0.7, 0.85, 0.999, 1.0):
        low, high = band_of(value)
        assert low <= value < high or value == 1.0


def test_coverage_answers_why_is_it_not_trading_yet() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(7, 10.0))
    coverage = estimator.coverage()

    assert coverage == {"trending_up|long|0.70-0.85": 7}


# --------------------------------------------------------------------------- the decision


def test_a_real_edge_that_does_not_clear_its_costs_is_a_no_trade() -> None:
    """The number that decides whether any of this is viable.

    At 10 bps taker per side, a round trip costs over 20 bps before spread or slippage.
    A strategy with a genuine, measured 23 bps gross edge nets under one basis point —
    and one basis point is not a business.
    """
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(200, 23.4))
    engine = ExpectedValueEngine(estimator, threshold_bps=5.0)

    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=CostModel(FeeSchedule(taker_bps=10.0)).estimate(
            quantity=0.1, conditions=CONDITIONS
        ),
    )

    assert result.gross_edge_bps == pytest.approx(23.4, abs=0.01)
    assert result.costs.total_bps > 20.0
    assert result.net_edge_bps < 5.0
    assert not result.is_tradeable
    assert "NO_TRADE" in result.explain()


def test_a_large_enough_edge_clears_and_is_reported_as_a_trade() -> None:
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(200, 120.0))
    engine = ExpectedValueEngine(estimator, threshold_bps=5.0)

    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=CostModel(FeeSchedule(taker_bps=10.0)).estimate(
            quantity=0.1, conditions=CONDITIONS
        ),
    )

    assert result.is_tradeable
    assert result.net_edge_bps > 90.0
    assert "TRADE" in result.explain()
    assert result.net_edge_currency == pytest.approx(
        result.costs.notional * result.net_edge_bps * BPS
    )


def test_a_trade_whose_costs_eat_most_of_the_edge_is_refused_even_when_net_is_positive() -> None:
    """Netting 6 bps out of 200 is fine. Netting 6 out of 30 is a coin flip on the cost
    model being exactly right, and the cost model is an estimate too."""
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(200, 29.0))
    engine = ExpectedValueEngine(estimator, threshold_bps=5.0, max_cost_ratio=0.6)

    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=TradeCosts(
            fee_bps=20.0, spread_bps=1.0, slippage_bps=0.0,
            latency_bps=0.5, impact_bps=0.5, notional=5_000.0,
        ),
    )

    assert result.net_edge_bps > 5.0  # would have passed the absolute threshold
    assert not result.is_tradeable
    assert "ceiling" in result.reason
    assert math.isinf(result.threshold_bps)


def test_a_non_actionable_direction_short_circuits_without_inventing_an_edge() -> None:
    engine = ExpectedValueEngine(EdgeEstimator())
    for direction in (Direction.HOLD, Direction.NO_TRADE):
        result = engine.evaluate(
            regime=MarketRegime.TRENDING_UP,
            direction=direction,
            confidence=0.9,
            costs=CostModel().estimate(quantity=0.1, conditions=CONDITIONS),
        )
        assert not result.is_tradeable
        assert result.gross_edge_bps == 0.0
        assert direction.value in result.reason


def test_the_decision_serialises_with_every_term_of_the_arithmetic() -> None:
    """The UI has to be able to show *why*, not just the verdict."""
    estimator = EdgeEstimator()
    estimator.record_many(outcomes(200, 120.0))
    engine = ExpectedValueEngine(estimator)
    payload = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=CostModel().estimate(quantity=0.1, conditions=CONDITIONS),
    ).as_dict()

    assert set(payload) >= {
        "gross_edge_bps", "net_edge_bps", "threshold_bps", "cost_ratio",
        "tradeable", "costs", "edge", "explanation",
    }
    assert payload["costs"]["total_bps"] > 0
    assert payload["edge"]["samples"] == 200


# --------------------------------------------------------- hierarchical backoff


def _varied(count: int, mean_bps: float, *, confidence: float, spread: float = 4.0) -> list[Outcome]:
    """Outcomes with real variance, alternating around the mean — a zero-variance bucket
    would make the standard error zero and the shrink invisible to the test."""
    return [
        Outcome(
            regime=MarketRegime.TRENDING_UP,
            direction=Direction.LONG,
            confidence=confidence,
            net_return_bps=mean_bps + (spread if i % 2 == 0 else -spread),
        )
        for i in range(count)
    ]


def test_a_thin_band_borrows_from_its_regime_at_double_the_uncertainty_discount() -> None:
    """The backoff and its price, in one scenario.

    The 0.70-0.85 band has 5 trades — far below the floor, and yesterday that meant
    NO_TRADE while 80 trades of the same regime and direction sat one band over. Now the
    pool answers, but as the coarser claim it is: level "regime", shrunk by TWO standard
    errors where the exact bucket is shrunk by one, and the basis sentence says exactly
    what was borrowed.
    """
    estimator = EdgeEstimator()
    estimator.record_many(_varied(80, 20.0, confidence=0.60))
    estimator.record_many(_varied(5, 20.0, confidence=0.75))

    estimate = estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
    )
    assert estimate is not None
    assert estimate.level == "regime"
    assert estimate.is_pooled
    assert estimate.samples == 85
    assert "pooled 85 trades" in estimate.basis
    assert "only 5" in estimate.basis
    # The discount is genuinely doubled: adjusted == mean - 2*SE, not mean - SE.
    assert estimate.adjusted_bps == pytest.approx(
        estimate.mean_bps - 2.0 * estimate.standard_error_bps
    )
    # And the confidence band reported is the one that was ASKED about, so a guardrail
    # keyed on the band still finds its pattern.
    assert estimate.confidence_band == band_of(0.75)


def test_an_exact_bucket_at_the_floor_is_untouched_by_the_backoff() -> None:
    """The finest level wins whenever it can answer, at the original one-SE shrink."""
    estimator = EdgeEstimator()
    estimator.record_many(_varied(MIN_SAMPLES_FOR_EDGE, 15.0, confidence=0.75))
    estimator.record_many(_varied(500, -60.0, confidence=0.60))  # a poisoned neighbour

    estimate = estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
    )
    assert estimate is not None
    assert estimate.level == "bucket"
    assert not estimate.is_pooled
    assert estimate.samples == MIN_SAMPLES_FOR_EDGE
    # The neighbouring band's -60s did not leak in.
    assert estimate.mean_bps == pytest.approx(15.0)
    assert estimate.adjusted_bps == pytest.approx(
        estimate.mean_bps - estimate.standard_error_bps
    )


def test_the_pool_needs_twice_the_floor_before_it_answers_at_all() -> None:
    """A coarser prior earns trust with MORE data, never less: 59 pooled trades refuse,
    the 60th answers."""
    estimator = EdgeEstimator()
    estimator.record_many(_varied(59, 20.0, confidence=0.60))
    assert (
        estimator.estimate(
            regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
        )
        is None
    )
    estimator.record(_varied(1, 20.0, confidence=0.60)[0])
    pooled = estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
    )
    assert pooled is not None
    assert pooled.level == "regime"


def test_the_pool_never_crosses_a_regime_or_a_direction() -> None:
    """A long in a trending market and a short in a ranging one are different animals.
    Hundreds of trades elsewhere must buy this bucket nothing."""
    estimator = EdgeEstimator()
    estimator.record_many(
        [
            Outcome(
                regime=MarketRegime.RANGING,
                direction=Direction.LONG,
                confidence=0.60,
                net_return_bps=25.0,
            )
            for _ in range(200)
        ]
    )
    estimator.record_many(
        [
            Outcome(
                regime=MarketRegime.TRENDING_UP,
                direction=Direction.SHORT,
                confidence=0.60,
                net_return_bps=25.0,
            )
            for _ in range(200)
        ]
    )
    assert (
        estimator.estimate(
            regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.60
        )
        is None
    )


def test_the_refusal_names_both_floors_and_what_would_unlock_each() -> None:
    """A NO_TRADE that says "not enough data" teaches nothing; one that says how much
    data, at which level, is a to-do list."""
    engine = ExpectedValueEngine(EdgeEstimator())
    costs = CostModel(FeeSchedule(maker_bps=1.0, taker_bps=7.5)).estimate(
        quantity=0.1, conditions=CONDITIONS
    )
    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=costs,
    )
    assert not result.is_tradeable
    assert "only 0 closed trades" in result.reason
    assert "0 across all its confidence bands" in result.reason
    assert "60 would allow" in result.reason


def test_a_pooled_trade_says_so_in_its_own_explanation() -> None:
    """The coarser claim is visible at the point of decision, not buried in a field."""
    estimator = EdgeEstimator()
    estimator.record_many(_varied(80, 40.0, confidence=0.60))
    engine = ExpectedValueEngine(estimator)
    costs = CostModel(FeeSchedule(maker_bps=1.0, taker_bps=7.5)).estimate(
        quantity=0.1, conditions=CONDITIONS
    )
    result = engine.evaluate(
        regime=MarketRegime.TRENDING_UP,
        direction=Direction.LONG,
        confidence=0.75,
        costs=costs,
    )
    assert result.edge_estimate is not None and result.edge_estimate.is_pooled
    assert "pooled from every confidence band" in result.explain()
