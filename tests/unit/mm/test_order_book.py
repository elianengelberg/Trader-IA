"""The local book follows Binance's documented sync procedure and refuses to be wrong:
a gap, a crossed book or a stale snapshot is declared, never papered over."""

from __future__ import annotations

import pytest

from tia.mm.latency import LatencyStats
from tia.mm.order_book import BookState, DepthUpdate, LocalOrderBook, snapshot_from_levels


def _update(U: int, u: int, bids=(), asks=()) -> DepthUpdate:  # type: ignore[no-untyped-def]
    return DepthUpdate(first_update_id=U, final_update_id=u, bids=tuple(bids), asks=tuple(asks), event_time_ms=1000 + u, received_at_ms=1200 + u)


def _synced_book() -> LocalOrderBook:
    book = LocalOrderBook(symbol="BTC-USD")
    book.begin_sync()
    assert book.apply_snapshot(snapshot_from_levels(100, [(100.0, 2.0), (99.0, 3.0), (98.0, 5.0)], [(101.0, 1.0), (102.0, 4.0), (103.0, 6.0)]))
    return book


def test_the_documented_sync_procedure_drops_old_events_and_brackets_the_snapshot() -> None:
    book = LocalOrderBook(symbol="BTC-USD")
    book.begin_sync()
    # Events buffered before the snapshot arrived.
    book.apply_update(_update(90, 95, bids=[(99.5, 1.0)]))   # entirely before the snapshot: dropped
    book.apply_update(_update(96, 101, bids=[(99.5, 2.0)]))  # brackets lastUpdateId+1 = 101: applied
    book.apply_update(_update(102, 104, asks=[(101.5, 0.5)]))
    assert book.state is BookState.SYNCING
    assert book.metrics.updates_buffered == 3

    assert book.apply_snapshot(snapshot_from_levels(100, [(100.0, 2.0)], [(101.0, 1.0)])) is True
    assert book.state is BookState.SYNCED
    assert book.update_id == 104
    assert book.metrics.updates_ignored_old == 1
    assert book.metrics.updates_applied == 2
    assert book.best_bid() == (100.0, 2.0)
    assert dict(book.top(5)[0])[99.5] == 2.0  # the second event's level, not the dropped one
    assert dict(book.top(5)[1])[101.5] == 0.5


def test_a_snapshot_older_than_the_first_buffered_event_is_refused() -> None:
    book = LocalOrderBook(symbol="BTC-USD")
    book.begin_sync()
    book.apply_update(_update(150, 155))
    assert book.apply_snapshot(snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)])) is False
    assert book.state is BookState.SYNCING
    assert book.metrics.snapshots_rejected_stale == 1
    # A newer snapshot that the buffered event brackets is accepted.
    assert book.apply_snapshot(snapshot_from_levels(152, [(100.0, 1.0)], [(101.0, 1.0)])) is True
    assert book.update_id == 155


def test_a_gap_invalidates_the_book_and_counts() -> None:
    book = _synced_book()
    assert book.apply_update(_update(101, 103, bids=[(100.0, 2.5)])) is True
    assert book.apply_update(_update(106, 108)) is False  # 104 and 105 were never seen
    assert book.state is BookState.OUT_OF_SYNC
    assert book.is_valid is False
    assert book.metrics.gaps == 1
    assert "gap" in book.last_invalid_reason
    assert book.best_bid() is None and book.mid is None
    # Later events are buffered for the rebuild, not applied to a dead book.
    book.apply_update(_update(109, 110))
    assert book.state is BookState.SYNCING and book.metrics.updates_buffered == 1


def test_overlapping_and_old_events_are_handled_as_documented() -> None:
    book = _synced_book()
    assert book.apply_update(_update(99, 102, bids=[(100.0, 9.0)])) is True  # overlaps: applied
    assert book.update_id == 102
    assert book.apply_update(_update(95, 101)) is True  # u below the book id: ignored
    assert book.metrics.updates_ignored_old == 1
    assert book.best_bid() == (100.0, 9.0)


def test_zero_quantity_removes_a_level_and_a_crossed_book_is_invalid() -> None:
    book = _synced_book()
    assert book.apply_update(_update(101, 101, asks=[(101.0, 0.0)])) is True
    assert book.best_ask() == (102.0, 4.0)
    assert book.apply_update(_update(102, 102, bids=[(102.5, 1.0)])) is False  # bid above ask
    assert book.state is BookState.OUT_OF_SYNC
    assert book.metrics.crossed_books == 1


def test_the_arithmetic_a_quote_needs() -> None:
    book = _synced_book()
    assert book.mid == pytest.approx(100.5)
    assert book.spread == pytest.approx(1.0)
    assert book.spread_bps == pytest.approx(1.0 / 100.5 * 10_000)
    # microprice = (ask*bid_size + bid*ask_size) / (bid_size + ask_size)
    assert book.microprice(1) == pytest.approx((101.0 * 2.0 + 100.0 * 1.0) / 3.0)
    assert book.depth(2) == (5.0, 5.0)
    assert book.imbalance(1) == pytest.approx((2.0 - 1.0) / 3.0)
    assert book.imbalance(3) == pytest.approx((10.0 - 11.0) / 21.0)
    assert book.cumulative_depth(3) == ([2.0, 5.0, 10.0], [1.0, 5.0, 11.0])
    assert book.weighted_mid(1) == pytest.approx((100.0 * 2.0 + 101.0 * 1.0) / 3.0)
    # Buying 3 walks 1 @101 and 2 @102: average 101.667 vs the touch 101.
    assert book.price_impact(3.0, "buy") == pytest.approx((101.6667 - 101.0) / 101.0 * 10_000, rel=1e-3)
    assert book.price_impact(100.0, "buy") is None  # the visible book cannot absorb it
    bid_conc, ask_conc = book.liquidity_concentration(3)
    assert bid_conc == pytest.approx(2.0 / 10.0) and ask_conc == pytest.approx(1.0 / 11.0)
    snapshot = book.snapshot(levels=2)
    assert snapshot["valid"] is True and len(snapshot["bids"]) == 2
    assert snapshot["imbalance"]["1"] == pytest.approx(1.0 / 3.0)


def test_an_invalid_book_yields_no_numbers() -> None:
    book = LocalOrderBook(symbol="BTC-USD")
    assert book.is_valid is False
    assert book.microprice() is None and book.imbalance(5) is None and book.spread_bps is None
    assert book.top(5) == ([], [])


def test_the_buffer_is_bounded() -> None:
    book = LocalOrderBook(symbol="BTC-USD", max_buffer=3)
    book.begin_sync()
    for i in range(10):
        book.buffer_update(_update(i, i))
    assert book.metrics.max_buffer == 4  # the moment before the oldest is dropped
    assert len(book._buffer) == 3


def test_latency_percentiles_come_from_the_window() -> None:
    stats = LatencyStats(window=100)
    for value in range(1, 101):
        stats.add(float(value))
    d = stats.as_dict()
    assert d["count"] == 100 and d["p50_ms"] == 50.0 and d["p95_ms"] == 95.0 and d["p99_ms"] == 99.0
    assert d["min_ms"] == 1.0 and d["max_ms"] == 100.0
    assert LatencyStats().as_dict()["p50_ms"] is None
