"""The causal comparison of the local book with the venue's bookTicker.

Both streams carry the venue's order book updateId; that id, not the receive instant, says
which local state a ticker is comparable with. Timing is measured and never judged; a
disagreement at the same id, after the causal window has closed, is a true inconsistency;
a crossed local book is impossible in any timing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tia.mm.consistency import (
    NOT_MEASURED,
    CausalTopOfBookMatcher,
    LocalTop,
    VenueTop,
    causal_comparison_from_tape,
    feed_from_service,
)
from tia.mm.order_book import snapshot_from_levels

TICK = 0.01


def _venue(update_id: int, bid: float, ask: float, t_ms: int, *, bid_size: float = 1.0, ask_size: float = 1.0) -> VenueTop:
    return VenueTop(update_id=update_id, bid=bid, bid_size=bid_size, ask=ask, ask_size=ask_size, received_at_ms=t_ms)


def _local(update_id: int, bid: float, ask: float, t_ms: int, *, bid_size: float = 1.0, ask_size: float = 1.0) -> LocalTop:
    return LocalTop(update_id=update_id, bid=bid, bid_size=bid_size, ask=ask, ask_size=ask_size, received_at_ms=t_ms)


def test_a_ticker_ahead_of_the_book_is_timing_and_resolves_consistent_once_the_book_catches_up() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.00, 100.01, 1000))
    # The venue's top moved at id 105; the ticker arrives before the depth batch does.
    m.on_ticker(_venue(105, 100.05, 100.06, 1010))
    instant = m.summary()["instant"]
    assert instant["venue_ahead_samples"] == 1 and instant["timing_disagreements"] == 1
    assert m.true_inconsistencies == 0
    # State 100 was below the new ticker's id: resolved against the ticker at 99, consistent.
    assert m.resolved == 1 and m.resolved_consistent == 1
    # The depth batch ending at 105 arrives 90 ms later with the same top: caught up.
    m.on_local_state(_local(105, 100.05, 100.06, 1100))
    m.on_ticker(_venue(106, 100.05, 100.06, 1150))  # proves nothing changed between 105 and 106
    s = m.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["true_inconsistencies"] == 0
    assert s["lag"]["id_lag_updates_when_venue_ahead"]["max"] == 5
    assert s["lag"]["catch_up_ms"] == {"count": 1, "p50": 90, "p95": 90, "p99": 90, "min": 90, "max": 90}
    assert s["lag"]["catch_up_updates"]["max"] == 5
    example = s["examples"]["timing_disagreement"][0]
    assert example["classification"] == "timing_disagreement" and example["id_lag"] == 5
    assert example["caught_up_after_ms"] == 90 and example["caught_up_at_local_update_id"] == 105
    assert s["consistent"] is True and s["persistent_true_inconsistency"] is False


def test_the_book_reaching_the_tickers_state_later_is_measured_at_the_first_state_at_or_past_its_id() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.00, 100.01, 1000))
    m.on_ticker(_venue(110, 100.02, 100.03, 1005))  # ten updates ahead of the book
    for update_id, t_ms in ((103, 1100), (106, 1200)):  # batches that do not reach 110 yet
        m.on_local_state(_local(update_id, 100.00, 100.01, t_ms))
    assert m.summary()["lag"]["catch_up_ms"]["count"] == 0
    m.on_local_state(_local(110, 100.02, 100.03, 1300))
    m.on_ticker(_venue(111, 100.02, 100.03, 1350))
    s = m.summary()
    # 103 and 106 are compared with the last ticker at or below them (99): consistent.
    assert s["resolved"] == 4 and s["resolved_consistent"] == 4 and s["true_inconsistencies"] == 0
    assert s["lag"]["catch_up_ms"]["max"] == 295 and s["lag"]["catch_up_updates"]["max"] == 10
    # The proof ticker at 111 is itself one update ahead of the book: it waits, as it should.
    assert s["lag"]["tickers_awaiting_catch_up_at_end"] == 1
    assert s["consistent"] is True


def test_three_consecutive_resolved_disagreements_are_a_persistent_true_inconsistency() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    for update_id, t_ms in ((100, 1000), (101, 1100), (102, 1200)):
        m.on_local_state(_local(update_id, 100.10, 100.11, t_ms))  # the local top is wrong
    assert m.resolved == 0  # nothing is judged until a later ticker closes the window
    m.on_ticker(_venue(103, 100.00, 100.01, 1250))  # the venue's top never moved
    s = m.summary()
    assert s["resolved"] == 3 and s["true_inconsistencies"] == 3
    assert s["max_consecutive_true_inconsistencies"] == 3 and s["persistent_true_inconsistency"] is True
    assert s["isolated_true_inconsistencies"] == 0
    assert s["consistent"] is False and s["impossible_state"] is False
    example = s["examples"]["true_inconsistency"][0]
    for key in (
        "t_ms", "local_bid", "local_ask", "venue_bid", "venue_ask", "local_update_id", "venue_update_id",
        "id_lag", "local_state_age_ms", "classification", "reason", "proof_ticker_update_id",
    ):
        assert key in example
    assert example["classification"] == "true_inconsistency"
    assert example["local_update_id"] == 100 and example["venue_update_id"] == 99 and example["id_lag"] == -1
    assert example["proof_ticker_update_id"] == 103 and example["local_state_age_ms"] == 250
    assert example["bid_diff_ticks"] == 10 and example["ask_diff_ticks"] == 10


def test_a_local_ask_at_or_below_the_local_bid_is_impossible_in_any_timing() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.02, 100.01, 1000))
    s = m.summary()
    assert s["impossible_state"] is True and s["impossible_state_reasons"]["local_spread_negative"] == 1
    assert s["consistent"] is False
    example = s["examples"]["impossible_state"][0]
    assert example["classification"] == "impossible_state" and "local ask <= local bid" in example["reason"]
    assert example["local_update_id"] == 100 and example["local_bid"] == 100.02 and example["local_ask"] == 100.01


def test_a_large_difference_explained_by_timing_is_not_an_inconsistency() -> None:
    # The VPS case: bookTicker 828 updates ahead, 1,388 ticks away from the local top.
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99_999, 84395.96, 84395.97, 990))
    m.on_local_state(_local(100_000, 84395.96, 84395.97, 1000))
    m.on_ticker(_venue(100_828, 84382.08, 84382.09, 1020))
    s = m.summary()
    example = s["examples"]["timing_disagreement"][0]
    assert example["max_abs_diff_ticks"] == 1388 and example["id_lag"] == 828
    assert s["true_inconsistencies"] == 0
    # The book gets there: the batch ending at 100_828 carries the venue's top.
    m.on_local_state(_local(100_828, 84382.08, 84382.09, 1130))
    m.on_ticker(_venue(100_829, 84382.08, 84382.09, 1140))
    s = m.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["true_inconsistencies"] == 0
    assert s["examples"]["timing_disagreement"][0]["caught_up_after_ms"] == 110
    assert s["consistent"] is True


def test_a_single_same_id_disagreement_is_a_true_inconsistency_recorded_as_isolated() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.02, 100.03, 1000))
    m.on_ticker(_venue(100, 100.00, 100.01, 1005))  # same id, different top: not timing
    assert m.summary()["instant"]["same_id_disagreements"] == 1
    m.on_ticker(_venue(101, 100.00, 100.01, 1050))
    m.on_local_state(_local(101, 100.00, 100.01, 1100))
    m.on_ticker(_venue(102, 100.00, 100.01, 1150))
    s = m.summary()
    assert s["true_inconsistencies"] == 1 and s["isolated_true_inconsistencies"] == 1
    assert s["persistent_true_inconsistency"] is False and s["consistent"] is True
    assert s["examples"]["true_inconsistency"][0]["venue_update_id"] == 100


def test_a_ticker_sequence_going_backwards_is_impossible() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(105, 100.00, 100.01, 1000))
    m.on_ticker(_venue(104, 100.00, 100.01, 1010))
    s = m.summary()
    assert s["impossible_state_reasons"]["ticker_sequence_regressions"] == 1 and s["impossible_state"] is True
    assert s["consistent"] is False
    assert "went backwards" in s["examples"]["impossible_state"][0]["reason"]


def test_a_crossed_venue_top_is_impossible_and_never_used_as_a_reference() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.00, 100.01, 1000))
    m.on_ticker(_venue(100, 100.05, 100.04, 1005))  # bid >= ask: the venue cannot report this
    m.on_ticker(_venue(101, 100.00, 100.01, 1050))
    s = m.summary()
    assert s["impossible_state_reasons"]["venue_crossed"] == 1 and s["consistent"] is False
    assert s["resolved_consistent"] == 1  # state 100 was compared with the ticker at 99


def test_a_disconnect_drops_pending_pairings_instead_of_judging_them() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.00, 100.01, 1000))  # pending: no ticker above 100 yet
    m.on_local_state(_local(101, 100.00, 100.01, 1100))
    m.note_discontinuity("stream disconnected")
    s = m.summary()
    assert s["discontinuities"] == 1 and s["unresolved_dropped"] == 2 and s["resolved"] == 0
    # A ticker running ahead when the stream drops is dropped too, never judged later.
    m.on_ticker(_venue(200, 100.50, 100.51, 2000))
    m.on_local_state(_local(200, 100.50, 100.51, 2100))
    m.on_ticker(_venue(260, 100.60, 100.61, 2105))  # resolves state 200, then waits for 260
    m.note_discontinuity("stream disconnected")
    s = m.summary()
    assert s["resolved"] == 1 and s["lag"]["tickers_dropped_before_catch_up"] == 1
    assert s["lag"]["tickers_awaiting_catch_up_at_end"] == 0
    # After the stream is back the ledger works again from the new tickers.
    m.on_ticker(_venue(300, 100.70, 100.71, 3000))
    m.on_local_state(_local(300, 100.70, 100.71, 3100))
    m.on_ticker(_venue(301, 100.70, 100.71, 3150))
    s = m.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["consistent"] is True


def test_nothing_resolved_is_not_measured_rather_than_consistent() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_ticker(_venue(100, 100.00, 100.01, 1000))
    s = m.summary()
    assert s["resolved"] == 0 and isinstance(s["consistent"], str) and s["consistent"].startswith(NOT_MEASURED)
    assert s["consistent"] is not True


def test_matching_prices_with_different_sizes_are_counted_and_not_judged() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990, bid_size=2.0))
    m.on_local_state(_local(100, 100.00, 100.01, 1000, bid_size=1.5))
    m.on_ticker(_venue(101, 100.00, 100.01, 1050))
    s = m.summary()
    assert s["resolved_consistent"] == 1 and s["resolved_exact"] == 0 and s["resolved_price_match_size_mismatch"] == 1
    assert s["true_inconsistencies"] == 0 and s["consistent"] is True


def test_the_reference_is_the_last_ticker_at_or_below_the_state_even_with_many_tickers_between() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(90, 100.00, 100.01, 900))
    m.on_ticker(_venue(95, 100.02, 100.03, 950))
    m.on_ticker(_venue(98, 100.04, 100.05, 980))
    m.on_local_state(_local(100, 100.04, 100.05, 1000))  # the batch 96..100 carries the top set at 98
    m.on_ticker(_venue(104, 100.06, 100.07, 1040))
    s = m.summary()
    assert s["resolved"] == 1 and s["resolved_consistent"] == 1 and s["true_inconsistencies"] == 0


# ------------------------------------------------------------- fed from the live service


def _ticker_frame(u: int, bid: float, ask: float) -> str:
    return json.dumps({"stream": "s@bookTicker", "data": {"u": u, "s": "BTCUSDT", "b": str(bid), "B": "1", "a": str(ask), "A": "1"}})


async def test_the_adapter_feeds_only_applied_depth_and_every_ticker_and_notes_disconnects(tmp_path: Path) -> None:
    from tests.unit.mm.test_replay import _depth, _service

    service, scripted, _calls, clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.00, 1.0)], [(100.01, 1.0)])])
    matcher = CausalTopOfBookMatcher(tick_size=TICK)
    service.subscribe(lambda kind, event, t_ms: feed_from_service(matcher, service.book, kind, event, t_ms))
    service.start()
    await asyncio.sleep(0.05)
    assert service.book.is_valid and matcher.local_states == 1  # the adopted snapshot is a local state
    await scripted.send(_ticker_frame(100, 100.00, 100.01))
    # The venue's top moves at 103; the ticker arrives before the batch that carries it.
    clock["ms"] += 20
    await scripted.send(_ticker_frame(103, 100.02, 100.03))
    assert matcher.venue_ahead_samples == 1 and matcher.timing_disagreements == 1
    clock["ms"] += 80
    await scripted.send(_depth(101, 103, bids=[(100.02, 1.0)], asks=[(100.03, 1.0), (100.01, 0.0)]))
    assert service.book.update_id == 103 and matcher.local_states == 2
    clock["ms"] += 10
    await scripted.send(_ticker_frame(104, 100.02, 100.03))
    s = matcher.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["true_inconsistencies"] == 0
    assert s["lag"]["catch_up_ms"]["max"] == 80 and s["lag"]["catch_up_updates"]["max"] == 3
    assert s["consistent"] is True
    # A depth batch the book cannot apply (a gap) feeds nothing; a drop notes a discontinuity.
    await scripted.send(_depth(110, 112, bids=[(100.03, 1.0)]))
    assert matcher.local_states == 2 and service.book.metrics.gaps == 1
    await scripted.drop()
    assert matcher.discontinuities == 1
    await service.close()


# ------------------------------------------------------------------ from a recorded tape


def test_a_recorded_segment_is_judged_by_the_same_causal_comparison_read_only(tmp_path: Path) -> None:
    from tia.mm.order_book import DepthUpdate
    from tia.mm.recorder import BookStateEvent, TickRecorder
    from tia.mm.streams import BookTickerEvent

    base = 1_758_214_800_000
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=1, now_ms=lambda: base)
    recorder.record("snapshot", BookStateEvent(100, ((100.00, 1.0),), ((100.01, 1.0),), base))
    recorder.record("book", BookTickerEvent(100, 100.00, 1.0, 100.01, 1.0, base + 1))
    # The venue's top moves at 103; the ticker is recorded before the batch that carries it.
    recorder.record("book", BookTickerEvent(103, 100.02, 1.0, 100.03, 1.0, base + 20))
    recorder.record("depth", DepthUpdate(101, 103, ((100.02, 1.0),), ((100.03, 1.0), (100.01, 0.0)), base + 90, base + 100))
    recorder.record("book", BookTickerEvent(104, 100.02, 1.0, 100.03, 1.0, base + 150))
    path = recorder.segments()[0]["path"]
    manifest_path = Path(path + ".manifest.json")
    before = manifest_path.read_bytes()

    open_result = causal_comparison_from_tape(path, tick_size=TICK)  # still open: not judged
    assert open_result["sealed"] is False and open_result["comparison"] is None

    recorder.close()
    before = manifest_path.read_bytes()
    result = causal_comparison_from_tape(path, tick_size=TICK)
    assert manifest_path.read_bytes() == before  # read-only: the manifest is untouched
    c = result["comparison"]
    assert result["sealed"] is True and result["lines"] == 5
    assert c["tickers"] == 3 and c["local_states"] == 2
    assert c["resolved"] == 2 and c["resolved_consistent"] == 2 and c["true_inconsistencies"] == 0
    # Two tickers arrived ahead of the book (103 and the proof ticker 104); only 103 differed.
    assert c["instant"]["timing_disagreements"] == 1 and c["instant"]["venue_ahead_samples"] == 2
    assert c["lag"]["catch_up_ms"]["max"] == 80 and c["lag"]["catch_up_updates"]["max"] == 3
    assert c["lag"]["tickers_awaiting_catch_up_at_end"] == 1
    assert c["consistent"] is True


# ------------------------------------------------------ intermediate tickers and unresolved


def test_a_ticker_intermediate_inside_a_batch_never_becomes_an_inconsistency() -> None:
    # The VPS case of 2026-09-24: the venue's top moved four times inside one 763-update
    # batch. Each intermediate ticker described a state the batch itself left behind; the
    # book at the end of the batch must equal the last ticker at or below its final id.
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(100580224185, 84318.00, 84318.01, 1000))
    m.on_local_state(_local(100580224185, 84318.00, 84318.01, 1005))
    for u, bid, ask, t in (
        (100580224189, 84318.00, 84318.01, 1010),  # inside the next batch, same top
        (100580224347, 84319.98, 84319.99, 1100),
        (100580224369, 84319.98, 84320.01, 1110),
        (100580224464, 84320.00, 84320.01, 1250),
        (100580224945, 84320.00, 84320.01, 1580),  # the last change at or below the batch end
    ):
        m.on_ticker(_venue(u, bid, ask, t))
    assert m.true_inconsistencies == 0 and m.summary()["instant"]["venue_ahead_samples"] == 5
    # The batch 224186..224948 arrives and leaves the local top at 84320.00/84320.01.
    m.on_local_state(_local(100580224948, 84320.00, 84320.01, 1640))
    m.on_ticker(_venue(100580224950, 84320.00, 84320.01, 1645))  # proof: nothing else fits before 224948
    s = m.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["true_inconsistencies"] == 0
    assert s["instant"]["timing_disagreements"] == 4  # 224347, 224369, 224464, 224945 differed at their instants
    assert s["persistent_true_inconsistency"] is False and s["consistent"] is True
    # Had the batch-end state been paired with the intermediate ticker 224189 instead, the
    # 200-tick move inside the batch would have read as an inconsistency. It is not paired.
    assert all(ex["classification"] == "timing_disagreement" for ex in s["examples"]["timing_disagreement"])


def test_states_without_a_proof_ticker_stay_unresolved_and_are_never_judged() -> None:
    m = CausalTopOfBookMatcher(tick_size=TICK)
    m.on_ticker(_venue(99, 100.00, 100.01, 990))
    m.on_local_state(_local(100, 100.05, 100.06, 1000))  # differs from ticker 99: the venue may have moved at 100
    m.on_local_state(_local(101, 100.05, 100.06, 1100))
    s = m.summary()
    assert s["unresolved_at_end"] == 2 and s["resolved"] == 0 and s["true_inconsistencies"] == 0
    assert s["persistent_true_inconsistency"] is False and str(s["consistent"]).startswith(NOT_MEASURED)
    # The proof ticker arrives with the venue's own move at 100: both states resolve consistent.
    m.on_ticker(_venue(100, 100.05, 100.06, 1005))  # arrives late, in venue order
    m.on_ticker(_venue(102, 100.05, 100.06, 1150))
    s = m.summary()
    assert s["resolved"] == 2 and s["resolved_consistent"] == 2 and s["unresolved_at_end"] == 0
    assert s["true_inconsistencies"] == 0 and s["consistent"] is True
