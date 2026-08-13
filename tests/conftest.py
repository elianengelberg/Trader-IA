"""Shared fixtures.

Two rules hold across the whole suite:

* No test touches the network. Providers used in tests are synthetic or fixture-backed.
* No test depends on wall-clock time. Everything runs on a ``SimulatedClock`` so a run on
  a loaded CI box produces the same result as a run on a laptop.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import Environment, Settings, settings_for_env
from tia.core.rng import RngRegistry
from tia.domain.instruments import DEFAULT_UNIVERSE, InstrumentUniverse
from tia.domain.market import Candle
from tia.events.bus import RecordingBus
from tia.events.idempotency import InMemoryIdempotencyStore

START = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(START)


@pytest.fixture
def rng() -> RngRegistry:
    return RngRegistry(20260812)


@pytest.fixture
def settings() -> Settings:
    return settings_for_env(Environment.TESTING)


@pytest.fixture
def universe() -> InstrumentUniverse:
    return DEFAULT_UNIVERSE


@pytest.fixture
def bus() -> RecordingBus:
    return RecordingBus()


@pytest.fixture
def idempotency(clock: SimulatedClock) -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore(clock)


def make_candle(
    *,
    symbol: str = "BTC-USD",
    timeframe: str = "1m",
    open_time: datetime | None = None,
    open_: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float = 101.0,
    volume: float = 1000.0,
    provider: str = "test",
) -> Candle:
    """Build a valid candle with sensible high/low so tests stay readable."""
    ot = open_time or START
    hi = high if high is not None else max(open_, close) * 1.001
    lo = low if low is not None else min(open_, close) * 0.999
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=ot,
        close_time=ot + timedelta(minutes=1),
        open=open_,
        high=hi,
        low=lo,
        close=close,
        volume=volume,
        trade_count=10,
        provider=provider,
    )


@pytest.fixture
def candle_factory() -> Iterator[type(make_candle)]:  # type: ignore[valid-type]
    yield make_candle


def linear_series(
    n: int,
    *,
    start_price: float = 100.0,
    step: float = 0.5,
    symbol: str = "BTC-USD",
    start: datetime = START,
    volume: float = 1000.0,
) -> list[Candle]:
    """A deterministic monotonic price series — the simplest input that makes trend
    behaviour unambiguous in a test."""
    candles: list[Candle] = []
    price = start_price
    for i in range(n):
        nxt = price + step
        candles.append(
            make_candle(
                symbol=symbol,
                open_time=start + timedelta(minutes=i),
                open_=price,
                close=nxt,
                high=max(price, nxt) + 0.1,
                low=min(price, nxt) - 0.1,
                volume=volume,
            )
        )
        price = nxt
    return candles


def proportional_series(
    n: int,
    *,
    start_price: float = 100.0,
    step_pct: float = 0.1,
    wick_pct: float = 0.05,
    symbol: str = "BTC-USD",
    start: datetime = START,
) -> list[Candle]:
    """A trending series whose bar geometry is a fixed *percentage* of price.

    Used where a test asserts a feature is scale-free: an absolute-sized wick would be
    enormous at price 100 and negligible at price 100,000, which is a property of the
    fixture rather than of the feature under test.
    """
    candles: list[Candle] = []
    price = start_price
    for i in range(n):
        nxt = price * (1 + step_pct / 100.0)
        wick = price * wick_pct / 100.0
        candles.append(
            make_candle(
                symbol=symbol,
                open_time=start + timedelta(minutes=i),
                open_=price,
                close=nxt,
                high=max(price, nxt) + wick,
                low=min(price, nxt) - wick,
            )
        )
        price = nxt
    return candles
