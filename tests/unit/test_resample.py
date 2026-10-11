"""Resampling never looks ahead: a coarse bar closes when its last fine bar closes, and
an incomplete bucket is dropped rather than invented."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.backtest.resample import resample_candles
from tia.domain.market import Candle

START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def minute(i: int, *, open_: float, high: float, low: float, close: float, volume: float = 1.0) -> Candle:
    t = START + timedelta(minutes=i)
    return Candle(
        symbol="BTC-USD", timeframe="1m", open_time=t, close_time=t + timedelta(minutes=1),
        open=open_, high=high, low=low, close=close, volume=volume, trade_count=1, provider="t",
    )


def test_five_one_minute_bars_become_one_five_minute_bar_with_the_right_ohlcv() -> None:
    fine = [
        minute(0, open_=100, high=101, low=99, close=100.5),
        minute(1, open_=100.5, high=103, low=100, close=102),
        minute(2, open_=102, high=102.5, low=98, close=99),
        minute(3, open_=99, high=100, low=98.5, close=99.5),
        minute(4, open_=99.5, high=100.5, low=99, close=100.2, volume=2.0),
    ]
    coarse = resample_candles(fine, "5m")
    assert len(coarse) == 1
    bar = coarse[0]
    assert bar.timeframe == "5m"
    assert bar.open_time == START and bar.close_time == START + timedelta(minutes=5)
    assert (bar.open, bar.high, bar.low, bar.close) == (100, 103, 98, 100.2)
    assert bar.volume == pytest.approx(6.0) and bar.trade_count == 5


def test_a_trailing_partial_bucket_is_dropped_not_completed() -> None:
    fine = [minute(i, open_=100, high=101, low=99, close=100) for i in range(7)]
    coarse = resample_candles(fine, "5m")
    assert len(coarse) == 1, "two minutes of the second bucket are not a five-minute bar"


def test_a_gap_inside_a_bucket_drops_that_bucket() -> None:
    fine = [minute(i, open_=100, high=101, low=99, close=100) for i in range(10) if i != 7]
    coarse = resample_candles(fine, "5m")
    assert [c.open_time for c in coarse] == [START]


def test_buckets_align_to_the_clock_grid_not_to_the_first_bar() -> None:
    fine = [minute(i, open_=100, high=101, low=99, close=100) for i in range(2, 12)]
    coarse = resample_candles(fine, "5m")
    # Minutes 2-4 are an incomplete bucket; 5-9 is the first complete one; 10-11 incomplete.
    assert [c.open_time for c in coarse] == [START + timedelta(minutes=5)]


def test_the_same_timeframe_is_returned_unchanged_and_a_finer_one_is_refused() -> None:
    fine = [minute(i, open_=100, high=101, low=99, close=100) for i in range(3)]
    assert resample_candles(fine, "1m") == fine
    with pytest.raises(ValueError):
        resample_candles(resample_candles(fine * 2, "1m"), "30s")
