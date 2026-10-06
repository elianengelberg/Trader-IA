"""Clocks kept apart. The venue's timestamps (trade time, acceptance time) are only ever
compared with each other; host durations only use host stamps; the handover snapshot a new
subscriber receives is recorded with its age instead of looking like a slow decision.
Fake venue, simulated clock, synthetic tape: nothing here is about Binance."""

from __future__ import annotations

from datetime import timedelta

import pytest

from tests.unit.mm.test_engine_replay import PROFILE, _config, _gate, _run, _tape
from tests.unit.mm.test_mm_execution_live import _quote, _streamed
from tests.unit.mm.test_mm_live_service import _live, _teardown
from tia.domain.enums import OrderState
from tia.mm.engine import MarketMakerEngine
from tia.mm.execution import LiveFill, LiveOrder


async def _filled_through_the_stream(venue_offset_ms: int):  # type: ignore[no-untyped-def]
    """An ask rests (REST acknowledgement, host clock), then the venue reports the trade with
    its own clock shifted by ``venue_offset_ms`` from the host's. Returns the order and the
    fill the adapter handed to the engine."""
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.t_ack_ms is not None and order.venue_ack_time_ms is not None
    venue_ack_dt = h.clock.now() - timedelta(milliseconds=300) + timedelta(milliseconds=venue_offset_ms)  # the venue's clock, shifted
    order.venue_ack_time_ms = int(venue_ack_dt.timestamp() * 1000)  # what the venue's NEW report would have said on its clock
    h.tick(400)  # the order rests 400 ms of host time
    trade_dt = venue_ack_dt + timedelta(milliseconds=250)  # on the venue's clock the trade came 250 ms after acceptance
    fill = h.venue.venue_fill(order.order_id, order.quantity, at=trade_dt)
    stream.report(order.order_id, execution_type="trade", status=OrderState.FILLED, last_qty=order.quantity, last_price=fill.price, trade_id=fill.fill_id, at=trade_dt)
    [live_fill] = h.execution.on_event("depth", None, h.book, h.tick(10))
    return h, order, live_fill


@pytest.mark.parametrize("venue_offset_ms", [-5_000, -74, 0, 123, 5_000])
async def test_host_resting_never_mixes_the_venue_clock_in_and_the_venue_resting_only_uses_venue_stamps(venue_offset_ms: int) -> None:
    h, order, fill = await _filled_through_the_stream(venue_offset_ms)
    assert fill.t_ms == order.venue_ack_time_ms + 250  # the venue's trade time, on the venue's clock
    assert fill.received_at_ms >= order.t_ack_ms  # host receipt after host acknowledgement, whatever the venue's clock says
    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("optimistic"), gate=_gate(), execution=h.execution)
    engine._on_fill(fill, h.t)
    [record] = engine.fill_records
    assert record["host_resting_ms"] == fill.received_at_ms - order.t_ack_ms and record["host_resting_ms"] >= 400
    assert record["venue_resting_ms"] == 250
    assert record["resting_ms"] == record["host_resting_ms"]
    assert record["venue_ack_time_ms"] == order.venue_ack_time_ms and record["t_decided_host_ms"] == order.t_decided_host_ms
    assert record["event_age_at_decision_ms"] == order.t_decided_host_ms - order.t_decision_ms >= 0
    await h.execution.close()


async def test_host_durations_are_identical_whatever_the_venue_clock_offset() -> None:
    results = {}
    for offset in (-5_000, -74, 0, 5_000):
        h, order, fill = await _filled_through_the_stream(offset)
        results[offset] = (fill.received_at_ms - order.t_ack_ms, fill.t_ms - order.venue_ack_time_ms)
        await h.execution.close()
    hosts = {v[0] for v in results.values()}
    venues = {v[1] for v in results.values()}
    assert len(hosts) == 1 and len(venues) == 1 and venues == {250}


async def test_a_fill_reported_before_any_acknowledgement_has_no_resting_time_rather_than_a_negative_one() -> None:
    order = LiveOrder(order_id="tiamm-x-1", side="buy", price=100.0, quantity=1.0, t_decision_ms=1_000, ttl_ms=30_000, reason="t")
    order.state = "filled"
    order.t_enqueued_ms = 1_002
    fill = LiveFill(fill_id="7", order_id=order.order_id, side="buy", price=100.0, quantity=1.0, t_ms=1_050, venue_trade_ids=(7,), received_at_ms=1_180, attribution_source="report")
    order.fills.append(fill)
    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("optimistic"), gate=_gate())
    engine.execution.orders[order.order_id] = order  # type: ignore[index]
    engine._on_fill(fill, 1_180)
    [record] = engine.fill_records
    assert record["t_ack_ms"] is None and record["host_resting_ms"] is None and record["venue_resting_ms"] is None and record["resting_ms"] is None


async def test_the_handover_snapshot_age_is_recorded_as_an_anomaly_and_the_decision_delay_stays_host_only() -> None:
    """The 982 ms of the 2026-10-06 run: the book's last update was 982 ms old when the
    service subscribed; the handover snapshot carried that stamp, so the first decision's
    event age was 982 ms while the callback itself took a few milliseconds."""
    live = await _live()
    service = live.service
    live.clock.advance_by(timedelta(milliseconds=982))  # the feed stays silent while the service prepares to start
    await service.start_live()
    [first, *_] = service.timing_anomalies
    assert first["kind"] == "snapshot" and first["handover"] is True and first["n"] == 1
    assert first["event_age_at_callback_ms"] == 982 and first["callback_ms"] < 200
    status = service.status()
    assert status["latency"]["event_age_at_callback_ms"]["max_ms"] == 982 and status["latency"]["market_event_to_processed_ms"]["max_ms"] >= 982
    assert status["latency"]["callback_ms"]["max_ms"] < 200
    sync = live.market.snapshot(levels=1)["sync"]
    assert sync["handovers"] == 1 and sync["last_handover_age_ms"] == 982
    if first["quotes_placed"]:
        orders = sorted(service.execution.orders.values(), key=lambda o: o.t_enqueued_ms or 0)
        o = orders[0]
        assert o.t_decided_host_ms - o.t_decision_ms == 982  # the market information was 982 ms old
        assert o.t_enqueued_ms - o.t_decided_host_ms == 0  # the host decision-to-enqueue was immediate
        assert status["latency"]["decision_to_enqueue_ms"]["max_ms"] == 982  # the documented event-stamp meaning, now explained by the anomaly
    assert status["timing"]["anomaly_threshold_ms"] == 200 and status["timing"]["market_events"] >= 1
    await _teardown(live)


async def test_a_fresh_handover_records_no_anomaly() -> None:
    live = await _live()
    await live.service.start_live()
    assert live.service.timing_anomalies == live.service.timing_anomalies.__class__(maxlen=200) or len(live.service.timing_anomalies) == 0
    assert live.market.snapshot(levels=1)["sync"]["handovers"] == 1 and live.market.snapshot(levels=1)["sync"]["last_handover_age_ms"] == 0
    await _teardown(live)


def test_the_paper_path_keeps_one_clock_and_the_golden_journal_hashes() -> None:
    from tests.unit.mm.test_markout_raw_export import GOLDEN

    engine = _run(_tape(40))
    assert engine.journal_hash() == GOLDEN[40]
    [record] = engine.fill_records
    assert record["host_resting_ms"] == record["resting_ms"] > 0 and record["venue_resting_ms"] is None  # a simulated venue has no clock of its own
    assert record["event_age_at_decision_ms"] is None or record["event_age_at_decision_ms"] >= 0
