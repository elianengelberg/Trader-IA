"""The market-data service: stream, book and recorder wired into one honest state.

Owns one :class:`MarketDataStream`, one :class:`LocalOrderBook`, optionally one
:class:`TickRecorder`, and the REST client that supplies depth snapshots. Runs the
documented synchronisation: on connect, and on every gap, buffer events, fetch a
snapshot, apply it, and only then declare the book usable. It never fabricates a level,
a trade or a timestamp; every figure in :meth:`snapshot` is a count of what happened.

Integrity and freshness are two different verdicts. A book can be rebuilt exactly and still
describe a market that no longer exists: the depth batch that reached it may have been old
when the venue emitted it. So two ages are kept apart: ``receive_age`` (now minus the
local receive time of the last applied event, which detects silence) and ``venue_age``
(now minus the venue event time ``E`` of the last applied depth batch, which detects data
that was already old on arrival). Spot bookTicker carries no ``E`` and gets none invented;
its contribution is how far ahead of the book it runs. Latency is an objective of the
project, not a footnote: see docs/MARKET_MAKING_PHASE3_AUDIT.md §22.7.

This is Phase 2 of the market-making plan: infrastructure only. It quotes nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from tia.core.clock import SystemClock
from tia.core.logging import get_logger
from tia.mm.latency import LatencyStats
from tia.mm.order_book import BookState, DepthSnapshot, LocalOrderBook
from tia.mm.recorder import BookStateEvent, TickRecorder
from tia.mm.streams import MarketDataStream

_log = get_logger("mm.market_data")

SnapshotFetcher = Callable[[], Awaitable[DepthSnapshot]]

#: PROVISIONAL_THRESHOLD. One second is ten depth batches behind the venue. Chosen so that
#: the multi-second lateness seen on the VPS on 2026-09-24 cannot pass as fresh, and high
#: enough not to trip on the transit measured on 2026-09-18 (p99 120 ms). The definitive
#: value must be calibrated from the venue_age distribution measured on the server.
PROVISIONAL_MAX_VENUE_AGE_S = 1.0


class Freshness(StrEnum):
    """What the book is good for right now. Only ``FRESH`` may feed a decision."""

    FRESH = "fresh"
    STALE_RECEIVE = "stale_receive"  # nothing received for longer than the silence limit
    STALE_VENUE = "stale_venue"  # the last batch applied was already old when the venue emitted it
    SYNCING = "syncing"  # rebuilding: buffering updates, waiting for a snapshot
    GAP = "gap"  # integrity: a sequence gap or a crossed book invalidated the book
    DISCONNECTED = "disconnected"


class MarketDataService:
    """Keeps the local book in sync with the venue and the tape on disk."""

    def __init__(
        self,
        symbol: str,
        *,
        stream: MarketDataStream,
        fetch_snapshot: SnapshotFetcher,
        recorder: TickRecorder | None = None,
        resync_cooldown_s: float = 1.0,
        max_data_age_s: float = 2.0,
        max_venue_age_s: float | None = PROVISIONAL_MAX_VENUE_AGE_S,
        venue_clock_offset_ms: float = 0.0,
        checkpoint_interval_s: float = 300.0,
        now_ms: Callable[[], int] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        self.symbol = symbol
        self.stream = stream
        self.book = LocalOrderBook(symbol=symbol)
        self.recorder = recorder
        if recorder is not None and recorder._checkpoint_source is None:
            recorder._checkpoint_source = self.book_state
        self._fetch_snapshot = fetch_snapshot
        self._resync_cooldown_s = resync_cooldown_s
        self._max_data_age_s = max_data_age_s
        #: None disables the venue-age rule (report only). The default is PROVISIONAL.
        self._max_venue_age_s = max_venue_age_s
        #: Host clock minus venue clock, in ms, if it was measured; 0 means not measured,
        #: and venue_age then carries the offset. Never estimated here.
        self._venue_clock_offset_ms = venue_clock_offset_ms
        self._checkpoint_interval_s = checkpoint_interval_s
        clock = SystemClock()
        # Snapshots and checkpoints are stamped on the same clock as the events they sit
        # between, so a receive-time inversion cannot come from two clocks disagreeing.
        self._now_ms = now_ms or getattr(stream, "now_ms", None) or clock.timestamp_ms
        self._monotonic_ns = monotonic_ns or clock.monotonic_ns
        self._resync_needed = asyncio.Event()
        self._task: asyncio.Task[Any] | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self.resyncs = 0
        self.resync_failures = 0
        self.snapshots_fetched = 0
        self.last_resync_error = ""
        self.started_at_ms: int | None = None
        self.trade_events = 0
        self.last_trade: Any = None
        self.checkpoints_written = 0
        self._last_checkpoint_ms: int | None = None
        # Integrity accounting: silences longer than the freshness limit while synced,
        # and the events a validation run asked us to ignore on purpose.
        self.stale_episodes = 0
        self.max_silence_ms = 0
        self._held_until_ms: int | None = None
        self.held_events = 0
        self.processing_us = LatencyStats()
        # Freshness: the venue time of the last depth batch the book applied (None after a
        # snapshot, which carries no E, until the next batch), the ticker stream's lead over
        # the book, and the state transitions. All bounded.
        self._last_venue_event_ms: int | None = None
        self._last_trade_event_ms: int | None = None
        self._ticker_ids: deque[int] = deque(maxlen=16_384)
        self._ticker_R: deque[int] = deque(maxlen=16_384)
        self._last_ticker_id: int | None = None
        self.ticker_lead_ids = LatencyStats()  # per applied batch: last ticker id - batch u
        self.ticker_lead_ms = LatencyStats()  # per applied batch: ms since the first ticker above u arrived
        self.stale_venue_episodes = 0
        self.freshness_transitions = 0
        self._freshness_state: Freshness | None = None
        self.last_freshness_change_ms: int | None = None
        self.last_freshness_reason = ""
        # Downstream consumers (the paper market maker) receive the same kinds of events
        # a replay of the tape would: snapshot, depth, trade, book, disconnect.
        self._subscribers: list[Callable[[str, Any, int], None]] = []
        self.subscriber_errors = 0

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self.started_at_ms = self._now_ms()
        self._unsubscribe = self.stream.subscribe(self._on_event)
        self.book.begin_sync()
        self._resync_needed.set()
        self.stream.start()
        self._task = asyncio.get_running_loop().create_task(self._resync_loop(), name="mm-book-sync")

    async def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._write_checkpoint()  # the last line: what a replay must end at
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        await self.stream.close()
        if self.recorder is not None:
            self.recorder.close()

    # ------------------------------------------------------------------ consumers

    def subscribe(self, callback: Callable[[str, Any, int], None]) -> Callable[[], None]:
        """``callback(kind, event, received_at_ms)`` after this service has processed the
        event. A consumer that raises is counted and never stops the feed."""
        self._subscribers.append(callback)
        if self.book.is_valid:
            # A consumer joining a synced feed starts from the book as it stands now —
            # the same thing a replay would read from the segment's opening checkpoint.
            bids, asks = self.book.levels()
            handover = DepthSnapshot(self.book.update_id, tuple(bids), tuple(asks))
            try:
                callback("snapshot", handover, self.book.last_received_at_ms or self._now_ms())
            except Exception as exc:
                self.subscriber_errors += 1
                _log.warning("mm_consumer_failed", kind="snapshot", error=str(exc)[:160])

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return unsubscribe

    def _notify(self, kind: str, event: Any, t_ms: int) -> None:
        for callback in list(self._subscribers):
            try:
                callback(kind, event, t_ms)
            except Exception as exc:  # a broken consumer must not break the book
                self.subscriber_errors += 1
                _log.warning("mm_consumer_failed", kind=kind, error=str(exc)[:160])

    # ------------------------------------------------------------------ validation aids

    def hold(self, seconds: float, *, reason: str = "validation stall") -> None:
        """Ignore every event for ``seconds``: a deliberate stall, written to the manifest.

        The book stops receiving while the venue keeps sending, so the freshness limit
        must trip, and the first event after the hold must reveal a sequence gap. Both
        are real detections on real data; the manifest records that the fault was
        injected so the hour is never mistaken for a clean one.
        """
        self._held_until_ms = self._now_ms() + int(seconds * 1000)
        if self.recorder is not None:
            self.recorder.note_fault(f"{reason}: {seconds:.1f}s of events ignored on purpose")

    @property
    def hold_active(self) -> bool:
        return self._held_until_ms is not None and self._now_ms() < self._held_until_ms

    def book_state(self) -> BookStateEvent | None:
        """The whole book now, or None while it cannot be trusted."""
        if not self.book.is_valid:
            return None
        bids, asks = self.book.levels()
        return BookStateEvent(
            update_id=self.book.update_id,
            bids=tuple(bids),
            asks=tuple(asks),
            received_at_ms=self._now_ms(),
            digest=self.book.digest(),
        )

    def _write_checkpoint(self) -> None:
        state = self.book_state()
        if state is None or self.recorder is None:
            return
        self.recorder.record("checkpoint", state)
        self.checkpoints_written += 1
        self._last_checkpoint_ms = self._now_ms()

    # ------------------------------------------------------------------ events

    def _on_event(self, kind: str, event: Any) -> None:
        if self.hold_active:
            self.held_events += 1
            return
        started_ns = self._monotonic_ns()
        try:
            self._handle(kind, event)
        finally:
            self.processing_us.add((self._monotonic_ns() - started_ns) / 1000.0)

    def _handle(self, kind: str, event: Any) -> None:
        if kind in ("depth", "trade") and self.book.is_valid and self.book.last_received_at_ms:
            silence = event.received_at_ms - self.book.last_received_at_ms
            if silence > self.max_silence_ms:
                self.max_silence_ms = silence
            if silence > self._max_data_age_s * 1000.0:
                self.stale_episodes += 1
        if self.recorder is not None:
            if kind == "disconnect":
                self.recorder.note_disconnect()
            else:
                self.recorder.record(kind, event)
        if kind == "depth":
            was_valid = self.book.is_valid
            ok = self.book.apply_update(event)
            if ok and self.book.is_valid and self.book.update_id == event.final_update_id:
                if event.event_time_ms:
                    self._last_venue_event_ms = int(event.event_time_ms)
                self._note_ticker_lead(event.final_update_id, event.received_at_ms)
            if ok and self.book.is_valid and self.recorder is not None:
                last = self._last_checkpoint_ms
                if last is not None and self._now_ms() - last >= self._checkpoint_interval_s * 1000.0:
                    self._write_checkpoint()
            if not ok and self.book.state is BookState.OUT_OF_SYNC:
                if was_valid and self.recorder is not None:
                    self.recorder.note_book_gap()
                self.book.begin_sync()
                self.book.buffer_update(event)  # the event that revealed the gap is kept
                self._resync_needed.set()
            elif self.book.state is BookState.SYNCING:
                self._resync_needed.set()
        elif kind == "trade":
            self.trade_events += 1
            self.last_trade = event
            if getattr(event, "event_time_ms", 0):
                self._last_trade_event_ms = int(event.event_time_ms)
        elif kind == "book":
            # No venue time on Spot bookTicker; what it gives is the venue's sequence.
            if self._last_ticker_id is None or event.update_id >= self._last_ticker_id:
                self._ticker_ids.append(int(event.update_id))
                self._ticker_R.append(int(event.received_at_ms))
                self._last_ticker_id = int(event.update_id)
        elif kind == "disconnect":
            # Whatever the book held may have missed events while the socket was down.
            if self.book.state is BookState.SYNCED:
                self.book.invalidate("stream disconnected")
                self.book.begin_sync()
            self._resync_needed.set()
        self._observe_freshness()
        received = getattr(event, "received_at_ms", None) or (event.get("at_ms") if isinstance(event, dict) else None) or self._now_ms()
        self._notify(kind, event, int(received))

    async def _resync_loop(self) -> None:
        while True:
            await self._resync_needed.wait()
            self._resync_needed.clear()
            if self.book.state is BookState.SYNCED:
                continue
            if not self.stream.connected:
                await asyncio.sleep(self._resync_cooldown_s)
                self._resync_needed.set()
                continue
            await self._resync_once()
            if self.book.state is not BookState.SYNCED:
                await asyncio.sleep(self._resync_cooldown_s)
                self._resync_needed.set()

    async def _resync_once(self) -> None:
        self.resyncs += 1
        try:
            snapshot = await self._fetch_snapshot()
            self.snapshots_fetched += 1
        except Exception as exc:
            self.resync_failures += 1
            self.last_resync_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.warning("mm_snapshot_failed", error=self.last_resync_error)
            return
        if self.book.state is not BookState.SYNCING:
            self.book.begin_sync()
        received_at_ms = self._now_ms()
        if self.recorder is not None:
            # Recorded before it is applied, in arrival order: a replay meets the very
            # same snapshot at the very same point of the tape.
            self.recorder.record(
                "snapshot",
                BookStateEvent(snapshot.last_update_id, snapshot.bids, snapshot.asks, received_at_ms),
            )
        accepted = self.book.apply_snapshot(snapshot, received_at_ms=received_at_ms)
        if not accepted:
            self.last_resync_error = "snapshot older than the buffered stream; fetching again"
            return
        if self.book.state is BookState.SYNCED:
            self.last_resync_error = ""
            self._last_checkpoint_ms = received_at_ms
            # A REST snapshot carries no venue event time: unknown, not invented, until the
            # first depth batch after it. Buffered batches replayed by the book count.
            self._last_venue_event_ms = None
            self._observe_freshness()
            _log.info("mm_book_synced", update_id=self.book.update_id, levels=len(self.book._bids) + len(self.book._asks))
            self._notify("snapshot", snapshot, received_at_ms)

    # ------------------------------------------------------------------ reading

    def data_age_s(self) -> float | None:
        """Receive age: seconds since the last event the book applied arrived. Detects
        silence; says nothing about how old that event already was."""
        if not self.book.last_received_at_ms:
            return None
        return (self._now_ms() - self.book.last_received_at_ms) / 1000.0

    receive_age_s = data_age_s

    def venue_age_s(self) -> float | None:
        """Venue age: seconds between the venue event time ``E`` of the last depth batch the
        book applied and now, net of the configured clock offset. None while unknown (no
        batch since the last snapshot). Never derived from bookTicker, which has no ``E``."""
        if self._last_venue_event_ms is None:
            return None
        return (self._now_ms() - self._venue_clock_offset_ms - self._last_venue_event_ms) / 1000.0

    def trade_venue_age_s(self) -> float | None:
        if self._last_trade_event_ms is None:
            return None
        return (self._now_ms() - self._venue_clock_offset_ms - self._last_trade_event_ms) / 1000.0

    def freshness(self) -> tuple[Freshness, str]:
        """The state and its reason, judged in this order: connection, book integrity,
        receive silence, venue age. A book that just received a batch which was already
        old at the venue is STALE_VENUE, not fresh."""
        if not self.stream.connected:
            return Freshness.DISCONNECTED, "stream disconnected"
        if not self.book.is_valid:
            why = self.book.last_invalid_reason or "not synced yet"
            state = Freshness.GAP if ("gap" in why or "crossed" in why) else Freshness.SYNCING
            return state, f"book {self.book.state.value}: {why}"
        receive_age = self.data_age_s()
        if receive_age is None or receive_age > self._max_data_age_s:
            shown = f"{receive_age:.1f}" if receive_age is not None else "?"
            return Freshness.STALE_RECEIVE, f"data {shown}s old, over {self._max_data_age_s}s"
        venue_age = self.venue_age_s()
        if self._max_venue_age_s is not None and venue_age is not None and venue_age > self._max_venue_age_s:
            return (
                Freshness.STALE_VENUE,
                f"venue data {venue_age:.1f}s old at the venue, over {self._max_venue_age_s}s "
                f"(PROVISIONAL threshold); received {receive_age:.1f}s ago",
            )
        return Freshness.FRESH, ""

    @property
    def usable(self) -> bool:
        """Only a FRESH book may quote: connected, valid, recently received, and not old at
        the venue when it was emitted."""
        return self.freshness()[0] is Freshness.FRESH

    def _observe_freshness(self) -> None:
        state, reason = self.freshness()
        if state is not self._freshness_state:
            if self._freshness_state is not None:
                self.freshness_transitions += 1
            if state is Freshness.STALE_VENUE:
                self.stale_venue_episodes += 1
            self._freshness_state = state
            self.last_freshness_change_ms = self._now_ms()
        self.last_freshness_reason = reason

    def _note_ticker_lead(self, batch_u: int, received_at_ms: int) -> None:
        """How far the bookTicker stream was ahead of this batch when it arrived: in venue
        updates (last ticker id minus the batch's final id) and in local time (since the
        first ticker above the batch's id arrived). Tickers at or below the batch are
        consumed: amortised O(1) per batch."""
        if self._last_ticker_id is None:
            return
        while self._ticker_ids and self._ticker_ids[0] <= batch_u:
            self._ticker_ids.popleft()
            self._ticker_R.popleft()
        self.ticker_lead_ids.add(self._last_ticker_id - batch_u)
        self.ticker_lead_ms.add(max(0, received_at_ms - self._ticker_R[0]) if self._ticker_R else 0)

    def snapshot(self, levels: int = 10) -> dict[str, Any]:
        age = self.data_age_s()
        venue_age = self.venue_age_s()
        state, reason = self.freshness()
        return {
            "symbol": self.symbol,
            "usable": state is Freshness.FRESH,
            "not_usable_reason": reason,
            "freshness": {
                "state": state.value,
                "reason": reason,
                "receive_age_s": round(age, 3) if age is not None else None,
                "venue_age_s": round(venue_age, 3) if venue_age is not None else None,
                "venue_age_source": "depth E of the last applied batch" if venue_age is not None else None,
                "trade_venue_age_s": round(self.trade_venue_age_s(), 3) if self.trade_venue_age_s() is not None else None,
                "max_data_age_s": self._max_data_age_s,
                "max_venue_age_s": self._max_venue_age_s,
                "max_venue_age_status": "PROVISIONAL_THRESHOLD: calibrate from the measured venue_age distribution" if self._max_venue_age_s is not None else "disabled (report only)",
                "venue_clock_offset_ms": self._venue_clock_offset_ms,
                "venue_clock_offset_status": "not measured: venue_age includes the host-venue offset" if not self._venue_clock_offset_ms else "configured",
                "transitions": self.freshness_transitions,
                "last_change_ms": self.last_freshness_change_ms,
                "stale_receive_episodes": self.stale_episodes,
                "stale_venue_episodes": self.stale_venue_episodes,
            },
            "latency": {
                "depth_receive_minus_event_ms": self.stream.as_dict().get("latency_depth_ms"),
                "trade_receive_minus_event_ms": self.stream.as_dict().get("latency_trade_ms"),
                "book_ticker": "no venue event time on Spot bookTicker: not measured, not invented",
                "ticker_lead_updates_at_batch_arrival": self.ticker_lead_ids.as_dict(),
                "ticker_lead_ms_at_batch_arrival": self.ticker_lead_ms.as_dict(),
                "note": "receive minus event includes the host-venue clock offset; lead figures need no clock",
            },
            "data_age_s": round(age, 3) if age is not None else None,
            "receive_age_s": round(age, 3) if age is not None else None,
            "venue_age_s": round(venue_age, 3) if venue_age is not None else None,
            "max_data_age_s": self._max_data_age_s,
            "uptime_s": round((self._now_ms() - self.started_at_ms) / 1000.0, 1) if self.started_at_ms else 0.0,
            "book": self.book.snapshot(levels=levels),
            "stream": self.stream.as_dict(),
            "sync": {
                "resyncs": self.resyncs,
                "snapshots_fetched": self.snapshots_fetched,
                "resync_failures": self.resync_failures,
                "last_resync_error": self.last_resync_error,
                "last_snapshot_update_id": self.book.last_snapshot_update_id,
                "checkpoints_written": self.checkpoints_written,
            },
            "integrity": {
                "stale_episodes": self.stale_episodes,
                "max_silence_ms": self.max_silence_ms,
                "hold_active": self.hold_active,
                "held_events": self.held_events,
            },
            "processing_us": self.processing_us.as_dict(),
            "trades": {
                "events": self.trade_events,
                "last": (
                    {"trade_id": self.last_trade.trade_id, "price": self.last_trade.price,
                     "quantity": self.last_trade.quantity, "aggressor": self.last_trade.aggressor,
                     "trade_time_ms": self.last_trade.trade_time_ms}
                    if self.last_trade is not None
                    else None
                ),
            },
            "recorder": self.recorder.status() if self.recorder is not None else None,
            "quoting": "disabled — phase 2 is market data only",
        }


__all__ = ["PROVISIONAL_MAX_VENUE_AGE_S", "Freshness", "MarketDataService", "SnapshotFetcher"]
