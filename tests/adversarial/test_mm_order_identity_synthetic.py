"""SYNTHETIC adversarial scenarios about order identity and the order of answers.

Fake venue and fake account stream (tests/unit/mm/fake_venue.py): evidence about *our*
invariants, never about Binance. Two orderings the Testnet runs showed are possible and
one the venue's wording makes possible:

* the REST cancel answers first and the stream's CANCELED report arrives later: the order
  is cancelled once, counted once, never reopened, nothing is asked;
* a report whose client id is not ours (a cancel's own id, no ``origClientOrderId``) but
  whose venue ``orderId`` is ours is correlated by that id and applied — not reported as an
  order this run does not know;
* a report whose ids match nothing we hold and that carries our prefix stays critical: the
  venue-id fallback never widens into guessing.
"""

from __future__ import annotations

from tests.unit.mm.test_mm_execution_live import _quote, _streamed
from tia.domain.enums import OrderState
from tia.mm.execution import CLIENT_ID_PREFIX


async def test_a_canceled_report_that_arrives_after_the_rest_cancel_answered_changes_nothing_and_asks_nothing() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.venue_order_id
    h.execution.cancel(order.order_id, h.t, reason="requote")
    await h.settle()  # the REST answer closes it first
    c = h.execution.counters
    assert order.state == "cancelled" and order.closed and c["cancelled"] == 1 and h.venue.cancels.count(order.order_id) == 1
    resolves_before = h.venue.calls.count("resolve")
    # The venue's report of the same cancel lands later, worded as the venue words it:
    # the cancel's own id as clientOrderId, ours in origClientOrderId.
    stream.report("web_cancel_late_1", execution_type="canceled", status=OrderState.CANCELLED, orig_client_order_id=order.order_id, venue_order_id=order.venue_order_id)
    await h.settle()
    assert order.state == "cancelled" and order.closed and c["cancelled"] == 1  # once
    assert order.order_id not in h.execution.orders and h.execution.open_orders() == []
    assert sum(1 for o in h.execution.closed if o.order_id == order.order_id) == 1  # held once, not re-closed
    assert h.venue.calls.count("resolve") == resolves_before and h.criticals == []
    assert c["venue_orders_unknown_locally"] == 0 and c["unknown_reports"] == 0 and h.venue.cancels.count(order.order_id) == 1
    await h.execution.close()


async def test_a_report_named_only_by_our_venue_order_id_is_correlated_by_it_and_applied() -> None:
    """clientOrderId is the cancel's, origClientOrderId is missing, orderId is ours."""
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.venue_order_id
    h.venue.venue_cancel(order.order_id)  # cancelled at the venue by someone at the console
    stream.report("web_cancel_console_9", execution_type="canceled", status=OrderState.CANCELLED, venue_order_id=order.venue_order_id)
    c = h.execution.counters
    assert order.state == "cancelled" and order.closed and c["cancelled"] == 1
    assert h.criticals == [] and c["venue_orders_unknown_locally"] == 0 and c["unknown_reports"] == 0
    await h.settle()
    assert h.execution.open_orders() == [] and h.execution.blocked_reason == ""
    await h.execution.close()


async def test_the_venue_id_fallback_never_adopts_an_order_whose_ids_match_nothing_we_hold() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    foreign_venue_id = str(int(order.venue_order_id) + 1_000_000)
    stream.report(f"{CLIENT_ID_PREFIX}otherrun-1-000001", execution_type="new", status=OrderState.ACKNOWLEDGED, venue_order_id=foreign_venue_id)
    c = h.execution.counters
    assert c["venue_orders_unknown_locally"] == 1 and h.criticals[-1][0] == "venue_order_unknown_locally"
    assert order.state == "resting" and len(h.execution.orders) == 1  # nothing adopted, nothing guessed
    assert c["acked"] == 1
    await h.execution.close()
