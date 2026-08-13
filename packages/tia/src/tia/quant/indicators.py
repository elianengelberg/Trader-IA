"""Technical indicators.

Pure functions over NumPy arrays. Three properties are non-negotiable and are enforced by
tests rather than by convention:

1. **Point-in-time correctness.** ``out[i]`` depends only on ``values[:i+1]``. Never on
   ``values[i+1:]``. This is checked mechanically by
   ``tests/unit/test_indicators.py::TestNoLookAhead``, which recomputes each indicator on
   truncated inputs and asserts the prefix is unchanged. An indicator that peeks is a
   backtest that lies.
2. **Aligned output.** Every function returns an array the same length as its input, with
   ``NaN`` where there is not yet enough history. Returning a shorter array is how
   off-by-one misalignment bugs enter a strategy — and they are close to undetectable
   once there.
3. **No mutation.** Inputs are never modified in place.

Formulas follow the conventional definitions (Wilder's smoothing for RSI/ATR/ADX). Each
is verified against hand-computed fixtures, not against another library, so a dependency
upgrade cannot silently change a signal.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


def _as_array(values: object) -> Array:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError(f"expected a 1-D series, got shape {arr.shape}")
    return arr


def _empty_like(values: Array) -> Array:
    return np.full(values.shape, np.nan, dtype=np.float64)


# --------------------------------------------------------------------------- moving averages


def sma(values: object, period: int) -> Array:
    """Simple moving average."""
    arr = _as_array(values)
    if period < 1:
        raise ValueError("period must be >= 1")
    out = _empty_like(arr)
    if arr.size < period:
        return out
    cumsum = np.cumsum(np.insert(arr, 0, 0.0))
    out[period - 1 :] = (cumsum[period:] - cumsum[:-period]) / period
    return out


def ema(values: object, period: int) -> Array:
    """Exponential moving average, seeded with the SMA of the first ``period`` values.

    Seeding with the SMA rather than the first observation is the conventional choice and
    removes a startup transient that would otherwise make early signals unreliable.
    """
    arr = _as_array(values)
    if period < 1:
        raise ValueError("period must be >= 1")
    out = _empty_like(arr)
    if arr.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = float(np.mean(arr[:period]))
    for i in range(period, arr.size):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def wilder_smooth(values: object, period: int) -> Array:
    """Wilder's smoothing (an EMA with alpha = 1/period), used by RSI, ATR and ADX."""
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    out[period - 1] = float(np.mean(arr[:period]))
    for i in range(period, arr.size):
        out[i] = (out[i - 1] * (period - 1) + arr[i]) / period
    return out


def vwap(high: object, low: object, close: object, volume: object) -> Array:
    """Cumulative volume-weighted average price over the supplied window.

    Note this is a *running* VWAP across the whole array, not a session VWAP — the caller
    slices to the session it cares about. Making that explicit here avoids inventing a
    session-boundary convention that would be wrong for at least one asset class.
    """
    h, low_, c, v = (_as_array(x) for x in (high, low, close, volume))
    typical = (h + low_ + c) / 3.0
    cum_pv = np.cumsum(typical * v)
    cum_v = np.cumsum(v)
    out = _empty_like(c)
    nonzero = cum_v > 0
    out[nonzero] = cum_pv[nonzero] / cum_v[nonzero]
    return out


# --------------------------------------------------------------------------- momentum


def rsi(values: object, period: int = 14) -> Array:
    """Relative Strength Index (Wilder)."""
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size <= period:
        return out

    delta = np.diff(arr)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    def to_rsi(gain: float, loss: float) -> float:
        if loss == 0.0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, arr.size):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = to_rsi(avg_gain, avg_loss)
    return out


def macd(
    values: object, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Array, Array, Array]:
    """Return ``(macd_line, signal_line, histogram)``."""
    if fast >= slow:
        raise ValueError("fast period must be shorter than slow period")
    arr = _as_array(values)
    fast_ema = ema(arr, fast)
    slow_ema = ema(arr, slow)
    line = fast_ema - slow_ema

    # The signal line is an EMA of the MACD line, which only exists from index slow-1.
    sig = _empty_like(arr)
    valid = ~np.isnan(line)
    if valid.sum() >= signal:
        start = int(np.argmax(valid))
        sig[start:] = ema(line[start:], signal)
    return line, sig, line - sig


def roc(values: object, period: int = 10) -> Array:
    """Rate of change, in percent."""
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size <= period:
        return out
    prior = arr[:-period]
    with np.errstate(divide="ignore", invalid="ignore"):
        out[period:] = np.where(prior != 0, (arr[period:] - prior) / prior * 100.0, np.nan)
    return out


def momentum(values: object, period: int = 10) -> Array:
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size <= period:
        return out
    out[period:] = arr[period:] - arr[:-period]
    return out


# --------------------------------------------------------------------------- volatility


def true_range(high: object, low: object, close: object) -> Array:
    """True range. ``out[0]`` is ``high[0] - low[0]`` since no prior close exists."""
    h, low_, c = (_as_array(x) for x in (high, low, close))
    if not (h.size == low_.size == c.size):
        raise ValueError("high, low and close must be the same length")
    out = np.empty(h.shape, dtype=np.float64)
    out[0] = h[0] - low_[0]
    prev_close = c[:-1]
    out[1:] = np.maximum.reduce(
        [h[1:] - low_[1:], np.abs(h[1:] - prev_close), np.abs(low_[1:] - prev_close)]
    )
    return out


def atr(high: object, low: object, close: object, period: int = 14) -> Array:
    """Average true range (Wilder)."""
    return wilder_smooth(true_range(high, low, close), period)


def bollinger_bands(
    values: object, period: int = 20, num_std: float = 2.0
) -> tuple[Array, Array, Array]:
    """Return ``(upper, middle, lower)``.

    Population standard deviation (``ddof=0``), matching the conventional definition.
    """
    arr = _as_array(values)
    middle = sma(arr, period)
    std = _empty_like(arr)
    if arr.size >= period:
        windows = np.lib.stride_tricks.sliding_window_view(arr, period)
        std[period - 1 :] = np.std(windows, axis=1)
    return middle + num_std * std, middle, middle - num_std * std


def bollinger_percent_b(values: object, period: int = 20, num_std: float = 2.0) -> Array:
    """Position within the bands: 0 at the lower band, 1 at the upper."""
    arr = _as_array(values)
    upper, _middle, lower = bollinger_bands(arr, period, num_std)
    width = upper - lower
    out = _empty_like(arr)
    valid = width > 0
    out[valid] = (arr[valid] - lower[valid]) / width[valid]
    return out


def realized_volatility(values: object, period: int = 20, annualization: float = 1.0) -> Array:
    """Rolling standard deviation of log returns, optionally annualized."""
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period + 1:
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        log_returns = np.diff(np.log(arr))
    if log_returns.size < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(log_returns, period)
    out[period:] = np.std(windows, axis=1) * np.sqrt(annualization)
    return out


# --------------------------------------------------------------------------- trend strength


def directional_movement(high: object, low: object) -> tuple[Array, Array]:
    """Return ``(+DM, -DM)``, both non-negative, one of which is zero per bar."""
    h, low_ = (_as_array(x) for x in (high, low))
    up = np.zeros(h.shape, dtype=np.float64)
    down = np.zeros(h.shape, dtype=np.float64)
    up_move = h[1:] - h[:-1]
    down_move = low_[:-1] - low_[1:]
    up[1:] = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    down[1:] = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    return up, down


def adx(high: object, low: object, close: object, period: int = 14) -> tuple[Array, Array, Array]:
    """Return ``(adx, plus_di, minus_di)`` — Wilder's directional system."""
    h, low_, c = (_as_array(x) for x in (high, low, close))
    plus_dm, minus_dm = directional_movement(h, low_)
    tr = true_range(h, low_, c)

    atr_ = wilder_smooth(tr, period)
    plus_sm = wilder_smooth(plus_dm, period)
    minus_sm = wilder_smooth(minus_dm, period)

    plus_di = _empty_like(h)
    minus_di = _empty_like(h)
    valid = (~np.isnan(atr_)) & (atr_ > 0)
    plus_di[valid] = 100.0 * plus_sm[valid] / atr_[valid]
    minus_di[valid] = 100.0 * minus_sm[valid] / atr_[valid]

    dx = _empty_like(h)
    denom = plus_di + minus_di
    ok = (~np.isnan(denom)) & (denom > 0)
    dx[ok] = 100.0 * np.abs(plus_di[ok] - minus_di[ok]) / denom[ok]

    adx_out = _empty_like(h)
    dx_valid_idx = np.flatnonzero(~np.isnan(dx))
    if dx_valid_idx.size >= period:
        start = int(dx_valid_idx[0])
        smoothed = wilder_smooth(dx[start:], period)
        adx_out[start:] = smoothed
    return adx_out, plus_di, minus_di


# --------------------------------------------------------------------------- structure


def rolling_max(values: object, period: int) -> Array:
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = np.max(windows, axis=1)
    return out


def rolling_min(values: object, period: int) -> Array:
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    out[period - 1 :] = np.min(windows, axis=1)
    return out


def donchian_channel(high: object, low: object, period: int = 20) -> tuple[Array, Array, Array]:
    """Return ``(upper, middle, lower)`` — the classic breakout reference."""
    upper = rolling_max(high, period)
    lower = rolling_min(low, period)
    return upper, (upper + lower) / 2.0, lower


def zscore(values: object, period: int = 20) -> Array:
    """Rolling z-score of the series against its own recent distribution."""
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    means = np.mean(windows, axis=1)
    stds = np.std(windows, axis=1)
    tail = arr[period - 1 :]
    safe = stds > 0
    result = np.full(tail.shape, 0.0)
    result[safe] = (tail[safe] - means[safe]) / stds[safe]
    out[period - 1 :] = result
    return out


def percentile_rank(values: object, period: int = 100) -> Array:
    """Rank of the current value within its trailing window, in ``[0, 1]``.

    Used for volatility regime detection: "is current volatility high *for this
    instrument*" is a far more useful question than "is it above some absolute number",
    which is meaningless across assets.
    """
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    current = arr[period - 1 :].reshape(-1, 1)
    out[period - 1 :] = np.mean(windows <= current, axis=1)
    return out


def slope(values: object, period: int = 20) -> Array:
    """Least-squares slope over a rolling window, normalized by the window mean.

    Normalizing makes the number comparable across instruments with wildly different
    price levels — a raw slope of 5 means something entirely different for BTC than for
    an index at 5,400.
    """
    arr = _as_array(values)
    out = _empty_like(arr)
    if arr.size < period:
        return out
    x = np.arange(period, dtype=np.float64)
    x_centered = x - x.mean()
    denom = float(np.sum(x_centered**2))
    windows = np.lib.stride_tricks.sliding_window_view(arr, period)
    y_centered = windows - windows.mean(axis=1, keepdims=True)
    slopes = (y_centered * x_centered).sum(axis=1) / denom
    means = windows.mean(axis=1)
    safe = means != 0
    normalized = np.zeros_like(slopes)
    normalized[safe] = slopes[safe] / means[safe] * period
    out[period - 1 :] = normalized
    return out


__all__ = [
    "adx",
    "atr",
    "bollinger_bands",
    "bollinger_percent_b",
    "directional_movement",
    "donchian_channel",
    "ema",
    "macd",
    "momentum",
    "percentile_rank",
    "realized_volatility",
    "roc",
    "rolling_max",
    "rolling_min",
    "rsi",
    "slope",
    "sma",
    "true_range",
    "vwap",
    "wilder_smooth",
    "zscore",
]
