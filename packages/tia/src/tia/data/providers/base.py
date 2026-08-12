"""Market data provider interface.

Everything downstream speaks :mod:`tia.domain.market` types only. A provider's job is to
fetch and *normalize*; no provider-specific shape escapes this package. That is what makes
swapping a data vendor a configuration change rather than a refactor.

Capabilities are declared rather than discovered. A component that needs an order book
asks ``provider.capabilities.order_book`` instead of calling and catching — a missing
capability is a configuration error, surfaced at startup, not a runtime surprise
mid-session.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from tia.domain.market import Candle, OrderBook, Quote, TradePrint


class ProviderCapabilities(BaseModel):
    """What a provider can actually do. Declared up front, checked at wiring time."""

    model_config = ConfigDict(frozen=True)

    name: str
    quotes: bool = False
    trades: bool = False
    candles: bool = True
    order_book: bool = False
    historical: bool = True
    streaming: bool = False
    requires_credentials: bool = False
    requires_network: bool = False
    supported_timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")
    max_history_bars: int = 1000
    notes: str = ""


class ProviderHealth(BaseModel):
    """Liveness of a feed. Consumed by the data-quality engine and the health endpoint."""

    model_config = ConfigDict(frozen=True)

    provider: str
    connected: bool
    last_message_at: datetime | None = None
    consecutive_failures: int = 0
    detail: str = ""


class MarketDataProvider(ABC):
    """Abstract source of normalized market data."""

    def __init__(self, capabilities: ProviderCapabilities) -> None:
        self._capabilities = capabilities
        self._consecutive_failures = 0
        self._last_message_at: datetime | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def name(self) -> str:
        return self._capabilities.name

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            connected=self._consecutive_failures == 0,
            last_message_at=self._last_message_at,
            consecutive_failures=self._consecutive_failures,
        )

    def _record_success(self, at: datetime) -> None:
        self._consecutive_failures = 0
        self._last_message_at = at

    def _record_failure(self) -> None:
        self._consecutive_failures += 1

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 500,
        end: datetime | None = None,
    ) -> list[Candle]:
        """Return up to ``limit`` **closed** candles ending at or before ``end``.

        Only closed bars, always. A forming bar's high, low and close are not yet facts,
        and acting on them is look-ahead bias wearing a different hat.
        """

    async def get_quote(self, symbol: str) -> Quote | None:  # noqa: ARG002 - default no-op
        """Latest top-of-book, or ``None`` when the provider cannot supply one."""
        return None

    async def get_trades(self, symbol: str, *, limit: int = 100) -> list[TradePrint]:  # noqa: ARG002 - default no-op
        return []

    async def get_order_book(self, symbol: str, *, depth: int = 10) -> OrderBook | None:  # noqa: ARG002 - default no-op
        return None

    def stream_candles(
        self, symbols: list[str], timeframe: str
    ) -> AsyncIterator[Candle]:  # pragma: no cover - overridden by streaming providers
        raise NotImplementedError(f"{self.name} does not support streaming")

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


__all__ = ["MarketDataProvider", "ProviderCapabilities", "ProviderHealth"]
