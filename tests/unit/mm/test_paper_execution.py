"""Paper execution: fills only from real prints past a queue bound, late arrivals,
late cancels, unresolved quantity never booked, costs itemised, inventory accounted."""

from __future__ import annotations

import pytest

from tia.mm.costs import MarketMakerCostConfig, MarketMakerCostModel
from tia.mm.latency_model import LatencyScenario
from tia.mm.ledger import MarketMakerLedger
from tia.mm.order_book import DepthUpdate, LocalOrderBook, snapshot_from_levels
from tia.mm.queue import QueueModel
from tia.mm.quoting import QuoteDecision
from tia.mm.sim import PaperMarketMakerExecution, SimulatedFill
from tia.mm.streams import TradeEvent

T0 = 1_789_754_400_000
LAT = LatencyScenario("baseline", "p-test", order_latency_ms=100.0, cancel_latency_ms=100.0, data_latency_ms=50.0, processing_ms=0.1, basis="test")


def _book() -> LocalOrderBook:
    book = LocalOrderBook("BTC-USD")
    book.begin_sync()
    assert book.apply_snapshot(snapshot_from_levels(100, [(100_000.0, 2.0), (99_999.9, 5.0)], [(100_000.2, 1.0), (100_000.3, 4.0)]))
    return book


def _trade(tid: int, t: int, price: float, qty: float, *, seller_hits_bid: bool) -> TradeEvent:
    return TradeEvent(trade_id=tid, price=price, quantity=qty, buyer_is_maker=seller_hits_bid, trade_time_ms=t - 5, event_time_ms=t - 2, received_at_ms=t)


def _depth(uid: int, t: int, bids=(), asks=()) -> DepthUpdate:  # type: ignore[no-untyped-def]
    return DepthUpdate(first_update_id=uid, final_update_id=uid, bids=tuple(bids), asks=tuple(asks), event_time_ms=t - 30, received_at_ms=t)


def _quote(bid: float | None = 100_000.0, ask: float | None = 100_000.2, size: float = 0.5) -> QuoteDecision:
    return QuoteDecision(T0, bid, ask, size if bid else 0.0, size if ask else 0.0, size, 2.0, 1.0, 100_000.1, 0.9, "test", 5_000)


# ------------------------------------------------------------------ 10. queue estimation


def test_prints_consume_the_queue_ahead_before_they_reach_us() -> None:
    q = QueueModel("buy", 100_000.0, quantity=1.0, t_arrival_ms=T0, ahead_conservative=2.0, ahead_optimistic=2.0, last_visible=2.0)
    assert q.on_trade(_trade(1, T0 + 10, 100_000.0, 1.5, seller_hits_bid=True)) == 0.0  # 1.5 of the 2.0 ahead
    assert q.ahead_conservative == pytest.approx(0.5) and q.filled == 0.0
    assert q.on_trade(_trade(2, T0 + 20, 100_000.0, 0.8, seller_hits_bid=True)) == pytest.approx(0.3)  # 0.5 clears the queue, 0.3 fills us
    assert q.resolution == "partial" and q.venue_trade_ids == [2]
    assert q.on_trade(_trade(3, T0 + 30, 100_000.0, 0.5, seller_hits_bid=False)) == 0.0  # a buyer lifting the ask never hits a bid
    assert q.on_trade(_trade(4, T0 + 40, 100_000.1, 0.5, seller_hits_bid=True)) == 0.0  # a sell above our price never reaches it
    assert q.on_trade(_trade(5, T0 - 1, 100_000.0, 5.0, seller_hits_bid=True)) == 0.0  # before we arrived: not ours
    assert q.on_trade(_trade(6, T0 + 50, 99_999.9, 0.1, seller_hits_bid=True)) == pytest.approx(0.7)  # traded through: the level was consumed, us included
    assert q.swept and q.resolution == "filled" and q.unresolved == 0.0


def test_cancellations_ahead_are_unknowable_so_they_only_make_the_fill_unresolved() -> None:
    q = QueueModel("buy", 100_000.0, quantity=1.0, t_arrival_ms=T0, ahead_conservative=2.0, ahead_optimistic=2.0, last_visible=2.0)
    q.on_visible(0.5)  # 1.5 vanished with no prints: cancellations, ahead or behind us — unknown
    assert q.ahead_optimistic == pytest.approx(0.5) and q.ahead_conservative == pytest.approx(0.5)  # the visible bound tightens both
    q2 = QueueModel("buy", 100_000.0, quantity=1.0, t_arrival_ms=T0, ahead_conservative=2.0, ahead_optimistic=2.0, last_visible=3.0)
    q2.on_visible(2.5)  # visible fell 0.5 but is still above what is ahead: optimistic says those were ahead
    assert q2.ahead_optimistic == pytest.approx(1.5) and q2.ahead_conservative == pytest.approx(2.0)
    assert q2.on_trade(_trade(1, T0 + 10, 100_000.0, 1.8, seller_hits_bid=True)) == 0.0  # conservative: 0.2 still ahead
    assert q2.filled == 0.0 and q2.filled_optimistic == pytest.approx(0.3) and q2.unresolved == pytest.approx(0.3)
    assert q2.resolution == "none"  # nothing booked on an unresolved fill


# ------------------------------------------------------------------ 11, 13, 14, 15. the simulator


def test_orders_arrive_after_the_latency_and_fill_only_on_prints_after_arrival() -> None:
    book, sim = _book(), PaperMarketMakerExecution(LAT)
    orders = sim.place(_quote(), T0)
    assert len(orders) == 2 and all(o.state == "pending_arrival" and o.t_arrival_ms == T0 + 100 for o in orders)
    assert sim.on_event("trade", _trade(1, T0 + 50, 100_000.0, 5.0, seller_hits_bid=True), book, T0 + 50) == []  # before arrival: no fill
    assert sim.on_event("depth", _depth(101, T0 + 120), book, T0 + 120) == []
    bid_order = next(o for o in orders if o.side == "buy")
    assert bid_order.state == "resting" and bid_order.queue is not None and bid_order.queue.ahead_conservative == 2.0
    assert sim.on_event("trade", _trade(2, T0 + 200, 100_000.0, 1.0, seller_hits_bid=True), book, T0 + 200) == []  # queue ahead
    fills = sim.on_event("trade", _trade(3, T0 + 300, 100_000.0, 1.3, seller_hits_bid=True), book, T0 + 300)
    assert len(fills) == 1 and fills[0].quantity == pytest.approx(0.3) and fills[0].venue_trade_ids == (3,) and fills[0].mid_at_fill == pytest.approx(100_000.1)
    assert bid_order.state == "resting" and bid_order.filled == pytest.approx(0.3)  # partial
    fills = sim.on_event("trade", _trade(4, T0 + 400, 100_000.0, 0.2, seller_hits_bid=True), book, T0 + 400)
    assert fills[0].quantity == pytest.approx(0.2) and bid_order.state == "filled"
    assert sim.stats()["fills"] == 2 and sim.stats()["states"]["filled"] == 1
    # No prints, no fills: the ask never sees a buyer and stays resting.
    ask_order = next(o for o in orders if o.side == "sell")
    assert ask_order.state == "resting" and ask_order.filled == 0.0


def test_a_cancel_takes_effect_late_and_a_print_in_between_still_fills() -> None:
    book, sim = _book(), PaperMarketMakerExecution(LAT)
    (order,) = sim.place(_quote(ask=None), T0)
    sim.on_event("depth", _depth(101, T0 + 100), book, T0 + 100)
    sim.cancel(order.order_id, T0 + 150, reason="requote")
    assert order.t_cancel_effective_ms == T0 + 250 and order.state == "resting"
    fills = sim.on_event("trade", _trade(1, T0 + 200, 100_000.0, 2.5, seller_hits_bid=True), book, T0 + 200)
    assert len(fills) == 1 and fills[0].quantity == pytest.approx(0.5) and order.state == "filled"  # the cancel came too late
    (again,) = sim.place(_quote(ask=None), T0 + 1_000)
    sim.on_event("depth", _depth(102, T0 + 1_100), book, T0 + 1_100)
    assert sim.cancel_all(T0 + 1_100, reason="gate") == 1
    sim.on_event("depth", _depth(103, T0 + 1_250), book, T0 + 1_250)
    assert again.state == "cancelled" and again.cancel_reason == "gate" and sim.cancelled == 1


def test_a_crossing_order_is_refused_and_a_ttl_expires_the_rest() -> None:
    book, sim = _book(), PaperMarketMakerExecution(LAT)
    (crossing,) = sim.place(_quote(bid=100_000.3, ask=None), T0)  # a bid above the best ask: a taker order
    sim.on_event("depth", _depth(101, T0 + 100), book, T0 + 100)
    assert crossing.state == "refused" and sim.refused_crossed == 1 and "taker" in crossing.cancel_reason
    (resting,) = sim.place(_quote(bid=99_999.9, ask=None), T0)
    sim.on_event("depth", _depth(102, T0 + 100), book, T0 + 100)
    sim.on_event("depth", _depth(103, T0 + 5_200), book, T0 + 5_200)  # ttl 5 s passed: cancel requested
    assert resting.t_cancel_requested_ms == T0 + 5_200 and sim.expired == 1
    sim.on_event("depth", _depth(104, T0 + 5_400), book, T0 + 5_400)
    assert resting.state == "cancelled"


def test_unresolved_quantity_is_counted_and_never_becomes_a_fill() -> None:
    book, sim = _book(), PaperMarketMakerExecution(LAT)
    (order,) = sim.place(_quote(ask=None, size=1.0), T0)
    first = _depth(101, T0 + 100)
    assert book.apply_update(first)
    sim.on_event("depth", first, book, T0 + 100)  # arrives: 2.0 ahead
    joined = _depth(102, T0 + 150, bids=[(100_000.0, 3.0)])  # 1.0 more joins the level, behind us
    assert book.apply_update(joined)
    sim.on_event("depth", joined, book, T0 + 150)
    pulled = _depth(103, T0 + 200, bids=[(100_000.0, 1.4)])  # 1.6 cancelled with no prints: ahead of us or behind us?
    assert book.apply_update(pulled)
    sim.on_event("depth", pulled, book, T0 + 200)
    assert order.queue is not None and order.queue.ahead_conservative == pytest.approx(1.4) and order.queue.ahead_optimistic == pytest.approx(0.4)
    fills = sim.on_event("trade", _trade(1, T0 + 300, 100_000.0, 0.6, seller_hits_bid=True), book, T0 + 300)
    assert fills == []  # conservative: 1.4 still ahead; 0.2 would fill only if the cancels were ahead of us
    assert order.filled == 0.0 and order.unresolved == pytest.approx(0.2)
    stats = sim.stats()
    assert stats["fills"] == 0 and stats["unresolved_fill_events"] == 1 and stats["unresolved_quantity"] == pytest.approx(0.2)


# ------------------------------------------------------------------ 12. fees, 6/16. inventory accounting, 22. restart


def test_fee_scenarios_are_explicit_and_the_verified_rate_is_not_guessed() -> None:
    model = MarketMakerCostModel(MarketMakerCostConfig(maker_fee_bps=10.0, maker_fee_adverse_bps=15.0))
    assert model.maker_fee_usd(10_000.0) == pytest.approx(10.0)
    assert model.maker_fee_usd(10_000.0, "adverse") == pytest.approx(15.0)
    with pytest.raises(ValueError, match="not been read"):
        model.maker_fee_usd(10_000.0, "verified")
    assert model.unwind_cost_usd(10_000.0, None) == {"fee_usd": 10.0, "slippage_usd": 0.0, "impact_known": False}
    assert model.as_dict()["status"] == "PROVISIONAL_COST_ASSUMPTION"


def _fill(fid: str, side: str, price: float, qty: float, t: int) -> SimulatedFill:
    return SimulatedFill(fid, "o", side, price, qty, t, (1,), 0.0, price)


def test_the_ledger_realises_on_reduction_marks_both_ways_and_itemises() -> None:
    ledger = MarketMakerLedger(10_000.0, MarketMakerCostModel(MarketMakerCostConfig(maker_fee_bps=10.0)))
    ledger.apply_fill(_fill("f1", "buy", 100_000.0, 0.01, T0))  # notional 1000, fee 1.0
    s = ledger.state
    assert s.inventory_btc == pytest.approx(0.01) and s.average_cost == 100_000.0 and s.cash_usd == pytest.approx(10_000 - 1_000 - 1.0)
    ledger.mark(T0 + 1, bid=100_010.0, ask=100_030.0)
    assert ledger.unrealised_mid_usd == pytest.approx(0.2) and ledger.unrealised_conservative_usd == pytest.approx(0.1)
    assert ledger.equity_usd == pytest.approx(10_000 - 1.0 + 0.2) and ledger.equity_conservative_usd == pytest.approx(10_000 - 1.0 + 0.1)
    ledger.apply_fill(_fill("f2", "sell", 100_020.0, 0.01, T0 + 2))  # realise 0.2, fee ~1.0002
    assert s.inventory_btc == 0.0 and s.realised_pnl_usd == pytest.approx(0.2) and s.fees_usd == pytest.approx(2.0002)
    snap = ledger.snapshot()
    assert snap["net_pnl_usd"] == pytest.approx(0.2 - 2.0002, abs=1e-6) and snap["gross_pnl_usd"] == pytest.approx(0.2)
    assert snap["fees_usd"] == pytest.approx(2.0002) and snap["fills"] == 2 and snap["max_inventory_btc"] == pytest.approx(0.01)
    # Flip through zero: sell 0.02 against a 0.01 long realises on 0.01 and opens a 0.01 short at the fill price.
    ledger.apply_fill(_fill("f3", "buy", 100_000.0, 0.01, T0 + 3))
    ledger.apply_fill(_fill("f4", "sell", 100_050.0, 0.02, T0 + 4))
    assert s.inventory_btc == pytest.approx(-0.01) and s.average_cost == 100_050.0 and s.realised_pnl_usd == pytest.approx(0.2 + 0.5)
    ledger.mark(T0 + 5, bid=100_040.0, ask=100_060.0)
    assert ledger.unrealised_conservative_usd == pytest.approx(-0.01 * (100_060.0 - 100_050.0))  # a short is marked at the ask
    view = ledger.view()
    assert view.inventory_btc == pytest.approx(-0.01) and view.peak_equity_usd >= view.equity_usd
    restored = MarketMakerLedger.restore(ledger.export())
    assert restored.state.inventory_btc == s.inventory_btc and restored.state.realised_pnl_usd == s.realised_pnl_usd and restored.state.fees_usd == s.fees_usd


def test_the_day_rolls_and_drawdown_is_measured_from_the_peak() -> None:
    ledger = MarketMakerLedger(10_000.0)
    ledger.mark(T0, bid=100_000.0, ask=100_000.2)
    assert ledger.state.day == "2026-09-18" and ledger.state.day_start_equity_usd == 10_000.0
    ledger.apply_fill(_fill("f1", "buy", 100_000.0, 0.01, T0 + 1))
    ledger.mark(T0 + 2, bid=101_000.0, ask=101_000.2)  # +10 unrealised
    peak = ledger.equity_usd
    ledger.mark(T0 + 3, bid=99_000.0, ask=99_000.2)
    assert ledger.state.peak_equity_usd == pytest.approx(peak) and ledger.drawdown_pct > 0
    ledger.mark(T0 + 86_400_000, bid=99_000.0, ask=99_000.2)
    assert ledger.state.day == "2026-09-19" and ledger.state.day_start_equity_usd == pytest.approx(ledger.equity_usd)
