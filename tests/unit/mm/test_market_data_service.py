"""The service runs the documented sync end to end: buffers, snapshots, applies, resyncs
on a gap, invalidates on a disconnect, and records everything with its verdict."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from tia.mm.market_data import MarketDataService
from tia.mm.order_book import BookState, snapshot_from_levels
from tia.mm.recorder import TickRecorder
from tia.mm.streams import MarketDataStream


def _depth(U: int, u: int, bids=(), asks=()) -> str:  # type: ignore[no-untyped-def]
    return json.dumps({"stream": "s@depth@100ms", "data": {"e": "depthUpdate", "E": 1_000 + u, "s": "BTCUSDT", "U": U, "u": u, "b": [[str(p), str(q)] for p, q in bids], "a": [[str(p), str(q)] for p, q in asks]}})


def _trade(t: int, price: float) -> str:
    return json.dumps({"stream": "s@trade", "data": {"e": "trade", "E": 2_000 + t, "s": "BTCUSDT", "t": t, "p": str(price), "q": "0.1", "T": 1_990 + t, "m": False, "M": True}})


class Scripted:
    """A connector whose frames the test feeds by hand, connection by connection."""

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


async def _service(tmp_path: Path, snapshots: list):  # type: ignore[no-untyped-def]
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    clock = {"ms": 1_700_000_000_000}
    calls = {"n": 0}

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return snapshots[min(calls["n"] - 1, len(snapshots) - 1)]

    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=lambda: clock["ms"])
    recorder = TickRecorder(tmp_path, "BTC-USD", flush_lines=1, now_ms=lambda: clock["ms"])
    service = MarketDataService("BTC-USD", stream=stream, fetch_snapshot=fetch_snapshot, recorder=recorder, resync_cooldown_s=0.01, now_ms=lambda: clock["ms"])
    return service, scripted, calls, clock


async def test_the_book_syncs_from_a_snapshot_then_follows_the_stream(tmp_path: Path) -> None:
    service, scripted, calls, _clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)])])
    service.start()
    await asyncio.sleep(0.05)
    assert calls["n"] >= 1
    assert service.book.state is BookState.SYNCED and service.book.update_id == 100
    await scripted.send(_depth(101, 102, bids=[(100.0, 2.0)]))
    await scripted.send(_trade(7, 100.5))
    assert service.book.best_bid() == (100.0, 2.0)
    assert service.trade_events == 1 and service.last_trade.trade_id == 7
    snap = service.snapshot()
    assert snap["usable"] is True and snap["book"]["metrics"]["rebuilds"] == 1
    assert snap["recorder"]["events_written"] >= 2
    await service.close()


async def test_a_gap_triggers_an_automatic_rebuild_and_marks_the_recording(tmp_path: Path) -> None:
    service, scripted, calls, _clock = await _service(
        tmp_path,
        [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)]), snapshot_from_levels(110, [(100.0, 5.0)], [(101.0, 5.0)])],
    )
    service.start()
    await asyncio.sleep(0.05)
    await scripted.send(_depth(101, 101))
    await scripted.send(_depth(105, 106))  # 102..104 never arrived
    assert service.book.metrics.gaps == 1
    await asyncio.sleep(0.1)  # the resync loop fetches the second snapshot
    assert calls["n"] >= 2
    assert service.book.state is BookState.SYNCED and service.book.update_id >= 110
    assert service.book.best_bid() == (100.0, 5.0)
    assert service.resyncs >= 2
    service.recorder.close()  # type: ignore[union-attr]
    manifest = service.recorder.segments()[0]["manifest"]  # type: ignore[union-attr]
    assert manifest["book_gaps"] == 1 and manifest["replayable"] is False
    await service.close()


async def test_a_disconnect_invalidates_and_the_reconnect_resyncs(tmp_path: Path) -> None:
    service, scripted, calls, _clock = await _service(
        tmp_path,
        [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)]), snapshot_from_levels(200, [(99.0, 1.0)], [(102.0, 1.0)])],
    )
    service.start()
    await asyncio.sleep(0.05)
    assert service.usable
    await scripted.drop()
    assert service.stream.status().reconnects >= 1
    await asyncio.sleep(0.15)
    assert calls["n"] >= 2
    assert service.book.update_id == 200 and service.book.best_ask() == (102.0, 1.0)
    assert service.snapshot()["recorder"]["current_manifest"]["disconnects"] >= 1
    await service.close()


async def test_stale_data_makes_the_service_unusable_and_says_why(tmp_path: Path) -> None:
    service, scripted, _calls, clock = await _service(tmp_path, [snapshot_from_levels(100, [(100.0, 1.0)], [(101.0, 1.0)])])
    service.start()
    await asyncio.sleep(0.05)
    await scripted.send(_depth(101, 101))
    assert service.usable
    clock["ms"] += 5_000
    assert service.usable is False
    assert "old" in service.snapshot()["not_usable_reason"]
    await service.close()
