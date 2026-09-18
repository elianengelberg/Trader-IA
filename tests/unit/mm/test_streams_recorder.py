"""The tick stream parses the documented frames with two clocks, counts what it cannot
deliver, and reconnects; the recorder writes honest, bounded, checksummed segments."""

from __future__ import annotations

import asyncio
import gzip
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tia.mm.recorder import MANIFEST_SUFFIX, TickRecorder
from tia.mm.streams import (
    MarketDataStream,
    parse_book_ticker,
    parse_depth_update,
    parse_trade,
)

DEPTH = {"stream": "btcusdt@depth@100ms", "data": {"e": "depthUpdate", "E": 1_000_000, "s": "BTCUSDT", "U": 10, "u": 12, "b": [["100.0", "2.0"], ["99.0", "0"]], "a": [["101.0", "1.5"]]}}
TRADE = {"stream": "btcusdt@trade", "data": {"e": "trade", "E": 1_000_050, "s": "BTCUSDT", "t": 77, "p": "100.5", "q": "0.25", "T": 1_000_040, "m": True, "M": True}}
BOOK = {"stream": "btcusdt@bookTicker", "data": {"u": 13, "s": "BTCUSDT", "b": "100.0", "B": "2.0", "a": "101.0", "A": "1.5"}}


def test_the_documented_frames_parse_with_both_clocks() -> None:
    d = parse_depth_update(DEPTH["data"], received_at_ms=1_000_210)
    assert (d.first_update_id, d.final_update_id) == (10, 12)
    assert d.bids == ((100.0, 2.0), (99.0, 0.0)) and d.asks == ((101.0, 1.5),)
    assert d.event_time_ms == 1_000_000 and d.received_at_ms == 1_000_210
    t = parse_trade(TRADE["data"], received_at_ms=1_000_260)
    assert t.trade_id == 77 and t.price == 100.5 and t.quantity == 0.25
    assert t.buyer_is_maker is True and t.aggressor == "sell"
    assert t.trade_time_ms == 1_000_040 and t.event_time_ms == 1_000_050
    b = parse_book_ticker(BOOK["data"], received_at_ms=5)
    assert b.update_id == 13 and b.bid == 100.0 and b.ask_size == 1.5


def test_the_stream_dispatches_in_order_measures_latency_and_counts_failures() -> None:
    clock = {"ms": 1_000_210}
    stream = MarketDataStream("BTC-USD", now_ms=lambda: clock["ms"], connector=lambda url: None)  # type: ignore[arg-type,return-value]
    seen: list[tuple[str, object]] = []
    stream.subscribe(lambda kind, event: seen.append((kind, event)))

    def broken(kind, event):  # type: ignore[no-untyped-def]
        raise RuntimeError("slow consumer")

    stream.subscribe(broken)
    stream.on_message(json.dumps(DEPTH))
    clock["ms"] = 1_000_260
    stream.on_message(json.dumps(TRADE))
    stream.on_message(json.dumps(BOOK))
    stream.on_message("not json")
    stream.on_message(json.dumps({"stream": "x", "data": {"e": "kline"}}))

    assert [k for k, _ in seen] == ["depth", "trade", "book"]
    status = stream.status()
    assert status.depth_events == 1 and status.trade_events == 1 and status.book_ticker_events == 1
    assert status.parse_errors == 2
    assert status.dropped_events == 3  # the broken subscriber, once per event
    assert stream.latency_depth.as_dict()["last_ms"] == 210.0
    assert stream.latency_trade.as_dict()["last_ms"] == 210.0
    assert stream.latency_trade_to_event.as_dict()["last_ms"] == 10.0
    assert stream.last_book_ticker is not None and stream.recent_trades[-1].trade_id == 77
    assert "btcusdt@depth@100ms/btcusdt@trade/btcusdt@bookTicker" in stream.url


async def test_a_dropped_socket_reconnects_and_tells_subscribers() -> None:
    import tia.mm.streams as module

    original = module.BACKOFF
    module.BACKOFF = (0.01,)
    attempts: list[str] = []

    @asynccontextmanager
    async def connect(url: str):  # type: ignore[no-untyped-def]
        attempts.append(url)

        async def frames():  # type: ignore[no-untyped-def]
            yield json.dumps(BOOK)
            if len(attempts) >= 3:
                await asyncio.sleep(3600)

        yield frames()

    try:
        stream = MarketDataStream("BTC-USD", connector=connect)
        events: list[str] = []
        stream.subscribe(lambda kind, event: events.append(kind))
        stream.start()
        await asyncio.sleep(0.15)
        assert len(attempts) >= 3
        assert stream.status().reconnects >= 2
        assert events.count("disconnect") >= 2 and events.count("book") >= 3
        await stream.close()
    finally:
        module.BACKOFF = original


def _events(n: int, start_id: int = 1):  # type: ignore[no-untyped-def]
    from tia.mm.order_book import DepthUpdate

    return [
        DepthUpdate(first_update_id=start_id + i, final_update_id=start_id + i, bids=((100.0, 1.0),), asks=(), event_time_ms=1_000 + i, received_at_ms=1_700_000_000_000 + i)
        for i in range(n)
    ]


def test_the_recorder_writes_batches_manifests_and_checksums(tmp_path: Path) -> None:
    clock = {"ms": 1_700_000_000_000}
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=3, flush_interval_s=3600, now_ms=lambda: clock["ms"])
    for event in _events(5):
        recorder.record("depth", event)
    status = recorder.status()
    assert status["events_written"] == 3 and status["buffered_lines"] == 2  # one batch flushed
    recorder.close()
    status = recorder.status()
    # Events alone are not a rebuildable hour: no snapshot, no checkpoint, not replayable.
    assert status["events_written"] == 5 and status["segments"] == 1 and status["segments_replayable"] == 0
    segment = recorder.segments()[0]
    manifest = json.loads(Path(segment["path"] + MANIFEST_SUFFIX).read_text())
    assert manifest["lines"] == 5 and manifest["depth_events"] == 5
    assert manifest["first_depth_update_id"] == 1 and manifest["last_depth_update_id"] == 5
    assert manifest["replayable"] is False and len(manifest["sha256"]) == 64
    assert "no initial book state" in manifest["not_replayable_reasons"][0]
    assert segment["sealed"] is True and manifest["format"] == 2
    with gzip.open(segment["path"], "rt") as fh:
        rows = [json.loads(line) for line in fh]
    assert [r["u"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0]["k"] == "depth" and rows[0]["R"] == 1_700_000_000_000 and rows[0]["E"] == 1_000
    assert TickRecorder.verify(segment["path"])["ok"] is True


def test_a_gap_or_disconnect_marks_the_hour_not_replayable(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: 1_700_000_000_000)
    recorder.record("depth", _events(1)[0])
    recorder.note_book_gap()
    recorder.note_disconnect()
    recorder.close()
    manifest = recorder.segments()[0]["manifest"]
    assert manifest["replayable"] is False
    assert manifest["book_gaps"] == 1 and manifest["disconnects"] == 1
    assert {"order book reported a sequence gap", "stream disconnected during the hour"} <= set(manifest["not_replayable_reasons"])


def test_a_full_buffer_drops_and_counts_instead_of_blocking(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=10_000, flush_interval_s=3600, max_buffer_lines=3, now_ms=lambda: 1_700_000_000_000)
    for event in _events(5):
        recorder.record("depth", event)
    assert recorder.status()["events_dropped"] == 2
    recorder.close()
    assert recorder.segments()[0]["manifest"]["replayable"] is False


def test_corruption_is_detected(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: 1_700_000_000_000)
    for event in _events(3):
        recorder.record("depth", event)
    recorder.close()
    path = Path(recorder.segments()[0]["path"])
    path.write_bytes(path.read_bytes()[:-5] + b"xxxxx")  # damage the tail
    result = TickRecorder.verify(path)
    assert result["ok"] is False
    assert recorder.segments()[0]["manifest"]["corrupt"] is True
    assert recorder.segments()[0]["replayable"] is False


def test_retention_and_the_disk_ceiling_evict_the_oldest_hour(tmp_path: Path) -> None:
    hour_ms = 3_600_000
    base = 1_700_000_000_000
    clock = {"ms": base}
    recorder = TickRecorder(tmp_path, "BTC-USD", retention_days=365, max_total_bytes=1, now_ms=lambda: clock["ms"])
    for hour in range(3):
        clock["ms"] = base + hour * hour_ms
        for event in _events(2, start_id=hour * 10 + 1):
            recorder.record("depth", type(event)(event.first_update_id, event.final_update_id, event.bids, event.asks, event.event_time_ms, clock["ms"]))
    recorder.close()
    # A one-byte ceiling: every rolled hour evicts what came before it.
    assert recorder.status()["segments_evicted"] >= 1
    assert len(recorder.segments()) <= 2


@pytest.mark.parametrize("kind", ["trade", "book"])
def test_every_event_kind_is_encoded_with_its_ids(tmp_path: Path, kind: str) -> None:
    from tia.mm.streams import BookTickerEvent, TradeEvent

    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: 1_700_000_000_000)
    event = (
        TradeEvent(trade_id=9, price=100.0, quantity=1.0, buyer_is_maker=False, trade_time_ms=1, event_time_ms=2, received_at_ms=1_700_000_000_000)
        if kind == "trade"
        else BookTickerEvent(update_id=4, bid=100.0, bid_size=1.0, ask=101.0, ask_size=2.0, received_at_ms=1_700_000_000_000)
    )
    recorder.record(kind, event)
    recorder.close()
    with gzip.open(recorder.segments()[0]["path"], "rt") as fh:
        row = json.loads(fh.readline())
    assert row["k"] == kind
    assert row.get("t") == 9 if kind == "trade" else row.get("u") == 4


def test_a_disconnect_before_the_first_tick_still_marks_the_hour(tmp_path: Path) -> None:
    """An integrity event with no tick yet must open the hour and flag it, not vanish."""
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: 1_700_000_000_000)
    recorder.note_disconnect()
    recorder.note_book_gap()
    status = recorder.status()
    assert status["current_manifest"]["disconnects"] == 1
    assert status["current_manifest"]["book_gaps"] == 1
    assert status["current_manifest"]["replayable"] is False
    recorder.close()
    manifest = recorder.segments()[0]["manifest"]
    assert manifest["disconnects"] == 1 and manifest["replayable"] is False


def test_receive_stamps_never_go_backwards_even_when_the_wall_clock_steps() -> None:
    """The receive clock is wall time anchored once to the monotonic clock: an NTP step
    changes the wall clock, not the order of what already arrived."""
    from datetime import UTC, datetime, timedelta

    from tia.core.clock import Clock
    from tia.mm.streams import ReceiveClock

    class SteppingClock(Clock):
        def __init__(self) -> None:
            self.wall = datetime(2026, 9, 18, 22, 0, 0, tzinfo=UTC)
            self.mono = 1_000_000_000

        def now(self) -> datetime:
            return self.wall

        def monotonic_ns(self) -> int:
            return self.mono

    fake = SteppingClock()
    clock = ReceiveClock(fake)
    first = clock.now_ms()
    fake.mono += 5_000_000  # 5 ms pass
    fake.wall -= timedelta(seconds=2)  # the wall clock is stepped back two seconds
    second = clock.now_ms()
    assert second == first + 5  # the stamp followed the monotonic clock, not the step
    fake.mono += 1_000_000
    assert clock.now_ms() == first + 6
