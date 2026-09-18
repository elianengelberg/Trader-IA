"""Binance's tick-level public streams for one symbol: diff-depth, trades, bookTicker.

One WebSocket connection carrying three streams (combined-stream endpoint), parsed
into typed events with **two timestamps each**: the exchange's (``E``, and ``T`` for
trades) and the local receive time. The difference is the latency the rest of the
market maker must respect; it is kept as a distribution (p50/p95/p99), per stream.

Documented payloads (binance-spot-api-docs, web-socket-streams.md):

* ``<symbol>@depth@100ms`` → ``{"e":"depthUpdate","E":ms,"s":..,"U":first,"u":final,
  "b":[[price,qty],..],"a":[[price,qty],..]}``
* ``<symbol>@trade`` → ``{"e":"trade","E":ms,"s":..,"t":id,"p":price,"q":qty,"T":ms,
  "m":buyer_is_maker,"M":ignore}``
* ``<symbol>@bookTicker`` → ``{"u":update_id,"s":..,"b":bid,"B":bid_qty,"a":ask,"A":ask_qty}``
  (no event time on spot)

The stream knows nothing about books or quotes: it delivers events to subscribers in
arrival order and counts what it could not deliver. A subscriber that cannot keep up
loses events — and the loss is counted, so a recording or a book built on this stream
can say whether it is complete.

Integration status: **REQUIRES VALIDATION** against the live endpoint; the parsers are
exercised against the documented frames in tests, and ``scripts/mm_market_data_check.py``
runs the real thing from a machine with egress.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from tia.core.clock import SystemClock
from tia.core.logging import get_logger
from tia.mm.latency import LatencyStats
from tia.mm.order_book import DepthUpdate

_log = get_logger("mm.streams")

DEFAULT_STREAM_URL = "wss://stream.binance.com:9443/stream"
BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)

Connector = Callable[[str], AbstractAsyncContextManager[AsyncIterator[str | bytes]]]


def _default_connector(url: str) -> AbstractAsyncContextManager[AsyncIterator[str | bytes]]:
    import websockets

    return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**22)


def venue_symbol(symbol: str) -> str:
    base, _, quote = symbol.partition("-")
    if not quote:
        return symbol.lower()
    quote = "usdt" if quote.upper() == "USD" else quote.lower()
    return f"{base.lower()}{quote}"


@dataclass(frozen=True)
class TradeEvent:
    trade_id: int
    price: float
    quantity: float
    buyer_is_maker: bool
    trade_time_ms: int
    event_time_ms: int
    received_at_ms: int

    @property
    def aggressor(self) -> str:
        """Who crossed the spread: buyer-is-maker means a seller hit the bid."""
        return "sell" if self.buyer_is_maker else "buy"


@dataclass(frozen=True)
class BookTickerEvent:
    update_id: int
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    received_at_ms: int


@dataclass(frozen=True)
class StreamStatus:
    connected: bool
    reconnects: int
    messages: int
    depth_events: int
    trade_events: int
    book_ticker_events: int
    parse_errors: int
    dropped_events: int
    last_error: str
    last_message_age_s: float | None


def parse_depth_update(data: dict[str, Any], received_at_ms: int) -> DepthUpdate:
    return DepthUpdate(
        first_update_id=int(data["U"]),
        final_update_id=int(data["u"]),
        bids=tuple((float(p), float(q)) for p, q in data.get("b", [])),
        asks=tuple((float(p), float(q)) for p, q in data.get("a", [])),
        event_time_ms=int(data.get("E", 0)),
        received_at_ms=received_at_ms,
    )


def parse_trade(data: dict[str, Any], received_at_ms: int) -> TradeEvent:
    return TradeEvent(
        trade_id=int(data["t"]),
        price=float(data["p"]),
        quantity=float(data["q"]),
        buyer_is_maker=bool(data["m"]),
        trade_time_ms=int(data["T"]),
        event_time_ms=int(data.get("E", 0)),
        received_at_ms=received_at_ms,
    )


def parse_book_ticker(data: dict[str, Any], received_at_ms: int) -> BookTickerEvent:
    return BookTickerEvent(
        update_id=int(data.get("u", 0)),
        bid=float(data["b"]),
        bid_size=float(data.get("B", 0.0)),
        ask=float(data["a"]),
        ask_size=float(data.get("A", 0.0)),
        received_at_ms=received_at_ms,
    )


class MarketDataStream:
    """The connection, the parsing, the dispatch, and the counts.

    Subscribers are plain callables ``(kind, event)`` with kind in
    ``{"depth", "trade", "book"}``; they are called synchronously in arrival order and
    must be fast. A subscriber that raises is counted as a dropped delivery for that
    subscriber and never stops the stream. ``now_ms`` is injectable for tests.
    """

    def __init__(
        self,
        symbol: str,
        *,
        stream_url: str = DEFAULT_STREAM_URL,
        depth_speed: str = "100ms",
        connector: Connector | None = None,
        now_ms: Callable[[], int] | None = None,
        recent: int = 200,
    ) -> None:
        self.symbol = symbol
        self._venue_symbol = venue_symbol(symbol)
        self._stream_url = stream_url
        self._depth_speed = depth_speed
        self._connector = connector or _default_connector
        self._now_ms = now_ms or SystemClock().timestamp_ms
        self._subscribers: list[Callable[[str, Any], None]] = []
        self._task: asyncio.Task[Any] | None = None

        self.connected = False
        self.reconnects = 0
        self.messages = 0
        self.depth_events = 0
        self.trade_events = 0
        self.book_ticker_events = 0
        self.parse_errors = 0
        self.dropped_events = 0
        self.last_error = ""
        self._last_message_ms: int | None = None
        self.latency_depth = LatencyStats()
        self.latency_trade = LatencyStats()
        self.latency_trade_to_event = LatencyStats()  # T -> E: the venue's own delay
        self.recent_trades: deque[TradeEvent] = deque(maxlen=recent)
        self.last_book_ticker: BookTickerEvent | None = None

    @property
    def url(self) -> str:
        s = self._venue_symbol
        return f"{self._stream_url}?streams={s}@depth@{self._depth_speed}/{s}@trade/{s}@bookTicker"

    def subscribe(self, callback: Callable[[str, Any], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return unsubscribe

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.get_running_loop().create_task(self._run(), name="mm-market-data")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self.connected = False

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                async with self._connector(self.url) as socket:
                    self.connected = True
                    self.last_error = ""
                    attempt = 0
                    _log.info("mm_stream_connected", url=self.url)
                    async for raw in socket:
                        self.on_message(raw)
                    raise ConnectionError("stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self.reconnects += 1
                self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                attempt += 1
                _log.warning("mm_stream_dropped", error=self.last_error, retry_in=delay)
                self._dispatch("disconnect", {"error": self.last_error, "at_ms": self._now_ms()})
                await asyncio.sleep(delay)

    # ------------------------------------------------------------------ messages

    def on_message(self, raw: str | bytes) -> None:
        received_at_ms = self._now_ms()
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            self.parse_errors += 1
            return
        data = frame.get("data", frame) if isinstance(frame, dict) else None
        if not isinstance(data, dict):
            self.parse_errors += 1
            return
        self.messages += 1
        self._last_message_ms = received_at_ms
        kind = data.get("e")
        try:
            if kind == "depthUpdate":
                event = parse_depth_update(data, received_at_ms)
                self.depth_events += 1
                if event.event_time_ms:
                    self.latency_depth.add(received_at_ms - event.event_time_ms)
                self._dispatch("depth", event)
            elif kind == "trade":
                trade = parse_trade(data, received_at_ms)
                self.trade_events += 1
                if trade.event_time_ms:
                    self.latency_trade.add(received_at_ms - trade.event_time_ms)
                    self.latency_trade_to_event.add(trade.event_time_ms - trade.trade_time_ms)
                self.recent_trades.append(trade)
                self._dispatch("trade", trade)
            elif "b" in data and "a" in data and "u" in data:
                ticker = parse_book_ticker(data, received_at_ms)
                self.book_ticker_events += 1
                self.last_book_ticker = ticker
                self._dispatch("book", ticker)
            else:
                self.parse_errors += 1
        except (KeyError, TypeError, ValueError) as exc:
            self.parse_errors += 1
            _log.warning("mm_stream_bad_frame", error=str(exc)[:120])

    def _dispatch(self, kind: str, event: Any) -> None:
        for callback in list(self._subscribers):
            try:
                callback(kind, event)
            except Exception as exc:  # a slow or broken subscriber never stops the tape
                self.dropped_events += 1
                _log.warning("mm_stream_subscriber_failed", kind=kind, error=str(exc)[:120])

    def status(self) -> StreamStatus:
        age = (
            (self._now_ms() - self._last_message_ms) / 1000.0
            if self._last_message_ms is not None
            else None
        )
        return StreamStatus(
            connected=self.connected,
            reconnects=self.reconnects,
            messages=self.messages,
            depth_events=self.depth_events,
            trade_events=self.trade_events,
            book_ticker_events=self.book_ticker_events,
            parse_errors=self.parse_errors,
            dropped_events=self.dropped_events,
            last_error=self.last_error,
            last_message_age_s=round(age, 3) if age is not None else None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.status().__dict__,
            "url": self.url,
            "latency_depth_ms": self.latency_depth.as_dict(),
            "latency_trade_ms": self.latency_trade.as_dict(),
            "venue_trade_to_event_ms": self.latency_trade_to_event.as_dict(),
        }


__all__ = [
    "BACKOFF",
    "DEFAULT_STREAM_URL",
    "BookTickerEvent",
    "MarketDataStream",
    "StreamStatus",
    "TradeEvent",
    "parse_book_ticker",
    "parse_depth_update",
    "parse_trade",
    "venue_symbol",
]
