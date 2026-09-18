"""The queue in front of a simulated resting order: two bounds on something unknown.

Binance publishes no L3, so where our order would sit at its price level is not
observable. What *is* observable: the visible quantity at that price when the order
arrives (everything already there is ahead of us), the prints at that price (which
consume the queue ahead before they can reach us), and the changes in visible quantity
that no print explains (cancellations — ahead of us or behind us, unknowable).

So the model keeps two queues:

* **conservative**: cancellations were behind us; only prints and the visible bound
  reduce what is ahead. Fills that clear this bound are **confirmed**.
* **optimistic**: cancellations were ahead of us. Fills that clear this bound but not
  the conservative one are **unresolved** — counted, reported, never booked.

One fact tightens the conservative bound for free: whatever is ahead of us is still
resting, so it can never exceed the quantity visible at our price right now.

A print that trades *through* our level (a sell below our bid, a buy above our ask)
means the whole level was consumed, us included: the remainder is a confirmed fill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tia.mm.streams import TradeEvent


@dataclass
class QueueModel:
    side: str  # "buy": a resting bid; "sell": a resting ask
    price: float
    quantity: float
    t_arrival_ms: int
    ahead_conservative: float
    ahead_optimistic: float
    filled: float = 0.0  # confirmed
    filled_optimistic: float = 0.0  # under the optimistic bound (includes the confirmed part)
    venue_trade_ids: list[int] = field(default_factory=list)
    swept: bool = False
    last_visible: float | None = None
    _traded_since_diff: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled)

    @property
    def unresolved(self) -> float:
        """Quantity that fills under the optimistic bound but not the conservative one."""
        return max(0.0, self.filled_optimistic - self.filled)

    @property
    def resolution(self) -> str:
        if self.filled >= self.quantity - 1e-12:
            return "filled"
        if self.filled > 0:
            return "partial"
        return "none"

    # ------------------------------------------------------------------ inputs

    def _hits_us(self, trade: TradeEvent) -> bool:
        if self.side == "buy":
            return trade.buyer_is_maker and trade.price <= self.price  # a seller crossed into the bid
        return (not trade.buyer_is_maker) and trade.price >= self.price  # a buyer lifted the ask

    def _through_us(self, trade: TradeEvent) -> bool:
        return trade.price < self.price if self.side == "buy" else trade.price > self.price

    def on_trade(self, trade: TradeEvent) -> float:
        """Apply one print. Returns the **confirmed** quantity filled by it."""
        if self.remaining <= 0 or trade.received_at_ms < self.t_arrival_ms or not self._hits_us(trade):
            return 0.0
        if self._through_us(trade):
            # The level was consumed entirely before the print went deeper: so was our order.
            confirmed = self.remaining
            self.swept = True
            self.ahead_conservative = self.ahead_optimistic = 0.0
            self.filled += confirmed
            self.filled_optimistic = max(self.filled_optimistic, self.filled)
            self.venue_trade_ids.append(trade.trade_id)
            return confirmed
        qty = trade.quantity
        self._traded_since_diff += qty
        # Conservative bound.
        consumed = min(qty, self.ahead_conservative)
        self.ahead_conservative -= consumed
        confirmed = min(qty - consumed, self.remaining)
        # Optimistic bound.
        consumed_o = min(qty, self.ahead_optimistic)
        self.ahead_optimistic -= consumed_o
        optimistic = min(qty - consumed_o, max(0.0, self.quantity - self.filled_optimistic))
        self.filled += confirmed
        self.filled_optimistic = max(self.filled_optimistic + optimistic, self.filled)
        if confirmed > 0 or optimistic > 0:
            self.venue_trade_ids.append(trade.trade_id)
        return confirmed

    def on_visible(self, visible_qty: float) -> None:
        """The visible quantity at our price after a depth diff."""
        if self.last_visible is not None:
            decrease = self.last_visible - visible_qty
            unexplained = max(0.0, decrease - self._traded_since_diff)
            if unexplained > 0:
                self.ahead_optimistic = max(0.0, self.ahead_optimistic - unexplained)
        # Whatever is ahead of us is still resting: it cannot exceed what is visible.
        self.ahead_conservative = min(self.ahead_conservative, visible_qty)
        self.ahead_optimistic = min(self.ahead_optimistic, self.ahead_conservative)
        self.last_visible = visible_qty
        self._traded_since_diff = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "filled": self.filled,
            "filled_optimistic": self.filled_optimistic,
            "unresolved": self.unresolved,
            "resolution": self.resolution,
            "ahead_conservative": self.ahead_conservative,
            "ahead_optimistic": self.ahead_optimistic,
            "estimated_queue_position": self.ahead_conservative,
            "swept": self.swept,
            "venue_trade_ids": list(self.venue_trade_ids),
        }


__all__ = ["QueueModel"]
