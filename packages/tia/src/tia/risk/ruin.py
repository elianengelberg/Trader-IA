"""Probability of ruin, and the Monte Carlo behind it.

A strategy with a positive expectancy still goes bankrupt if it bets too much. That is not
a paradox and it is not rare — it is the single most common way a *correct* edge produces
a zero balance, and no amount of Sharpe ratio warns you about it.

Two estimates, deliberately both:

* **Analytic** — a closed form for the fixed-fractional case. Instant, and useful as a
  sanity check on the simulation.
* **Monte Carlo** — resamples the actual trade distribution. Slower, makes no distributional
  assumption, and is the one to trust when the two disagree, because real trade returns are
  neither normal nor independent enough for the closed form to be exact.

Every simulation is **seeded**. A risk number that changes each time you look at it is not
a risk number.

**What "ruin" means here.** Not "balance reaches zero" — an account is finished long before
that, because position sizes shrink with equity and the strategy stops being viable. Ruin is
defined as equity falling below :data:`RUIN_THRESHOLD` of its starting value, and the
threshold is stated in every result rather than left implicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from tia.core.rng import derive_seed

#: Equity fraction below which the account is treated as ruined. 50% because a strategy
#: that has halved needs a 100% gain to recover, and almost none do.
RUIN_THRESHOLD = 0.5

#: Simulation paths. Enough for a stable estimate at the third decimal; more buys
#: precision the inputs do not have.
DEFAULT_PATHS = 20_000


@dataclass(frozen=True)
class RuinEstimate:
    """The answer plus everything needed to judge how much to trust it."""

    probability_of_ruin: float
    #: Median and worst-case drawdown across the simulated paths.
    median_max_drawdown_pct: float
    worst_max_drawdown_pct: float
    #: The 5th percentile of final equity, as a fraction of starting equity.
    equity_5th_percentile: float
    median_final_equity: float
    longest_losing_streak: int
    paths: int
    horizon_trades: int
    ruin_threshold: float
    analytic_probability: float | None
    seed: int

    @property
    def is_acceptable(self) -> bool:
        """Below 1%. Not a law of nature — a threshold, chosen because a 1-in-100 chance
        of losing half the capital is roughly the most anyone should accept from a system
        they are not watching continuously."""
        return self.probability_of_ruin < 0.01

    def as_dict(self) -> dict[str, Any]:
        return {
            "probability_of_ruin": round(self.probability_of_ruin, 6),
            "analytic_probability": (
                None if self.analytic_probability is None else round(self.analytic_probability, 6)
            ),
            "median_max_drawdown_pct": round(self.median_max_drawdown_pct, 4),
            "worst_max_drawdown_pct": round(self.worst_max_drawdown_pct, 4),
            "equity_5th_percentile": round(self.equity_5th_percentile, 4),
            "median_final_equity": round(self.median_final_equity, 4),
            "longest_losing_streak": self.longest_losing_streak,
            "paths": self.paths,
            "horizon_trades": self.horizon_trades,
            "ruin_threshold": self.ruin_threshold,
            "acceptable": self.is_acceptable,
            "seed": self.seed,
        }

    def explain(self) -> str:
        return (
            f"Over {self.horizon_trades} trades simulated {self.paths:,} times, equity fell "
            f"below {self.ruin_threshold:.0%} of its starting value in "
            f"{self.probability_of_ruin:.2%} of paths. Median worst drawdown "
            f"{self.median_max_drawdown_pct:.1f}%, worst observed "
            f"{self.worst_max_drawdown_pct:.1f}%. The 5th-percentile outcome ends at "
            f"{self.equity_5th_percentile:.2f}x starting equity. This describes the "
            f"simulated distribution of a historical trade sample; it is not a forecast."
        )


def analytic_probability_of_ruin(
    *, win_rate: float, payoff_ratio: float, risk_fraction: float
) -> float | None:
    """Closed-form ruin probability for fixed-fractional betting.

    The classic gambler's-ruin form, applicable when every bet risks the same *fraction*
    of current equity and outcomes are independent. Returns ``None`` when the assumptions
    do not hold — a negative-expectancy system ruins with probability 1 and does not need
    a formula, and a zero risk fraction never trades.
    """
    if not (0.0 < win_rate < 1.0) or payoff_ratio <= 0 or risk_fraction <= 0:
        return None

    edge = win_rate * payoff_ratio - (1.0 - win_rate)
    if edge <= 0:
        return 1.0

    # Units of risk between the starting equity and the ruin threshold.
    units = math.log(RUIN_THRESHOLD) / math.log(1.0 - risk_fraction)
    if units <= 0:
        return 1.0

    # a = probability the process drifts down one unit before up one unit.
    ratio = (1.0 - win_rate) / (win_rate * payoff_ratio)
    if ratio >= 1.0:
        return 1.0
    return float(min(1.0, ratio**units))


def monte_carlo_ruin(
    trade_returns: list[float] | np.ndarray,
    *,
    horizon_trades: int = 250,
    paths: int = DEFAULT_PATHS,
    seed: int = 20260812,
    ruin_threshold: float = RUIN_THRESHOLD,
) -> RuinEstimate:
    """Resample the observed trade distribution and see where it ends up.

    ``trade_returns`` are per-trade returns as fractions of equity at risk (0.01 = +1%).
    Sampled **with replacement**, which assumes trades are exchangeable — an assumption
    that is wrong when returns are autocorrelated, and wrong in the optimistic direction
    because it breaks up losing streaks. The bootstrap below therefore also reports the
    longest streak it produced, so that optimism is at least visible.
    """
    returns = np.asarray(trade_returns, dtype=np.float64)
    returns = returns[np.isfinite(returns)]
    if returns.size < 2:
        raise ValueError(
            f"a ruin estimate needs at least two closed trades; got {returns.size}. "
            "Run a backtest or paper session first."
        )
    if horizon_trades < 1 or paths < 1:
        raise ValueError("horizon_trades and paths must both be positive")

    rng = np.random.default_rng(derive_seed(seed, f"ruin:{returns.size}:{horizon_trades}"))
    draws = rng.choice(returns, size=(paths, horizon_trades), replace=True)

    # Compounding, because the next trade is sized off the equity the last one left.
    equity_paths = np.cumprod(1.0 + draws, axis=1)
    equity_paths = np.clip(equity_paths, 0.0, None)

    running_peak = np.maximum.accumulate(equity_paths, axis=1)
    drawdowns = (running_peak - equity_paths) / np.where(running_peak > 0, running_peak, 1.0)
    max_drawdowns = drawdowns.max(axis=1) * 100.0

    ruined = (equity_paths.min(axis=1) < ruin_threshold).mean()
    final_equity = equity_paths[:, -1]

    losses = draws < 0
    longest_streak = int(_longest_run(losses))

    win_rate = float((returns > 0).mean())
    wins = returns[returns > 0]
    losses_only = returns[returns < 0]
    payoff = (
        float(wins.mean() / abs(losses_only.mean()))
        if wins.size and losses_only.size and losses_only.mean() != 0
        else 0.0
    )
    typical_risk = float(np.abs(returns).mean())

    return RuinEstimate(
        probability_of_ruin=float(ruined),
        median_max_drawdown_pct=float(np.median(max_drawdowns)),
        worst_max_drawdown_pct=float(max_drawdowns.max()),
        equity_5th_percentile=float(np.percentile(final_equity, 5)),
        median_final_equity=float(np.median(final_equity)),
        longest_losing_streak=longest_streak,
        paths=paths,
        horizon_trades=horizon_trades,
        ruin_threshold=ruin_threshold,
        analytic_probability=analytic_probability_of_ruin(
            win_rate=win_rate, payoff_ratio=payoff, risk_fraction=typical_risk
        ),
        seed=seed,
    )


def _longest_run(mask: np.ndarray) -> int:
    """Longest run of True along the last axis, across all rows."""
    longest = 0
    for row in mask:
        current = 0
        for value in row:
            current = current + 1 if value else 0
            longest = max(longest, current)
    return longest


def max_safe_risk_fraction(
    trade_returns: list[float] | np.ndarray,
    *,
    target_ruin_probability: float = 0.01,
    horizon_trades: int = 250,
    seed: int = 20260812,
    candidates: tuple[float, ...] = (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05),
) -> tuple[float, RuinEstimate] | None:
    """The largest per-trade risk whose simulated ruin probability stays under target.

    Searched over a fixed ladder rather than optimised continuously: the input distribution
    does not support three-decimal precision, and presenting a number like "1.37%" would
    imply it does. Returns ``None`` when even the smallest candidate is too risky, which is
    a real answer meaning *do not trade this*.
    """
    base = np.asarray(trade_returns, dtype=np.float64)
    base = base[np.isfinite(base)]
    if base.size < 2:
        raise ValueError("need at least two closed trades")

    typical = float(np.abs(base).mean())
    if typical <= 0:
        return None

    best: tuple[float, RuinEstimate] | None = None
    for fraction in candidates:
        # Rescale the observed distribution to the candidate risk level.
        scaled = base * (fraction / typical)
        estimate = monte_carlo_ruin(
            scaled, horizon_trades=horizon_trades, paths=5_000, seed=seed
        )
        if estimate.probability_of_ruin <= target_ruin_probability:
            best = (fraction, estimate)
        else:
            break
    return best


__all__ = [
    "DEFAULT_PATHS",
    "RUIN_THRESHOLD",
    "RuinEstimate",
    "analytic_probability_of_ruin",
    "max_safe_risk_fraction",
    "monte_carlo_ruin",
]
