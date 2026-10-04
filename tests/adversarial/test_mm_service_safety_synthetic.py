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
    assert kill["trigger"] == "reconciliation" and kill["sticky"] and kill["engaged"]  # the safety finding stays visible, first cause kept
    assert kill["shutdown"]["reason"] == "operator (by test)" and any(h["action"] == "shutdown" for h in kill["history"])
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


async def test_the_whole_life_of_a_submission_whose_answer_timed_out_after_the_venue_accepted_it() -> None:
    """SUBMIT UNKNOWN → RESOLVE → FOUND → ADOPT, and never SUBMIT UNKNOWN → RETRY. The venue
    accepted the order and the answer never came back: the order is UNKNOWN, quoting is
    blocked, the venue is asked by our client id, the order is found resting, adopted with
    the venue's orderId, acknowledged once, and later cancelled through the venue like any
    other. One submission at the venue, one order, no duplicate."""
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    venue.next_submit = ["timeout_after_accept"]
    await live.feed(2)
    await asyncio.sleep(0.05)
    service.engine.on_event("tick", None, live.clock.timestamp_ms())
    c = service.execution.counters
    assert c["unknown"] >= 1 and c["resolved_present"] >= 1
    assert venue.calls.count("submit") == c["submitted"] and len(venue.submits) == c["submitted"]
    adopted = list(service.execution.closed) + list(service.execution.orders.values())
    first = min(adopted, key=lambda o: o.t_enqueued_ms or 0)
    assert first.venue_order_id and first.ack_source in ("resolve", "stream", "rest", "sync")
    await live.feed(8)  # TTL and requotes: the adopted order is cancelled through the venue
    assert first.state in ("cancelled", "filled") and first.closed
    assert venue.cancels.count(first.order_id) <= 1
    assert not service.kill.engaged and service.execution.blocked_reason == "" and service.execution.unknown_orders() == []
    assert len({o.client_order_id for o in venue.orders.values()}) == len(venue.orders)  # one venue order per client id
    await _teardown(live)


async def test_a_just_acknowledged_order_absent_from_an_older_open_orders_picture_is_not_asked_about() -> None:
    """The open-orders sync is a picture with an instant. An order acknowledged after that
    instant cannot be in it and is not 'missing'; one acknowledged before it and absent is
    asked about once, found resting, and nothing changes."""
    from tests.unit.mm.test_mm_execution_live import _harness, _quote

    h = await _harness()
    [older] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    snapshot_t = h.tick(50)
    [newer] = h.execution.place(_quote(bid=99_990.0, ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert older.state == "resting" and newer.state == "resting" and newer.t_ack_ms >= snapshot_t
    c = h.execution.counters
    resolves_before = h.venue.calls.count("resolve")
    h.execution.absorb_open_orders([], snapshot_t_ms=snapshot_t)  # a picture from before both were... only the older one should have been in it
    await h.settle()
    assert c["missing_at_venue"] == 1  # the older one is asked about; the newer one is not
    assert h.venue.calls.count("resolve") == resolves_before + 1
    assert older.state == "resting" and newer.state == "resting" and c["resolved_present"] == 1
    assert h.execution.open_orders() and h.execution.blocked_reason == ""
    await h.execution.close()


async def test_a_restart_after_a_run_died_with_orders_open_leaves_no_orphan_and_duplicates_nothing() -> None:
    """The first run is killed with quotes resting: no stop(), no cancel. The second run on the
    same account finds them under its own prefix, cancels them before quoting, reconciles
    clean, quotes with its own ids, and stops with nothing open. No client id is ever
    submitted twice; no order of the dead run is adopted or resent."""
    from tia.mm.execution import CLIENT_ID_PREFIX

    first = await _live(run_id="run-one")
    venue = first.venue
    await first.service.start_live()
    left = await first.until_resting()
    # The process dies: the engine stops hearing the market, the loops end, the worker goes.
    if first.service._unsubscribe is not None:
        first.service._unsubscribe()
        first.service._unsubscribe = None
    for task in (first.service._reconcile_task, first.service._heartbeat_task):
        if task is not None:
            task.cancel()
    await first.service.execution.close()
    assert [cid for cid, o in venue.orders.items() if not o.state.is_terminal] == left  # the venue still holds them

    second = await _live(venue=venue, run_id="run-two")
    report = await second.service.start_live()
    sweep = second.service.orphan_sweep
    assert sweep is not None and sweep["found"] == left and [c["order_id"] for c in sweep["cancelled"]] == left and sweep["failed"] == []
    assert not report.critical and not second.service.kill.engaged, report.as_dict()
    assert all(venue.orders[cid].state.is_terminal for cid in left)
    await second.until_resting()
    own = f"{CLIENT_ID_PREFIX}{second.service.execution.run_tag[:8]}"
    resting = [cid for cid, o in venue.orders.items() if not o.state.is_terminal]
    assert resting and all(cid.startswith(own) for cid in resting)
    submitted = [i.client_order_id for i in venue.submits]
    assert len(submitted) == len(set(submitted))  # no client id submitted twice across both runs
    assert second.service.execution.counters["venue_orders_unknown_locally"] == 0
    status = await second.service.stop(reason="drill", actor="test")
    assert status["open_orders"] == [] and not any(not o.state.is_terminal for o in venue.orders.values())
    assert status["kill_switch"]["shutdown"] and not status["kill_switch"]["engaged"]
    await first.market.close()
    await second.market.close()
