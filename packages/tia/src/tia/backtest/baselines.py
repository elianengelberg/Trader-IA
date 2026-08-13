"""Baselines. Not optional.

A strategy's Sharpe means nothing on its own. The question is never "did it make money?"
but "did it beat the thing anyone could have done without it?", and for most strategies
on most datasets the honest answer is no — a fact that disappears the moment a report
quotes a return with nothing to compare it against.

Five baselines, each answering a different way of being fooled:

* **buy and hold** — did the strategy add anything over simply owning the asset? On a
  rising sample, most long-biased strategies lose to this and look excellent anyway.
* **SMA cross** — did it beat the most obvious technical rule in existence?
* **volatility-targeted** — did it beat exposure sizing alone, with no view on direction?
  Much of what looks like alpha is a volatility-timing effect.
* **random entry** — did it beat coin flips *matched on trade count*, so it pays the same
  costs and holds for the same duration? This is the one that catches a strategy whose
  apparent edge is really just the drift of the sample.
* **always flat** — the zero line, which a strategy paying real costs can genuinely fail
  to beat.

All five are evaluated on the same bars, with the same fee and slippage assumptions, and
the same forced liquidation at the sample boundary. A baseline computed on gross returns
against a strategy computed on net returns is not a comparison.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from tia.core.config import ExecutionSimConfig
from tia.core.rng import RngRegistry
from tia.domain.market import Candle
from tia.quant.statistics import PerformanceMetrics, TradeRecord, compute_metrics


@dataclass(frozen=True)
class BaselineResult:
    """One baseline's outcome, in the same shape as a strategy's."""

    name: str
    description: str
    metrics: PerformanceMetrics
    equity_curve: tuple[float, ...]
    trades: int

    @property
    def total_return_pct(self) -> float:
        return self.metrics.total_return_pct


def _equity_from_exposure(
    closes: np.ndarray,
    exposure: np.ndarray,
    *,
    initial_capital: float,
    costs: ExecutionSimConfig,
) -> np.ndarray:
    """Equity curve for a series of target exposures, charged for every change.

    ``exposure[i]`` is the fraction of capital held *during* bar ``i+1``, so a decision
    taken from bar *i*'s close is only ever applied to the following bar's return. That
    one-bar offset is the whole reason baselines are computed here rather than by
    multiplying signals and returns directly, which is the classic way a baseline
    accidentally becomes clairvoyant.
    """
    returns = np.diff(closes) / closes[:-1]
    applied = exposure[: returns.size]
    turnover = np.abs(np.diff(np.concatenate(([0.0], applied))))
    per_leg_cost = (costs.taker_fee_bps + costs.base_slippage_bps) / 10_000.0

    equity = np.empty(closes.size, dtype=np.float64)
    equity[0] = initial_capital
    for i in range(returns.size):
        gross = 1.0 + applied[i] * returns[i]
        equity[i + 1] = max(0.0, equity[i] * gross - equity[i] * turnover[i] * per_leg_cost)
    return equity


def _trade_records(
    closes: np.ndarray, exposure: np.ndarray, equity: np.ndarray, symbol: str
) -> list[TradeRecord]:
    """Reconstruct round trips from an exposure series, for the trade-based metrics."""
    records: list[TradeRecord] = []
    entry_index: int | None = None
    for i in range(exposure.size):
        holding = abs(exposure[i]) > 1e-12
        if holding and entry_index is None:
            entry_index = i
        elif not holding and entry_index is not None:
            pnl = float(equity[i] - equity[entry_index])
            base = float(equity[entry_index])
            records.append(
                TradeRecord(
                    symbol=symbol,
                    pnl=pnl,
                    return_pct=(pnl / base * 100.0) if base > 0 else 0.0,
                    duration_seconds=0.0,
                    entry_price=float(closes[entry_index]),
                    exit_price=float(closes[i]),
                    quantity=1.0,
                )
            )
            entry_index = None
    if entry_index is not None:
        pnl = float(equity[-1] - equity[entry_index])
        base = float(equity[entry_index])
        records.append(
            TradeRecord(
                symbol=symbol,
                pnl=pnl,
                return_pct=(pnl / base * 100.0) if base > 0 else 0.0,
                duration_seconds=0.0,
                entry_price=float(closes[entry_index]),
                exit_price=float(closes[-1]),
                quantity=1.0,
            )
        )
    return records


def _finish(
    name: str,
    description: str,
    closes: np.ndarray,
    exposure: np.ndarray,
    *,
    symbol: str,
    initial_capital: float,
    costs: ExecutionSimConfig,
    periods_per_year: float,
) -> BaselineResult:
    equity = _equity_from_exposure(
        closes, exposure, initial_capital=initial_capital, costs=costs
    )
    records = _trade_records(closes, exposure, equity, symbol)
    metrics = compute_metrics(
        equity_curve=equity,
        trades=records,
        periods_per_year=periods_per_year,
        bars_in_market=int(np.count_nonzero(np.abs(exposure) > 1e-12)),
    )
    return BaselineResult(
        name=name,
        description=description,
        metrics=metrics,
        equity_curve=tuple(float(v) for v in equity),
        trades=len(records),
    )


# --------------------------------------------------------------------------- the five


def buy_and_hold(
    candles: Sequence[Candle],
    *,
    initial_capital: float = 100_000.0,
    costs: ExecutionSimConfig | None = None,
    periods_per_year: float = 525_600.0,
) -> BaselineResult:
    """Fully invested from the first bar to the last, paying one round trip."""
    costs = costs or ExecutionSimConfig()
    closes = np.array([c.close for c in candles], dtype=np.float64)
    exposure = np.ones(closes.size, dtype=np.float64)
    return _finish(
        "buy_and_hold",
        "long the asset for the whole sample; one entry, one exit, no timing",
        closes,
        exposure,
        symbol=candles[0].symbol,
        initial_capital=initial_capital,
        costs=costs,
        periods_per_year=periods_per_year,
    )


def sma_cross(
    candles: Sequence[Candle],
    *,
    fast: int = 20,
    slow: int = 50,
    initial_capital: float = 100_000.0,
    costs: ExecutionSimConfig | None = None,
    periods_per_year: float = 525_600.0,
    allow_short: bool = False,
) -> BaselineResult:
    """Long while the fast average is above the slow one.

    The most obvious technical rule there is. A strategy that cannot beat it is not
    contributing anything a two-line script could not.
    """
    if fast >= slow:
        raise ValueError("fast window must be shorter than slow")
    costs = costs or ExecutionSimConfig()
    closes = np.array([c.close for c in candles], dtype=np.float64)

    exposure = np.zeros(closes.size, dtype=np.float64)
    for i in range(slow, closes.size):
        # Windows end at bar i, and the exposure is applied to bar i+1 by
        # ``_equity_from_exposure``. Neither average can see the bar it acts on.
        fast_mean = closes[i - fast + 1 : i + 1].mean()
        slow_mean = closes[i - slow + 1 : i + 1].mean()
        if fast_mean > slow_mean:
            exposure[i] = 1.0
        elif allow_short and fast_mean < slow_mean:
            exposure[i] = -1.0

    return _finish(
        "sma_cross",
        f"long while SMA({fast}) > SMA({slow})"
        + (", short when below" if allow_short else ", flat otherwise"),
        closes,
        exposure,
        symbol=candles[0].symbol,
        initial_capital=initial_capital,
        costs=costs,
        periods_per_year=periods_per_year,
    )


def volatility_targeted(
    candles: Sequence[Candle],
    *,
    target_annual_vol: float = 0.15,
    window: int = 60,
    max_leverage: float = 1.0,
    initial_capital: float = 100_000.0,
    costs: ExecutionSimConfig | None = None,
    periods_per_year: float = 525_600.0,
) -> BaselineResult:
    """Always long, sized so realised volatility hits a target.

    No view on direction at all — only on how much to hold. A surprising share of what
    gets reported as alpha is this effect and nothing more.
    """
    costs = costs or ExecutionSimConfig()
    closes = np.array([c.close for c in candles], dtype=np.float64)
    returns = np.diff(closes) / closes[:-1]

    exposure = np.zeros(closes.size, dtype=np.float64)
    for i in range(window, closes.size):
        recent = returns[i - window : i]  # ends at bar i-1, so bar i is unseen
        realised = float(np.std(recent, ddof=1)) if recent.size > 1 else 0.0
        annualised = realised * math.sqrt(periods_per_year)
        if annualised <= 1e-12:
            continue
        exposure[i] = min(max_leverage, target_annual_vol / annualised)

    return _finish(
        "volatility_targeted",
        f"always long, sized to a {target_annual_vol:.0%} annualised volatility target "
        f"from a {window}-bar window",
        closes,
        exposure,
        symbol=candles[0].symbol,
        initial_capital=initial_capital,
        costs=costs,
        periods_per_year=periods_per_year,
    )


def random_entry(
    candles: Sequence[Candle],
    *,
    trade_count: int,
    average_bars_held: int,
    seed: int = 20260812,
    initial_capital: float = 100_000.0,
    costs: ExecutionSimConfig | None = None,
    periods_per_year: float = 525_600.0,
    allow_short: bool = True,
) -> BaselineResult:
    """Coin-flip entries, matched to the strategy's trade count and holding period.

    The matching is the point. An unmatched random baseline trades a different number of
    times, pays different costs and holds for a different duration, so beating it proves
    nothing. Matched, it isolates the only thing left: whether the *timing and direction*
    carried information.

    Seeded, so the comparison is reproducible rather than a number that changes each time
    someone reruns the report until it flatters them.
    """
    costs = costs or ExecutionSimConfig()
    closes = np.array([c.close for c in candles], dtype=np.float64)
    exposure = np.zeros(closes.size, dtype=np.float64)

    if trade_count > 0 and average_bars_held > 0 and closes.size > average_bars_held + 2:
        rng = RngRegistry(seed).get("baseline:random_entry")
        latest_start = closes.size - average_bars_held - 1
        starts = rng.integers(0, max(1, latest_start), size=trade_count)
        for start in np.sort(starts):
            direction = 1.0 if (not allow_short or rng.random() < 0.5) else -1.0
            end = min(closes.size, int(start) + average_bars_held)
            exposure[int(start) : end] = direction

    return _finish(
        "random_entry",
        f"{trade_count} seeded random entries held ~{average_bars_held} bars each, "
        "matched to the strategy's trade count and duration",
        closes,
        exposure,
        symbol=candles[0].symbol,
        initial_capital=initial_capital,
        costs=costs,
        periods_per_year=periods_per_year,
    )


def always_flat(
    candles: Sequence[Candle],
    *,
    initial_capital: float = 100_000.0,
    periods_per_year: float = 525_600.0,
) -> BaselineResult:
    """Never trade. The zero line, and a genuinely hard baseline to beat after costs."""
    closes = np.array([c.close for c in candles], dtype=np.float64)
    equity = np.full(closes.size, initial_capital, dtype=np.float64)
    return BaselineResult(
        name="always_flat",
        description="no positions at any point; the return a strategy must justify",
        metrics=compute_metrics(
            equity_curve=equity, trades=[], periods_per_year=periods_per_year
        ),
        equity_curve=tuple(float(v) for v in equity),
        trades=0,
    )


def run_all_baselines(
    candles: Sequence[Candle],
    *,
    strategy_trade_count: int,
    strategy_average_bars_held: int,
    initial_capital: float = 100_000.0,
    costs: ExecutionSimConfig | None = None,
    periods_per_year: float = 525_600.0,
    seed: int = 20260812,
) -> list[BaselineResult]:
    """Every mandatory baseline, on the same bars and the same cost assumptions."""
    if len(candles) < 3:
        raise ValueError("baselines need at least three bars")
    costs = costs or ExecutionSimConfig()
    shared = {
        "initial_capital": initial_capital,
        "costs": costs,
        "periods_per_year": periods_per_year,
    }
    return [
        buy_and_hold(candles, **shared),  # type: ignore[arg-type]
        sma_cross(candles, **shared),  # type: ignore[arg-type]
        volatility_targeted(candles, **shared),  # type: ignore[arg-type]
        random_entry(
            candles,
            trade_count=strategy_trade_count,
            average_bars_held=strategy_average_bars_held,
            seed=seed,
            **shared,  # type: ignore[arg-type]
        ),
        always_flat(
            candles, initial_capital=initial_capital, periods_per_year=periods_per_year
        ),
    ]


__all__ = [
    "BaselineResult",
    "always_flat",
    "buy_and_hold",
    "random_entry",
    "run_all_baselines",
    "sma_cross",
    "volatility_targeted",
]
