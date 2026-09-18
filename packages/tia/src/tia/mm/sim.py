"""Paper execution for the market maker: orders that arrive late, rest in an
estimated queue, fill only on real prints, and cancel late too.

What a fill needs here: a resting order that arrived (decision time plus the
scenario's order latency) at a price the book had not already crossed, and real
trades at that price — or through it — after the arrival, beyond the conservative
queue bound. Nothing else fills anything. A cancel takes effect after the cancel
latency, and a print that lands in between fills the order it was meant to remove.
An order whose price would have crossed the book on arrival would have been a taker
order, which this maker does not model: it is refused and counted.

Every fill names the venue trade ids that produced it and the queue bound it cleared;
quantity that would fill only under the optimistic bound is reported as **unresolved**
and never booked.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from tia.mm.latency_model import LatencyScenario
from tia.mm.order_book import DepthUpdate, LocalOrderBook
from tia.mm.queue import QueueModel
from tia.mm.quoting import QuoteDecision
from tia.mm.streams import TradeEvent


@dataclass(frozen=True)
class SimulatedFill:
    fill_id: str
    order_id: str
    side: str
    price: float
    quantity: float
    t_ms: int
    venue_trade_ids: tuple[int, ...]
    queue_ahead_at_arrival: float
    mid_at_fill: float | None
    resolution: str = "confirmed"

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class SimulatedOrder:
    order_id: str
    side: str
    price: float
    quantity: float
    t_decision_ms: int
    t_arrival_ms: int
    ttl_ms: int
    reason: str
    state: str = "pending_arrival"  # resting | filled | cancelled | refused
    queue: QueueModel | None = None
    fills: list[SimulatedFill] = field(default_factory=list)
    t_cancel_requested_ms: int | None = None
    t_cancel_effective_ms: int | None = None
    cancel_reason: str = ""

    @property
    def filled(self) -> float:
        return sum(f.quantity for f in self.fills)

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled)

    @property
    def unresolved(self) -> float:
        return self.queue.unresolved if self.queue is not None else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "filled": self.filled,
            "unresolved": self.unresolved,
            "state": self.state,
            "t_decision_ms": self.t_decision_ms,
            "t_arrival_ms": self.t_arrival_ms,
            "t_cancel_requested_ms": self.t_cancel_requested_ms,
            "t_cancel_effective_ms": self.t_cancel_effective_ms,
            "cancel_reason": self.cancel_reason,
            "reason": self.reason,
            "queue": self.queue.as_dict() if self.queue else None,
        }


class PaperMarketMakerExecution:
    def __init__(self, latency: LatencyScenario, *, keep_closed: int = 2_000) -> None:
        self.latency = latency
        #: Orders still in flight or resting. Terminal orders move to ``closed`` so a
        #: day-long run never iterates its whole history on every event.
        self.orders: dict[str, SimulatedOrder] = {}
        self.closed: deque[SimulatedOrder] = deque(maxlen=keep_closed)
        self._terminal_counts: dict[str, int] = {}
        self._partial_closed = 0
        self._unresolved_closed = 0.0
        self._seq = 0
        self.placed = 0
        self.arrived = 0
        self.refused_crossed = 0
        self.cancelled = 0
        self.expired = 0
        self.fills: list[SimulatedFill] = []
        self.unresolved_fills = 0
        #: (order, quantity) pairs whose unresolved quantity grew during the last event.
        self.last_unresolved: list[tuple[SimulatedOrder, float]] = []

    # ------------------------------------------------------------------ orders

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq:08d}"

    def place(self, decision: QuoteDecision, t_ms: int) -> list[SimulatedOrder]:
        """One simulated order per quoted side, arriving after the order latency."""
        out: list[SimulatedOrder] = []
        arrival = t_ms + round(self.latency.order_latency_ms)
        for side, price, qty in (("buy", decision.bid_price, decision.bid_size), ("sell", decision.ask_price, decision.ask_size)):
            if price is None or qty <= 0:
                continue
            order = SimulatedOrder(self._next_id("mmo"), side, price, qty, t_ms, arrival, decision.ttl_ms, decision.quote_reason)
            self.orders[order.order_id] = order
            self.placed += 1
            out.append(order)
        return out

    def _close(self, order: SimulatedOrder) -> None:
        self.orders.pop(order.order_id, None)
        self.closed.append(order)
        self._terminal_counts[order.state] = self._terminal_counts.get(order.state, 0) + 1
        if 0 < order.filled < order.quantity:
            self._partial_closed += 1
        self._unresolved_closed += order.unresolved

    def cancel(self, order_id: str, t_ms: int, *, reason: str) -> None:
        order = self.orders.get(order_id)
        if order is None or order.state in ("filled", "cancelled", "refused") or order.t_cancel_requested_ms is not None:
            return
        order.t_cancel_requested_ms = t_ms
        order.t_cancel_effective_ms = t_ms + round(self.latency.cancel_latency_ms)
        order.cancel_reason = reason

    def cancel_all(self, t_ms: int, *, reason: str) -> int:
        count = 0
        for order in self.orders.values():
            if order.state in ("pending_arrival", "resting") and order.t_cancel_requested_ms is None:
                self.cancel(order.order_id, t_ms, reason=reason)
                count += 1
        return count

    def open_orders(self) -> list[SimulatedOrder]:
        return [o for o in self.orders.values() if o.state in ("pending_arrival", "resting")]

    # ------------------------------------------------------------------ the tape

    def on_event(self, kind: str, event: Any, book: LocalOrderBook, t_ms: int) -> list[SimulatedFill]:
        """Advance every order with one event. Returns the confirmed fills it produced."""
        produced: list[SimulatedFill] = []
        self.last_unresolved = []
        for order in list(self.orders.values()):
            if order.state == "pending_arrival" and t_ms >= order.t_arrival_ms:
                self._arrive(order, book)
                if order.state == "refused":
                    self._close(order)
                    continue
            if order.state != "resting" or order.queue is None:
                continue
            if kind == "trade" and isinstance(event, TradeEvent):
                before_unresolved = order.queue.unresolved
                confirmed = order.queue.on_trade(event)
                if confirmed > 0:
                    fill = SimulatedFill(
                        fill_id=self._next_id("mmf"),
                        order_id=order.order_id,
                        side=order.side,
                        price=order.price,
                        quantity=confirmed,
                        t_ms=t_ms,
                        venue_trade_ids=(event.trade_id,),
                        queue_ahead_at_arrival=order.queue.ahead_at_arrival,
                        mid_at_fill=book.mid,
                    )
                    order.fills.append(fill)
                    self.fills.append(fill)
                    produced.append(fill)
                if order.queue.unresolved > before_unresolved:
                    self.unresolved_fills += 1
                    self.last_unresolved.append((order, order.queue.unresolved - before_unresolved))
                if order.remaining <= 1e-12:
                    order.state = "filled"
                    self._close(order)
                    continue
            elif kind == "depth" and isinstance(event, DepthUpdate):
                side = "bid" if order.side == "buy" else "ask"
                order.queue.on_visible(book.quantity_at(side, order.price))
            # Cancels and expiries take effect after their own latency.
            if order.t_cancel_requested_ms is None and t_ms >= order.t_arrival_ms + order.ttl_ms:
                self.cancel(order.order_id, t_ms, reason="ttl expired")
                self.expired += 1
            if order.t_cancel_effective_ms is not None and t_ms >= order.t_cancel_effective_ms:
                order.state = "cancelled"
                self.cancelled += 1
                self._close(order)
        return produced

    def _arrive(self, order: SimulatedOrder, book: LocalOrderBook) -> None:
        self.arrived += 1
        best_bid, best_ask = book.best_bid(), book.best_ask()
        if not book.is_valid or best_bid is None or best_ask is None:
            order.state = "refused"
            order.cancel_reason = "book not valid at arrival"
            return
        crosses = order.price >= best_ask[0] if order.side == "buy" else order.price <= best_bid[0]
        if crosses:
            order.state = "refused"
            order.cancel_reason = "would have crossed the book at arrival: a taker order, not modelled"
            self.refused_crossed += 1
            return
        visible = book.quantity_at("bid" if order.side == "buy" else "ask", order.price)
        order.queue = QueueModel(order.side, order.price, order.quantity, order.t_arrival_ms, ahead_conservative=visible, ahead_optimistic=visible, last_visible=visible)
        order.state = "resting"

    def stats(self) -> dict[str, Any]:
        states = dict(self._terminal_counts)
        for order in self.orders.values():
            states[order.state] = states.get(order.state, 0) + 1
        return {
            "placed": self.placed,
            "arrived": self.arrived,
            "refused_crossed": self.refused_crossed,
            "cancelled": self.cancelled,
            "expired": self.expired,
            "fills": len(self.fills),
            "partial_orders": self._partial_closed + sum(1 for o in self.orders.values() if 0 < o.filled < o.quantity),
            "unresolved_fill_events": self.unresolved_fills,
            "unresolved_quantity": self._unresolved_closed + sum(o.unresolved for o in self.orders.values()),
            "states": states,
            "active": len(self.orders),
            "latency": self.latency.as_dict(),
        }


__all__ = ["PaperMarketMakerExecution", "SimulatedFill", "SimulatedOrder"]
