"""Freshness of the market data: receive age against venue age, and the states between.

A book can be rebuilt exactly and still describe a market that no longer exists. These
tests feed a scripted stream with explicit venue event times so that ``receive_age`` (how
long since the last event arrived) and ``venue_age`` (how old that event already was when
the venue emitted it) can be pulled apart, and check that only a FRESH book is usable.
Every frame here is synthetic; the venue event time E is a number the test chooses.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tests.unit.mm.test_replay import Scripted
from tia.mm.market_data import PROVISIONAL_MAX_VENUE_AGE_S, Freshness, MarketDataService
from tia.mm.order_book import BookState, snapshot_from_levels
from tia.mm.streams import MarketDataStream

T0 = 1_790_000_000_000


def _depth(U: int, u: int, E: int, bids=(), asks=()) -> str:  # type: ignore[no-untyped-def]
    return json.dumps({"stream": "s@depth@100ms", "data": {"e": "depthUpdate", "E": E, "s": "BTCUSDT", "U": U, "u": u, "b": [[str(p), str(q)] for p, q in bids], "a": [[str(p), str(q)] for p, q in asks]}})


def _depth_without_E(U: int, u: int) -> str:
    return json.dumps({"stream": "s@depth@100ms", "data": {"e": "depthUpdate", "s": "BTCUSDT", "U": U, "u": u, "b": [], "a": []}})


def _ticker(u: int, bid: float, ask: float) -> str:
    return json.dumps({"stream": "s@bookTicker", "data": {"u": u, "s": "BTCUSDT", "b": str(bid), "B": "1", "a": str(ask), "A": "1"}})


async def _service(tmp_path: Path, **kw):  # type: ignore[no-untyped-def]
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    clock = {"ms": T0}

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        return snapshot_from_levels(100, [(100.0, 1.0)], [(100.01, 1.0)])

    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=lambda: clock["ms"])
    service = MarketDataService("BTC-USD", stream=stream, fetch_snapshot=fetch_snapshot, recorder=None, resync_cooldown_s=0.01, now_ms=lambda: clock["ms"], **kw)
    service.start()
    await asyncio.sleep(0.05)
    assert service.book.is_valid
    return service, scripted, clock


async def test_a_batch_that_was_old_at_the_venue_is_stale_venue_even_though_it_just_arrived(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 3_000))  # emitted 3 s ago, received now
    state, reason = service.freshness()
    assert state is Freshness.STALE_VENUE and service.usable is False
    assert "venue data 3.0s old" in reason and "PROVISIONAL" in reason
    snap = service.snapshot()
    assert snap["freshness"]["receive_age_s"] == 0.0 and snap["freshness"]["venue_age_s"] == 3.0
    assert snap["receive_age_s"] == 0.0 and snap["venue_age_s"] == 3.0 and snap["data_age_s"] == 0.0
    assert snap["freshness"]["stale_venue_episodes"] == 1
    assert snap["freshness"]["max_venue_age_s"] == PROVISIONAL_MAX_VENUE_AGE_S
    assert "PROVISIONAL" in snap["freshness"]["max_venue_age_status"]
    await service.close()


async def test_silence_is_stale_receive_and_is_judged_before_venue_age(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 100))
    assert service.freshness()[0] is Freshness.FRESH and service.usable
    clock["ms"] += 5_000
    state, reason = service.freshness()
    assert state is Freshness.STALE_RECEIVE and service.usable is False
    assert reason == "data 5.0s old, over 2.0s"
    snap = service.snapshot()
    assert snap["freshness"]["receive_age_s"] == 5.0 and snap["freshness"]["venue_age_s"] == 5.1
    await service.close()


async def test_a_stream_without_venue_time_gets_no_venue_age_invented(tmp_path: Path) -> None:
    service, scripted, _clock = await _service(tmp_path)
    # Right after the REST snapshot nothing carries E: venue age is unknown, not zero.
    snap = service.snapshot()
    assert snap["freshness"]["venue_age_s"] is None and snap["freshness"]["venue_age_source"] is None
    assert service.freshness()[0] is Freshness.FRESH
    # bookTicker carries no E either: tracked for its sequence, never for an age.
    await scripted.send(_ticker(105, 100.0, 100.01))
    await scripted.send(_ticker(110, 100.02, 100.03))
    assert service.venue_age_s() is None and service.snapshot()["latency"]["ticker_lead_ms_at_batch_arrival"]["count"] == 0
    # A depth event without E leaves venue age unknown as well.
    await scripted.send(_depth_without_E(101, 105))
    assert service.book.update_id == 105 and service.venue_age_s() is None
    assert service.freshness()[0] is Freshness.FRESH
    await service.close()


async def test_gap_and_syncing_are_integrity_states_not_staleness(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 100))
    assert service.freshness()[0] is Freshness.FRESH
    await scripted.send(_depth(150, 151, E=clock["ms"] - 100))  # 102..149 never arrived
    state, reason = service.freshness()
    assert state is Freshness.GAP and "gap" in reason and service.usable is False
    assert service.book.state in (BookState.OUT_OF_SYNC, BookState.SYNCING)
    await asyncio.sleep(0.1)  # the resync loop fetches the snapshot (id 100) and retries
    # The scripted snapshot is older than the buffered stream, so the book keeps syncing.
    state, reason = service.freshness()
    assert state in (Freshness.SYNCING, Freshness.GAP) and service.usable is False
    await service.close()


async def test_fresh_to_stale_venue_to_fresh_is_counted_as_two_transitions(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 100))
    assert service.freshness()[0] is Freshness.FRESH
    clock["ms"] += 100
    await scripted.send(_depth(102, 102, E=clock["ms"] - 2_500))  # venue lagged 2.5 s
    assert service.freshness()[0] is Freshness.STALE_VENUE and service.usable is False
    clock["ms"] += 100
    await scripted.send(_depth(103, 103, E=clock["ms"] - 120))  # the venue caught up
    assert service.freshness()[0] is Freshness.FRESH and service.usable
    snap = service.snapshot()["freshness"]
    assert snap["transitions"] == 2 and snap["stale_venue_episodes"] == 1
    assert snap["last_change_ms"] == clock["ms"]
    await service.close()


async def test_ticker_lead_is_measured_at_each_batch_arrival_without_any_clock(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_ticker(105, 100.0, 100.01))
    clock["ms"] += 20
    await scripted.send(_ticker(110, 100.02, 100.03))
    clock["ms"] += 70
    await scripted.send(_depth(101, 105, E=clock["ms"] - 100))  # the batch the first ticker belonged to
    lat = service.snapshot()["latency"]
    assert lat["ticker_lead_updates_at_batch_arrival"]["last_ms"] == 5  # 110 - 105 updates ahead
    assert lat["ticker_lead_ms_at_batch_arrival"]["last_ms"] == 70  # ticker 110 arrived 70 ms before
    clock["ms"] += 100
    await scripted.send(_depth(106, 110, E=clock["ms"] - 100))
    lat = service.snapshot()["latency"]
    assert lat["ticker_lead_updates_at_batch_arrival"]["last_ms"] == 0 and lat["ticker_lead_ms_at_batch_arrival"]["last_ms"] == 0
    assert lat["ticker_lead_ms_at_batch_arrival"]["count"] == 2
    await service.close()


async def test_the_venue_rule_can_be_disabled_to_report_only(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path, max_venue_age_s=None)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 8_000))
    assert service.freshness()[0] is Freshness.FRESH and service.usable
    snap = service.snapshot()["freshness"]
    assert snap["venue_age_s"] == 8.0 and snap["max_venue_age_s"] is None and "disabled" in snap["max_venue_age_status"]
    await service.close()


async def test_a_measured_clock_offset_is_applied_and_never_estimated(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path, venue_clock_offset_ms=2_000.0)  # host clock 2 s ahead
    await scripted.send(_depth(101, 101, E=clock["ms"] - 2_100))
    assert service.venue_age_s() == 0.1 and service.freshness()[0] is Freshness.FRESH
    assert service.snapshot()["freshness"]["venue_clock_offset_status"] == "configured"
    await service.close()
    plain, scripted2, clock2 = await _service(tmp_path)
    await scripted2.send(_depth(101, 101, E=clock2["ms"] - 2_100))
    assert plain.venue_age_s() == 2.1 and plain.freshness()[0] is Freshness.STALE_VENUE
    assert "not measured" in plain.snapshot()["freshness"]["venue_clock_offset_status"]
    await plain.close()


async def test_a_disconnect_outranks_every_other_state(tmp_path: Path) -> None:
    service, scripted, clock = await _service(tmp_path)
    await scripted.send(_depth(101, 101, E=clock["ms"] - 100))
    seen: list[tuple[str, Freshness, str, bool]] = []
    # The scripted stream reconnects within milliseconds, so the state is read at the
    # moment the disconnect is processed: through a consumer, the way the maker sees it.
    service.subscribe(lambda kind, event, t_ms: seen.append((kind, *service.freshness(), service.usable)) if kind == "disconnect" else None)
    await scripted.drop()
    assert seen and seen[0][1] is Freshness.DISCONNECTED and seen[0][2] == "stream disconnected" and seen[0][3] is False
    await asyncio.sleep(0.1)  # reconnected and resynced: fresh again, two transitions counted
    assert service.freshness()[0] is Freshness.FRESH
    assert service.snapshot()["freshness"]["transitions"] >= 2
    await service.close()
