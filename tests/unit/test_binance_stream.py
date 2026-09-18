"""The stream provider: documented frames become bars and quotes, the loop wakes on a
close, latency is measured against the exchange's clock, and a dead socket is a slower
feed, never a blind one."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.data.providers.binance_stream import (
    BinanceStreamProvider,
    parse_book_ticker,
    parse_kline_event,
)
from tia.domain.market import Candle

T0 = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
T0_MS = int(T0.timestamp() * 1000)


def _kline(open_ms: int, *, closed: bool, event_ms: int, close: str = "60010") -> str:
    return json.dumps(
        {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline", "E": event_ms, "s": "BTCUSDT",
                "k": {
                    "t": open_ms, "T": open_ms + 59_999, "s": "BTCUSDT", "i": "1m",
                    "o": "60000", "c": close, "h": "60020", "l": "59990", "v": "12.5",
                    "n": 100, "x": closed, "q": "1", "V": "1", "Q": "1", "B": "0",
                },
            },
        }
    )


def _ticker(bid: str, ask: str) -> str:
    return json.dumps(
        {"stream": "btcusdt@bookTicker", "data": {"u": 1, "s": "BTCUSDT", "b": bid, "B": "3", "a": ask, "A": "2"}}
    )


class FakeRest:
    """The REST client underneath: recorded history, counted calls."""

    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.calls = 0
        self.closed = False
        from tia.data.providers.base import ProviderCapabilities

        self.capabilities = ProviderCapabilities(
            name="fake-rest", supported_timeframes=("1m", "1h"), max_history_bars=1000
        )

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        return self.candles[-limit:]

    async def get_quote(self, symbol):  # type: ignore[no-untyped-def]
        return None

    async def close(self) -> None:
        self.closed = True


def _history(n: int) -> list[Candle]:
    out = []
    for i in range(n):
        open_time = T0 - timedelta(minutes=n - i)
        out.append(
            Candle(
                symbol="BTC-USD", timeframe="1m", open_time=open_time,
                close_time=open_time + timedelta(seconds=59.999),
                open=60000.0, high=60010.0, low=59990.0, close=60000.0, volume=1.0,
            )
        )
    return out


def _connector_from(scripts: list[list[str]], seen: list[str]):  # type: ignore[no-untyped-def]
    """Each connect() serves the next script; an exhausted script ends the socket."""
    attempts = {"n": 0}

    @asynccontextmanager
    async def connect(url: str):  # type: ignore[no-untyped-def]
        seen.append(url)
        index = min(attempts["n"], len(scripts) - 1)
        attempts["n"] += 1
        frames = scripts[index]

        async def messages():  # type: ignore[no-untyped-def]
            for frame in frames:
                await asyncio.sleep(0)
                yield frame
            if index >= len(scripts) - 1:
                await asyncio.sleep(3600)  # the last script stays open

        yield messages()

    return connect


def test_a_kline_frame_parses_to_a_candle_and_a_ticker_to_a_quote() -> None:
    data = json.loads(_kline(T0_MS, closed=True, event_ms=T0_MS + 60_150))["data"]
    candle, closed, event_ms = parse_kline_event(data, "BTC-USD")
    assert closed is True and event_ms == T0_MS + 60_150
    assert candle.open_time == T0 and candle.close == 60010.0 and candle.timeframe == "1m"
    quote = parse_book_ticker(json.loads(_ticker("60000.1", "60000.2"))["data"], "BTC-USD", T0)
    assert quote.bid == 60000.1 and quote.ask == 60000.2 and quote.bid_size == 3.0


async def test_the_buffer_is_seeded_from_rest_and_grows_from_the_stream() -> None:
    clock = SimulatedClock(start=T0 + timedelta(seconds=61))
    rest = FakeRest(_history(300))
    seen: list[str] = []
    provider = BinanceStreamProvider(
        rest, symbol="BTC-USD", clock=clock,  # type: ignore[arg-type]
        connector=_connector_from([[_kline(T0_MS, closed=False, event_ms=T0_MS + 30_000)]], seen),
    )
    provider.start()
    await asyncio.sleep(0.05)
    assert seen and "btcusdt@kline_1m/btcusdt@bookticker" in seen[0].lower()

    first = await provider.get_candles("BTC-USD", "1m", limit=200)
    assert rest.calls == 1 and len(first) == 200
    assert provider.feed_state()["transport"] == "websocket"

    # A closed bar on the stream lands on the seeded history; the next read is free.
    provider._on_message(_kline(T0_MS, closed=True, event_ms=T0_MS + 60_180))
    again = await provider.get_candles("BTC-USD", "1m", limit=200)
    assert rest.calls == 1
    assert again[-1].open_time == T0 and again[-1].close == 60010.0
    assert provider.feed_state()["closed_bars"] == 1
    # Latency: the machine's clock against the exchange's event stamp.
    assert provider.feed_state()["latency_ms"] == pytest.approx(
        int(clock.now().timestamp() * 1000) - (T0_MS + 60_180)
    )
    await provider.close()
    assert rest.closed


async def test_the_loop_wakes_on_a_closed_bar_and_times_out_otherwise() -> None:
    clock = SimulatedClock(start=T0)
    provider = BinanceStreamProvider(
        FakeRest(_history(10)), symbol="BTC-USD", clock=clock,  # type: ignore[arg-type]
        connector=_connector_from([[]], []),
    )
    provider.start()
    await asyncio.sleep(0.02)
    provider._on_message(_ticker("1", "2"))  # any message: the stream is alive

    async def arrive() -> None:
        await asyncio.sleep(0.02)
        provider._on_message(_kline(T0_MS, closed=True, event_ms=T0_MS + 60_000))

    task = asyncio.create_task(arrive())
    assert await provider.wait_for_bar(timeout_seconds=1.0) is True
    await task
    assert await provider.wait_for_bar(timeout_seconds=0.05) is False
    await provider.close()


async def test_a_stale_or_dead_stream_falls_back_to_rest_and_says_so() -> None:
    clock = SimulatedClock(start=T0)
    rest = FakeRest(_history(50))
    provider = BinanceStreamProvider(
        rest, symbol="BTC-USD", clock=clock,  # type: ignore[arg-type]
        connector=_connector_from([[]], []),
    )
    # Never started: not connected, nothing heard.
    assert provider.feed_state()["transport"] == "rest-fallback"
    assert len(await provider.get_candles("BTC-USD", "1m", limit=20)) == 20
    assert rest.calls == 1

    provider.start()
    await asyncio.sleep(0.02)
    provider._on_message(_ticker("1", "2"))
    assert provider.healthy
    clock.advance_by(timedelta(seconds=30))  # silence
    assert not provider.healthy
    await provider.get_candles("BTC-USD", "1m", limit=20)
    assert rest.calls == 2  # served from REST while the stream is stale
    assert (await provider.get_quote("BTC-USD")) is None  # the streamed quote aged out
    await provider.close()


async def test_other_timeframes_go_to_rest() -> None:
    rest = FakeRest(_history(5))
    provider = BinanceStreamProvider(rest, symbol="BTC-USD", clock=SimulatedClock(start=T0), connector=_connector_from([[]], []))  # type: ignore[arg-type]
    await provider.get_candles("BTC-USD", "1h", limit=5)
    assert rest.calls == 1
    await provider.close()


async def test_a_dropped_socket_reconnects_with_backoff() -> None:
    import tia.data.providers.binance_stream as module

    seen: list[str] = []
    original = module.BACKOFF
    module.BACKOFF = (0.01, 0.01)
    try:
        provider = BinanceStreamProvider(
            FakeRest(_history(5)), symbol="BTC-USD", clock=SimulatedClock(start=T0),  # type: ignore[arg-type]
            connector=_connector_from([[_ticker("1", "2")], [_ticker("1", "2")], []], seen),
        )
        provider.start()
        await asyncio.sleep(0.2)
        assert len(seen) >= 3  # two drops, three connections
        assert provider.feed_state()["reconnects"] >= 2
        assert "stream ended" in provider.feed_state()["last_error"] or provider._connected
        await provider.close()
    finally:
        module.BACKOFF = original


def test_the_stream_url_names_both_streams_for_the_venue_symbol() -> None:
    provider = BinanceStreamProvider(FakeRest([]), symbol="BTC-USD", clock=SimulatedClock(start=T0), connector=_connector_from([[]], []))  # type: ignore[arg-type]
    assert provider.url == "wss://stream.binance.com:9443/stream?streams=btcusdt@kline_1m/btcusdt@bookTicker"
