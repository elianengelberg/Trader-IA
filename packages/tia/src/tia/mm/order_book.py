"""A local order book kept in step with Binance's diff-depth stream — or declared broken.

Binance's documented procedure for a spot local book (web-socket-streams.md, "How to
manage a local order book correctly"), which this class follows to the letter:

1. Open the stream and buffer every event.
2. Take a REST depth snapshot; it carries ``lastUpdateId``.
3. If ``lastUpdateId`` is strictly below the ``U`` of the first buffered event, the
   snapshot is too old: take another.
4. Discard buffered events whose ``u`` is at or below ``lastUpdateId``.
5. The first remaining event must have ``lastUpdateId`` inside ``[U, u]``.
6. The book is the snapshot; its update id is ``lastUpdateId``.
7. For every later event: ``u`` below the book's id → ignore; ``U`` above the book's
   id + 1 → events were missed, the book is discarded and the process restarts;
   otherwise apply it and set the book's id to ``u``.

An update is absolute (the level's new quantity; zero removes it). A book that has
lost its sequence, or whose best bid is not below its best ask, is **invalid** and
says so: no metric is computed from it and nothing upstream may quote on it until it
has been rebuilt from a fresh snapshot and re-verified. Every drop, gap and rebuild is
counted, because a book that is silently wrong is worse than no book.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BookState(StrEnum):
    EMPTY = "empty"  # nothing applied yet
    SYNCING = "syncing"  # buffering updates, waiting for a usable snapshot
    SYNCED = "synced"  # in step with the venue
    OUT_OF_SYNC = "out_of_sync"  # a gap or a crossed book: invalid until rebuilt


@dataclass(frozen=True)
class DepthSnapshot:
    """A REST snapshot: absolute levels plus the venue's ``lastUpdateId``."""

    last_update_id: int
    bids: tuple[tuple[float, float], ...]  # (price, quantity), best first
    asks: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class DepthUpdate:
    """One diff-depth event: ``U``..``u`` and the levels it changes."""

    first_update_id: int
    final_update_id: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    event_time_ms: int = 0
    received_at_ms: int = 0


@dataclass
class BookMetrics:
    updates_applied: int = 0
    updates_ignored_old: int = 0
    updates_buffered: int = 0
    gaps: int = 0
    rebuilds: int = 0
    snapshots_rejected_stale: int = 0
    crossed_books: int = 0
    invalidations: int = 0
    max_buffer: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class LocalOrderBook:
    """The book, its state, and the arithmetic a quote needs from it."""

    symbol: str
    max_buffer: int = 5000
    #: A level this far inside the mid, in bps, is never real: a data error, not a market.
    max_reasonable_spread_bps: float = 500.0

    state: BookState = BookState.EMPTY
    update_id: int = 0
    _bids: dict[float, float] = field(default_factory=dict)
    _asks: dict[float, float] = field(default_factory=dict)
    _buffer: deque[DepthUpdate] = field(default_factory=deque)
    metrics: BookMetrics = field(default_factory=BookMetrics)
    last_invalid_reason: str = ""
    last_event_time_ms: int = 0
    last_received_at_ms: int = 0
    first_applied_update_id: int | None = None
    last_snapshot_update_id: int | None = None

    # ------------------------------------------------------------------ validity

    @property
    def is_valid(self) -> bool:
        return self.state is BookState.SYNCED and bool(self._bids) and bool(self._asks)

    def invalidate(self, reason: str) -> None:
        """Declare the book unusable. Levels are dropped; a rebuild is required."""
        if self.state is not BookState.OUT_OF_SYNC:
            self.metrics.invalidations += 1
        self.state = BookState.OUT_OF_SYNC
        self.last_invalid_reason = reason
        self._bids.clear()
        self._asks.clear()
        self._buffer.clear()

    def begin_sync(self) -> None:
        """Start (or restart) the documented procedure: buffer until a snapshot lands."""
        self.state = BookState.SYNCING
        self._bids.clear()
        self._asks.clear()
        self._buffer.clear()
        self.update_id = 0

    # ------------------------------------------------------------------ inputs

    def buffer_update(self, update: DepthUpdate) -> None:
        """Hold an event while no snapshot has been applied yet."""
        self._buffer.append(update)
        self.metrics.updates_buffered += 1
        self.metrics.max_buffer = max(self.metrics.max_buffer, len(self._buffer))
        if len(self._buffer) > self.max_buffer:
            self._buffer.popleft()

    def apply_snapshot(self, snapshot: DepthSnapshot, *, received_at_ms: int | None = None) -> bool:
        """Adopt a snapshot and drain the buffer against it. False when it was too old.

        ``received_at_ms`` is when the REST reply arrived: it seeds the freshness clock
        so a book that just synced is not reported as stale before the first stream event.

        Too old means the first buffered event starts after the snapshot's id: the
        events between them are lost, so the caller must fetch a newer snapshot (the
        buffer is kept, the book stays SYNCING).
        """
        if self._buffer and snapshot.last_update_id < self._buffer[0].first_update_id:
            self.metrics.snapshots_rejected_stale += 1
            return False

        # Drop everything the snapshot already contains.
        while self._buffer and self._buffer[0].final_update_id <= snapshot.last_update_id:
            self._buffer.popleft()
            self.metrics.updates_ignored_old += 1

        if self._buffer:
            head = self._buffer[0]
            if not (head.first_update_id <= snapshot.last_update_id + 1 <= head.final_update_id):
                # The documented invariant failed: the first surviving event does not
                # bracket the snapshot. Refuse it; the caller fetches again.
                self.metrics.snapshots_rejected_stale += 1
                return False

        self._bids = {p: q for p, q in snapshot.bids if q > 0}
        self._asks = {p: q for p, q in snapshot.asks if q > 0}
        self.update_id = snapshot.last_update_id
        self.last_snapshot_update_id = snapshot.last_update_id
        self.state = BookState.SYNCED
        self.metrics.rebuilds += 1
        self.last_invalid_reason = ""
        if received_at_ms is not None:
            self.last_received_at_ms = received_at_ms

        pending = list(self._buffer)
        self._buffer.clear()
        for update in pending:
            if not self.apply_update(update):
                return True  # apply_update already invalidated; the caller resyncs
        return self._verify()

    def apply_update(self, update: DepthUpdate) -> bool:
        """Apply one event to a SYNCED book. False when the book became invalid.

        While SYNCING the event is buffered instead. On an EMPTY or OUT_OF_SYNC book the
        event is buffered too: it will be drained once a snapshot arrives.
        """
        if self.state is not BookState.SYNCED:
            if self.state is not BookState.SYNCING:
                self.begin_sync()
            self.buffer_update(update)
            return False

        if update.final_update_id < self.update_id:
            self.metrics.updates_ignored_old += 1
            return True
        if update.first_update_id > self.update_id + 1:
            self.metrics.gaps += 1
            self.invalidate(
                f"gap: event U={update.first_update_id} after book id {self.update_id}"
            )
            return False

        for price, quantity in update.bids:
            if quantity <= 0:
                self._bids.pop(price, None)
            else:
                self._bids[price] = quantity
        for price, quantity in update.asks:
            if quantity <= 0:
                self._asks.pop(price, None)
            else:
                self._asks[price] = quantity
        self.update_id = update.final_update_id
        if self.first_applied_update_id is None:
            self.first_applied_update_id = update.first_update_id
        self.last_event_time_ms = update.event_time_ms
        self.last_received_at_ms = update.received_at_ms
        self.metrics.updates_applied += 1
        return self._verify()

    def quantity_at(self, side: str, price: float) -> float:
        """Visible quantity at one price on one side, 0 when the level is absent."""
        levels = self._bids if side == "bid" else self._asks
        return levels.get(price, 0.0)

    # ------------------------------------------------------------------ state export

    def levels(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Every level held, bids best-first and asks best-first, for a checkpoint."""
        bids = sorted(self._bids.items(), key=lambda kv: -kv[0])
        asks = sorted(self._asks.items(), key=lambda kv: kv[0])
        return bids, asks

    def digest(self) -> str:
        """SHA-256 of the update id and every level: equal books have equal digests."""
        import hashlib
        import json

        bids, asks = self.levels()
        payload = json.dumps([self.update_id, bids, asks], separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def _verify(self) -> bool:
        """A book whose best bid is not below its best ask is not a book."""
        if not self._bids or not self._asks:
            return True  # a one-sided book is thin, not wrong
        bid, ask = max(self._bids), min(self._asks)
        if bid >= ask:
            self.metrics.crossed_books += 1
            self.invalidate(f"crossed: bid {bid} >= ask {ask}")
            return False
        mid = (bid + ask) / 2.0
        if (ask - bid) / mid * 10_000.0 > self.max_reasonable_spread_bps:
            self.invalidate(f"implausible spread {(ask - bid) / mid * 10_000.0:.0f} bps")
            return False
        return True

    # ------------------------------------------------------------------ reading

    def best_bid(self) -> tuple[float, float] | None:
        if not self.is_valid:
            return None
        price = max(self._bids)
        return price, self._bids[price]

    def best_ask(self) -> tuple[float, float] | None:
        if not self.is_valid:
            return None
        price = min(self._asks)
        return price, self._asks[price]

    def top(self, n: int) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """The best ``n`` levels per side, best first. Empty when the book is invalid."""
        if not self.is_valid:
            return [], []
        bids = sorted(self._bids.items(), key=lambda kv: -kv[0])[:n]
        asks = sorted(self._asks.items(), key=lambda kv: kv[0])[:n]
        return bids, asks

    @property
    def mid(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid[0] + ask[0]) / 2.0

    @property
    def spread(self) -> float | None:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return ask[0] - bid[0]

    @property
    def spread_bps(self) -> float | None:
        spread, mid = self.spread, self.mid
        if spread is None or not mid:
            return None
        return spread / mid * 10_000.0

    def depth(self, n: int) -> tuple[float, float]:
        """Total quantity on the best ``n`` levels, (bid, ask)."""
        bids, asks = self.top(n)
        return sum(q for _, q in bids), sum(q for _, q in asks)

    def depth_notional(self, n: int) -> tuple[float, float]:
        bids, asks = self.top(n)
        return sum(p * q for p, q in bids), sum(p * q for p, q in asks)

    def cumulative_depth(self, n: int) -> tuple[list[float], list[float]]:
        """Running quantity per level, best first, for both sides."""
        bids, asks = self.top(n)
        out_b: list[float] = []
        out_a: list[float] = []
        running = 0.0
        for _, q in bids:
            running += q
            out_b.append(running)
        running = 0.0
        for _, q in asks:
            running += q
            out_a.append(running)
        return out_b, out_a

    def imbalance(self, n: int) -> float | None:
        """(bid depth - ask depth) / (bid depth + ask depth) over ``n`` levels, in [-1, 1].

        A feature, not a signal: whether it predicts anything is measured downstream.
        """
        bid_depth, ask_depth = self.depth(n)
        total = bid_depth + ask_depth
        if not self.is_valid or total <= 0:
            return None
        return (bid_depth - ask_depth) / total

    def microprice(self, n: int = 1) -> float | None:
        """Size-weighted mid: (ask * bid_size + bid * ask_size) / (bid_size + ask_size).

        With ``n > 1`` the sizes are the depth over ``n`` levels and the prices the
        best ones — the same formula on a deeper view of the book.
        """
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        bid_size, ask_size = self.depth(n) if n > 1 else (bid[1], ask[1])
        total = bid_size + ask_size
        if total <= 0:
            return None
        return (ask[0] * bid_size + bid[0] * ask_size) / total

    def weighted_mid(self, n: int) -> float | None:
        """Quantity-weighted average price across the best ``n`` levels of both sides."""
        bids, asks = self.top(n)
        levels = bids + asks
        total = sum(q for _, q in levels)
        if not levels or total <= 0:
            return None
        return sum(p * q for p, q in levels) / total

    def price_impact(self, quantity: float, side: str) -> float | None:
        """Bps of slippage to fill ``quantity`` by walking the visible book. None if the
        visible book cannot absorb it — the honest answer, not the last level's price."""
        if not self.is_valid or quantity <= 0:
            return None
        levels = (
            sorted(self._asks.items(), key=lambda kv: kv[0])
            if side == "buy"
            else sorted(self._bids.items(), key=lambda kv: -kv[0])
        )
        remaining, cost = quantity, 0.0
        for price, size in levels:
            take = min(remaining, size)
            cost += take * price
            remaining -= take
            if remaining <= 1e-12:
                break
        if remaining > 1e-12:
            return None
        average = cost / quantity
        reference = levels[0][0]
        return abs(average - reference) / reference * 10_000.0

    def liquidity_concentration(self, n: int) -> tuple[float | None, float | None]:
        """Share of the best level in the best ``n`` levels' depth, per side. Near 1 means
        one level holds the depth and can vanish at once."""
        bids, asks = self.top(n)
        bid_total = sum(q for _, q in bids)
        ask_total = sum(q for _, q in asks)
        return (
            bids[0][1] / bid_total if bids and bid_total > 0 else None,
            asks[0][1] / ask_total if asks and ask_total > 0 else None,
        )

    def snapshot(self, levels: int = 20) -> dict[str, Any]:
        """The book as the API and the recorder see it."""
        bids, asks = self.top(levels)
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "valid": self.is_valid,
            "update_id": self.update_id,
            "first_applied_update_id": self.first_applied_update_id,
            "last_snapshot_update_id": self.last_snapshot_update_id,
            "last_invalid_reason": self.last_invalid_reason,
            "levels_bid": len(self._bids),
            "levels_ask": len(self._asks),
            "buffered": len(self._buffer),
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "mid": self.mid,
            "spread": self.spread,
            "spread_bps": round(self.spread_bps, 4) if self.spread_bps is not None else None,
            "microprice_1": self.microprice(1),
            "microprice_5": self.microprice(5),
            "imbalance": {str(n): self.imbalance(n) for n in (1, 5, 10, 20)},
            "depth": {str(n): self.depth(n) for n in (1, 5, 10, 20)},
            "weighted_mid_5": self.weighted_mid(5),
            "concentration_10": self.liquidity_concentration(10),
            "bids": bids,
            "asks": asks,
            "metrics": self.metrics.as_dict(),
            "last_event_time_ms": self.last_event_time_ms,
            "last_received_at_ms": self.last_received_at_ms,
        }


def snapshot_from_levels(
    last_update_id: int,
    bids: Sequence[tuple[float, float]] | Sequence[Sequence[float]],
    asks: Sequence[tuple[float, float]] | Sequence[Sequence[float]],
) -> DepthSnapshot:
    return DepthSnapshot(
        last_update_id=int(last_update_id),
        bids=tuple((float(p), float(q)) for p, q in bids),
        asks=tuple((float(p), float(q)) for p, q in asks),
    )


__all__ = [
    "BookMetrics",
    "BookState",
    "DepthSnapshot",
    "DepthUpdate",
    "LocalOrderBook",
    "snapshot_from_levels",
]
