"""Performance statistics.

Every number a report or a dashboard displays about strategy performance is computed
here, in deterministic code, from a recorded equity curve and trade list. **The language
model never produces these figures** — its job is language and context, and a plausible
hallucinated Sharpe ratio is worse than no Sharpe ratio at all.

Two things this module refuses to do:

* **Annualize a Sharpe ratio from a handful of observations.** Below a configurable
  minimum, the value is returned as ``None`` rather than as a confident-looking number.
  A Sharpe computed from 9 trades is noise wearing a decimal point.
* **Report a metric without its sample size.** Every result carries the count it was
  derived from, so a reader can judge whether to believe it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

Array = NDArray[np.float64]

# Below this many observations, ratio metrics are reported as None rather than as a
# number the reader would over-trust.
MIN_OBSERVATIONS_FOR_RATIOS = 30


def _is_effectively_zero(dispersion: float, scale: float) -> bool:
    """Whether a standard deviation is zero for practical purposes.

    ``np.std`` of a constant array returns ~1e-18 rather than exactly 0.0, so an
    equality check silently passes and the ratio explodes to ~1e16 — a number that then
    looks like a real result on a dashboard. Compare against the scale of the data
    instead of against zero.
    """
    return dispersion <= max(abs(scale), 1.0) * 1e-12


@dataclass(frozen=True)
class TradeRecord:
    """One round-trip, as consumed by the statistics layer."""

    symbol: str
    pnl: float
    return_pct: float
    duration_seconds: float
    entry_price: float
    exit_price: float
    quantity: float
    fees: float = 0.0


class PerformanceMetrics(BaseModel):
    """A complete performance summary.

    Optional ratio fields are ``None`` when the sample is too small to support them —
    deliberately, so the caller must decide what to do rather than being handed a
    number that looks authoritative.
    """

    model_config = ConfigDict(frozen=True)

    observations: int = 0
    trades: int = 0

    total_return_pct: float = 0.0
    annualized_return_pct: float | None = None
    volatility_pct: float | None = None
    annualized_volatility_pct: float | None = None

    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None

    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0
    time_in_drawdown_pct: float = 0.0

    win_rate: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    average_win: float | None = None
    average_loss: float | None = None
    largest_win: float = 0.0
    largest_loss: float = 0.0
    payoff_ratio: float | None = None

    skewness: float | None = None
    kurtosis: float | None = None
    var_95_pct: float | None = None
    cvar_95_pct: float | None = None

    stability: float | None = Field(
        default=None, description="R^2 of the log equity curve against time; 1.0 is a straight line"
    )
    exposure_pct: float = 0.0
    total_fees: float = 0.0

    warnings: tuple[str, ...] = ()

    def is_reliable(self) -> bool:
        """Whether the sample supports the ratio metrics at all."""
        return self.observations >= MIN_OBSERVATIONS_FOR_RATIOS and self.trades >= 10

    def summary_line(self) -> str:
        def fmt(value: float | None, suffix: str = "") -> str:
            return "n/a" if value is None else f"{value:.2f}{suffix}"

        return (
            f"return={self.total_return_pct:.2f}% "
            f"sharpe={fmt(self.sharpe)} "
            f"sortino={fmt(self.sortino)} "
            f"maxDD={self.max_drawdown_pct:.2f}% "
            f"trades={self.trades} "
            f"win={fmt(None if self.win_rate is None else self.win_rate * 100, '%')}"
        )


def returns_from_equity(equity: object) -> Array:
    """Simple period returns from an equity curve."""
    arr = np.asarray(equity, dtype=np.float64)
    if arr.size < 2:
        return np.array([], dtype=np.float64)
    prior = arr[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(prior != 0, (arr[1:] - prior) / prior, 0.0)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def drawdown_series(equity: object) -> Array:
    """Drawdown at each point, as a positive percentage from the running peak."""
    arr = np.asarray(equity, dtype=np.float64)
    if arr.size == 0:
        return np.array([], dtype=np.float64)
    peaks = np.maximum.accumulate(arr)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peaks > 0, (peaks - arr) / peaks * 100.0, 0.0)
    return np.nan_to_num(dd, nan=0.0, posinf=0.0, neginf=0.0)


def max_drawdown(equity: object) -> tuple[float, int]:
    """Return ``(max_drawdown_pct, longest_drawdown_duration_in_bars)``."""
    dd = drawdown_series(equity)
    if dd.size == 0:
        return (0.0, 0)
    longest = current = 0
    for value in dd:
        current = current + 1 if value > 1e-12 else 0
        longest = max(longest, current)
    return (float(np.max(dd)), longest)


def sharpe_ratio(
    returns: object, *, periods_per_year: float, risk_free_rate: float = 0.0
) -> float | None:
    """Annualized Sharpe ratio, or ``None`` when the sample is too small."""
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < MIN_OBSERVATIONS_FOR_RATIOS:
        return None
    excess = arr - risk_free_rate / periods_per_year
    mean = float(np.mean(excess))
    sd = float(np.std(excess, ddof=1))
    if _is_effectively_zero(sd, mean):
        # Constant returns. There is no risk in the sample to adjust for, so a
        # risk-adjusted ratio is undefined rather than enormous.
        return None
    return float(mean / sd * math.sqrt(periods_per_year))


def sortino_ratio(
    returns: object, *, periods_per_year: float, risk_free_rate: float = 0.0
) -> float | None:
    """Annualized Sortino ratio (downside deviation in the denominator)."""
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < MIN_OBSERVATIONS_FOR_RATIOS:
        return None
    excess = arr - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    if downside.size == 0:
        # No losing period in the sample. That is not an infinite Sortino, it is an
        # unrepresentative sample — say so rather than print a huge number.
        return None
    mean = float(np.mean(excess))
    dd = float(np.sqrt(np.mean(downside**2)))
    if _is_effectively_zero(dd, mean):
        return None
    return float(mean / dd * math.sqrt(periods_per_year))


def profit_factor(trade_pnls: object) -> float | None:
    """Gross profit divided by gross loss."""
    arr = np.asarray(trade_pnls, dtype=np.float64)
    if arr.size == 0:
        return None
    gross_profit = float(arr[arr > 0].sum())
    gross_loss = float(-arr[arr < 0].sum())
    if gross_loss == 0.0:
        return None if gross_profit == 0.0 else float("inf")
    return gross_profit / gross_loss


def expectancy(trade_pnls: object) -> float | None:
    """Average P&L per trade — the number that actually decides whether to keep trading."""
    arr = np.asarray(trade_pnls, dtype=np.float64)
    return float(np.mean(arr)) if arr.size else None


def value_at_risk(returns: object, confidence: float = 0.95) -> float | None:
    """Historical VaR as a positive percentage loss at the given confidence."""
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < 20:
        return None
    return float(-np.percentile(arr, (1.0 - confidence) * 100.0) * 100.0)


def conditional_var(returns: object, confidence: float = 0.95) -> float | None:
    """Expected shortfall — the average loss in the tail beyond VaR."""
    arr = np.asarray(returns, dtype=np.float64)
    if arr.size < 20:
        return None
    threshold = np.percentile(arr, (1.0 - confidence) * 100.0)
    tail = arr[arr <= threshold]
    if tail.size == 0:
        return None
    return float(-np.mean(tail) * 100.0)


def stability_of_returns(equity: object) -> float | None:
    """R² of the log equity curve against time.

    A high total return achieved in one lucky bar and a high total return accumulated
    steadily look identical in a summary table. This tells them apart.
    """
    arr = np.asarray(equity, dtype=np.float64)
    if arr.size < 10 or np.any(arr <= 0):
        return None
    y = np.log(arr)
    x = np.arange(y.size, dtype=np.float64)
    x_c = x - x.mean()
    y_c = y - y.mean()
    denom = float(np.sum(x_c**2) * np.sum(y_c**2))
    if denom <= 0:
        return None
    corr = float(np.sum(x_c * y_c) / math.sqrt(denom))
    return corr**2


def compute_metrics(
    *,
    equity_curve: object,
    trades: list[TradeRecord] | None = None,
    periods_per_year: float,
    risk_free_rate: float = 0.0,
    bars_in_market: int = 0,
) -> PerformanceMetrics:
    """Compute the full metric set from an equity curve and optional trade list."""
    equity = np.asarray(equity_curve, dtype=np.float64)
    trades = trades or []
    warnings: list[str] = []

    if equity.size < 2:
        return PerformanceMetrics(
            observations=int(equity.size),
            trades=len(trades),
            warnings=("equity curve too short to compute any metric",),
        )

    rets = returns_from_equity(equity)
    total_return = float((equity[-1] / equity[0] - 1.0) * 100.0) if equity[0] > 0 else 0.0
    dd_pct, dd_duration = max_drawdown(equity)
    dd_series = drawdown_series(equity)

    years = equity.size / periods_per_year if periods_per_year > 0 else 0.0
    annualized: float | None = None
    if years > 0 and equity[0] > 0 and equity[-1] > 0:
        if years >= 0.05:  # ~18 days; below that, annualizing is fantasy
            annualized = float(((equity[-1] / equity[0]) ** (1.0 / years) - 1.0) * 100.0)
        else:
            warnings.append(
                f"period too short to annualize ({years * 365:.1f} days); "
                "annualized_return_pct withheld"
            )

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    if 0 < len(trades) < 10:
        warnings.append(f"only {len(trades)} trades; trade statistics are not meaningful")
    if 0 < rets.size < MIN_OBSERVATIONS_FOR_RATIOS:
        warnings.append(
            f"only {rets.size} return observations; risk-adjusted ratios withheld "
            f"(minimum {MIN_OBSERVATIONS_FOR_RATIOS})"
        )

    vol = float(np.std(rets, ddof=1)) if rets.size > 1 else None
    if vol is not None and _is_effectively_zero(vol, float(np.mean(rets))):
        vol = 0.0
    ann_vol = vol * math.sqrt(periods_per_year) * 100.0 if vol is not None else None

    calmar: float | None = None
    if annualized is not None and dd_pct > 1e-9:
        calmar = annualized / dd_pct

    skew: float | None = None
    kurt: float | None = None
    if rets.size >= MIN_OBSERVATIONS_FOR_RATIOS:
        sd = float(np.std(rets))
        if not _is_effectively_zero(sd, float(np.mean(rets))):
            centered = rets - float(np.mean(rets))
            skew = float(np.mean(centered**3) / sd**3)
            kurt = float(np.mean(centered**4) / sd**4 - 3.0)

    return PerformanceMetrics(
        observations=int(rets.size),
        trades=len(trades),
        total_return_pct=total_return,
        annualized_return_pct=annualized,
        volatility_pct=vol * 100.0 if vol is not None else None,
        annualized_volatility_pct=ann_vol,
        sharpe=sharpe_ratio(rets, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate),
        sortino=sortino_ratio(rets, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate),
        calmar=calmar,
        max_drawdown_pct=dd_pct,
        max_drawdown_duration_bars=dd_duration,
        time_in_drawdown_pct=float(np.mean(dd_series > 1e-12) * 100.0),
        win_rate=len(wins) / len(trades) if trades else None,
        profit_factor=profit_factor(pnls) if trades else None,
        expectancy=expectancy(pnls) if trades else None,
        average_win=float(np.mean(wins)) if wins else None,
        average_loss=float(np.mean(losses)) if losses else None,
        largest_win=float(max(wins)) if wins else 0.0,
        largest_loss=float(min(losses)) if losses else 0.0,
        payoff_ratio=(
            float(np.mean(wins) / abs(np.mean(losses))) if wins and losses else None
        ),
        skewness=skew,
        kurtosis=kurt,
        var_95_pct=value_at_risk(rets),
        cvar_95_pct=conditional_var(rets),
        stability=stability_of_returns(equity),
        exposure_pct=float(bars_in_market / equity.size * 100.0) if equity.size else 0.0,
        total_fees=float(sum(t.fees for t in trades)),
        warnings=tuple(warnings),
    )


def correlation_matrix(series_by_symbol: dict[str, object]) -> dict[tuple[str, str], float]:
    """Pairwise Pearson correlation of returns, over the overlapping window.

    Series of differing lengths are truncated to their common tail, because correlating
    a 500-bar series against a 50-bar one by index is a silent alignment bug.
    """
    symbols = sorted(series_by_symbol)
    arrays = {s: np.asarray(series_by_symbol[s], dtype=np.float64) for s in symbols}
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(symbols):
        for b in symbols[i:]:
            xa, xb = arrays[a], arrays[b]
            n = min(xa.size, xb.size)
            if n < 3:
                out[(a, b)] = out[(b, a)] = 0.0
                continue
            va, vb = xa[-n:], xb[-n:]
            if np.std(va) == 0 or np.std(vb) == 0:
                value = 0.0
            else:
                value = float(np.corrcoef(va, vb)[0, 1])
                if math.isnan(value):
                    value = 0.0
            out[(a, b)] = out[(b, a)] = value
    return out


__all__ = [
    "MIN_OBSERVATIONS_FOR_RATIOS",
    "PerformanceMetrics",
    "TradeRecord",
    "compute_metrics",
    "conditional_var",
    "correlation_matrix",
    "drawdown_series",
    "expectancy",
    "max_drawdown",
    "profit_factor",
    "returns_from_equity",
    "sharpe_ratio",
    "sortino_ratio",
    "stability_of_returns",
    "value_at_risk",
]
