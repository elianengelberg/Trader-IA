"""Feature computation.

Turns a candle series into the flat numeric vector every downstream component reads. Two
rules make this layer trustworthy:

1. **Point in time.** Features for bar *t* use bars ``[0..t]`` only. The builder is handed
   a series that has already been truncated by the caller; it never receives, and so can
   never accidentally read, a future bar.
2. **Versioned and hashed.** Every feature set carries ``feature_version`` and a content
   hash. When a decision is replayed months later, the hash proves whether the features
   were computed by the same code — a silent formula change is otherwise indistinguishable
   from a strategy that stopped working.

Feature names are stable identifiers. Renaming one is a breaking change that requires a
``FEATURE_VERSION`` bump, because persisted decisions reference them by name.
"""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.core.ids import content_hash
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle
from tia.quant import indicators as ind

FEATURE_VERSION = "1.0.0"

# Bars needed before the slowest feature is meaningful. Below this, the builder reports
# insufficient history rather than emitting features computed from a handful of bars.
MIN_BARS = 120


class FeatureSet(BaseModel):
    """A computed feature vector for one bar."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    bar_open_time: datetime
    bar_close_time: datetime
    feature_version: str = FEATURE_VERSION
    feature_hash: str = ""
    values: dict[str, float] = Field(default_factory=dict)
    bars_used: int = 0
    complete: bool = True

    @field_validator("bar_open_time", "bar_close_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="feature bar time")

    def get(self, name: str, default: float = float("nan")) -> float:
        return self.values.get(name, default)

    def require(self, name: str) -> float:
        if name not in self.values:
            raise KeyError(f"feature {name!r} not present in this set (version {self.feature_version})")
        return self.values[name]

    def has_all(self, *names: str) -> bool:
        return all(n in self.values and math.isfinite(self.values[n]) for n in names)

    def finite_values(self) -> dict[str, float]:
        return {k: v for k, v in self.values.items() if math.isfinite(v)}


def _last(arr: np.ndarray) -> float:
    """Last finite value of an indicator array, or NaN."""
    if arr.size == 0:
        return float("nan")
    value = float(arr[-1])
    return value if math.isfinite(value) else float("nan")


class FeatureBuilder:
    """Computes a :class:`FeatureSet` from a closed candle series."""

    def __init__(self, *, min_bars: int = MIN_BARS) -> None:
        self._min_bars = min_bars

    @property
    def min_bars(self) -> int:
        return self._min_bars

    def build(self, symbol: str, timeframe: str, candles: list[Candle]) -> FeatureSet:
        """Compute features for the **last** bar in ``candles``.

        The caller is responsible for passing only bars that had closed at decision time.
        The backtester enforces this by construction.
        """
        if not candles:
            raise ValueError("cannot build features from an empty series")

        last = candles[-1]
        tf = Timeframe.parse(timeframe)
        complete = len(candles) >= self._min_bars

        close = np.array([c.close for c in candles], dtype=np.float64)
        high = np.array([c.high for c in candles], dtype=np.float64)
        low = np.array([c.low for c in candles], dtype=np.float64)
        volume = np.array([c.volume for c in candles], dtype=np.float64)

        annualization = tf.bars_per_year()
        values: dict[str, float] = {}

        # --- price / trend ------------------------------------------------
        ema_fast = ind.ema(close, 12)
        ema_slow = ind.ema(close, 26)
        ema_trend = ind.ema(close, 50)
        sma_200 = ind.sma(close, min(200, max(20, len(close) - 1)))

        values["close"] = float(last.close)
        values["ema_12"] = _last(ema_fast)
        values["ema_26"] = _last(ema_slow)
        values["ema_50"] = _last(ema_trend)
        values["sma_200"] = _last(sma_200)

        # Distances are expressed in percent of price so they are comparable across
        # instruments trading at completely different levels.
        for name, series in (("ema_12", ema_fast), ("ema_26", ema_slow), ("ema_50", ema_trend)):
            ref = _last(series)
            values[f"dist_{name}_pct"] = (
                (last.close - ref) / ref * 100.0 if math.isfinite(ref) and ref != 0 else float("nan")
            )

        values["ema_fast_above_slow"] = (
            1.0
            if math.isfinite(values["ema_12"])
            and math.isfinite(values["ema_26"])
            and values["ema_12"] > values["ema_26"]
            else 0.0
        )
        values["trend_slope_20"] = _last(ind.slope(close, 20))
        values["trend_slope_50"] = _last(ind.slope(close, 50))

        # --- momentum -----------------------------------------------------
        values["rsi_14"] = _last(ind.rsi(close, 14))
        macd_line, macd_signal, macd_hist = ind.macd(close)
        values["macd"] = _last(macd_line)
        values["macd_signal"] = _last(macd_signal)
        values["macd_histogram"] = _last(macd_hist)
        values["roc_10"] = _last(ind.roc(close, 10))
        values["momentum_20"] = _last(ind.momentum(close, 20))

        # --- volatility ---------------------------------------------------
        atr_series = ind.atr(high, low, close, 14)
        atr_value = _last(atr_series)
        values["atr_14"] = atr_value
        values["atr_pct"] = (
            atr_value / last.close * 100.0 if math.isfinite(atr_value) and last.close > 0 else float("nan")
        )
        realized = ind.realized_volatility(close, 20, annualization)
        values["realized_vol_20"] = _last(realized)
        values["realized_vol_60"] = _last(ind.realized_volatility(close, 60, annualization))
        values["vol_percentile_100"] = _last(ind.percentile_rank(realized, 100))

        upper, middle, lower = ind.bollinger_bands(close, 20, 2.0)
        values["bb_upper"] = _last(upper)
        values["bb_middle"] = _last(middle)
        values["bb_lower"] = _last(lower)
        values["bb_percent_b"] = _last(ind.bollinger_percent_b(close, 20, 2.0))
        mid = _last(middle)
        values["bb_width_pct"] = (
            (_last(upper) - _last(lower)) / mid * 100.0
            if math.isfinite(mid) and mid != 0
            else float("nan")
        )

        # --- trend strength -----------------------------------------------
        adx_series, plus_di, minus_di = ind.adx(high, low, close, 14)
        values["adx_14"] = _last(adx_series)
        values["plus_di"] = _last(plus_di)
        values["minus_di"] = _last(minus_di)
        di_plus, di_minus = values["plus_di"], values["minus_di"]
        values["di_spread"] = (
            di_plus - di_minus if math.isfinite(di_plus) and math.isfinite(di_minus) else float("nan")
        )

        # --- structure ----------------------------------------------------
        # The breakout reference excludes the current bar. Including it makes the
        # comparison self-referential: the current high is by construction part of the
        # rolling max, so `close >= upper` can essentially never be true and the flag
        # would silently never fire. A breakout is a move beyond what came *before*.
        if len(candles) > 20:
            prior_upper, prior_mid, prior_lower = ind.donchian_channel(high[:-1], low[:-1], 20)
            upper_v, mid_v, lower_v = _last(prior_upper), _last(prior_mid), _last(prior_lower)
        else:
            upper_v = mid_v = lower_v = float("nan")

        values["donchian_upper_20"] = upper_v
        values["donchian_lower_20"] = lower_v
        values["donchian_mid_20"] = mid_v
        if math.isfinite(upper_v) and math.isfinite(lower_v) and upper_v > lower_v:
            # Clamped so a genuine breakout reads as 1.0 rather than 1.4, keeping the
            # feature interpretable as "position within the prior range".
            values["channel_position"] = max(
                0.0, min(1.0, (last.close - lower_v) / (upper_v - lower_v))
            )
        else:
            values["channel_position"] = float("nan")
        values["breakout_up"] = 1.0 if math.isfinite(upper_v) and last.close > upper_v else 0.0
        values["breakout_down"] = 1.0 if math.isfinite(lower_v) and last.close < lower_v else 0.0

        values["zscore_20"] = _last(ind.zscore(close, 20))
        values["zscore_60"] = _last(ind.zscore(close, 60))

        # --- volume -------------------------------------------------------
        vol_sma = ind.sma(volume, 20)
        vol_ref = _last(vol_sma)
        values["volume"] = float(last.volume)
        values["volume_sma_20"] = vol_ref
        values["volume_ratio"] = (
            last.volume / vol_ref if math.isfinite(vol_ref) and vol_ref > 0 else float("nan")
        )
        values["volume_zscore_20"] = _last(ind.zscore(volume, 20))
        values["vwap"] = _last(ind.vwap(high, low, close, volume))
        vwap_value = values["vwap"]
        values["dist_vwap_pct"] = (
            (last.close - vwap_value) / vwap_value * 100.0
            if math.isfinite(vwap_value) and vwap_value != 0
            else float("nan")
        )

        # --- bar shape ----------------------------------------------------
        bar_range = last.high - last.low
        values["bar_range_pct"] = bar_range / last.close * 100.0 if last.close > 0 else 0.0
        values["bar_body_ratio"] = abs(last.close - last.open) / bar_range if bar_range > 0 else 0.0
        values["bar_is_up"] = 1.0 if last.close >= last.open else 0.0
        values["upper_wick_ratio"] = (
            (last.high - max(last.open, last.close)) / bar_range if bar_range > 0 else 0.0
        )
        values["lower_wick_ratio"] = (
            (min(last.open, last.close) - last.low) / bar_range if bar_range > 0 else 0.0
        )

        # --- returns ------------------------------------------------------
        with np.errstate(divide="ignore", invalid="ignore"):
            log_returns = np.diff(np.log(close)) if close.size > 1 else np.array([])
        values["return_1"] = float(log_returns[-1] * 100.0) if log_returns.size else 0.0
        for window in (5, 20, 60):
            values[f"return_{window}"] = (
                float(np.sum(log_returns[-window:]) * 100.0) if log_returns.size >= window else float("nan")
            )
        values["gap_pct"] = (
            (last.open - candles[-2].close) / candles[-2].close * 100.0
            if len(candles) > 1 and candles[-2].close > 0
            else 0.0
        )

        rounded = {k: (round(v, 10) if math.isfinite(v) else float("nan")) for k, v in values.items()}
        finite = {k: v for k, v in sorted(rounded.items()) if math.isfinite(v)}

        return FeatureSet(
            symbol=symbol,
            timeframe=timeframe,
            bar_open_time=last.open_time,
            bar_close_time=last.close_time,
            feature_version=FEATURE_VERSION,
            feature_hash=content_hash({"v": FEATURE_VERSION, "f": finite}),
            values=rounded,
            bars_used=len(candles),
            complete=complete,
        )

    def build_series(
        self, symbol: str, timeframe: str, candles: list[Candle], *, start_index: int | None = None
    ) -> list[FeatureSet]:
        """Build a feature set for each bar from ``start_index`` onwards.

        Each call sees a strictly truncated prefix, which is what makes the no-look-ahead
        property structural rather than a matter of discipline.
        """
        first = start_index if start_index is not None else self._min_bars
        first = max(1, first)
        return [
            self.build(symbol, timeframe, candles[: i + 1]) for i in range(first - 1, len(candles))
        ]


__all__ = ["FEATURE_VERSION", "MIN_BARS", "FeatureBuilder", "FeatureSet"]
