"""Binance public market data — **opt-in and unverified in this environment**.

Integration status: **REQUIRES VALIDATION**.

This client is written against the documented shape of Binance's *public* spot market
data endpoints, which need no API key and no signature. It could **not** be exercised
here: this sandbox's egress proxy blocks both ``api.binance.com`` and
``developers.binance.com``, so not a single request was made and not one field name was
confirmed against the primary source.

Consequences, deliberately chosen:

* It is never selected by default, and the ``demo`` environment refuses it outright.
* It is excluded from the test suite's default run (marked ``network``).
* Before trusting it, run ``scripts/validate_binance.py`` from a machine with egress. It
  checks the kline array's positional layout specifically, because a reordering there
  produces candles that parse cleanly and are wrong.

If a field name or the array ordering has changed, :meth:`_parse_kline` raises with the
raw payload attached rather than silently producing a plausible-looking wrong candle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from tia.core.clock import Clock, SystemClock, ensure_utc, utc_from_millis
from tia.core.errors import ProviderError, ProviderUnavailableError
from tia.core.logging import get_logger
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.domain.market import Candle, Quote

_log = get_logger("data.binance")

# Documented mapping from our timeframe vocabulary to Binance's interval strings.
_INTERVAL_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
}

MAX_LIMIT = 1000


class BinancePublicProvider(MarketDataProvider):
    """Read-only client for Binance public spot market data.

    Market data only — no key, no signature, and no order-placing surface exists on this
    class by construction.
    """

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__(
            ProviderCapabilities(
                name="binance",
                quotes=True,
                trades=False,
                candles=True,
                order_book=True,
                historical=True,
                streaming=False,
                requires_credentials=False,
                requires_network=True,
                supported_timeframes=tuple(_INTERVAL_MAP),
                max_history_bars=MAX_LIMIT,
                notes=(
                    "REQUIRES VALIDATION: written from documented public-endpoint shapes; "
                    "unverified in the build environment (host blocked by egress proxy)."
                ),
            )
        )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        # A quote carries no timestamp of its own on this endpoint, so one has to be
        # stamped locally. It comes from an injected clock rather than ``datetime.now``
        # so a replay of recorded responses reproduces the same timestamps.
        self._clock = clock or SystemClock()

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"User-Agent": "trader-ia/0.1 (research; simulation-only)"},
            )
        return self._client

    @staticmethod
    def to_venue_symbol(symbol: str) -> str:
        """``BTC-USD`` -> ``BTCUSDT``. USD is mapped to USDT, the actual spot quote asset."""
        base, _, quote = symbol.partition("-")
        if not quote:
            return symbol.upper()
        quote = "USDT" if quote.upper() == "USD" else quote.upper()
        return f"{base.upper()}{quote}"

    def _parse_kline(self, row: Any, symbol: str, timeframe: str) -> Candle:
        """Parse one kline array.

        Documented layout: ``[openTime, open, high, low, close, volume, closeTime,
        quoteAssetVolume, numberOfTrades, ...]``. Positional access is fragile by nature,
        so a shape mismatch raises with the payload attached instead of guessing.
        """
        if not isinstance(row, list | tuple) or len(row) < 9:
            raise ProviderError(
                "unexpected kline shape from Binance; the response format may have changed",
                provider=self.name,
                received=str(row)[:300],
            )
        try:
            open_time = utc_from_millis(int(row[0]))
            close_time = utc_from_millis(int(row[6]))
            return Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=close_time,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                trade_count=int(row[8]),
                provider=self.name,
            )
        except (TypeError, ValueError, IndexError) as exc:
            raise ProviderError(
                f"failed to parse kline: {exc}", provider=self.name, received=str(row)[:300]
            ) from exc

    async def get_candles(
        self, symbol: str, timeframe: str, *, limit: int = 500, end: datetime | None = None
    ) -> list[Candle]:
        interval = _INTERVAL_MAP.get(timeframe)
        if interval is None:
            raise ProviderError(
                f"timeframe {timeframe!r} is not supported by this provider",
                provider=self.name,
                supported=sorted(_INTERVAL_MAP),
            )

        params: dict[str, Any] = {
            "symbol": self.to_venue_symbol(symbol),
            "interval": interval,
            "limit": min(limit, MAX_LIMIT),
        }
        if end is not None:
            params["endTime"] = int(ensure_utc(end).timestamp() * 1000)

        client = await self._http()
        try:
            response = await client.get("/api/v3/klines", params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            self._record_failure()
            raise ProviderUnavailableError(
                f"binance request failed: {exc}",
                provider=self.name,
                consecutive_failures=self._consecutive_failures,
            ) from exc

        if not isinstance(payload, list):
            self._record_failure()
            raise ProviderError(
                "expected a JSON array of klines", provider=self.name, received=str(payload)[:300]
            )

        candles = [self._parse_kline(row, symbol, timeframe) for row in payload]
        # The most recent kline is the *forming* bar. Acting on it is look-ahead bias, so
        # it is dropped here rather than filtered by every caller.
        now_ms = int(ensure_utc(end).timestamp() * 1000) if end else None
        if candles and now_ms is None:
            candles = candles[:-1]
        if candles:
            self._record_success(candles[-1].close_time)
        return candles

    async def server_time_ms(self) -> int:
        """The venue's own clock, for the skew monitor. REQUIRES VALIDATION."""
        client = await self._http()
        response = await client.get("/api/v3/time")
        response.raise_for_status()
        return int(response.json()["serverTime"])

    async def get_quote(self, symbol: str) -> Quote | None:
        client = await self._http()
        try:
            response = await client.get(
                "/api/v3/ticker/bookTicker", params={"symbol": self.to_venue_symbol(symbol)}
            )
            response.raise_for_status()
            data = response.json()
            return Quote(
                symbol=symbol,
                timestamp=self._clock.now(),
                bid=float(data["bidPrice"]),
                ask=float(data["askPrice"]),
                bid_size=float(data["bidQty"]),
                ask_size=float(data["askQty"]),
                provider=self.name,
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            self._record_failure()
            _log.warning("binance_quote_failed", error=str(exc))
            return None

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


__all__ = ["MAX_LIMIT", "BinancePublicProvider"]
