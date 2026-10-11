"""Aggregate closed bars into a coarser timeframe without looking ahead.

A coarse bar exists only once every fine bar inside it has closed: its ``close_time`` is the
bucket's end, its open is the first fine open, its close the last fine close. A bucket whose
last fine bar does not reach the bucket's end (a trailing partial bucket, or a gap in the
source) is dropped rather than completed from thin air — an invented bar is the quietest
way to leak the future into a backtest.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from tia.domain.instruments import Timeframe
from tia.domain.market import Candle


def resample_candles(candles: Sequence[Candle], target_timeframe: str) -> list[Candle]:
    """Resample ``candles`` (one timeframe, chronological) into ``target_timeframe`` bars."""
    bars = list(candles)
    if not bars:
        return []
    target = Timeframe.parse(target_timeframe)
    delta: timedelta = target.delta
    step = delta.total_seconds()
    if step <= 0:
        raise ValueError(f"target timeframe {target_timeframe!r} has no positive length")
    source_step = (bars[0].close_time - bars[0].open_time).total_seconds()
    if source_step <= 0 or step < source_step or step % source_step != 0:
        raise ValueError(
            f"cannot resample {bars[0].timeframe} bars into {target_timeframe}: the target "
            "must be a whole multiple of the source"
        )
    if step == source_step:
        return bars

    symbol = bars[0].symbol
    expected = round(step / source_step)
    out: list[Candle] = []
    bucket: list[Candle] = []
    bucket_start: float | None = None

    def flush() -> None:
        if not bucket or bucket_start is None:
            return
        end = bucket_start + step
        # Complete means every fine bar is present and the last one closes exactly at the
        # bucket's end. A bucket with a hole, or one that started mid-way, is dropped.
        if len(bucket) != expected or bucket[-1].close_time.timestamp() != end:
            return
        out.append(
            Candle(
                symbol=symbol,
                timeframe=target_timeframe,
                open_time=bucket[0].open_time.__class__.fromtimestamp(
                    bucket_start, tz=bucket[0].open_time.tzinfo
                ),
                close_time=bucket[-1].close_time,
                open=bucket[0].open,
                high=max(c.high for c in bucket),
                low=min(c.low for c in bucket),
                close=bucket[-1].close,
                volume=sum(c.volume for c in bucket),
                trade_count=sum(c.trade_count for c in bucket),
                provider=bucket[0].provider,
            )
        )

    for candle in bars:
        ts = candle.open_time.timestamp()
        start = ts - (ts % step)
        if bucket_start is None or start != bucket_start:
            flush()
            bucket = []
            bucket_start = start
        bucket.append(candle)
    flush()
    return out


__all__ = ["resample_candles"]
