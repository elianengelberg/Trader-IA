"""The higher-timeframe context: a tide only when both horizons agree, and no claim
from bars that cannot support one."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from tia.domain.market import Candle
from tia.quant.trend_context import MIN_HOURS, trend_context


def _hourly(closes: list[float], *, timeframe: str = "1h") -> list[Candle]:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    step = timedelta(hours=1) if timeframe == "1h" else timedelta(minutes=1)
    out = []
    for i, close in enumerate(closes):
        open_time = start + step * i
        out.append(
            Candle(
                symbol="BTC-USD", timeframe=timeframe, open_time=open_time,
                close_time=open_time + step - timedelta(seconds=1),
                open=close, high=close * 1.001, low=close * 0.999, close=close, volume=1.0,
            )
        )
    return out


def _drift(hours: int, per_hour: float, *, wobble: float = 0.002) -> list[float]:
    price, closes = 50_000.0, []
    for i in range(hours):
        price *= math.exp(per_hour + (wobble if i % 2 else -wobble))
        closes.append(price)
    return closes


def test_a_steady_climb_over_both_horizons_is_an_up_bias() -> None:
    ctx = trend_context(_hourly(_drift(720, 0.0006)), z_threshold=1.0)
    assert ctx.available and ctx.bias == "up"
    assert ctx.z_1w is not None and ctx.z_1w > 1.0
    assert ctx.z_4w is not None and ctx.z_4w > 1.0
    assert ctx.return_4w_pct is not None and ctx.return_4w_pct > 0
    assert ctx.agrees_with(True) is True
    assert ctx.agrees_with(False) is False
    assert "both above" in ctx.reason


def test_a_steady_decline_is_a_down_bias() -> None:
    ctx = trend_context(_hourly(_drift(720, -0.0006)))
    assert ctx.bias == "down"
    assert ctx.agrees_with(False) is True


def test_disagreeing_horizons_are_flat_and_impose_nothing() -> None:
    """Four weeks up, but the last week fell hard: not a tide the evidence says to follow."""
    # 23 days of climbing, then a week giving a third of it back: the four-week window is
    # still well up, the one-week window well down.
    up = _drift(552, 0.0010)
    down = [c * up[-1] / 50_000.0 for c in _drift(168, -0.0012)]
    closes = up + down
    ctx = trend_context(_hourly(closes))
    assert ctx.available and ctx.bias == "flat"
    assert ctx.agrees_with(True) is None


def test_noise_around_a_flat_price_is_flat() -> None:
    ctx = trend_context(_hourly(_drift(720, 0.0, wobble=0.004)))
    assert ctx.bias == "flat"


def test_minute_bars_served_to_an_hourly_request_are_refused_not_misread() -> None:
    ctx = trend_context(_hourly(_drift(720, 0.0006), timeframe="1m"), timeframe="1h")
    assert ctx.available is False
    assert ctx.bias == "unknown"
    assert "served" in ctx.reason
    assert ctx.agrees_with(True) is None


def test_too_few_bars_make_no_claim() -> None:
    ctx = trend_context(_hourly(_drift(MIN_HOURS - 1, 0.001)))
    assert ctx.available is False and "needed" in ctx.reason
    assert trend_context([]).available is False


def test_the_context_serialises() -> None:
    import json

    json.dumps(trend_context(_hourly(_drift(300, 0.0005))).as_dict())
