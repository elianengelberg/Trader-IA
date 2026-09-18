"""Data properties of the market-making tape: the ground every later phase stands on.

Three properties, all structural:

* **Determinism.** The same segment replayed twice yields the same book, digest for
  digest, event after event.
* **Prefix invariance.** The book after the first ``k`` events of a tape is the same
  whether or not events ``k+1…n`` exist. If it were not, something read the future.
* **Checkpoint sufficiency.** Adopting a checkpoint of the book and continuing yields
  the same book as never having stopped — which is what makes an hour's file
  rebuildable on its own.

Every event here is synthetic; the properties are about the machinery, not the market.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from tia.mm.order_book import (
    BookState,
    DepthSnapshot,
    DepthUpdate,
    LocalOrderBook,
    snapshot_from_levels,
)
from tia.mm.recorder import BookStateEvent, TickRecorder
from tia.mm.replay import replay_segment
from tia.mm.streams import TradeEvent

BASE_MS = 1_789_754_400_000
MID = 100_000.0


def _price(offset: int) -> float:
    return round(MID + offset * 0.1, 1)


# A depth diff touches a few prices around the mid with absolute quantities (0 removes).
_level = st.tuples(st.integers(min_value=-30, max_value=30), st.sampled_from([0.0, 0.05, 0.5, 1.25, 3.0]))
_diff = st.tuples(st.lists(_level, min_size=0, max_size=4), st.lists(_level, min_size=0, max_size=4))
_tape = st.lists(_diff, min_size=1, max_size=60)


def _updates(diffs: list) -> list[DepthUpdate]:  # type: ignore[type-arg]
    """Sequential ids, bids strictly below the mid, asks strictly above: never crossed."""
    out: list[DepthUpdate] = []
    uid = 101
    for i, (bids, asks) in enumerate(diffs):
        out.append(
            DepthUpdate(
                first_update_id=uid,
                final_update_id=uid,
                bids=tuple((_price(-abs(o) - 1), q) for o, q in bids),
                asks=tuple((_price(abs(o) + 1), q) for o, q in asks),
                event_time_ms=BASE_MS + i * 100 - 30,
                received_at_ms=BASE_MS + i * 100,
            )
        )
        uid += 1
    return out


def _fresh_book() -> LocalOrderBook:
    book = LocalOrderBook("BTC-USD")
    book.begin_sync()
    assert book.apply_snapshot(snapshot_from_levels(100, [(_price(-1), 1.0), (_price(-2), 2.0)], [(_price(1), 1.0), (_price(2), 2.0)]))
    return book


def _digests(updates: list[DepthUpdate]) -> list[str]:
    book = _fresh_book()
    out = []
    for update in updates:
        assert book.apply_update(update)
        out.append(book.digest())
    return out


@settings(max_examples=60, deadline=None)
@given(_tape)
def test_the_book_is_deterministic(diffs: list) -> None:  # type: ignore[type-arg]
    updates = _updates(diffs)
    assert _digests(updates) == _digests(updates)


@settings(max_examples=60, deadline=None)
@given(_tape, st.data())
def test_a_prefix_of_the_tape_yields_a_prefix_of_the_book_states(diffs: list, data: st.DataObject) -> None:  # type: ignore[type-arg]
    updates = _updates(diffs)
    k = data.draw(st.integers(min_value=1, max_value=len(updates)))
    assert _digests(updates[:k]) == _digests(updates)[:k]


@settings(max_examples=60, deadline=None)
@given(_tape, st.data())
def test_a_checkpoint_is_sufficient_to_continue(diffs: list, data: st.DataObject) -> None:  # type: ignore[type-arg]
    updates = _updates(diffs)
    k = data.draw(st.integers(min_value=0, max_value=len(updates)))
    # Run straight through.
    straight = _fresh_book()
    for update in updates:
        assert straight.apply_update(update)
    # Run to k, checkpoint, adopt the checkpoint in a new book, continue.
    partial = _fresh_book()
    for update in updates[:k]:
        assert partial.apply_update(update)
    bids, asks = partial.levels()
    resumed = LocalOrderBook("BTC-USD")
    resumed.begin_sync()
    assert resumed.apply_snapshot(DepthSnapshot(partial.update_id, tuple(bids), tuple(asks)))
    for update in updates[k:]:
        assert resumed.apply_update(update)
    assert resumed.digest() == straight.digest()
    assert resumed.state is BookState.SYNCED and resumed.update_id == straight.update_id


def test_a_recorded_segment_replays_identically_twice_and_in_arrival_order(tmp_path: Path) -> None:
    updates = _updates([([(-3, 0.5)], [(2, 0.0)]), ([(-1, 2.0)], []), ([], [(4, 1.5)])])
    book = _fresh_book()
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE_MS, checkpoint_source=None)
    bids, asks = book.levels()
    recorder.record("snapshot", BookStateEvent(book.update_id, tuple(bids), tuple(asks), BASE_MS))
    for i, update in enumerate(updates):
        recorder.record("depth", update)
        assert book.apply_update(update)
        recorder.record("trade", TradeEvent(trade_id=10 + i, price=MID, quantity=0.1, buyer_is_maker=bool(i % 2), trade_time_ms=update.received_at_ms - 5, event_time_ms=update.received_at_ms - 2, received_at_ms=update.received_at_ms + 1))
    bids, asks = book.levels()
    recorder.record("checkpoint", BookStateEvent(book.update_id, tuple(bids), tuple(asks), BASE_MS + 1_000, digest=book.digest()))
    recorder.close()
    path = recorder.segments()[0]["path"]
    first, second = replay_segment(path), replay_segment(path)
    assert first.ok and second.ok, (first.reasons, second.reasons)
    assert first.as_dict() == second.as_dict()
    assert first.final_digest == book.digest() and first.receive_time_regressions == 0
    assert first.trade_id_jumps == 0

    # A tape whose lines are not in arrival order is reported, not silently accepted.
    with gzip.open(path, "rt") as fh:
        rows = [json.loads(line) for line in fh]
    rows[2], rows[3] = rows[3], rows[2]  # swap two lines: R goes backwards once
    shuffled = tmp_path / "BTC-USD" / "shuffled.jsonl.gz"
    with gzip.open(shuffled, "wt") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    result = replay_segment(shuffled, allow_flagged=True)
    assert result.receive_time_regressions >= 1
    assert any("arrival order" in reason for reason in result.reasons)
