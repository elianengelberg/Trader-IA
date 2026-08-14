"""The risk budget, and the one property it must never violate.

Most of this file is about a single claim: **risk never rises because the account is
losing.** That claim covers martingale, revenge trading and "increase size to recover the
drawdown", which are the same behaviour under three names, and it is asserted as a property
over randomised inputs rather than as a handful of examples — because a hand-picked example
proves only that the author thought of that case.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tia.risk.budget import (
    PROFILES,
    BudgetInputs,
    DrawdownState,
    RiskBudgetEngine,
    RiskProfileName,
    annualise_volatility,
    assert_no_martingale,
    assert_profiles_are_ordered,
)

BASE = BudgetInputs(
    equity=10_000.0,
    peak_equity=10_000.0,
    drawdown_pct=0.0,
    realised_annual_volatility=0.20,
    consecutive_losses=0,
    trades_today=0,
    open_gross_exposure_pct=0.0,
)


def inputs(**changes: float | int) -> BudgetInputs:
    from dataclasses import replace

    return replace(BASE, **changes)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- the property


@settings(max_examples=300, deadline=None)
@given(
    equity=st.floats(min_value=100.0, max_value=1_000_000.0),
    drawdown=st.floats(min_value=0.0, max_value=40.0),
    volatility=st.floats(min_value=0.0, max_value=3.0),
    losses=st.integers(min_value=0, max_value=15),
    trades=st.integers(min_value=0, max_value=30),
    exposure=st.floats(min_value=0.0, max_value=150.0),
    profile=st.sampled_from(list(RiskProfileName)),
)
def test_risk_never_increases_with_losses_under_any_inputs(
    equity: float,
    drawdown: float,
    volatility: float,
    losses: int,
    trades: int,
    exposure: float,
    profile: RiskProfileName,
) -> None:
    """§76: no Martingale, no revenge trading, no raising risk to recover a loss.

    Hypothesis searches for any combination of equity, drawdown, volatility, streak,
    trade count and exposure where deepening the drawdown or adding a loss makes the
    budget *larger*. There must be none.
    """
    engine = RiskBudgetEngine(profile)
    assert_no_martingale(
        engine,
        BudgetInputs(
            equity=equity,
            peak_equity=equity,
            drawdown_pct=drawdown,
            realised_annual_volatility=volatility,
            consecutive_losses=losses,
            trades_today=trades,
            open_gross_exposure_pct=exposure,
        ),
    )


@settings(max_examples=200, deadline=None)
@given(
    drawdown=st.floats(min_value=0.0, max_value=30.0),
    step=st.floats(min_value=0.01, max_value=10.0),
)
def test_the_drawdown_multiplier_is_monotonically_non_increasing(
    drawdown: float, step: float
) -> None:
    """Stronger than the no-martingale check: not merely "never rises after one more
    percent of drawdown", but never rises after *any* amount of it."""
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    shallow = engine.compute(inputs(drawdown_pct=drawdown))
    deeper = engine.compute(inputs(drawdown_pct=drawdown + step))
    assert deeper.risk_currency <= shallow.risk_currency + 1e-9


def test_a_longer_losing_streak_halves_the_budget_and_keeps_halving() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    dampener = PROFILES[RiskProfileName.BALANCED].consecutive_loss_dampener

    before = engine.compute(inputs(consecutive_losses=dampener - 1))
    first = engine.compute(inputs(consecutive_losses=dampener))
    second = engine.compute(inputs(consecutive_losses=dampener + 1))

    assert before.streak_multiplier == 1.0
    assert first.streak_multiplier == pytest.approx(0.5)
    assert second.streak_multiplier == pytest.approx(0.25)


# --------------------------------------------------------------------------- states


def test_the_drawdown_state_machine_moves_one_way_through_its_thresholds() -> None:
    profile = PROFILES[RiskProfileName.BALANCED]
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)

    assert engine.state_for(0.0) is DrawdownState.NORMAL
    assert engine.state_for(profile.defensive_drawdown_pct - 0.01) is DrawdownState.NORMAL
    assert engine.state_for(profile.defensive_drawdown_pct) is DrawdownState.DEFENSIVE
    assert engine.state_for(profile.emergency_drawdown_pct - 0.01) is DrawdownState.DEFENSIVE
    assert engine.state_for(profile.emergency_drawdown_pct) is DrawdownState.EMERGENCY
    assert engine.state_for(90.0) is DrawdownState.EMERGENCY


def test_emergency_stops_new_trades_entirely_rather_than_shrinking_them() -> None:
    """A very small position is still a position, and the emergency state exists because
    the evidence says stop, not slow down."""
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    budget = engine.compute(inputs(drawdown_pct=12.0))

    assert budget.state is DrawdownState.EMERGENCY
    assert budget.allows_new_trades is False
    assert budget.risk_currency == 0.0
    assert budget.risk_pct == 0.0
    assert "emergency" in budget.binding_constraint


@pytest.mark.parametrize("name", list(RiskProfileName))
def test_the_budget_is_continuous_across_the_defensive_boundary(name: RiskProfileName) -> None:
    """A step at the threshold means a hundredth of a percent of drawdown changes position
    size discontinuously — and if the step goes *up*, it is martingale behaviour arriving
    by accident.

    Parametrised across all three profiles deliberately. An earlier version of this test
    checked only ``balanced``, which passed because that profile's defensive multiplier
    happened to equal the constant the normal-state taper ended at. ``aggressive`` did not,
    and its budget rose 6% on crossing into the defensive state. One profile is not a test
    of a formula that takes the profile as a parameter.
    """
    profile = PROFILES[name]
    engine = RiskBudgetEngine(name)

    just_under = engine.compute(inputs(drawdown_pct=profile.defensive_drawdown_pct - 1e-6))
    just_over = engine.compute(inputs(drawdown_pct=profile.defensive_drawdown_pct + 1e-6))

    assert just_over.risk_currency == pytest.approx(just_under.risk_currency, rel=1e-4)
    assert just_over.risk_currency <= just_under.risk_currency + 1e-9


@pytest.mark.parametrize("name", list(RiskProfileName))
def test_the_drawdown_taper_hits_its_endpoints_exactly(name: RiskProfileName) -> None:
    """Full budget at no drawdown, the profile's defensive multiplier at the defensive
    threshold, zero at the emergency threshold. Anchoring the taper to the profile rather
    than to a constant is what keeps the two segments joined."""
    profile = PROFILES[name]
    engine = RiskBudgetEngine(name)

    assert engine.compute(inputs(drawdown_pct=0.0)).drawdown_multiplier == pytest.approx(1.0)
    assert engine.compute(
        inputs(drawdown_pct=profile.defensive_drawdown_pct)
    ).drawdown_multiplier == pytest.approx(profile.defensive_multiplier)
    assert engine.compute(
        inputs(drawdown_pct=profile.emergency_drawdown_pct)
    ).drawdown_multiplier == 0.0


def test_a_profile_whose_thresholds_are_out_of_order_is_rejected() -> None:
    """An emergency threshold below the defensive one means the defensive state is
    unreachable, and a state machine with an unreachable state is a bug wearing a
    configuration costume."""
    from pydantic import ValidationError

    from tia.risk.budget import RiskProfile

    with pytest.raises(ValidationError, match="emergency_drawdown_pct"):
        RiskProfile(
            name=RiskProfileName.BALANCED,
            risk_per_trade_pct=0.5,
            defensive_drawdown_pct=10.0,
            emergency_drawdown_pct=5.0,
            max_gross_exposure_pct=80.0,
            defensive_multiplier=0.5,
            target_annual_volatility=0.2,
            max_trades_per_day=20,
            consecutive_loss_dampener=4,
        )


# --------------------------------------------------------------------------- volatility


def test_low_volatility_never_licenses_a_bigger_position_than_the_profile_allows() -> None:
    """Uncapped volatility targeting is how a quiet market builds leverage that one gap
    erases. The multiplier is capped at 1.0 and this is the test that says so."""
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    quiet = engine.compute(inputs(realised_annual_volatility=0.001))
    calibrated = engine.compute(inputs(realised_annual_volatility=0.20))

    assert quiet.volatility_multiplier == 1.0
    assert quiet.risk_currency == pytest.approx(calibrated.risk_currency)


def test_high_volatility_shrinks_the_position_proportionally() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    target = PROFILES[RiskProfileName.BALANCED].target_annual_volatility
    budget = engine.compute(inputs(realised_annual_volatility=target * 4))

    assert budget.volatility_multiplier == pytest.approx(0.25)
    assert budget.binding_constraint == "volatility"


def test_unknown_volatility_does_not_silently_become_zero_volatility() -> None:
    """A zero reading means "not measured yet", and treating it as "the market is calm"
    would be the optimistic reading of missing data."""
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    assert engine.compute(inputs(realised_annual_volatility=0.0)).volatility_multiplier == 1.0


# --------------------------------------------------------------------------- caps


def test_the_daily_trade_cap_and_exposure_cap_each_stop_trading() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    profile = PROFILES[RiskProfileName.BALANCED]

    capped = engine.compute(inputs(trades_today=profile.max_trades_per_day))
    assert not capped.allows_new_trades
    assert "daily trade cap" in capped.binding_constraint

    exposed = engine.compute(inputs(open_gross_exposure_pct=profile.max_gross_exposure_pct))
    assert not exposed.allows_new_trades
    assert "gross exposure" in exposed.binding_constraint


def test_the_binding_constraint_names_the_multiplier_that_actually_bound() -> None:
    """The UI shows this string next to a reduced size. If it named the wrong constraint,
    an operator would go and adjust the wrong thing."""
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    dampener = PROFILES[RiskProfileName.BALANCED].consecutive_loss_dampener

    assert engine.compute(BASE).binding_constraint == "none"
    assert engine.compute(inputs(consecutive_losses=dampener)).binding_constraint == "loss streak"
    assert engine.compute(inputs(drawdown_pct=4.0)).binding_constraint == "drawdown"


# --------------------------------------------------------------------------- profiles


def test_the_three_profiles_are_ordered_on_every_dimension() -> None:
    assert_profiles_are_ordered()


def test_a_more_aggressive_profile_risks_more_under_identical_conditions() -> None:
    budgets = {
        name: RiskBudgetEngine(name).compute(BASE).risk_currency for name in RiskProfileName
    }
    assert (
        budgets[RiskProfileName.CONSERVATIVE]
        < budgets[RiskProfileName.BALANCED]
        < budgets[RiskProfileName.AGGRESSIVE]
    )


def test_a_profile_cannot_be_mutated_at_runtime() -> None:
    """Risk parameters are configuration. Nothing in the running system — including a
    model output — may edit them."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PROFILES[RiskProfileName.CONSERVATIVE].risk_per_trade_pct = 5.0  # type: ignore[misc]


# --------------------------------------------------------------------------- helpers


def test_annualising_volatility_uses_square_root_of_time() -> None:
    assert annualise_volatility(0.01, 0.0) == 0.0
    assert annualise_volatility(0.01, 10_000.0) == pytest.approx(1.0)
