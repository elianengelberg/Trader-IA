"""Regressions for the two integrity faults found on the VPS, plus the rules that
replaced them. Synthetic events throughout.

Fault 1: a segment with no snapshot and no checkpoint claimed replayable=true.
Fault 2: a second session in the same hour appended to the existing file; its manifest
counted only its own lines while the checksum covered the whole file.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tia.mm.consistency import TopOfBookSample, summarise
from tia.mm.order_book import DepthSnapshot, DepthUpdate, LocalOrderBook
from tia.mm.recorder import MANIFEST_SUFFIX, BookStateEvent, RecorderBusyError, TickRecorder
from tia.mm.replay import replay_directory, replay_segment

HOUR_MS = 3_600_000
BASE = 1_789_754_400_000  # 2026-09-18T18:00:00Z


def _depth(uid: int, at_ms: int, qty: float = 1.0) -> DepthUpdate:
    return DepthUpdate(first_update_id=uid, final_update_id=uid, bids=((100.0, qty),), asks=((101.0, 1.0),), event_time_ms=at_ms - 30, received_at_ms=at_ms)


def _state(uid: int, at_ms: int, qty: float = 1.0) -> BookStateEvent:
    bids, asks = ((100.0, qty),), ((101.0, 1.0),)
    book = LocalOrderBook("BTC-USD")
    book.begin_sync()
    assert book.apply_snapshot(DepthSnapshot(uid, bids, asks))
    return BookStateEvent(update_id=uid, bids=bids, asks=asks, received_at_ms=at_ms, digest=book.digest())


def _count_lines(path: str) -> int:
    with gzip.open(path, "rb") as fh:
        return sum(1 for _ in fh)


def _rows(path: str) -> list[dict]:  # type: ignore[type-arg]
    with gzip.open(path, "rt") as fh:
        return [json.loads(line) for line in fh]


# ------------------------------------------------------------- fault 2: never append


def test_a_second_session_in_the_same_hour_gets_its_own_file_and_manifest(tmp_path: Path) -> None:
    first = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    first.record("snapshot", _state(1, BASE))
    for i in range(2, 12):
        first.record("depth", _depth(i, BASE + i))
    first.record("checkpoint", _state(11, BASE + 12))
    first.close()

    second = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE + 60_000)  # same hour, later
    second.record("snapshot", _state(50, BASE + 60_000))
    for i in range(51, 56):
        second.record("depth", _depth(i, BASE + 60_000 + i))
    second.record("checkpoint", _state(55, BASE + 61_000))
    second.close()

    segments = second.segments()
    assert [Path(s["path"]).name for s in segments] == ["20260918-18.jsonl.gz", "20260918-18.part02.jsonl.gz"]
    for segment in segments:
        manifest = segment["manifest"]
        assert manifest["lines"] == _count_lines(segment["path"])  # the manifest describes its own file
        assert TickRecorder.verify(segment["path"])["ok"] is True
        assert segment["replayable"] is True
        result = replay_segment(segment["path"])
        assert result.ok, result.reasons
    assert segments[0]["manifest"]["lines"] == 12 and segments[1]["manifest"]["lines"] == 7
    assert segments[1]["manifest"]["part"] == 2 and result.part == 2


def test_a_concurrent_writer_on_the_same_directory_is_refused(tmp_path: Path) -> None:
    holder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    with pytest.raises(RecorderBusyError):
        TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    other_symbol = TickRecorder(tmp_path, "ETH-USD", now_ms=lambda: BASE)  # a different directory
    other_symbol.close()
    holder.close()
    TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE).close()  # released on close


# ------------------------------------------------------------- fault 1: rebuildable or not replayable


def test_a_segment_without_initial_state_is_never_replayable(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    for i in range(1, 6):
        recorder.record("depth", _depth(i, BASE + i))
    recorder.close()
    segment = recorder.segments()[0]
    assert segment["replayable"] is False
    assert "no initial book state" in segment["not_replayable"]
    result = replay_segment(segment["path"])
    assert result.ok is False and any("not replayable" in r for r in result.reasons)


def test_a_segment_without_closing_checkpoint_is_not_replayable(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    recorder.record("snapshot", _state(1, BASE))
    recorder.record("depth", _depth(2, BASE + 1))
    recorder.close()  # the book was never handed over at close
    manifest = recorder.segments()[0]["manifest"]
    assert manifest["closing_checkpoint"] is False and manifest["replayable"] is False
    assert "no closing checkpoint" in manifest["not_replayable_reasons"][0]


def test_an_hour_rollover_seals_the_old_file_with_a_closing_checkpoint(tmp_path: Path) -> None:
    clock = {"ms": BASE + HOUR_MS - 2_000}
    book = {"uid": 0, "qty": 1.0}

    def source() -> BookStateEvent | None:
        return _state(book["uid"], clock["ms"], book["qty"]) if book["uid"] else None

    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: clock["ms"], checkpoint_source=source)
    recorder.record("snapshot", _state(10, clock["ms"]))
    book["uid"] = 10
    for uid in range(11, 14):  # still hour 18
        clock["ms"] += 500
        recorder.record("depth", _depth(uid, clock["ms"], qty=float(uid)))
        book["uid"], book["qty"] = uid, float(uid)
    clock["ms"] += 1_000  # crosses into hour 19
    recorder.record("depth", _depth(14, clock["ms"], qty=14.0))
    book["uid"], book["qty"] = 14, 14.0
    recorder.record("checkpoint", source())  # type: ignore[arg-type]
    recorder.close()

    old, new = recorder.segments()
    assert Path(old["path"]).name == "20260918-18.jsonl.gz" and Path(new["path"]).name == "20260918-19.jsonl.gz"
    assert old["replayable"] is True and new["replayable"] is True
    old_rows, new_rows = _rows(old["path"]), _rows(new["path"])
    assert old_rows[-1]["k"] == "checkpoint" and old_rows[-1]["id"] == 13  # closes where the hour ended
    assert new_rows[0]["k"] == "checkpoint" and new_rows[0]["id"] == 13  # opens from the same state
    assert new_rows[-1]["k"] == "checkpoint" and new_rows[-1]["id"] == 14
    for result in replay_directory(tmp_path, "BTC-USD"):
        assert result.ok, result.reasons
        assert result.digest_matches_manifest is True and result.final_matches_manifest is True


def test_a_legacy_manifest_is_reported_not_replayable(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    recorder.record("snapshot", _state(1, BASE))
    recorder.record("checkpoint", _state(1, BASE + 1))
    recorder.close()
    segment = recorder.segments()[0]
    manifest_path = Path(segment["path"] + MANIFEST_SUFFIX)
    legacy = json.loads(manifest_path.read_text())
    legacy.pop("format")  # a manifest written before the book's state was recorded
    manifest_path.write_text(json.dumps(legacy))
    listed = recorder.segments()[0]
    assert listed["replayable"] is False and "legacy" in listed["not_replayable"]
    result = replay_segment(segment["path"])
    assert result.ok is False and result.manifest_format == 1


def test_an_unsealed_segment_is_not_replayable_until_closed(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=1, now_ms=lambda: BASE)
    recorder.record("snapshot", _state(1, BASE))
    recorder.record("checkpoint", _state(1, BASE + 1))
    open_segment = recorder.segments()[0]
    assert open_segment["sealed"] is False and open_segment["replayable"] is False
    assert "not sealed" in open_segment["not_replayable"]
    assert replay_segment(open_segment["path"]).ok is False
    recorder.close()
    assert recorder.segments()[0]["replayable"] is True and replay_segment(open_segment["path"]).ok


# ------------------------------------------------------------- bookTicker comparison rules


def _sample(t: float, lb: float, la: float, vb: float, va: float, *, local_id: int = 10, venue_id: int = 10) -> TopOfBookSample:
    return TopOfBookSample(t=t, local_bid=lb, local_ask=la, local_update_id=local_id, venue_bid=vb, venue_ask=va, venue_update_id=venue_id, tick_size=0.01)


def test_one_instant_inside_the_venue_top_is_timing_not_an_inconsistency() -> None:
    # The VPS sample: local 81213.99/81214.00 against venue 81214.59/81214.60, once.
    once = _sample(30, 81213.99, 81214.00, 81214.59, 81214.60, local_id=100, venue_id=104)
    assert once.crossed_vs_venue and once.venue_ahead and once.max_abs_diff_ticks == 60
    assert not once.local_spread_negative
    assert once.explanation.startswith("timing")
    summary = summarise([_sample(25, 81214.59, 81214.60, 81214.59, 81214.60), once, _sample(35, 81214.61, 81214.62, 81214.61, 81214.62)])
    assert summary["crossed_vs_venue_instants"] == 1 and summary["max_consecutive_disagreements"] == 1
    assert summary["persistent_inconsistency"] is False and summary["impossible_state"] is False


def test_a_disagreement_that_survives_three_samples_is_persistent() -> None:
    samples = [_sample(t, 100.00, 100.01, 100.50, 100.51) for t in (5, 10, 15)]
    summary = summarise(samples)
    assert summary["max_consecutive_disagreements"] == 3 and summary["persistent_inconsistency"] is True


def test_a_crossed_local_book_is_impossible_whatever_the_timing() -> None:
    summary = summarise([_sample(5, 100.02, 100.01, 100.00, 100.01)])
    assert summary["impossible_state"] is True and summary["persistent_inconsistency"] is False
    assert summary["worst_samples"][0]["explanation"].startswith("IMPOSSIBLE")


# ------------------------------------------------------------- receive-time order across a rollover


def test_a_rollover_checkpoint_never_carries_a_later_stamp_than_the_event_that_triggered_it(tmp_path: Path) -> None:
    """Reproduces the VPS finding: the wall clock ticks between the stream stamping an
    event and the recorder rolling the hour. The opening checkpoint used to carry the
    later wall-clock stamp ahead of the event's earlier R — one receive-time inversion
    at the start of every hour file. Checkpoints now carry the R of their place in the
    tape: the closing one the last event's, the opening one the triggering event's."""
    hour_start = BASE + HOUR_MS
    clock = {"ms": hour_start - 5}
    book = {"uid": 0}

    def source() -> BookStateEvent | None:
        # The service's book_state() stamps with the wall clock at call time.
        return _state(book["uid"], clock["ms"]) if book["uid"] else None

    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: clock["ms"], checkpoint_source=source)
    recorder.record("snapshot", _state(10, clock["ms"]))
    book["uid"] = 10
    for uid in (11, 12):
        clock["ms"] += 1
        recorder.record("depth", _depth(uid, clock["ms"]))
        book["uid"] = uid
    # The first event of the new hour was stamped R = hour_start by the stream, but by
    # the time the recorder processes it the wall clock reads hour_start + 3.
    event = _depth(13, hour_start)
    clock["ms"] = hour_start + 3
    recorder.record("depth", event)
    book["uid"] = 13
    recorder.record("checkpoint", source())  # type: ignore[arg-type]
    recorder.close()

    old, new = recorder.segments()
    old_rows, new_rows = _rows(old["path"]), _rows(new["path"])
    assert old_rows[-1]["k"] == "checkpoint" and old_rows[-1]["R"] == old_rows[-2]["R"]  # closes at the last event's R
    assert new_rows[0]["k"] == "checkpoint" and new_rows[0]["R"] == hour_start == new_rows[1]["R"]  # opens at the triggering event's R
    for rows in (old_rows, new_rows):
        stamps = [r["R"] for r in rows]
        assert stamps == sorted(stamps), stamps
    for result in replay_directory(tmp_path, "BTC-USD"):
        assert result.ok, result.reasons
        assert result.receive_time_regressions == 0


def test_the_replay_tells_a_clock_step_from_a_reordered_tape_and_fails_both(tmp_path: Path) -> None:
    """R going backwards while the venue sequence still advances is a stamp artefact
    (clock step); R and the venue sequence both going backwards is a reordered tape.
    The replay names which one it saw — and fails either way, because the recorder
    stamps on a monotonic receive clock and a legitimate tape has no regression."""
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE)
    recorder.record("snapshot", _state(1, BASE))
    recorder.record("depth", _depth(2, BASE + 10))
    recorder.record("depth", _depth(3, BASE + 8))  # the wall clock stepped back 2 ms; u still advances
    recorder.record("depth", _depth(4, BASE + 12))
    recorder.record("checkpoint", _state(4, BASE + 13))
    recorder.close()
    path = recorder.segments()[0]["path"]
    stepped = replay_segment(path)
    assert stepped.ok is False and any("not in arrival order" in r for r in stepped.reasons)
    assert stepped.receive_time_regressions == 1 and stepped.clock_artifacts == 1 and stepped.order_violations == 0
    sample = stepped.regression_samples[0]
    assert sample["classified"] == "clock_artifact" and sample["receive_time_delta_ms"] == -2
    assert sample["previous"]["u"] == 2 and sample["current"]["u"] == 3 and sample["current"]["stream"] == "depth@100ms"

    # Now swap two depth lines on disk: R and u both go backwards.
    rows = _rows(path)
    rows[2], rows[3] = rows[3], rows[2]
    with gzip.open(path, "wt") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    reordered = replay_segment(path, allow_flagged=True)
    assert reordered.order_violations >= 1 and any("not in arrival order" in r for r in reordered.reasons)
    assert reordered.ok is False
