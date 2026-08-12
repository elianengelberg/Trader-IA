"""Normalized market data.

Every provider converts into these types. Downstream code never sees a provider-specific
shape, which is what makes swapping providers a configuration change rather than a
refactor.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tia.core.clock import ensure_utc
from tia.core.ids import content_hash
from tia.domain.enums import MarketRegime


class _MarketModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _reject_nan(cls, v: Any) -> Any:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("non-finite numeric value")
        return v


class Candle(_MarketModel):
    """A closed OHLCV bar.

    Only *closed* bars enter the pipeline. Acting on a forming bar is look-ahead by
    another name: its high/low/close are not yet facts.
    """

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    trade_count: int = Field(0, ge=0)
    provider: str = "unknown"

    @field_validator("open_time", "close_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="candle time")

    @model_validator(mode="after")
    def _ohlc_invariants(self) -> Candle:
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError(
                f"OHLC invariant violated: o={self.open} h={self.high} l={self.low} c={self.close}"
            )
        if self.high < self.low:
            raise ValueError("high < low")
        return self

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0

    @property
    def range_pct(self) -> float:
        return (self.high - self.low) / self.low * 100.0 if self.low > 0 else 0.0

    @property
    def is_up(self) -> bool:
        return self.close >= self.open

    def dedup_key(self) -> tuple[str, str, str, int]:
        return (self.provider, self.symbol, self.timeframe, int(self.open_time.timestamp()))


class Quote(_MarketModel):
    """Top-of-book snapshot."""

    symbol: str
    timestamp: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    bid_size: float = Field(0.0, ge=0)
    ask_size: float = Field(0.0, ge=0)
    provider: str = "unknown"

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="quote timestamp")

    @model_validator(mode="after")
    def _crossed(self) -> Quote:
        if self.ask < self.bid:
            raise ValueError(f"crossed book: bid={self.bid} > ask={self.ask}")
        return self

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> float:
        mid = self.mid
        return (self.spread / mid) * 10_000.0 if mid > 0 else float("inf")


class TradePrint(_MarketModel):
    """A single executed trade observed on the tape."""

    symbol: str
    timestamp: datetime
    price: float = Field(gt=0)
    size: float = Field(gt=0)
    aggressor: str | None = None
    provider: str = "unknown"

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="trade timestamp")


class OrderBookLevel(_MarketModel):
    price: float = Field(gt=0)
    size: float = Field(ge=0)


class OrderBook(_MarketModel):
    """Depth snapshot. Optional: not every provider exposes one."""

    symbol: str
    timestamp: datetime
    bids: tuple[OrderBookLevel, ...] = ()
    asks: tuple[OrderBookLevel, ...] = ()
    provider: str = "unknown"

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="book timestamp")

    def depth_within(self, bps: float) -> tuple[float, float]:
        """Notional resting within ``bps`` of the mid, per side."""
        if not self.bids or not self.asks:
            return (0.0, 0.0)
        mid = (self.bids[0].price + self.asks[0].price) / 2.0
        band = mid * bps / 10_000.0
        bid_depth = sum(lvl.price * lvl.size for lvl in self.bids if lvl.price >= mid - band)
        ask_depth = sum(lvl.price * lvl.size for lvl in self.asks if lvl.price <= mid + band)
        return (bid_depth, ask_depth)


class MarketSnapshot(BaseModel):
    """Exactly what the system saw when it decided.

    Content-addressed: ``snapshot_id`` is a hash of the contents, so an identical market
    view always produces an identical id and two decisions can be compared for
    "did they see the same thing?" without a deep diff.
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = ""
    taken_at: datetime
    symbol: str
    timeframe: str
    last_close: float
    last_candle_open_time: datetime
    quote: Quote | None = None
    indicators: dict[str, float] = Field(default_factory=dict)
    features: dict[str, float] = Field(default_factory=dict)
    regime: MarketRegime = MarketRegime.UNKNOWN
    volatility: float = 0.0
    data_quality_score: float = 1.0
    data_freshness_score: float = 1.0
    news_refs: tuple[str, ...] = ()
    macro_refs: tuple[str, ...] = ()
    open_positions: dict[str, float] = Field(default_factory=dict)
    gross_exposure: float = 0.0
    net_exposure: float = 0.0
    available_capital: float = 0.0
    equity: float = 0.0

    @field_validator("taken_at", "last_candle_open_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="snapshot time")

    @model_validator(mode="after")
    def _assign_id(self) -> MarketSnapshot:
        if not self.snapshot_id:
            payload = self.model_dump(mode="json", exclude={"snapshot_id"})
            object.__setattr__(self, "snapshot_id", f"snap_{content_hash(payload)}")
        return self


class NewsItem(_MarketModel):
    """A news article as seen by the system. Body is stored by hash, not verbatim."""

    news_id: str
    published_at: datetime
    ingested_at: datetime
    source: str
    headline: str
    body_hash: str
    url: str | None = None
    symbols: tuple[str, ...] = ()
    language: str = "en"

    @field_validator("published_at", "ingested_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="news time")


class MacroEvent(_MarketModel):
    """A scheduled or released macroeconomic datapoint."""

    macro_id: str
    released_at: datetime
    region: str
    indicator: str
    actual: float | None = None
    consensus: float | None = None
    previous: float | None = None
    unit: str = ""

    @field_validator("released_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="macro time")

    @property
    def surprise(self) -> float | None:
        if self.actual is None or self.consensus is None:
            return None
        return self.actual - self.consensus


__all__ = [
    "Candle",
    "MacroEvent",
    "MarketSnapshot",
    "NewsItem",
    "OrderBook",
    "OrderBookLevel",
    "Quote",
    "TradePrint",
]
