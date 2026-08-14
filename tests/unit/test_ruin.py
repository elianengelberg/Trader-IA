"""Probability of ruin.

A positive expectancy is not protection. Betting too much of a winning edge goes bankrupt
with probability approaching one, and nothing in a Sharpe ratio warns about it — which is
why this is computed separately and shown separately.

Two estimates on purpose, analytic and simulated, so that a disagreement between them is
visible rather than averaged away. Every simulation is seeded: a risk number that changes
each time you look at it is not a risk number.
"""

from __future__ import annotations

import numpy as np
import pytest

from tia.risk.ruin import (
    RUIN_THRESHOLD,
    analytic_probability_of_ruin,
    max_safe_risk_fraction,
    monte_carlo_ruin,
)


def coin_flip_returns(
    *, win_rate: float, win: float, loss: float, count: int = 500, seed: int = 7
) -> list[float]:
    rng = np.random.default_rng(seed)
    return [win if rng.random() < win_rate else -loss for _ in range(count)]


# --------------------------------------------------------------------------- determinism


def test_the_same_inputs_and_seed_produce_the_same_number_every_time() -> None:
    returns = coin_flip_returns(win_rate=0.55, win=0.01, loss=0.01)
    first = monte_carlo_ruin(returns, paths=2_000, seed=42)
    second = monte_carlo_ruin(returns, paths=2_000, seed=42)

    assert first.probability_of_ruin == second.probability_of_ruin
    assert first.worst_max_drawdown_pct == second.worst_max_drawdown_pct


def test_a_different_seed_gives_a_similar_answer_not_an_unrelated_one() -> None:
    """If the estimate moved materially with the seed, the path count would be too low for
    the precision the number is presented with."""
    returns = coin_flip_returns(win_rate=0.52, win=0.02, loss=0.02)
    a = monte_carlo_ruin(returns, paths=8_000, seed=1)
    b = monte_carlo_ruin(returns, paths=8_000, seed=2)

    assert a.probability_of_ruin == pytest.approx(b.probability_of_ruin, abs=0.02)


# --------------------------------------------------------------------------- the point


def test_betting_more_of_the_same_winning_edge_raises_the_ruin_probability() -> None:
    """The whole reason this module exists.

    Same edge, same win rate, same everything — only the fraction risked changes, and the
    probability of losing half the account goes from negligible to near-certain.
    """
    small = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.55, win=0.005, loss=0.005), paths=4_000, seed=11
    )
    large = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.55, win=0.40, loss=0.40), paths=4_000, seed=11
    )

    assert small.probability_of_ruin < 0.01
    assert large.probability_of_ruin > 0.5
    assert small.is_acceptable
    assert not large.is_acceptable


def test_a_negative_expectancy_ruins_regardless_of_bet_size() -> None:
    losing = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.35, win=0.02, loss=0.02, count=800), paths=3_000, seed=5
    )
    assert losing.probability_of_ruin > 0.9
    assert analytic_probability_of_ruin(win_rate=0.35, payoff_ratio=1.0, risk_fraction=0.02) == 1.0


def test_ruin_means_half_the_account_not_a_zero_balance() -> None:
    """An account is finished long before zero: position sizes shrink with equity and the
    strategy stops being viable. The threshold is stated in every result rather than left
    implicit."""
    estimate = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.5, win=0.05, loss=0.05), paths=2_000, seed=3
    )
    assert estimate.ruin_threshold == RUIN_THRESHOLD == 0.5
    assert f"{RUIN_THRESHOLD:.0%}" in estimate.explain()


# --------------------------------------------------------------------------- honesty


def test_the_estimate_reports_the_longest_losing_streak_it_produced() -> None:
    """The bootstrap resamples with replacement, which breaks up losing streaks and is
    therefore optimistic. Reporting the streak makes that optimism visible instead of
    leaving it in a docstring."""
    estimate = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.5, win=0.01, loss=0.01), paths=1_000, seed=9
    )
    assert estimate.longest_losing_streak > 0


def test_the_explanation_describes_a_simulation_and_does_not_forecast() -> None:
    """§63/§76: no claim about future returns, at the exact place a number looks most
    like a promise."""
    text = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.55, win=0.01, loss=0.01), paths=1_000, seed=4
    ).explain()

    assert "it is not a forecast" in text
    assert "simulated" in text


def test_both_estimates_are_reported_so_a_disagreement_is_visible() -> None:
    estimate = monte_carlo_ruin(
        coin_flip_returns(win_rate=0.6, win=0.01, loss=0.01), paths=3_000, seed=8
    )
    payload = estimate.as_dict()

    assert "probability_of_ruin" in payload
    assert "analytic_probability" in payload
    assert payload["seed"] == 8


# --------------------------------------------------------------------------- refusals


def test_too_few_trades_raises_rather_than_producing_a_number() -> None:
    """One trade is not a distribution. Producing a ruin probability from it would put a
    precise-looking figure in front of someone deciding how much to risk."""
    with pytest.raises(ValueError, match="at least two closed trades"):
        monte_carlo_ruin([0.01])


def test_non_finite_returns_are_dropped_before_they_poison_the_simulation() -> None:
    returns = [0.01, -0.01, float("nan"), 0.02, float("inf"), -0.02]
    estimate = monte_carlo_ruin(returns, paths=500, seed=6)
    assert 0.0 <= estimate.probability_of_ruin <= 1.0


def test_the_analytic_form_declines_when_its_assumptions_do_not_hold() -> None:
    assert analytic_probability_of_ruin(win_rate=0.0, payoff_ratio=1.0, risk_fraction=0.01) is None
    assert analytic_probability_of_ruin(win_rate=1.0, payoff_ratio=1.0, risk_fraction=0.01) is None
    assert analytic_probability_of_ruin(win_rate=0.5, payoff_ratio=0.0, risk_fraction=0.01) is None
    assert analytic_probability_of_ruin(win_rate=0.5, payoff_ratio=2.0, risk_fraction=0.0) is None


# --------------------------------------------------------------------------- sizing


def test_the_safe_risk_search_returns_a_fraction_and_the_evidence_for_it() -> None:
    result = max_safe_risk_fraction(
        coin_flip_returns(win_rate=0.58, win=0.01, loss=0.01), horizon_trades=200, seed=13
    )

    assert result is not None
    fraction, estimate = result
    assert 0 < fraction <= 0.05
    assert estimate.probability_of_ruin <= 0.01


def test_the_search_answers_do_not_trade_this_when_even_the_smallest_bet_ruins() -> None:
    """``None`` is a real answer, not a failure to compute one."""
    hopeless = coin_flip_returns(win_rate=0.2, win=0.01, loss=0.05, count=400)
    assert max_safe_risk_fraction(hopeless, horizon_trades=400, seed=2) is None


def test_the_search_reports_a_ladder_value_not_false_precision() -> None:
    """The input distribution does not support three decimals, and printing "1.37%" would
    imply it does."""
    result = max_safe_risk_fraction(
        coin_flip_returns(win_rate=0.6, win=0.01, loss=0.01), horizon_trades=200, seed=21
    )
    assert result is not None
    assert result[0] in (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05)
