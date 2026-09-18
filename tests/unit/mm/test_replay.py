"""Replay, checkpoints, stall injection and connection accounting — offline, scripted.

Every event here is synthetic: these tests prove the mechanics, never the market.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tia.mm.market_data import MarketDataService
from tia.mm.order_book import BookState, snapshot_from_levels
from tia.mm.recorder import BookStateEvent, TickRecorder
from tia.mm.replay import replay_directory, replay_segment
from tia.mm.streams import MarketDataStream

BASE_MS = 1_758_214_800_000


def _depth(U: int, u: int, bids=(), asks=()) -> str:  # type: ignore[no-untyped-def]
    return json.dumps({"stream": "s@depth@100ms", "data": {"e": "depthUpdate", "E": 1_000 + u, "s": "BTCUSDT", "U": U, "u": u, "b": [[str(p), str(q)] for p, q in bids], "a": [[str(p), str(q)] for p, q in asks]}})


def _trade(t: int, price: float) -> str:
    return json.dumps({"stream": "s@trade", "data": {"e": "trade", "E": 2_000 + t, "s": "BTCUSDT", "t": t, "p": str(price), "q": "0.1", "T": 1_990 + t, "m": False, "M": True}})


class Scripted:
    def __init__(self) -> None:
        self.queues: list[asyncio.Queue[str | None]] = []

    def connector(self):  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def connect(url: str):  # type: ignore[no-untyped-def]
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            self.queues.append(queue)

            async def frames():  # type: ignore[no-untyped-def]
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    yield item

            yield frames()

        return connect

    async def send(self, frame: str) -> None:
        await self.queues[-1].put(frame)
        await asyncio.sleep(0.01)

    async def drop(self) -> None:
        await self.queues[-1].put(None)
        await asyncio.sleep(0.05)


async def _service(tmp_path: Path, snapshots: list, **kw):  # type: ignore[no-untyped-def]
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    clock = {"ms": BASE_MS}
    calls = {"n": 0}

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return snapshots[min(calls["n"] - 1, len(snapshots) - 1)]

    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=lambda: clock["ms"])
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=1, now_ms=lambda: clock["ms"])
    service = MarketDataService("BTC-USD", stream=stream, fetch_snapshot=fetch_snapshot, recorder=recorder, resync_cooldown_s=0.01, now_ms=lambda: clock["ms"], **kw)
    return service, scripted, calls, clock


def _lines(path: str) -> list[dict]:  # type: ignore[type-arg]
    with gzip.open(path, "rt") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --------------------------------------------------------------------- round trip


async def test_a_recorded_segment_replays_to_the_recorded_book(tmp_path: Path) -> None:
    service, scripted, _calls, clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.0, 1.0), (99.0, 2.0)], [(101.0, 1.0), (102.0, 3.0)])])
    service.start()
    await asyncio.sleep(0.005)
    await scripted.send(_depth(96, 101, bids=[(100.0, 1.5)]))  # buffered, brackets the snapshot
    await asyncio.sleep(0.05)
    assert service.book.state is BookState.SYNCED
    for i in range(2, 12):
        clock["ms"] += 100
        await scripted.send(_depth(100 + i, 100 + i, bids=[(99.0 + i * 0.01, 0.5)], asks=[(102.0, 0.0)] if i == 5 else ()))
    await scripted.send(_trade(50, 100.5))
    await scripted.send(_trade(51, 100.6))
    await service.close()  # closing checkpoint + segment close

    segment = service.recorder.segments()[0]  # type: ignore[union-attr]
    kinds = [row["k"] for row in _lines(segment["path"])]
    assert "snapshot" in kinds and kinds[-1] == "checkpoint"
    assert kinds.index("snapshot") <= 1  # recorded right where the live sync met it
    manifest = segment["manifest"]
    assert manifest["snapshot_events"] == 1 and manifest["checkpoint_events"] == 1
    assert manifest["raw_bytes"] > manifest["bytes"] > 0
    assert manifest["replayable"] is True and manifest["sha256"]

    result = replay_segment(segment["path"])
    assert result.ok, result.reasons
    assert result.checksum == "ok"
    assert result.snapshots_applied == 1 and result.checkpoints_compared == 1
    assert result.checkpoint_mismatches == 0 and result.unregistered_gaps == 0
    assert result.trade_id_jumps == 0 and result.sequence_breaks == 0
    assert result.final_update_id == 111 == manifest["last_checkpoint_update_id"]
    assert result.digest_matches_manifest is True and result.final_matches_manifest is True
    assert result.best_bid == (100.0, 1.5) and result.levels_ask == 1  # 102.0 was removed at i == 5
    assert replay_directory(tmp_path, "BTC-USD")[0].ok


async def test_tampering_and_silent_loss_are_both_caught_by_the_replay(tmp_path: Path) -> None:
    service, scripted, _calls, clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)])])
    service.start()
    await asyncio.sleep(0.05)
    for i in range(1, 8):
        clock["ms"] += 100
        await scripted.send(_depth(100 + i, 100 + i, bids=[(100.0, 1.0 + i)]))
    await service.close()
    segment = service.recorder.segments()[0]  # type: ignore[union-attr]
    rows = _lines(segment["path"])
    # Remove one depth line in the middle: a loss the manifest never registered.
    kept = [r for r in rows if not (r["k"] == "depth" and r["u"] == 104)]
    with gzip.open(segment["path"], "wt") as fh:
        for r in kept:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    result = replay_segment(segment["path"])
    assert result.ok is False
    assert "integrity check failed" in result.reasons[0]  # checksum no longer matches
    assert result.gaps_in_replay == 1 and result.unregistered_gaps == 1
    assert any("not registered" in r for r in result.reasons)
    # After the unregistered gap the replayed book is invalid, so the closing checkpoint
    # can only be adopted, never compared: the loss shows up as the gap, not hidden by it.
    assert result.checkpoints_adopted == 1 and result.checkpoints_compared == 0


async def test_a_flagged_segment_is_refused_unless_allowed(tmp_path: Path) -> None:
    service, scripted, _calls, _clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)])])
    service.start()
    await asyncio.sleep(0.05)
    await scripted.send(_depth(101, 101))
    await scripted.drop()
    await asyncio.sleep(0.1)
    await service.close()
    segment = service.recorder.segments()[0]  # type: ignore[union-attr]
    assert segment["replayable"] is False
    refused = replay_segment(segment["path"])
    assert refused.ok is False and "flagged" in refused.reasons[0]
    allowed = replay_segment(segment["path"], allow_flagged=True)
    assert allowed.ok, allowed.reasons  # the re-sync snapshot is in the tape: it still rebuilds
    assert allowed.snapshots_applied == 2


# --------------------------------------------------------------------- stall injection


async def test_an_injected_stall_is_detected_as_stale_then_as_a_gap_then_resynced(tmp_path: Path) -> None:
    service, scripted, calls, clock = await _service(
        tmp_path,
        [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)]), snapshot_from_levels(300, [(100.5, 1.0)], [(101.5, 1.0)])],
    )
    service.start()
    await asyncio.sleep(0.05)
    await scripted.send(_depth(101, 101))
    assert service.usable
    service.hold(3.0)
    assert service.hold_active
    for i in range(2, 6):  # the venue keeps sending; we ignore it on purpose
        clock["ms"] += 600
        await scripted.send(_depth(100 + i, 100 + i))
    assert service.held_events == 4
    snap = service.snapshot()
    assert snap["usable"] is False and "old" in snap["not_usable_reason"]
    clock["ms"] += 1_500  # the hold is over; the next event reveals the gap
    assert not service.hold_active
    await scripted.send(_depth(150, 151))
    assert service.book.metrics.gaps == 1 and service.stale_episodes == 1
    await asyncio.sleep(0.1)
    assert calls["n"] >= 2 and service.book.update_id >= 300
    await scripted.send(_depth(301, 301))
    assert service.usable
    await service.close()
    manifest = service.recorder.segments()[0]["manifest"]  # type: ignore[union-attr]
    assert manifest["faults_injected"] and manifest["book_gaps"] == 1
    assert manifest["replayable"] is False
    assert any("fault injected" in r for r in manifest["not_replayable_reasons"])
    assert service.processing_us.count >= 1


# --------------------------------------------------------------------- recorder details


def test_book_state_lines_carry_the_whole_book_and_open_the_next_hour(tmp_path: Path) -> None:
    clock = {"ms": BASE_MS}
    state = BookStateEvent(update_id=7, bids=((100.0, 1.0),), asks=((101.0, 2.0),), received_at_ms=BASE_MS, digest="abc")
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=1, now_ms=lambda: clock["ms"], checkpoint_source=lambda: state)
    recorder.record("snapshot", state)
    recorder.note_fault("test fault")
    clock["ms"] += 3_600_000  # the next hour opens with a checkpoint first
    recorder.record("trade", type("T", (), {"trade_id": 1, "price": 100.0, "quantity": 1.0, "buyer_is_maker": False, "trade_time_ms": 1, "event_time_ms": 2, "received_at_ms": clock["ms"]})())
    recorder.close()
    first, second = recorder.segments()
    rows = _lines(first["path"])
    # Every hour opens with the book the source hands over, then the events follow.
    assert rows[0]["k"] == "checkpoint"
    assert rows[1] == {"k": "snapshot", "R": BASE_MS, "id": 7, "b": [[100.0, 1.0]], "a": [[101.0, 2.0]], "sha": "abc"}
    assert first["manifest"]["faults_injected"] == ["test fault"] and first["manifest"]["replayable"] is False
    rows = _lines(second["path"])
    assert [r["k"] for r in rows] == ["checkpoint", "trade"]
    assert second["manifest"]["checkpoint_events"] == 1 and second["manifest"]["last_checkpoint_digest"] == "abc"


# --------------------------------------------------------------------- connection accounting


async def test_drops_and_connect_failures_are_counted_apart() -> None:
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=lambda: BASE_MS)
    seen: list[str] = []
    stream.subscribe(lambda kind, _event: seen.append(kind))
    stream.start()
    await asyncio.sleep(0.02)
    await scripted.drop()
    status = stream.status()
    assert status.connections == 2 and status.disconnects == 1 and status.connect_failures == 0
    assert seen == ["disconnect"]
    await stream.close()

    attempts = {"n": 0}

    @asynccontextmanager
    async def failing(url: str):  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        raise ConnectionError("refused")
        yield  # pragma: no cover

    broken = MarketDataStream("BTC-USD", connector=failing, now_ms=lambda: BASE_MS)
    broken.subscribe(lambda kind, _event: seen.append(kind))
    broken.start()
    await asyncio.sleep(0.05)
    await broken.close()
    status = broken.status()
    assert attempts["n"] >= 2 and status.connect_failures >= 2 and status.disconnects == 0
    assert seen == ["disconnect"]  # a failed connect is not a disconnect: nothing was up


@pytest.mark.parametrize("kind", ["snapshot", "checkpoint"])
def test_a_segment_holding_only_book_state_still_replays(tmp_path: Path, kind: str) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: BASE_MS)
    recorder.record(kind, BookStateEvent(update_id=5, bids=((100.0, 1.0),), asks=((101.0, 1.0),), received_at_ms=BASE_MS))
    recorder.close()
    result = replay_segment(recorder.segments()[0]["path"])
    assert result.ok, result.reasons
    assert result.final_update_id == 5 and result.final_valid
