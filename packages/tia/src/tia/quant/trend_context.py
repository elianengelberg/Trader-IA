"""Higher-timeframe trend context: the one crypto anomaly the literature agrees on.

Liu and Tsyvinski (Review of Financial Studies, 2021) and Liu, Tsyvinski and Wu (Journal
of Finance, 2022) document strong **time-series momentum at one-to-four-week horizons**
in bitcoin, ether and the cross-section of coins; replications through 2026 find it
survives the spot-ETF era. Nothing else at any horizon has that weight of evidence
behind it, and the intraday effects that do exist are small next to trading costs.

A session that decides on one-minute bars therefore needs to know which way the
multi-week tide is running, and this module is that knowledge, reduced to three
numbers it can act on:

* ``z_1w`` — the last week's log return in units of its own hourly volatility scaled to
  a week, so "+1.5" means the week moved one and a half typical weeks upward.
* ``z_4w`` — the same over four weeks.
* ``bias`` — ``up`` when both agree above the threshold, ``down`` when both agree below
  it, ``flat`` otherwise. Agreement is required on purpose: a four-week uptrend whose
  last week broke down is not a trend the evidence says to follow.

Everything here is pure arithmetic on closed hourly candles; the runtime decides what a
bias means for an entry (refuse against it, or size it down) and says so in its record.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tia.domain.market import Candle

#: Hours in the two horizons the evidence is strongest at.
ONE_WEEK_HOURS = 168
FOUR_WEEKS_HOURS = 672

#: Fewer closed hourly bars than this and no bias is claimed: a week of data cannot
#: speak for four.
MIN_HOURS = 240


@dataclass(frozen=True)
class TrendContext:
    """What the higher timeframe says, with the arithmetic that says it."""

    available: bool
    bias: str  # "up" | "down" | "flat" | "unknown"
    z_1w: float | None
    z_4w: float | None
    return_1w_pct: float | None
    return_4w_pct: float | None
    hourly_vol_pct: float | None
    bars: int
    timeframe: str
    reason: str
    as_of: str | None = None

    def agrees_with(self, direction_is_long: bool) -> bool | None:
        """True with the tide, False against it, None when there is no tide to speak of."""
        if not self.available or self.bias == "flat":
            return None
        return (self.bias == "up") == direction_is_long

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "bias": self.bias,
            "z_1w": round(self.z_1w, 3) if self.z_1w is not None else None,
            "z_4w": round(self.z_4w, 3) if self.z_4w is not None else None,
            "return_1w_pct": round(self.return_1w_pct, 3) if self.return_1w_pct is not None else None,
            "return_4w_pct": round(self.return_4w_pct, 3) if self.return_4w_pct is not None else None,
            "hourly_vol_pct": round(self.hourly_vol_pct, 4) if self.hourly_vol_pct is not None else None,
            "bars": self.bars,
            "timeframe": self.timeframe,
            "reason": self.reason,
            "as_of": self.as_of,
        }


def _unavailable(reason: str, *, bars: int = 0, timeframe: str = "") -> TrendContext:
    return TrendContext(
        available=False, bias="unknown", z_1w=None, z_4w=None, return_1w_pct=None,
        return_4w_pct=None, hourly_vol_pct=None, bars=bars, timeframe=timeframe, reason=reason,
    )


def trend_context(
    candles: Sequence[Candle], *, timeframe: str = "1h", z_threshold: float = 1.0
) -> TrendContext:
    """Compute the higher-timeframe bias from closed hourly candles.

    Refuses to answer — ``available=False`` — when the candles are not the timeframe
    asked for (a feed that served minute bars to an hourly request) or there are too few
    of them. An unavailable context imposes no bias; the caller must treat it as "no
    tide known", never as "flat".
    """
    if not candles:
        return _unavailable("no candles", timeframe=timeframe)
    served = {c.timeframe for c in candles}
    if served != {timeframe}:
        return _unavailable(
            f"feed served {sorted(served)} bars to a {timeframe} request",
            bars=len(candles), timeframe=timeframe,
        )
    closes = [c.close for c in candles if c.close > 0]
    if len(closes) < MIN_HOURS:
        return _unavailable(
            f"{len(closes)} closed {timeframe} bars; {MIN_HOURS} needed",
            bars=len(closes), timeframe=timeframe,
        )

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / max(1, len(log_returns) - 1)
    hourly_vol = math.sqrt(variance)
    if hourly_vol <= 0:
        return _unavailable("zero volatility", bars=len(closes), timeframe=timeframe)

    def z_over(hours: int) -> tuple[float, float]:
        span = min(hours, len(closes) - 1)
        ret = math.log(closes[-1] / closes[-1 - span])
        return ret / (hourly_vol * math.sqrt(span)), (math.exp(ret) - 1.0) * 100.0

    z_1w, ret_1w = z_over(ONE_WEEK_HOURS)
    z_4w, ret_4w = z_over(FOUR_WEEKS_HOURS)

    if z_1w >= z_threshold and z_4w >= z_threshold:
        bias, reason = "up", f"1w {z_1w:+.1f}sd and 4w {z_4w:+.1f}sd both above +{z_threshold:g}sd"
    elif z_1w <= -z_threshold and z_4w <= -z_threshold:
        bias, reason = "down", f"1w {z_1w:+.1f}sd and 4w {z_4w:+.1f}sd both below -{z_threshold:g}sd"
    else:
        bias, reason = "flat", f"1w {z_1w:+.1f}sd, 4w {z_4w:+.1f}sd: no agreed tide beyond ±{z_threshold:g}sd"

    return TrendContext(
        available=True,
        bias=bias,
        z_1w=z_1w,
        z_4w=z_4w,
        return_1w_pct=ret_1w,
        return_4w_pct=ret_4w,
        hourly_vol_pct=hourly_vol * 100.0,
        bars=len(closes),
        timeframe=timeframe,
        reason=reason,
        as_of=candles[-1].close_time.isoformat(),
    )


__all__ = ["FOUR_WEEKS_HOURS", "MIN_HOURS", "ONE_WEEK_HOURS", "TrendContext", "trend_context"]
