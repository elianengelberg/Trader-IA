"""Comparing the local book with the venue's own bookTicker, without pretending they are
one stream.

``depth@100ms`` is batched every 100 ms; ``bookTicker`` is sent on every top-of-book
change. Sampled at the same instant they are at different points in time, so a difference
at one instant, however large, says nothing by itself. What both streams share is the
venue's order book ``updateId``: a depth batch ends at ``u``, and a bookTicker carries the
``u`` of the change it reports. That id is the causal clock, and the comparison here is
made on it, not on receive time.

**Causal rule.** The venue's top of book at id ``L`` is the last bookTicker whose id is at
or below ``L`` (bookTicker is emitted on every change of the best bid or ask, so no change
can hide between that ticker and ``L``). It is known to be the last one once a bookTicker
with an id above ``L`` has arrived. So each local state, the top of the local book after
applying the batch that ends at ``L``, is compared with that ticker, and only then. A
ticker that runs ahead of the book, or a book that runs ahead of the tickers, is a
``timing_disagreement`` at the instant it is seen: described, measured, never judged.

**Verdicts.** Three, kept apart: ``timing_disagreement`` (explained by the streams'
ordering and resolved once the book reaches the ticker's id), ``true_inconsistency`` (a
local state that differs from the venue's top at the same id, after the causal window has
closed; ``persistent`` when several consecutive states disagree), and
``impossible_state`` (a local ask at or below the local bid, a venue top that is crossed,
a bookTicker sequence that goes backwards). Everything else is a count.

**What is not available, and is not invented.** Spot bookTicker carries no event time, so
exchange-side timing of the ticker cannot be measured; the catch-up figures below are in
local receive time, which is what the pairing needs. The comparison assumes the two
streams share the ``updateId`` space and that the bookTicker stream is complete between
two received tickers; a systematic disagreement rate would expose either assumption.

The instant sampling of the first phase (``TopOfBookSample`` / ``summarise``) is kept as a
description of what an observer sees at one instant; it decides nothing.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Consecutive samples (each seconds apart) a disagreement must survive to be called
#: persistent in the instant sampling. Three samples at 5 s spacing is 15 s: two orders of
#: magnitude past the 100 ms batching of the depth stream.
PERSISTENT_SAMPLES = 3

#: Consecutive causally resolved local states that must disagree with the venue's top at
#: their own id for the disagreement to be called persistent. One resolved disagreement is
#: reported and kept as an example; three in a row cannot be a lost ticker.
PERSISTENT_STATES = 3

NOT_MEASURED = "NOT MEASURED"


@dataclass(frozen=True)
class TopOfBookSample:
    t: float
    local_bid: float
    local_ask: float
    local_update_id: int
    venue_bid: float
    venue_ask: float
    venue_update_id: int
    tick_size: float

    @property
    def bid_diff_ticks(self) -> int:
        return round((self.local_bid - self.venue_bid) / self.tick_size)

    @property
    def ask_diff_ticks(self) -> int:
        return round((self.local_ask - self.venue_ask) / self.tick_size)

    @property
    def max_abs_diff_ticks(self) -> int:
        return max(abs(self.bid_diff_ticks), abs(self.ask_diff_ticks))

    @property
    def exact(self) -> bool:
        return self.bid_diff_ticks == 0 and self.ask_diff_ticks == 0

    @property
    def within_1_tick(self) -> bool:
        return self.max_abs_diff_ticks <= 1

    @property
    def local_spread_negative(self) -> bool:
        """Impossible in any timing: the local book itself is crossed."""
        return self.local_ask <= self.local_bid

    @property
    def crossed_vs_venue(self) -> bool:
        """Local top inside the venue's top at this instant. Timing unless persistent."""
        return self.local_bid > self.venue_ask or self.local_ask < self.venue_bid

    @property
    def venue_ahead(self) -> bool:
        """The ticker carries a later sequence id than the book: the book has not yet
        received that batch, so any difference is explained by the stream's timing."""
        return self.venue_update_id > self.local_update_id

    @property
    def id_lag(self) -> int:
        return self.local_update_id - self.venue_update_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "local_bid": self.local_bid,
            "local_ask": self.local_ask,
            "venue_bid": self.venue_bid,
            "venue_ask": self.venue_ask,
            "bid_diff_ticks": self.bid_diff_ticks,
            "ask_diff_ticks": self.ask_diff_ticks,
            "exact": self.exact,
            "within_1_tick": self.within_1_tick,
            "crossed_vs_venue": self.crossed_vs_venue,
            "venue_ahead": self.venue_ahead,
            "id_lag": self.id_lag,
            "local_spread_negative": self.local_spread_negative,
            "explanation": self.explanation,
        }

    @property
    def explanation(self) -> str:
        if self.local_spread_negative:
            return "IMPOSSIBLE: local ask <= local bid"
        if self.exact:
            return "exact match"
        if self.venue_ahead:
            return "timing: bookTicker is ahead of the depth batch the book has applied"
        if self.crossed_vs_venue:
            return "timing at one instant: local top inside the venue's top; inconsistency only if it persists"
        return "timing between two streams (ticks of difference)"


def summarise(samples: list[TopOfBookSample], *, persistent_samples: int = PERSISTENT_SAMPLES) -> dict[str, Any]:
    """What instant samples say. Descriptive since the causal matcher exists; the two
    verdict keys are kept for the tests and reports that read them."""
    consecutive = 0
    max_consecutive = 0
    consecutive_crossed = 0
    max_consecutive_crossed = 0
    for sample in samples:
        consecutive = 0 if sample.within_1_tick else consecutive + 1
        max_consecutive = max(max_consecutive, consecutive)
        consecutive_crossed = consecutive_crossed + 1 if sample.crossed_vs_venue else 0
        max_consecutive_crossed = max(max_consecutive_crossed, consecutive_crossed)
    worst = sorted(samples, key=lambda x: -x.max_abs_diff_ticks)[:5]
    return {
        "samples": len(samples),
        "exact": sum(1 for x in samples if x.exact),
        "within_1_tick": sum(1 for x in samples if x.within_1_tick),
        "beyond_1_tick": sum(1 for x in samples if not x.within_1_tick),
        "venue_ahead_samples": sum(1 for x in samples if x.venue_ahead),
        "crossed_vs_venue_instants": sum(1 for x in samples if x.crossed_vs_venue),
        "max_consecutive_crossed_vs_venue": max_consecutive_crossed,
        "local_spread_negative": sum(1 for x in samples if x.local_spread_negative),
        "max_abs_diff_ticks": max((x.max_abs_diff_ticks for x in samples), default=None),
        "max_consecutive_disagreements": max_consecutive,
        "persistent_samples_threshold": persistent_samples,
        "persistent_inconsistency": max_consecutive >= persistent_samples,
        "impossible_state": any(x.local_spread_negative for x in samples),
        "worst_samples": [x.as_dict() for x in worst],
        "rule": (
            "instant sampling of two separate streams: descriptive only. The verdict on "
            "consistency comes from the causal comparison on the venue's updateId "
            "(CausalTopOfBookMatcher)."
        ),
    }


# --------------------------------------------------------------------------- causal


@dataclass(frozen=True)
class VenueTop:
    """One bookTicker: the venue's best bid/ask after the change at ``update_id``."""

    update_id: int
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    received_at_ms: int


@dataclass(frozen=True)
class LocalTop:
    """The local book's best bid/ask after applying the batch that ends at ``update_id``."""

    update_id: int
    bid: float
    bid_size: float
    ask: float
    ask_size: float
    received_at_ms: int


def _percentiles(values: list[int] | list[float]) -> dict[str, Any]:
    """Nearest-rank p50/p95/p99 with min, max and count; NOT MEASURED when empty."""
    if not values:
        return {"count": 0, "p50": NOT_MEASURED, "p95": NOT_MEASURED, "p99": NOT_MEASURED, "min": NOT_MEASURED, "max": NOT_MEASURED}
    ordered = sorted(values)

    def rank(pct: float) -> Any:
        idx = max(0, min(len(ordered) - 1, math.ceil(pct / 100.0 * len(ordered)) - 1))
        return ordered[idx]

    return {
        "count": len(ordered),
        "p50": rank(50),
        "p95": rank(95),
        "p99": rank(99),
        "min": ordered[0],
        "max": ordered[-1],
    }


class CausalTopOfBookMatcher:
    """Pairs local book states with the venue's bookTicker on the order book ``updateId``.

    Feed it every bookTicker (:meth:`on_ticker`) and every local state after a depth
    batch or a snapshot is applied (:meth:`on_local_state`), in arrival order. It keeps
    the ledgers bounded and reports through :meth:`summary`.

    Two ledgers, kept apart on purpose:

    * the **instant** ledger, per ticker: what an observer sees the moment the ticker
      arrives, against whatever the local book holds then. Differences here are
      ``timing_disagreement`` whenever the two ids differ; they are measured (how far
      ahead, how long until the book catches up) and never judged;
    * the **causal** ledger, per local state: the top of the local book at id ``L``
      against the venue's last top-of-book change at or before ``L``, resolved once a
      ticker above ``L`` proves nothing else fits in between. A difference here is a
      ``true_inconsistency``; several consecutive ones are ``persistent``.
    """

    def __init__(
        self,
        *,
        tick_size: float,
        persistent_states: int = PERSISTENT_STATES,
        max_pending: int = 20_000,
        max_examples: int = 10,
        max_lag_samples: int = 500_000,
    ) -> None:
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        self.tick_size = tick_size
        self.persistent_states = persistent_states
        self._max_pending = max_pending
        self._max_examples = max_examples
        self._max_lag_samples = max_lag_samples

        self._tickers: deque[VenueTop] = deque()  # ascending ids, arrival order
        self._pending_states: deque[LocalTop] = deque()  # ids >= last ticker id
        self._pending_tickers: deque[tuple[VenueTop, int, dict[str, Any] | None]] = deque()
        self._last_local: LocalTop | None = None
        self._last_ticker_id: int | None = None

        # instant ledger
        self.tickers = 0
        self.ticker_duplicates = 0
        self.ticker_sequence_regressions = 0
        self.venue_crossed = 0
        self.instant_comparisons = 0
        self.instant_disagreements = 0
        self.timing_disagreements = 0
        self.same_id_disagreements = 0
        self.venue_ahead_samples = 0
        self.local_ahead_samples = 0
        self.same_id_samples = 0
        self._id_lag_all: list[int] = []
        self._id_lag_ahead: list[int] = []
        self._catch_up_ms: list[int] = []
        self._catch_up_updates: list[int] = []
        self.tickers_dropped_before_catch_up = 0

        # causal ledger
        self.local_states = 0
        self.local_spread_negative = 0
        self.resolved = 0
        self.resolved_consistent = 0
        self.resolved_exact = 0
        self.resolved_size_mismatch = 0
        self.true_inconsistencies = 0
        self.unresolvable_no_ticker = 0
        self.unresolved_dropped = 0
        self.discontinuities = 0
        self._current_run = 0
        self._runs: list[int] = []

        self.examples: dict[str, list[dict[str, Any]]] = {
            "timing_disagreement": [],
            "true_inconsistency": [],
            "impossible_state": [],
        }

    # ------------------------------------------------------------------ inputs

    def note_discontinuity(self, reason: str) -> None:
        """The ticker stream can no longer be assumed complete (a disconnect): pending
        pairings are dropped and counted, never resolved against a possibly stale ticker."""
        self.discontinuities += 1
        self.last_discontinuity_reason = reason
        self.unresolved_dropped += len(self._pending_states)
        self.tickers_dropped_before_catch_up += len(self._pending_tickers)
        self._pending_states.clear()
        self._pending_tickers.clear()
        self._tickers.clear()
        self._last_ticker_id = None
        self._end_run()

    def on_ticker(self, ticker: VenueTop) -> None:
        self.tickers += 1
        if ticker.bid >= ticker.ask:
            self.venue_crossed += 1
            self._impossible("venue bookTicker is crossed: bid >= ask", ticker=ticker)
            return
        if self._last_ticker_id is not None:
            if ticker.update_id < self._last_ticker_id:
                self.ticker_sequence_regressions += 1
                self._impossible(
                    f"bookTicker updateId went backwards: {self._last_ticker_id} -> {ticker.update_id}",
                    ticker=ticker,
                )
                return
            if ticker.update_id == self._last_ticker_id:
                self.ticker_duplicates += 1
                self._tickers.pop()  # the later report of the same id is the one kept
        self._tickers.append(ticker)
        self._last_ticker_id = ticker.update_id
        self._prune_tickers()

        local = self._last_local
        if local is not None:
            self._instant(ticker, local)

        # Every pending local state below this id is now causally comparable.
        self._drain(limit_id=ticker.update_id, at_ms=ticker.received_at_ms)

    def on_local_state(self, state: LocalTop) -> None:
        self.local_states += 1
        if state.ask <= state.bid:
            self.local_spread_negative += 1
            self._impossible("local ask <= local bid", state=state)
            return
        self._last_local = state
        self._catch_up(state)
        if len(self._pending_states) >= self._max_pending:
            self._pending_states.popleft()
            self.unresolved_dropped += 1
        self._pending_states.append(state)
        if self._last_ticker_id is not None:
            self._drain(limit_id=self._last_ticker_id, at_ms=state.received_at_ms)

    # ------------------------------------------------------------------ instant ledger

    def _instant(self, ticker: VenueTop, local: LocalTop) -> None:
        self.instant_comparisons += 1
        lag = ticker.update_id - local.update_id
        self._sample(self._id_lag_all, lag)
        bid_ticks = self._ticks(local.bid - ticker.bid)
        ask_ticks = self._ticks(local.ask - ticker.ask)
        match = bid_ticks == 0 and ask_ticks == 0
        example: dict[str, Any] | None = None
        if lag > 0:
            self.venue_ahead_samples += 1
            self._sample(self._id_lag_ahead, lag)
        elif lag < 0:
            self.local_ahead_samples += 1
        else:
            self.same_id_samples += 1
        if not match:
            self.instant_disagreements += 1
            if lag == 0:
                # Same id, different top: nothing about ordering explains it. The causal
                # ledger records it as a true inconsistency of this very state.
                self.same_id_disagreements += 1
            else:
                self.timing_disagreements += 1
                reason = (
                    f"bookTicker updateId is {lag} ahead of the local book"
                    if lag > 0
                    else f"local book is {-lag} updates ahead of this bookTicker"
                )
                example = self._example_row(local, ticker, at_ms=ticker.received_at_ms, classification="timing_disagreement", reason=reason)
                self._keep_worst(self.examples["timing_disagreement"], example, key="max_abs_diff_ticks")
        if lag > 0:
            if len(self._pending_tickers) >= self._max_pending:
                self._pending_tickers.popleft()
                self.tickers_dropped_before_catch_up += 1
            self._pending_tickers.append((ticker, local.update_id, example))

    def _catch_up(self, state: LocalTop) -> None:
        while self._pending_tickers and self._pending_tickers[0][0].update_id <= state.update_id:
            ticker, local_id_at_arrival, example = self._pending_tickers.popleft()
            waited_ms = state.received_at_ms - ticker.received_at_ms
            self._sample(self._catch_up_ms, waited_ms)
            self._sample(self._catch_up_updates, state.update_id - local_id_at_arrival)
            if example is not None:
                example["caught_up_after_ms"] = waited_ms
                example["caught_up_at_local_update_id"] = state.update_id

    # ------------------------------------------------------------------ causal ledger

    def _drain(self, *, limit_id: int, at_ms: int) -> None:
        while self._pending_states and self._pending_states[0].update_id < limit_id:
            state = self._pending_states.popleft()
            self._resolve(state, proof_id=limit_id, at_ms=at_ms)
        self._prune_tickers()

    def _reference_for(self, update_id: int) -> VenueTop | None:
        reference: VenueTop | None = None
        for ticker in self._tickers:  # ascending; the deque is pruned, so this stays short
            if ticker.update_id > update_id:
                break
            reference = ticker
        return reference

    def _resolve(self, state: LocalTop, *, proof_id: int, at_ms: int) -> None:
        reference = self._reference_for(state.update_id)
        if reference is None:
            self.unresolvable_no_ticker += 1
            return
        self.resolved += 1
        bid_ticks = self._ticks(state.bid - reference.bid)
        ask_ticks = self._ticks(state.ask - reference.ask)
        if bid_ticks == 0 and ask_ticks == 0:
            self.resolved_consistent += 1
            if self._same_size(state.bid_size, reference.bid_size) and self._same_size(state.ask_size, reference.ask_size):
                self.resolved_exact += 1
            else:
                self.resolved_size_mismatch += 1
            self._end_run()
            return
        self.true_inconsistencies += 1
        self._current_run += 1
        row = self._example_row(
            state,
            reference,
            at_ms=at_ms,
            classification="true_inconsistency",
            reason=(
                f"local top at updateId {state.update_id} differs from the venue's last top-of-book "
                f"change at or before that id (bookTicker updateId {reference.update_id}); the bookTicker "
                f"at updateId {proof_id} proves no other change fits in between"
            ),
        )
        row["proof_ticker_update_id"] = proof_id
        if len(self.examples["true_inconsistency"]) < self._max_examples:
            self.examples["true_inconsistency"].append(row)

    def _end_run(self) -> None:
        if self._current_run:
            self._runs.append(self._current_run)
            self._current_run = 0

    def _prune_tickers(self) -> None:
        """Keep only what a resolution can still need: the last ticker at or below the
        oldest state still to be resolved, and everything after it. With nothing pending,
        the next state's id is above the last local id, so that is the floor."""
        if self._pending_states:
            floor = self._pending_states[0].update_id
        elif self._last_local is not None:
            floor = self._last_local.update_id
        else:
            while len(self._tickers) > self._max_pending:  # no book yet: bounded, nothing else
                self._tickers.popleft()
            return
        while len(self._tickers) >= 2 and self._tickers[1].update_id <= floor:
            self._tickers.popleft()

    # ------------------------------------------------------------------ helpers

    def _ticks(self, diff: float) -> int:
        return round(diff / self.tick_size)

    @staticmethod
    def _same_size(a: float, b: float) -> bool:
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)

    def _sample(self, bucket: list[int], value: int) -> None:
        if len(bucket) < self._max_lag_samples:
            bucket.append(value)

    def _impossible(self, reason: str, *, ticker: VenueTop | None = None, state: LocalTop | None = None) -> None:
        row: dict[str, Any] = {"classification": "impossible_state", "reason": reason}
        if ticker is not None:
            row.update({"t_ms": ticker.received_at_ms, "venue_update_id": ticker.update_id, "venue_bid": ticker.bid, "venue_ask": ticker.ask})
        if state is not None:
            row.update({"t_ms": state.received_at_ms, "local_update_id": state.update_id, "local_bid": state.bid, "local_ask": state.ask})
        if self._last_local is not None and state is None:
            row.update({"local_update_id": self._last_local.update_id, "local_bid": self._last_local.bid, "local_ask": self._last_local.ask})
        if len(self.examples["impossible_state"]) < self._max_examples:
            self.examples["impossible_state"].append(row)

    def _example_row(self, local: LocalTop, venue: VenueTop, *, at_ms: int, classification: str, reason: str) -> dict[str, Any]:
        bid_ticks = self._ticks(local.bid - venue.bid)
        ask_ticks = self._ticks(local.ask - venue.ask)
        return {
            "t_ms": at_ms,
            "local_received_at_ms": local.received_at_ms,
            "venue_received_at_ms": venue.received_at_ms,
            "local_bid": local.bid,
            "local_ask": local.ask,
            "local_bid_size": local.bid_size,
            "local_ask_size": local.ask_size,
            "venue_bid": venue.bid,
            "venue_ask": venue.ask,
            "venue_bid_size": venue.bid_size,
            "venue_ask_size": venue.ask_size,
            "local_update_id": local.update_id,
            "venue_update_id": venue.update_id,
            "id_lag": venue.update_id - local.update_id,
            "local_state_age_ms": at_ms - local.received_at_ms,
            "bid_diff_ticks": bid_ticks,
            "ask_diff_ticks": ask_ticks,
            "max_abs_diff_ticks": max(abs(bid_ticks), abs(ask_ticks)),
            "classification": classification,
            "reason": reason,
        }

    def _keep_worst(self, bucket: list[dict[str, Any]], row: dict[str, Any], *, key: str) -> None:
        if len(bucket) < self._max_examples:
            bucket.append(row)
            return
        weakest = min(range(len(bucket)), key=lambda i: bucket[i][key])
        if row[key] > bucket[weakest][key]:
            bucket[weakest] = row

    # ------------------------------------------------------------------ output

    @property
    def impossible_state(self) -> bool:
        return bool(self.local_spread_negative or self.venue_crossed or self.ticker_sequence_regressions)

    @property
    def persistent_true_inconsistency(self) -> bool:
        runs = [*self._runs, self._current_run]
        return any(run >= self.persistent_states for run in runs)

    @property
    def consistent(self) -> bool | str:
        """The verdict criterion 12 reads. False on any impossible state or a persistent
        true inconsistency; NOT MEASURED when nothing could be resolved causally."""
        if self.impossible_state or self.persistent_true_inconsistency:
            return False
        if self.resolved == 0:
            return f"{NOT_MEASURED}: no local state could be paired causally with a bookTicker"
        return True

    def summary(self) -> dict[str, Any]:
        runs = [*self._runs, self._current_run]
        return {
            "method": (
                "causal on the venue's order book updateId: the local top after the depth batch ending at "
                "id L is compared with the venue's last bookTicker at or below L, once a bookTicker above L "
                "has arrived. Instant differences between the two streams are timing, measured and not judged."
            ),
            "tick_size": self.tick_size,
            "tickers": self.tickers,
            "ticker_duplicates": self.ticker_duplicates,
            "local_states": self.local_states,
            "resolved": self.resolved,
            "resolved_consistent": self.resolved_consistent,
            "resolved_exact": self.resolved_exact,
            "resolved_price_match_size_mismatch": self.resolved_size_mismatch,
            "true_inconsistencies": self.true_inconsistencies,
            "isolated_true_inconsistencies": sum(run for run in runs if 0 < run < self.persistent_states),
            "max_consecutive_true_inconsistencies": max(runs, default=0),
            "persistent_states_threshold": self.persistent_states,
            "persistent_true_inconsistency": self.persistent_true_inconsistency,
            "unresolved_at_end": len(self._pending_states),
            "unresolvable_no_ticker": self.unresolvable_no_ticker,
            "unresolved_dropped": self.unresolved_dropped,
            "discontinuities": self.discontinuities,
            "impossible_state": self.impossible_state,
            "impossible_state_reasons": {
                "local_spread_negative": self.local_spread_negative,
                "venue_crossed": self.venue_crossed,
                "ticker_sequence_regressions": self.ticker_sequence_regressions,
            },
            "instant": {
                "comparisons": self.instant_comparisons,
                "disagreements": self.instant_disagreements,
                "timing_disagreements": self.timing_disagreements,
                "same_id_disagreements": self.same_id_disagreements,
                "venue_ahead_samples": self.venue_ahead_samples,
                "local_ahead_samples": self.local_ahead_samples,
                "same_id_samples": self.same_id_samples,
            },
            "lag": {
                "id_lag_updates_all": _percentiles(self._id_lag_all),
                "id_lag_updates_when_venue_ahead": _percentiles(self._id_lag_ahead),
                "catch_up_ms": _percentiles(self._catch_up_ms),
                "catch_up_updates": _percentiles(self._catch_up_updates),
                "tickers_awaiting_catch_up_at_end": len(self._pending_tickers),
                "tickers_dropped_before_catch_up": self.tickers_dropped_before_catch_up,
                "clock": "local receive time; Spot bookTicker carries no exchange event time",
            },
            "examples": {k: list(v) for k, v in self.examples.items()},
            "consistent": self.consistent,
            "rule": (
                "consistent is False on any impossible_state (local ask <= bid, venue top crossed, "
                "bookTicker sequence backwards) or on a persistent_true_inconsistency "
                f"({self.persistent_states} consecutive causally resolved local states that differ from the "
                "venue's top at their own id); timing_disagreement never fails it; NOT MEASURED when "
                "no state could be resolved."
            ),
        }


def feed_from_service(matcher: CausalTopOfBookMatcher, book: Any, kind: str, event: Any, received_at_ms: int) -> None:
    """Adapter for ``MarketDataService.subscribe``: called after the service has processed
    each event, with the service's own book. A bookTicker feeds the venue side; a depth
    batch the book actually applied (its final id is now the book's id), or a snapshot the
    book adopted, feeds the local side; a disconnect ends the assumption that the ticker
    stream is complete. Buffered or ignored depth events feed nothing."""
    if kind == "book":
        matcher.on_ticker(VenueTop(event.update_id, event.bid, event.bid_size, event.ask, event.ask_size, received_at_ms))
    elif kind in ("depth", "snapshot"):
        applied = kind == "snapshot" or book.update_id == getattr(event, "final_update_id", None)
        if applied and book.is_valid:
            best_bid, best_ask = book.best_bid(), book.best_ask()
            if best_bid and best_ask:
                matcher.on_local_state(LocalTop(book.update_id, best_bid[0], best_bid[1], best_ask[0], best_ask[1], received_at_ms))
    elif kind == "disconnect":
        matcher.note_discontinuity("stream disconnected")


def causal_comparison_from_tape(path: Path | str, *, tick_size: float, persistent_states: int = PERSISTENT_STATES) -> dict[str, Any]:
    """The same causal comparison, from a recorded segment instead of the live feed.

    Reads the segment line by line (read-only: no manifest is ever written), rebuilds the
    book the way the replay does and feeds the matcher with every recorded bookTicker and
    every depth batch the book applied. Lets a segment recorded before this comparison
    existed be judged by it, on the very same data. Skips nothing silently: a segment that
    is not sealed is reported as such and not compared."""
    import gzip
    import json

    from tia.mm.order_book import BookState, DepthSnapshot, DepthUpdate, LocalOrderBook

    path = Path(path)
    manifest_path = Path(str(path) + ".manifest.json")
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    out: dict[str, Any] = {"path": str(path), "sealed": bool(manifest.get("closed_at")), "lines": 0}
    if not out["sealed"]:
        out["comparison"] = None
        out["reason"] = "segment not sealed: a recorder may still be writing it; not compared"
        return out

    def levels(rows: list[list[float]]) -> tuple[tuple[float, float], ...]:
        return tuple((float(p), float(q)) for p, q in rows)

    book = LocalOrderBook(symbol=str(manifest.get("symbol", "")))
    matcher = CausalTopOfBookMatcher(tick_size=tick_size, persistent_states=persistent_states)

    def local_state(received_at_ms: int) -> None:
        best_bid, best_ask = book.best_bid(), book.best_ask()
        if best_bid and best_ask:
            matcher.on_local_state(LocalTop(book.update_id, best_bid[0], best_bid[1], best_ask[0], best_ask[1], received_at_ms))

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            out["lines"] += 1
            row = json.loads(raw)
            kind = row.get("k")
            received_at_ms = int(row.get("R", 0) or 0)
            if kind == "book":
                matcher.on_ticker(VenueTop(int(row["u"]), float(row["b"]), float(row.get("B", 0.0)), float(row["a"]), float(row.get("A", 0.0)), received_at_ms))
            elif kind in ("snapshot", "checkpoint"):
                if kind == "checkpoint" and book.is_valid:
                    continue  # a verification line; the book is already in that state
                state = DepthSnapshot(int(row["id"]), levels(row["b"]), levels(row["a"]))
                if book.state is not BookState.SYNCING:
                    book.begin_sync()
                if book.apply_snapshot(state, received_at_ms=received_at_ms) and book.is_valid:
                    local_state(received_at_ms)
            elif kind == "depth":
                update = DepthUpdate(
                    first_update_id=int(row["U"]),
                    final_update_id=int(row["u"]),
                    bids=levels(row.get("b", [])),
                    asks=levels(row.get("a", [])),
                    event_time_ms=int(row.get("E", 0)),
                    received_at_ms=received_at_ms,
                )
                ok = book.apply_update(update)
                if ok and book.is_valid and book.update_id == update.final_update_id:
                    local_state(received_at_ms)
                elif not ok and book.state is BookState.OUT_OF_SYNC:
                    book.begin_sync()
                    book.buffer_update(update)
    out["comparison"] = matcher.summary()
    return out


__all__ = [
    "NOT_MEASURED",
    "PERSISTENT_SAMPLES",
    "PERSISTENT_STATES",
    "CausalTopOfBookMatcher",
    "LocalTop",
    "TopOfBookSample",
    "VenueTop",
    "causal_comparison_from_tape",
    "feed_from_service",
    "summarise",
]
