"""SYNTHETIC adversarial scenarios for the live market-making service's safety state.

Fake venue, fake stream, simulated clock: evidence about our invariants under hostile
timing, never about Binance. Each scenario attacks one rule of the safety model documented
in ``docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md`` §11:

* a reconciliation reads the venue at one instant and the local picture later; what the
  maker did in between is not a discrepancy;
* a critical finding engages the kill switch sticky and stop() still completes with the
  first cause kept and nothing left open;
* an order whose fate was unknown and that the venue confirms never existed releases the
  transient condition on its own — UNKNOWN → reconcile → resolved — and quoting resumes;
* a fill the venue reports is reconciled clean: the ledger and the account agree.
"""

from __future__ import annotations

import asyncio

from tests.unit.mm.test_mm_live_service import _delayed_snapshot, _live, _teardown


async def test_an_order_acknowledged_after_the_venue_snapshot_is_not_reported_missing() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    await live.until_resting()
    await _delayed_snapshot(venue, 0.15)
    task = asyncio.create_task(service.reconcile())
    await asyncio.sleep(0.02)  # snapshot taken; now requote: the old quotes close, new ones rest
    service.execution.cancel_all(live.clock.timestamp_ms(), reason="requote")
    for _ in range(4):
        await asyncio.sleep(0.01)
        service.engine.on_event("tick", None, live.clock.timestamp_ms())
    await live.feed(4)
    report = await task
    kinds = {i["kind"] for i in report.discrepancies}
    assert "local_order_missing_at_venue" not in kinds  # acknowledged after the picture: cannot be in it
    assert "venue_order_unknown_locally" not in kinds and not report.critical
    assert not service.kill.engaged
    await _teardown(live)


async def test_a_sticky_kill_from_a_critical_finding_survives_to_stop_with_its_first_cause_and_nothing_open() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    await live.until_resting()
    venue.add_foreign_open_order("someone-else-9")  # someone else trades this account
    report = await service.reconcile()
    assert report.critical and "foreign_open_order" in report.summary
    assert service.kill.engaged and service.kill.sticky and service.kill.trigger == "reconciliation"
    await live.feed(4)  # the maker places nothing under a sticky kill
    assert service.execution.open_orders() == [] and service.state_label == "safe"
    placed_before = service.execution.counters["placed"]
    await live.feed(4)
    assert service.execution.counters["placed"] == placed_before
    status = await service.stop(reason="operator", actor="test")
    kill = status["kill_switch"]
    assert kill["trigger"] == "reconciliation" and kill["sticky"]  # the first cause is kept; the stop is in the history
    assert any(h["trigger"] == "stop" for h in kill["history"])
    assert status["open_orders"] == [] and not any(not o.state.is_terminal for o in venue.orders.values())
    await live.market.close()


async def test_an_unknown_order_the_venue_confirms_never_arrived_releases_the_transient_condition_and_quoting_resumes() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    venue.next_submit = ["timeout"]  # the first submission's answer never comes back
    await live.feed(2)
    await asyncio.sleep(0.05)
    service.engine.on_event("tick", None, live.clock.timestamp_ms())
    c = service.execution.counters
    assert c["unknown"] >= 1
    await live.feed(6)  # the resolution answers "never arrived"; the condition clears itself
    assert service.execution.unknown_orders() == [] and service.execution.blocked_reason == ""
    assert not service.kill.engaged, service.kill.as_dict()
    assert c["resolved_absent"] >= 1 and c["unknown"] >= 1
    await live.until_resting()  # quoting resumed through the real path
    assert service.state_label in ("quoting", "no_quote")
    await _teardown(live)


async def test_a_fill_the_venue_reports_reconciles_clean_and_the_ledger_agrees_with_the_account() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    [cid, *_] = await live.until_resting()
    order = venue.orders[cid]
    venue.venue_fill(cid, order.quantity)
    await live.feed(4)  # the trade poll books it; the engine sees the fill
    ledger = service.live_ledger.snapshot()
    assert ledger["fills"] == 1 and abs(abs(ledger["inventory_btc"]) - order.quantity) < 1e-12
    report = await service.reconcile()
    assert report.ok and not report.critical, report.as_dict()
    assert abs(report.balances["expected_base_btc"] - report.balances["venue_base_btc"]) <= 2e-5
    assert abs(report.balances["expected_quote_usd"] - report.balances["venue_quote_usd"]) <= 0.5
    assert not service.kill.engaged
    await _teardown(live)
