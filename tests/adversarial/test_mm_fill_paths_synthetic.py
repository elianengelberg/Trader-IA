"""SYNTHETIC adversarial scenarios for the live market maker's fill and order-state paths.

Everything here runs against ``FakeVenue`` and ``FakeUserStream`` (tests/unit/mm/fake_venue.py).
It is evidence about *our* invariants under hostile orderings — never evidence about how
Binance behaves. Each scenario is built to break one invariant: a fill booked twice, a fill
lost, a terminal order reopened, a cancel sent twice, a state the venue never confirmed.

Invariants under attack:

* a venue trade id is booked once, whichever source names it first and however many times
  it is named afterwards (report then history, history then report, after a reconnect);
* a fill the account stream never delivered still reaches the ledger through the history,
  including after the order was closed by a CANCELED report that carried executed quantity;
* a report that arrives before any acknowledgement (REST still in flight, no NEW seen) is
  applied as what it says, and the late REST answer cannot undo it;
* a terminal order stays terminal: a replayed NEW never reopens it;
* a cancel asked for twice (and a cancel_all on top) reaches the venue once.
"""

from __future__ import annotations

import asyncio

from tests.unit.mm.test_mm_execution_live import _quote, _streamed
from tia.domain.enums import OrderState


async def test_a_trade_the_history_booked_first_is_not_booked_again_when_its_report_arrives() -> None:
    """History then report: the reverse of the usual order. The report is the duplicate."""
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    fill = h.venue.venue_fill(order.order_id, 0.001)  # the venue traded; its report is delayed
    await h.settle()  # the trade poll finds it first
    c = h.execution.counters
    assert c["fills"] == 1 and c["trade_poll_fills"] == 1 and order.state == "filled" and order.closed
    stream.report(order.order_id, execution_type="trade", status=OrderState.FILLED, last_qty=0.001, last_price=fill.price, trade_id=fill.fill_id, is_maker=True, cumulative_qty=0.001)
    assert c["fills"] == 1 and c["duplicate_trades"] >= 1 and order.state == "filled"
    assert sum(f.quantity for f in order.fills) == 0.001
    await h.execution.close()


async def test_a_partial_fill_whose_report_was_lost_is_recovered_from_the_history_after_the_cancel_closed_the_order() -> None:
    """The TRADE report never arrives; the CANCELED report that follows carries the
    executed quantity. The order closes as cancelled, and the fill is still owed."""
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting"
    h.venue.venue_fill(order.order_id, 0.0004)  # partial; the stream drops this one on the floor
    h.venue.venue_cancel(order.order_id)
    stream.report("web_cancel_42", execution_type="canceled", status=OrderState.CANCELLED, orig_client_order_id=order.order_id, venue_order_id=order.venue_order_id, cumulative_qty=0.0004)
    assert order.state == "cancelled" and order.closed
    assert order.venue_executed_qty == 0.0004 and order.filled == 0.0  # the venue said more than we booked
    await h.settle()  # the adapter asked for the history at once
    c = h.execution.counters
    assert c["fills"] == 1 and c["trade_poll_fills"] == 1 and order.filled == 0.0004
    assert order.state == "cancelled" and order.closed  # closed with a partial fill, as the venue has it
    await h.execution.close()


async def test_a_fill_reported_before_any_acknowledgement_is_applied_and_the_late_rest_answer_cannot_undo_it() -> None:
    """The REST submit is still in flight and the first word from the venue is a TRADE that
    fills the order (the NEW it sent first was lost). The order is acknowledged, filled and
    closed from that report; when the REST acknowledgement finally lands it changes nothing."""
    h, stream = await _streamed()
    h.venue.hang_seconds = 0.25
    h.venue.next_submit = ["hang"]
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await asyncio.sleep(0.02)
    assert order.state == "pending_arrival" and order.t_ack_ms is None
    stream.report(order.order_id, execution_type="trade", status=OrderState.FILLED, last_qty=0.001, last_price=99_999.9, trade_id="777001", is_maker=True, venue_order_id="7777", cumulative_qty=0.001)
    c = h.execution.counters
    assert order.state == "filled" and order.closed and order.ack_source == "stream" and order.filled == 0.001
    assert c["fills"] == 1 and c["report_fills"] == 1 and c["acked"] == 1 and c["reports_before_rest_ack"] == 1
    await asyncio.sleep(0.3)  # the REST acknowledgement arrives
    await h.settle()
    assert order.state == "filled" and c["fills"] == 1 and c["acked"] == 1 and h.execution.open_orders() == []
    assert h.execution.blocked_reason == ""
    await h.execution.close()


async def test_a_fill_during_a_stream_outage_is_booked_from_the_history_and_its_late_report_after_reconnect_is_a_duplicate() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    stream.drop()
    assert h.execution.stream_connected is False and any(k == "user_stream_down" for k, _ in h.criticals)
    fill = h.venue.venue_fill(order.order_id, 0.001)  # traded while the stream was down
    await h.settle()  # the history is the only source now, and it is read fast
    c = h.execution.counters
    assert c["fills"] == 1 and c["trade_poll_fills"] == 1 and order.state == "filled"
    stream.reconnect()
    assert h.execution.stream_connected is True
    stream.report(order.order_id, execution_type="trade", status=OrderState.FILLED, last_qty=0.001, last_price=fill.price, trade_id=fill.fill_id, is_maker=True, cumulative_qty=0.001)
    assert c["fills"] == 1 and c["duplicate_trades"] >= 1 and len(order.fills) == 1
    await h.execution.close()


async def test_a_replayed_new_report_never_reopens_a_cancelled_order() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.execution.cancel(order.order_id, h.t, reason="requote")
    await h.settle()
    assert order.state == "cancelled" and order.closed
    c = h.execution.counters
    acked_before = c["acked"]
    stream.report(order.order_id, execution_type="new", status=OrderState.ACKNOWLEDGED, venue_order_id=order.venue_order_id)  # stale, replayed
    assert order.state == "cancelled" and order.closed and order.order_id not in h.execution.orders
    assert c["acked"] == acked_before and h.execution.open_orders() == []
    await h.execution.close()


async def test_a_cancel_asked_for_twice_and_a_cancel_all_on_top_reach_the_venue_once() -> None:
    h, _stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.execution.cancel(order.order_id, h.t, reason="first")
    h.execution.cancel(order.order_id, h.t, reason="second")
    assert h.execution.cancel_all(h.t, reason="third") == 0  # already requested: nothing new
    await h.settle()
    assert h.venue.cancels.count(order.order_id) == 1 and order.state == "cancelled"
    assert h.execution.counters["cancel_requests"] == 1 and order.cancel_reason.startswith("first")
    await h.execution.close()
