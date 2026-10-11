"""One semantics for every cost (Phase 1.3, Etapa Dos), checked against hand-worked numbers.

Every expected value here was computed on paper from the model's stated formulas before
the test was written; none is a number the code produced and was then pasted back. The
fixture is deliberately plain so each component can be isolated:

* fees 2.5 bps maker / 7.5 bps taker (the simulator's defaults),
* a 2 bps wide book, price 100,000, one unit at the touch, no bar volume (no impact), no
  latency, no volatility — so the only execution cost besides fees is the spread crossed.

**The worked example the report cites** (``test_the_worked_example``): 0.01 BTC at
100,000 = 1,000 notional; a maker entry and a taker exit pay 2.5 + 7.5 = 10 bps of fees;
one crossing of a 2 bps spread costs 1 bps; three eight-hour funding settlements at
+0.0001 on a long pay 3 x 0.0001 = 0.0003 = 3 bps; total 14 bps = 1.40 of currency. The
estimator's gross edge of 30 bps minus those 14 bps leaves 16 bps net, which clears the
5 bps threshold with a cost ratio of 14/30 ≈ 0.47 under the 0.6 ceiling.
"""

from __future__ import annotations

import math

import pytest

from tia.domain.enums import Direction, MarketRegime
from tia.economics.costs import (
    BPS,
    FUNDING_PERIOD_SECONDS,
    CostModel,
    FeeSchedule,
    MarketConditions,
    TradeCosts,
)
from tia.economics.expected_value import (
    MIN_SAMPLES_FOR_EDGE,
    EdgeEstimator,
    ExpectedValueEngine,
    Outcome,
)

REGIME = MarketRegime.TRENDING_UP
FEES = FeeSchedule(maker_bps=2.5, taker_bps=7.5)
PRICE = 100_000.0


def _conditions(**overrides: float) -> MarketConditions:
    base = {
        "price": PRICE,
        "spread_bps": 2.0,
        "volatility_per_bar": 0.0,
        "top_of_book_quantity": 1.0,
        "bar_volume": 0.0,
        "latency_ms": 0.0,
        "bar_seconds": 60.0,
    }
    base.update(overrides)
    return MarketConditions(**base)


def _model() -> CostModel:
    return CostModel(FEES)


def _seeded(gross_bps: float, *, direction: Direction = Direction.LONG, fees_bps: float = 10.0) -> EdgeEstimator:
    estimator = EdgeEstimator()
    estimator.record_many(
        [
            Outcome(
                regime=REGIME, direction=direction, confidence=0.9,
                net_return_bps=gross_bps - fees_bps, fees_bps=fees_bps, gross_return_bps=gross_bps,
            )
            for _ in range(MIN_SAMPLES_FOR_EDGE)
        ]
    )
    return estimator


# ------------------------------------------------------------------- fees and liquidity


def test_maker_entry_and_taker_exit_pay_each_legs_fee_and_cross_the_spread_once() -> None:
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True)
    assert costs.entry_fee_bps == 2.5 and costs.exit_fee_bps == 7.5
    assert costs.fee_bps == pytest.approx(10.0)
    assert costs.entry_maker is True and costs.exit_maker is False
    # One crossing: half the 2 bps spread.
    assert costs.spread_bps == pytest.approx(1.0)
    assert costs.slippage_bps == 0.0 and costs.impact_bps == 0.0 and costs.latency_bps == 0.0
    assert costs.execution_bps == pytest.approx(1.0)
    assert costs.total_bps == pytest.approx(11.0)


def test_taker_entry_and_taker_exit_pay_two_taker_fees_and_cross_twice() -> None:
    costs = _model().estimate(quantity=0.01, conditions=_conditions())
    assert costs.fee_bps == pytest.approx(15.0)
    assert costs.spread_bps == pytest.approx(2.0), "two crossings of half a 2 bps spread"
    assert costs.total_bps == pytest.approx(17.0)


def test_maker_both_legs_pays_two_maker_fees_and_crosses_nothing() -> None:
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True, exit_maker=True)
    assert costs.fee_bps == pytest.approx(5.0)
    assert costs.spread_bps == 0.0 and costs.execution_bps == 0.0
    assert costs.total_bps == pytest.approx(5.0)


def test_with_zero_spread_slippage_impact_and_latency_only_the_fees_remain() -> None:
    conditions = _conditions(spread_bps=0.0, bar_volume=0.0, latency_ms=0.0, volatility_per_bar=0.0)
    costs = _model().estimate(quantity=0.01, conditions=conditions)
    assert costs.execution_bps == 0.0 and costs.carry_bps == 0.0
    assert costs.total_bps == pytest.approx(15.0)
    assert costs.dominant_component == "fees"


def test_long_and_short_pay_the_same_execution_costs() -> None:
    long = _model().estimate(quantity=0.01, conditions=_conditions(), direction=Direction.LONG)
    short = _model().estimate(quantity=0.01, conditions=_conditions(), direction=Direction.SHORT)
    assert long.fee_bps == short.fee_bps and long.execution_bps == short.execution_bps
    assert long.total_bps == pytest.approx(short.total_bps)


# ---------------------------------------------------------- slippage, impact, latency


def test_slippage_is_charged_only_past_the_touch_and_once_per_crossing() -> None:
    """Four units against one at the touch: overflow 3, ratio 3, coefficient 0.5, floor of
    the spread at 2 bps → 0.5 x √3 x 2 = 1.7320508 bps per crossing."""
    expected = 0.5 * math.sqrt(3.0) * 2.0
    one = _model().estimate(quantity=4.0, conditions=_conditions(), entry_maker=True)
    two = _model().estimate(quantity=4.0, conditions=_conditions())
    assert one.slippage_bps == pytest.approx(expected)
    assert two.slippage_bps == pytest.approx(2.0 * expected)
    within = _model().estimate(quantity=1.0, conditions=_conditions())
    assert within.slippage_bps == 0.0, "an order that fits at the touch slips nothing"


def test_unknown_depth_is_priced_as_ignorance_not_as_plenty() -> None:
    """No book: half a bar's volatility (10 bps per bar → 5 bps) or half the spread,
    whichever is larger, per crossing."""
    conditions = _conditions(top_of_book_quantity=0.0, volatility_per_bar=0.001)
    costs = _model().estimate(quantity=0.01, conditions=conditions, entry_maker=True)
    assert costs.slippage_bps == pytest.approx(5.0)


def test_impact_is_the_square_root_of_participation_per_crossing() -> None:
    """A quarter of the bar's volume: 0.35 x √0.25 x 100 = 17.5 bps per crossing."""
    conditions = _conditions(bar_volume=1.0)
    one = _model().estimate(quantity=0.25, conditions=conditions, entry_maker=True)
    two = _model().estimate(quantity=0.25, conditions=conditions)
    assert one.impact_bps == pytest.approx(17.5)
    assert two.impact_bps == pytest.approx(35.0)


def test_latency_scales_volatility_by_the_square_root_of_time_and_is_charged_once() -> None:
    """6 s of a 60 s bar is a tenth; √0.1 x 10 bps = 3.1622777 bps, independent of legs."""
    conditions = _conditions(latency_ms=6_000.0, volatility_per_bar=0.001)
    one = _model().estimate(quantity=0.01, conditions=conditions, entry_maker=True)
    two = _model().estimate(quantity=0.01, conditions=conditions)
    assert one.latency_bps == pytest.approx(math.sqrt(0.1) * 10.0)
    assert two.latency_bps == pytest.approx(one.latency_bps)


# ------------------------------------------------------------------------- carry


def test_funding_period_is_eight_hours() -> None:
    assert FUNDING_PERIOD_SECONDS == 8 * 3600


def test_a_long_pays_a_positive_funding_rate_per_settlement() -> None:
    """Three settlements at +0.0001: 3 x 0.0001 = 0.0003 = 3 bps."""
    costs = _model().estimate(
        quantity=0.01, conditions=_conditions(), entry_maker=True,
        direction=Direction.LONG, funding_rate=0.0001, funding_periods=3,
    )
    assert costs.funding_bps == pytest.approx(3.0)
    assert costs.funding_known is True and costs.complete is True
    assert costs.carry_bps == pytest.approx(3.0)
    assert costs.total_bps == pytest.approx(14.0)


def test_a_short_pays_a_negative_rate_and_a_long_pays_nothing_on_it() -> None:
    short = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.SHORT,
        funding_rate=-0.0001, funding_periods=3,
    )
    long = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.LONG,
        funding_rate=-0.0001, funding_periods=3,
    )
    assert short.funding_bps == pytest.approx(3.0)
    assert long.funding_bps == 0.0, "a payment the long would receive is never credited"
    assert long.complete and short.complete


def test_a_funding_payment_the_position_would_receive_is_never_credited() -> None:
    short = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.SHORT,
        funding_rate=0.0001, funding_periods=3,
    )
    assert short.funding_bps == 0.0 and short.funding_known is True
    assert short.total_bps == pytest.approx(17.0), "the estimate never improves for a carry"


def test_no_horizon_means_no_funding_and_a_complete_estimate() -> None:
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), funding_rate=None, funding_periods=0)
    assert costs.funding_bps == 0.0 and costs.complete is True


@pytest.mark.parametrize("rate", [None, float("nan"), float("inf")])
def test_a_horizon_with_no_finite_rate_leaves_the_estimate_incomplete_not_free(rate: float | None) -> None:
    costs = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.LONG,
        funding_rate=rate, funding_periods=3,
    )
    assert costs.funding_bps == 0.0, "nothing invented"
    assert costs.funding_known is False and costs.complete is False
    assert costs.as_dict()["complete"] is False


def test_an_incomplete_estimate_never_makes_a_trade_tradeable() -> None:
    """A 300 bps edge against 11 bps of priced costs would trade; with a carry the model
    could not price, it does not — an unknown cost is not a small one."""
    incomplete = _model().estimate(
        quantity=0.01, conditions=_conditions(), entry_maker=True,
        direction=Direction.LONG, funding_rate=None, funding_periods=3,
    )
    complete = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True)
    estimator = _seeded(300.0)
    engine = ExpectedValueEngine(estimator, threshold_bps=5.0, max_cost_ratio=0.6)
    yes = engine.evaluate(regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=complete)
    no = engine.evaluate(regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=incomplete)
    assert yes.is_tradeable is True
    assert no.is_tradeable is False
    assert no.net_edge_bps == pytest.approx(yes.net_edge_bps), "the priced part is identical"
    assert "incomplete" in no.explain()


def test_borrow_is_charged_to_a_short_per_day_and_never_to_a_long() -> None:
    """5 bps per day over two days: 10 bps on a short; a long borrows nothing."""
    short = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.SHORT,
        borrow_rate_bps_per_day=5.0, holding_days=2.0,
    )
    long = _model().estimate(
        quantity=0.01, conditions=_conditions(), direction=Direction.LONG,
        borrow_rate_bps_per_day=5.0, holding_days=2.0,
    )
    assert short.borrow_bps == pytest.approx(10.0) and short.total_bps == pytest.approx(27.0)
    assert long.borrow_bps == 0.0


# -------------------------------------------------------------- units and conversions


def test_basis_points_convert_to_currency_through_the_notional() -> None:
    """0.01 BTC at 100,000 is 1,000 of notional; 15 bps of it is 1.50."""
    costs = _model().estimate(quantity=0.01, conditions=_conditions(spread_bps=0.0))
    assert costs.notional == pytest.approx(1_000.0)
    assert costs.total_bps == pytest.approx(15.0)
    assert costs.total_currency == pytest.approx(1.50)
    assert BPS == 1e-4


def test_the_notional_uses_the_absolute_quantity_so_a_short_is_not_negative() -> None:
    costs = _model().estimate(quantity=-0.01, conditions=_conditions())
    assert costs.notional == pytest.approx(1_000.0) and costs.total_currency > 0


def test_a_price_level_does_not_change_the_cost_in_basis_points() -> None:
    low = _model().estimate(quantity=1.0, conditions=_conditions(price=1_000.0))
    high = _model().estimate(quantity=0.01, conditions=_conditions(price=100_000.0))
    assert low.total_bps == pytest.approx(high.total_bps)
    assert low.total_currency == pytest.approx(high.total_currency), "same notional, same money"


def test_the_itemisation_adds_up_to_the_total() -> None:
    costs = _model().estimate(
        quantity=4.0, conditions=_conditions(bar_volume=16.0, latency_ms=6_000.0, volatility_per_bar=0.001),
        direction=Direction.SHORT, funding_rate=-0.0001, funding_periods=2,
        borrow_rate_bps_per_day=1.0, holding_days=1.0,
    )
    itemised = (
        costs.fee_bps + costs.spread_bps + costs.slippage_bps + costs.latency_bps
        + costs.impact_bps + costs.funding_bps + costs.borrow_bps
    )
    assert costs.total_bps == pytest.approx(itemised)
    assert costs.entry_fee_bps + costs.exit_fee_bps == pytest.approx(costs.fee_bps)
    d = costs.as_dict()
    assert d["total_bps"] == pytest.approx(
        d["fee_bps"] + d["execution_bps"] + d["carry_bps"], abs=1e-3
    )


# --------------------------------------------------- costs once, in the expected value


def test_costs_are_subtracted_from_the_gross_edge_exactly_once() -> None:
    """Past trades averaged +30 gross and paid 10; today's trade costs 11. Net is
    30 - 11 = 19, not 30 - 10 - 11 = 9."""
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True)
    ev = ExpectedValueEngine(_seeded(30.0), threshold_bps=5.0).evaluate(
        regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=costs
    )
    assert ev.gross_edge_bps == pytest.approx(30.0)
    assert ev.net_edge_bps == pytest.approx(19.0)
    assert ev.is_tradeable is True


def test_a_winner_before_costs_is_a_loser_after_them_and_is_refused() -> None:
    """+8 bps gross against 11 bps of costs: -3 bps net, refused at any threshold ≥ 0."""
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True)
    for threshold in (5.0, 0.0):
        ev = ExpectedValueEngine(_seeded(8.0), threshold_bps=threshold).evaluate(
            regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=costs
        )
        assert ev.net_edge_bps == pytest.approx(-3.0)
        assert ev.is_tradeable is False
    assert math.isclose(ev.net_edge_currency, -0.30, abs_tol=1e-9), "-3 bps of 1,000"


def test_a_loser_before_costs_loses_more_after_them() -> None:
    """A bucket whose mean is -5 bps is shrunk to 0 (never credited); minus 11 bps of
    costs the net is -11 and the trade is refused."""
    costs = _model().estimate(quantity=0.01, conditions=_conditions(), entry_maker=True)
    ev = ExpectedValueEngine(_seeded(-5.0), threshold_bps=5.0).evaluate(
        regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=costs
    )
    assert ev.gross_edge_bps <= 0.0
    assert ev.net_edge_bps == pytest.approx(ev.gross_edge_bps - 11.0)
    assert ev.is_tradeable is False


def test_the_cost_ratio_ceiling_refuses_a_trade_that_depends_on_the_cost_model() -> None:
    """17 bps of costs out of 25 gross is 68 % — net +8 clears 5 bps, the ratio does not."""
    costs = _model().estimate(quantity=0.01, conditions=_conditions())
    ev = ExpectedValueEngine(_seeded(25.0), threshold_bps=5.0, max_cost_ratio=0.6).evaluate(
        regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=costs
    )
    assert ev.net_edge_bps == pytest.approx(8.0)
    assert ev.cost_ratio == pytest.approx(0.68)
    assert ev.is_tradeable is False and "ceiling" in ev.reason


def test_the_worked_example() -> None:
    """The report's example, end to end: 0.01 BTC at 100,000; maker in, taker out; one
    crossing of a 2 bps book; three settlements at +0.0001 on a long; gross edge 30."""
    costs = _model().estimate(
        quantity=0.01, conditions=_conditions(), entry_maker=True,
        direction=Direction.LONG, funding_rate=0.0001, funding_periods=3,
    )
    assert costs.notional == pytest.approx(1_000.0)
    assert costs.fee_bps == pytest.approx(10.0)       # 2.5 + 7.5
    assert costs.spread_bps == pytest.approx(1.0)     # 2.0 x ½ x 1 crossing
    assert costs.funding_bps == pytest.approx(3.0)    # 3 x 0.0001 / 1e-4
    assert costs.total_bps == pytest.approx(14.0)
    assert costs.total_currency == pytest.approx(1.40)
    ev = ExpectedValueEngine(_seeded(30.0), threshold_bps=5.0, max_cost_ratio=0.6).evaluate(
        regime=REGIME, direction=Direction.LONG, confidence=0.9, costs=costs
    )
    assert ev.net_edge_bps == pytest.approx(16.0)
    assert ev.net_edge_currency == pytest.approx(1.60)
    assert ev.cost_ratio == pytest.approx(14.0 / 30.0)
    assert ev.is_tradeable is True


# ------------------------------------------------ the estimator's sample stays gross


def test_the_backtester_feeds_the_estimator_gross_returns_with_the_fees_beside_them() -> None:
    """What the backtester writes for a closed trade: gross and fees separately, so the
    sample is the gross move and the engine subtracts today's costs once."""
    outcome = Outcome(
        regime=REGIME, direction=Direction.LONG, confidence=0.8,
        net_return_bps=40.0 - 10.0, fees_bps=10.0, gross_return_bps=40.0, market_data="backtest",
    )
    assert outcome.edge_sample_bps == pytest.approx(40.0)


def test_trade_costs_defaults_are_a_complete_fee_only_estimate() -> None:
    plain = TradeCosts(fee_bps=10.0, spread_bps=0.0, slippage_bps=0.0, latency_bps=0.0, impact_bps=0.0, notional=1.0)
    assert plain.complete and plain.carry_bps == 0.0 and plain.total_bps == 10.0
