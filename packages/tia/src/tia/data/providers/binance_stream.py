"""Binance market data over WebSocket: the bar the moment it closes, the book as it moves.

The 24/7 session used to poll the REST klines endpoint every ten seconds. A one-minute
bar that closed at :00.000 was therefore seen anywhere from a fraction of a second to
ten seconds later, plus the request itself — and the quote that prices the spread was a
separate request per bar. This provider replaces that with Binance's public streams:

* ``<symbol>@kline_1m`` pushes the forming bar as it changes and flags the moment it
  closes (``x: true``), so the session decides within the network's latency of the
  close rather than the poll interval's.
* ``<symbol>@bookTicker`` pushes the best bid and ask on every change, so the spread
  gate and the cost model price against the book as it is, not as it was a bar ago.

What it does **not** do, stated so nobody mistakes it for more: it does not make the
session faster than the exchange's distance. Frankfurt to Binance's matching engine is
on the order of two hundred milliseconds each way, and every kline event carries the
exchange's own timestamp, so the lag is measured and shown rather than assumed away.
A colocated market maker sees the same book two hundred milliseconds before this
process does, and no software here changes that.

The REST client stays underneath as history and as fallback: the buffer is seeded from
it, other timeframes go to it, and a stream that is down or stale is reported as such
and polled around — a dead socket is a slower feed, never a blind one.

Integration status: **REQUIRES VALIDATION** — the stream endpoint could not be reached
from the build environment; the payload parsing follows Binance's documented shapes
and is exercised against recorded frames in the tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any

from tia.core.clock import Clock, SystemClock
from tia.core.logging import get_logger
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.domain.market import Candle, Quote

_log = get_logger("data.binance_stream")

DEFAULT_STREAM_URL = "wss://stream.binance.com:9443/stream"

#: A stream that has said nothing for this long is not a live stream; candles and quotes
#: come from REST until it speaks again.
STALE_AFTER_SECONDS = 10.0
#: A quote older than this is not the book as it is.
QUOTE_FRESH_SECONDS = 5.0
#: Reconnect backoff, seconds: doubles up to the last value.
BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)

Connector = Callable[[str], AbstractAsyncContextManager[AsyncIterator[str | bytes]]]


def _default_connector(url: str) -> AbstractAsyncContextManager[AsyncIterator[str | bytes]]:
    import websockets

    return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20)


def venue_symbol(symbol: str) -> str:
    """``BTC-USD`` -> ``btcusdt``, the stream's lower-case spelling of the spot pair."""
    base, _, quote = symbol.partition("-")
    if not quote:
        return symbol.lower()
    quote = "usdt" if quote.upper() == "USD" else quote.lower()
    return f"{base.lower()}{quote}"


def parse_kline_event(data: dict[str, Any], symbol: str) -> tuple[Candle, bool, int]:
    """One ``kline`` event -> (candle, closed, exchange event time ms).

    Documented shape: ``{"e": "kline", "E": <ms>, "k": {"t": open_ms, "T": close_ms,
    "i": "1m", "o","h","l","c","v", "x": closed, ...}}``.
    """
    k = data["k"]
    candle = Candle(
        symbol=symbol,
        timeframe=str(k["i"]),
        open_time=datetime.fromtimestamp(int(k["t"]) / 1000.0, tz=UTC),
        close_time=datetime.fromtimestamp(int(k["T"]) / 1000.0, tz=UTC),
        open=float(k["o"]),
        high=float(k["h"]),
        low=float(k["l"]),
        close=float(k["c"]),
        volume=float(k["v"]),
    )
    return candle, bool(k.get("x", False)), int(data.get("E", 0))


def parse_book_ticker(data: dict[str, Any], symbol: str, at: datetime) -> Quote:
    """One ``bookTicker`` event -> Quote. Documented shape: ``{"u", "s", "b", "B", "a", "A"}``."""
    return Quote(
        symbol=symbol,
        timestamp=at,
        bid=float(data["b"]),
        ask=float(data["a"]),
        bid_size=float(data.get("B", 0.0)),
        ask_size=float(data.get("A", 0.0)),
        provider="binance-ws",
    )


class BinanceStreamProvider(MarketDataProvider):
    """Streamed candles and quotes for one symbol, REST underneath for everything else."""

    def __init__(
        self,
        rest: Any,
        *,
        symbol: str,
        timeframe: str = "1m",
        stream_url: str = DEFAULT_STREAM_URL,
        clock: Clock | None = None,
        connector: Connector | None = None,
        buffer_size: int = 1500,
    ) -> None:
        rest_capabilities = getattr(rest, "capabilities", None)
        super().__init__(
            ProviderCapabilities(
                name="binance-stream",
                quotes=True,
                trades=False,
                candles=True,
                order_book=True,
                historical=True,
                streaming=True,
                requires_credentials=False,
                requires_network=True,
                supported_timeframes=(
                    rest_capabilities.supported_timeframes if rest_capabilities else (timeframe,)
                ),
                max_history_bars=(
                    rest_capabilities.max_history_bars if rest_capabilities else 1000
                ),
                notes=(
                    "Public kline and bookTicker streams with the REST client as history "
                    "and fallback. REQUIRES VALIDATION against the live endpoint."
                ),
            )
        )
        self._rest = rest
        self._symbol = symbol
        self._venue_symbol = venue_symbol(symbol)
        self._timeframe = timeframe
        self._stream_url = stream_url
        self._clock = clock or SystemClock()
        self._connector = connector or _default_connector

        self._candles: deque[Candle] = deque(maxlen=buffer_size)
        self._seeded = False
        self._forming: Candle | None = None
        self._quote: Quote | None = None
        self._quote_at: datetime | None = None
        self._bar_event = asyncio.Event()
        self._bar_seq = 0

        self._task: asyncio.Task[Any] | None = None
        self._connected = False
        self._connected_at: datetime | None = None
        self._last_event_at: datetime | None = None
        self._last_error = ""
        self._reconnects = 0
        self._messages = 0
        self._closed_bars = 0
        self._latency_last_ms: float | None = None
        self._latency_ema_ms: float | None = None

    # ------------------------------------------------------------------ lifecycle

    @property
    def url(self) -> str:
        return f"{self._stream_url}?streams={self._venue_symbol}@kline_{self._timeframe}/{self._venue_symbol}@bookTicker"

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.get_running_loop().create_task(self._run(), name="binance-stream")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._connected = False
        closer = getattr(self._rest, "close", None)
        if callable(closer):
            await closer()

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                async with self._connector(self.url) as socket:
                    self._connected = True
                    self._connected_at = self._clock.now()
                    self._last_error = ""
                    attempt = 0
                    _log.info("binance_stream_connected", url=self.url)
                    async for raw in socket:
                        self._on_message(raw)
                    raise ConnectionError("stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._reconnects += 1
                self._last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                attempt += 1
                _log.warning("binance_stream_dropped", error=self._last_error, retry_in=delay)
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------ messages

    def _on_message(self, raw: str | bytes) -> None:
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            return
        data = frame.get("data", frame) if isinstance(frame, dict) else None
        if not isinstance(data, dict):
            return
        now = self._clock.now()
        self._messages += 1
        self._last_event_at = now
        self._record_success(now)
        kind = data.get("e") or ("bookTicker" if "b" in data and "a" in data else "")
        if kind == "kline":
            try:
                candle, closed, event_ms = parse_kline_event(data, self._symbol)
            except (KeyError, TypeError, ValueError) as exc:
                _log.warning("binance_stream_bad_kline", error=str(exc)[:120])
                return
            if event_ms:
                latency = int(now.timestamp() * 1000) - event_ms
                self._latency_last_ms = float(latency)
                self._latency_ema_ms = (
                    float(latency)
                    if self._latency_ema_ms is None
                    else 0.9 * self._latency_ema_ms + 0.1 * float(latency)
                )
            if closed:
                self._forming = None
                if not self._candles or candle.open_time > self._candles[-1].open_time:
                    self._candles.append(candle)
                    self._closed_bars += 1
                    self._bar_seq += 1
                    self._bar_event.set()
            else:
                self._forming = candle
        elif kind == "bookTicker":
            try:
                self._quote = parse_book_ticker(data, self._symbol, now)
                self._quote_at = now
            except (KeyError, TypeError, ValueError) as exc:
                _log.warning("binance_stream_bad_quote", error=str(exc)[:120])

    # ------------------------------------------------------------------ freshness

    def _age_seconds(self, at: datetime | None) -> float | None:
        if at is None:
            return None
        return (self._clock.now() - at).total_seconds()

    @property
    def healthy(self) -> bool:
        """Connected and heard from recently. Anything else is served from REST."""
        age = self._age_seconds(self._last_event_at)
        return self._connected and age is not None and age <= STALE_AFTER_SECONDS

    async def wait_for_bar(self, timeout_seconds: float) -> bool:
        """Block until the next closed bar arrives, or ``timeout_seconds`` pass.

        True when a bar arrived. The runtime uses this in place of its poll sleep, so a
        decision follows the close by the network's latency instead of the poll's.
        """
        if not self.healthy:
            await asyncio.sleep(timeout_seconds)
            return False
        self._bar_event.clear()
        try:
            await asyncio.wait_for(self._bar_event.wait(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    # ------------------------------------------------------------------ provider API

    async def get_candles(
        self, symbol: str, timeframe: str, *, limit: int = 500, end: datetime | None = None
    ) -> list[Candle]:
        if symbol != self._symbol or timeframe != self._timeframe or end is not None:
            return await self._rest.get_candles(symbol, timeframe, limit=limit, end=end)
        if self.healthy and self._seeded and len(self._candles) >= min(limit, 2):
            return list(self._candles)[-limit:]
        # Not yet seeded, or the stream is stale: REST is the truth, and the buffer is
        # rebuilt from it so a streamed bar that arrives next lands on a complete history.
        history = await self._rest.get_candles(symbol, timeframe, limit=max(limit, 200), end=end)
        streamed = [c for c in self._candles if history and c.open_time > history[-1].open_time]
        self._candles.clear()
        self._candles.extend(history)
        self._candles.extend(streamed)
        self._seeded = bool(history)
        return list(self._candles)[-limit:]

    async def get_quote(self, symbol: str) -> Quote | None:
        age = self._age_seconds(self._quote_at)
        if (
            symbol == self._symbol
            and self._quote is not None
            and age is not None
            and age <= QUOTE_FRESH_SECONDS
        ):
            return self._quote
        return await self._rest.get_quote(symbol)

    async def order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return await self._rest.order_book(symbol, limit)

    async def server_time_ms(self) -> int:
        return await self._rest.server_time_ms()

    def feed_state(self) -> dict[str, Any]:
        """What the dashboard shows: which transport is serving, and how far behind."""
        forming = self._forming
        return {
            "transport": "websocket" if self.healthy else "rest-fallback",
            "connected": self._connected,
            "connected_at": self._connected_at.isoformat() if self._connected_at else None,
            "last_event_age_s": (
                round(self._age_seconds(self._last_event_at), 2)
                if self._last_event_at
                else None
            ),
            "latency_ms": round(self._latency_last_ms) if self._latency_last_ms is not None else None,
            "latency_ema_ms": (
                round(self._latency_ema_ms) if self._latency_ema_ms is not None else None
            ),
            "messages": self._messages,
            "closed_bars": self._closed_bars,
            "reconnects": self._reconnects,
            "buffered_bars": len(self._candles),
            "last_error": self._last_error,
            "forming_close": forming.close if forming else None,
            "quote_age_s": round(self._age_seconds(self._quote_at), 2) if self._quote_at else None,
            "url": self.url,
            "note": (
                "Latency is the exchange's event timestamp against this machine's clock: "
                "network distance plus clock offset. A colocated participant sees the same "
                "book that many milliseconds earlier."
            ),
        }


__all__ = [
    "BACKOFF",
    "DEFAULT_STREAM_URL",
    "QUOTE_FRESH_SECONDS",
    "STALE_AFTER_SECONDS",
    "BinanceStreamProvider",
    "parse_book_ticker",
    "parse_kline_event",
    "venue_symbol",
]
