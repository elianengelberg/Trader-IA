"""Statistical inference for the strategy experiment: intervals, multiplicity, verdicts.

Everything a verdict depends on is here, fixed before any result is read, and imported by
the harness rather than defined in it, so a test can exercise the exact rule the script
applies.

**Interval.** The mean net return per trade is estimated with a *circular block
bootstrap* (Politis & Romano, 1992), not an i.i.d. one: consecutive round trips are not
independent — regimes persist, volatility clusters, a losing streak is one event spread
over several trades — and resampling them as if they were understates the uncertainty.
Blocks of consecutive trades are drawn with replacement from the series wrapped around on
itself; the block length follows the ``n ** (1/3)`` rate (Hall, Horowitz & Jing, 1995),
which is a defensible default, not an optimal choice for any particular series. The
i.i.d. interval is computed alongside for comparison and never used for a verdict.

**Level.** Two-sided 90 %, pre-registered in Phase 1 and kept. The decision reads only
the lower bound, so the one-sided error is 5 %. It is not tuned to any result.

**Multiplicity.** Several candidates (one per strategy x horizon) are judged on the same
validation partition. The verdict interval is computed at the Bonferroni-adjusted level
``1 - (1 - level) / k`` for the ``k`` candidates in the family, which keeps the family-wise
one-sided error at 5 % whatever their dependence. Conservative on purpose; the cost
variants of one candidate are robustness checks of that candidate, not extra candidates.

**Verdict.** ``PROMISING_ON_VALIDATION`` requires the adjusted lower bound to be strictly
above zero, plus profit factor, drawdown and the cost stress. It means "worth a further
out-of-sample evaluation" and nothing more — not profitable, not an authorisation for
real money.

**What this does not do.** It does not remove selection bias from choosing the best of
``k``; it bounds the false-positive rate of the label. It does not estimate the probability
of backtest overfitting, and it says nothing about data that was never evaluated.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: Pre-registered acceptance criteria for the VALIDATION partition. Fixed, applied
#: mechanically, documented in docs/STRATEGY_IMPROVEMENT_PHASE.md §7 (Phase 1.1 update).
CRITERIA: dict[str, Any] = {
    "min_trades": 30,  # below this nothing is said: INSUFFICIENT
    "ci_level": 0.90,  # two-sided; the decision uses the lower bound only (5 % one-sided)
    "ci_lower_min_bps": 0.0,  # the (adjusted) lower bound must be STRICTLY above this
    "min_profit_factor": 1.2,
    "max_drawdown_pct": 1.0,
    "fee_stress_multiplier": 1.5,  # mean net bps must stay > 0 with fees x1.5: else FRAGILE
    "bootstrap": "circular_block",  # block length round(n ** (1/3)); i.i.d. reported alongside
    "resamples": 2_000,
    "multiplicity": "bonferroni",  # family = (strategy, timeframe) candidates on validation
}


class Verdict(StrEnum):
    INSUFFICIENT = "INSUFFICIENT"
    UNFAVOURABLE = "UNFAVOURABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    FRAGILE = "FRAGILE"
    PROMISING_ON_VALIDATION = "PROMISING_ON_VALIDATION"


@dataclass(frozen=True)
class VerdictResult:
    verdict: Verdict
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict.value, "reason": self.reason}


# ---------------------------------------------------------------------------- intervals


def block_length(n: int) -> int:
    """``round(n ** (1/3))``, at least 1 and at most ``n``."""
    if n <= 0:
        return 1
    return max(1, min(n, round(n ** (1.0 / 3.0))))


def adjusted_level(level: float, k: int) -> float:
    """Bonferroni: the per-candidate level that keeps the family at ``level``."""
    if not 0.0 < level < 1.0:
        raise ValueError("level must be strictly between 0 and 1")
    k = max(1, int(k))
    return 1.0 - (1.0 - level) / k


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation between order statistics (Hyndman & Fan type 7, the default
    of ``numpy.quantile`` and R). Before 1.3 the index was truncated to an integer, which
    biased both ends of every interval toward the centre by up to one order statistic —
    at 2 000 resamples and a 90 % level, the lower bound read the 100th mean where the
    99.95th was asked for (Phase 1.3).
    """
    last = len(sorted_values) - 1
    position = q * last
    below = int(position)
    above = min(below + 1, last)
    weight = position - below
    return sorted_values[below] * (1.0 - weight) + sorted_values[above] * weight


def _percentiles(means: list[float], level: float) -> tuple[float, float]:
    means = sorted(means)
    alpha = (1.0 - level) / 2.0
    return (_quantile(means, alpha), _quantile(means, 1.0 - alpha))


def _all_finite(values: list[float]) -> bool:
    return all(math.isfinite(v) for v in values)


def iid_bootstrap_ci(
    values: list[float], *, seed: int, level: float = 0.90, resamples: int = 2_000
) -> tuple[float, float] | None:
    """Percentile bootstrap of the mean treating trades as independent. For comparison."""
    n = len(values)
    if n < 2 or not _all_finite(values):
        return None  # a NaN would sort anywhere and read as a bound (Phase 1.3)
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(values, k=n)) for _ in range(resamples)]
    return _percentiles(means, level)


def block_bootstrap_ci(
    values: list[float],
    *,
    seed: int,
    level: float = 0.90,
    resamples: int = 2_000,
    block: int | None = None,
) -> tuple[float, float] | None:
    """Circular block bootstrap percentile interval of the mean.

    Each resample concatenates ``ceil(n / b)`` blocks of ``b`` consecutive values, each
    block starting at a uniformly random position of the series wrapped around on itself,
    truncated to ``n``. Reproducible for a given ``seed``; ``block`` defaults to
    :func:`block_length`. ``None`` below two values.
    """
    n = len(values)
    if n < 2 or not _all_finite(values):
        return None  # a NaN would sort anywhere and read as a bound (Phase 1.3)
    b = block or block_length(n)
    b = max(1, min(n, int(b)))
    rng = random.Random(seed)
    blocks_needed = -(-n // b)
    means: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        for _ in range(blocks_needed):
            start = rng.randrange(n)
            sample.extend(values[(start + j) % n] for j in range(b))
        means.append(statistics.fmean(sample[:n]))
    return _percentiles(means, level)


# ---------------------------------------------------------------------------- verdicts


def verdict(
    *,
    trades: int,
    ci: tuple[float, float] | None,
    profit_factor: float | None,
    max_drawdown_pct: float,
    stressed_mean_bps: float | None,
    criteria: dict[str, Any] = CRITERIA,
) -> VerdictResult:
    """The pre-registered rule, in this order and no other.

    ``ci`` is the interval the decision is read from — the multiplicity-adjusted block
    bootstrap interval, when candidates were compared. ``stressed_mean_bps`` is the mean
    net return under the fee stress; ``None`` means the stress was not run, and then
    nothing can be called promising.
    """
    min_trades = int(criteria["min_trades"])
    if trades < min_trades or ci is None:
        return VerdictResult(
            Verdict.INSUFFICIENT,
            f"{trades} trades; at least {min_trades} are needed before an interval means anything",
        )
    lo, hi = ci
    if not (math.isfinite(lo) and math.isfinite(hi)):
        # NaN compares False to everything and would slide past every bound below.
        return VerdictResult(Verdict.INSUFFICIENT, f"the interval [{lo}, {hi}] is not finite")
    floor = float(criteria["ci_lower_min_bps"])
    if hi < 0.0:
        return VerdictResult(
            Verdict.UNFAVOURABLE, f"the whole interval [{lo:.2f}, {hi:.2f}] bps is below zero"
        )
    if lo <= floor:
        return VerdictResult(
            Verdict.INCONCLUSIVE,
            f"the lower bound {lo:.2f} bps is not strictly above {floor:.2f}: zero is inside "
            "the noise",
        )
    pf_min = float(criteria["min_profit_factor"])
    if profit_factor is None or math.isnan(profit_factor) or profit_factor <= pf_min:
        return VerdictResult(
            Verdict.INCONCLUSIVE,
            f"profit factor {profit_factor if profit_factor is not None else 'n/a'} is not above {pf_min}",
        )
    dd_max = float(criteria["max_drawdown_pct"])
    if not math.isfinite(max_drawdown_pct) or max_drawdown_pct >= dd_max:
        return VerdictResult(
            Verdict.INCONCLUSIVE, f"max drawdown {max_drawdown_pct:.2f} % is not below {dd_max:.2f} %"
        )
    if stressed_mean_bps is None:
        return VerdictResult(
            Verdict.INCONCLUSIVE,
            f"the cost stress (fees x{criteria['fee_stress_multiplier']}) was not run; nothing is "
            "promising without it",
        )
    if math.isnan(stressed_mean_bps) or stressed_mean_bps <= 0.0:
        return VerdictResult(
            Verdict.FRAGILE,
            f"mean net {stressed_mean_bps:.2f} bps under fees x{criteria['fee_stress_multiplier']} "
            "is not positive",
        )
    return VerdictResult(
        Verdict.PROMISING_ON_VALIDATION,
        f"adjusted lower bound {lo:.2f} bps > {floor:.2f}, PF > {pf_min}, drawdown < {dd_max} %, "
        "positive under cost stress — worth a further out-of-sample evaluation; not a claim "
        "of profitability",
    )


__all__ = [
    "CRITERIA",
    "Verdict",
    "VerdictResult",
    "adjusted_level",
    "block_bootstrap_ci",
    "block_length",
    "iid_bootstrap_ci",
    "verdict",
]
