"""An in-memory venue behind the abstract ``ExecutionProvider``, for the live adapter's tests.

It is a *simulated* provider (no token needed) that behaves like the venue's documented
contract: idempotent on the client order id, post-only orders rejected with -2010 when they
would take, fills injected by the test and read back through ``get_trades``, cancels that
can race fills, and switches to make any call time out, fail, or hang. Nothing here is a
network; everything here is what the adapter must be correct against.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

from tia.core.clock import Clock
from tia.core.errors import (
    ExecutionError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import ExecutionReport, Fill, Order, OrderIntent
from tia.domain.portfolio import AccountBalance, PortfolioState, Position
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider


class FakeVenue(ExecutionProvider):
    def __init__(
        self,
        clock: Clock,
        *,
        best_bid: float = 100_000.0,
        best_ask: float = 100_000.2,
        quote_balance: float = 5_000.0,
        base_balance: float = 0.05,
        base_locked: float = 0.0,
        name: str = "fake-venue",
        activation: Any = None,
        simulated: bool = True,
    ) -> None:
        super().__init__(
            ExecutionCapabilities(name=name, is_simulated=simulated, models_fees=False, models_slippage=False, models_latency=False),
            activation=activation,
            clock=clock,
        )
        self.clock = clock
        self.best_bid, self.best_ask = best_bid, best_ask
        self.quote_balance, self.base_balance, self.base_locked = quote_balance, base_balance, base_locked
        self.orders: dict[str, Order] = {}  # by client order id
        self.by_venue_id: dict[str, str] = {}
        self.trades: list[Fill] = []
        self.foreign_open: list[Order] = []
        self.submits: list[OrderIntent] = []  # accepted by the venue
        self.received: list[OrderIntent] = []  # reached the venue, accepted or not
        self.cancels: list[str] = []
        self.calls: list[str] = []
        self._venue_seq = 1000
        self._trade_seq = 5000
        #: Behaviour switches, consumed per call: "timeout", "transport", "reject:<code>",
        #: "hang" or a callable returning one of those.
        self.next_submit: list[str] = []
        self.next_cancel: list[str] = []
        self.fail_queries: str | None = None
        self.hang_seconds = 10.0
        self.fee_bps = 1.0
        self.fee_asset = "USDT"
        self.reject_cancel_of_closed = True

    # ------------------------------------------------------------------ helpers for tests

    def _pop(self, switches: list[str]) -> str:
        return switches.pop(0) if switches else ""

    async def _behave(self, switch: str, path: str) -> None:
        if switch == "timeout":
            raise ReconciliationError(f"{path} timed out; UNKNOWN", path=path)
        if switch == "transport":
            raise ProviderUnavailableError(f"transport error on {path}", provider=self.name)
        if switch == "rate_limited":
            raise ProviderUnavailableError(f"{path} rate limited", provider=self.name)
        if switch == "hang":
            await asyncio.sleep(self.hang_seconds)
        if switch.startswith("reject:"):
            code = int(switch.split(":", 1)[1])
            raise OrderRejectedError(f"rejected {path} code={code}", code=code, path=path)

    def venue_fill(self, client_order_id: str, quantity: float, *, price: float | None = None, is_maker: bool = True, at: datetime | None = None, fee_asset: str | None = None) -> Fill:
        """The venue matched part or all of a resting order: a trade appears in the history
        and the order's status moves. The adapter learns of it only through get_trades."""
        order = self.orders[client_order_id]
        self._trade_seq += 1
        fill_price = price if price is not None else (order.limit_price or 0.0)
        fee = fill_price * quantity * self.fee_bps / 10_000.0
        fill = Fill(
            fill_id=str(self._trade_seq),
            order_id=order.order_id,
            sequence=0,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=fill_price,
            fee=fee,
            fee_asset=fee_asset if fee_asset is not None else self.fee_asset,
            liquidity="maker" if is_maker else "taker",
            filled_at=at or self.clock.now(),
        )
        self.trades.append(fill)
        order.filled_quantity = min(order.quantity, order.filled_quantity + quantity)
        order.average_fill_price = fill_price
        order.state = OrderState.FILLED if order.filled_quantity >= order.quantity - 1e-12 else OrderState.PARTIALLY_FILLED
        order.updated_at = fill.filled_at
        if order.side is Side.BUY:
            self.quote_balance -= fill_price * quantity + fee
            self.base_balance += quantity
        else:
            self.quote_balance += fill_price * quantity - fee
            self.base_balance -= quantity
        return fill

    def foreign_trade(self, *, price: float, quantity: float, side: Side = Side.BUY, at: datetime | None = None) -> Fill:
        """A trade on the account from an order this adapter never placed."""
        self._trade_seq += 1
        fill = Fill(fill_id=str(self._trade_seq), order_id="999999", sequence=0, symbol="BTC-USD", side=side, quantity=quantity, price=price, fee=0.0, liquidity="taker", filled_at=at or self.clock.now())
        self.trades.append(fill)
        return fill

    def add_foreign_open_order(self, client_order_id: str = "someone-else-1") -> Order:
        now = self.clock.now()
        self._venue_seq += 1
        order = Order(order_id=str(self._venue_seq), client_order_id=client_order_id, intent_id="", signal_id="", symbol="BTC-USD", side=Side.SELL, order_type=OrderType.LIMIT, quantity=0.01, limit_price=self.best_ask + 50, state=OrderState.ACKNOWLEDGED, created_at=now, updated_at=now)
        self.foreign_open.append(order)
        return order

    def venue_cancel(self, client_order_id: str) -> None:
        order = self.orders[client_order_id]
        if not order.state.is_terminal:
            order.state = OrderState.CANCELLED
            order.updated_at = self.clock.now()

    # ------------------------------------------------------------------ the contract

    async def submit_order(self, intent: OrderIntent) -> Order:
        self.calls.append("submit")
        self.assert_may_trade()
        existing = self.orders.get(intent.client_order_id)
        if existing is not None:
            return existing
        switch = self._pop(self.next_submit)
        if switch != "timeout":
            self.received.append(intent)
        if switch != "timeout_after_accept":
            await self._behave(switch, "order")
        self.submits.append(intent)
        now = self.clock.now()
        if intent.order_type is not OrderType.LIMIT_MAKER:
            raise OrderRejectedError("this venue accepts only LIMIT_MAKER in these tests", code=-1013, path="order")
        price = intent.limit_price or 0.0
        would_take = (intent.side is Side.BUY and price >= self.best_ask) or (intent.side is Side.SELL and price <= self.best_bid)
        if would_take:
            raise OrderRejectedError("Order would immediately match and take.", code=-2010, path="order")
        self._venue_seq += 1
        order = Order(
            order_id=str(self._venue_seq),
            client_order_id=intent.client_order_id,
            intent_id=intent.intent_id,
            signal_id=intent.signal_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            state=OrderState.ACKNOWLEDGED,
            created_at=now,
            updated_at=now,
        )
        self.orders[intent.client_order_id] = order
        self.by_venue_id[order.order_id] = intent.client_order_id
        if switch == "timeout_after_accept":
            # The venue took the order; the answer never reached us.
            raise ReconciliationError("order timed out after the venue accepted it; UNKNOWN", path="order")
        return order.model_copy()

    async def resolve_unknown_order(self, *, symbol: str, client_order_id: str) -> Order | None:
        self.calls.append("resolve")
        if self.fail_queries:
            await self._behave(self.fail_queries, "order")
        order = self.orders.get(client_order_id)
        return order.model_copy() if order is not None else None

    async def cancel_order(self, order_id: str) -> Order:
        self.calls.append("cancel")
        self.assert_may_trade()
        order = self.orders.get(order_id) or self.orders.get(self.by_venue_id.get(order_id, ""))
        if order is None:
            raise ExecutionError(f"unknown order {order_id}", order_id=order_id)
        await self._behave(self._pop(self.next_cancel), "order")
        self.cancels.append(order.client_order_id)
        if order.state.is_terminal:
            if self.reject_cancel_of_closed:
                raise OrderRejectedError("Unknown order sent.", code=-2011, path="order")
            return order.model_copy()
        order.state = OrderState.CANCELLED
        order.updated_at = self.clock.now()
        return order.model_copy()

    async def get_order(self, order_id: str) -> Order | None:
        self.calls.append("get_order")
        if self.fail_queries:
            await self._behave(self.fail_queries, "order")
        order = self.orders.get(order_id) or self.orders.get(self.by_venue_id.get(order_id, ""))
        return order.model_copy() if order is not None else None

    async def get_orders(self, *, open_only: bool = False, symbol: str | None = None) -> list[Order]:
        self.calls.append("open_orders")
        if self.fail_queries:
            await self._behave(self.fail_queries, "openOrders")
        if not open_only:
            return [o.model_copy() for o in self.orders.values()]
        return [o.model_copy() for o in self.orders.values() if not o.state.is_terminal] + [o.model_copy() for o in self.foreign_open if not o.state.is_terminal]

    async def get_positions(self) -> dict[str, Position]:
        self.calls.append("positions")
        total = self.base_balance + self.base_locked
        return {"BTC-USD": Position(symbol="BTC-USD", quantity=total, average_price=0.0)} if total > 0 else {}

    async def get_balance(self) -> float:
        self.calls.append("balance")
        if self.fail_queries:
            await self._behave(self.fail_queries, "account")
        return self.quote_balance

    @property
    def quote_asset(self) -> str:
        return "USDT"

    def locked(self) -> tuple[float, float]:
        """(quote locked by resting bids, base locked by resting asks): the venue's rule."""
        quote = base = 0.0
        for order in self.orders.values():
            if order.state.is_terminal:
                continue
            remaining = order.remaining_quantity
            if order.side is Side.BUY:
                quote += remaining * (order.limit_price or 0.0)
            else:
                base += remaining
        return quote, base

    async def get_balances(self) -> dict[str, AccountBalance]:
        """Both assets, free and locked, as the venue would report them."""
        self.calls.append("balances")
        if self.fail_queries:
            await self._behave(self.fail_queries, "account")
        return self.balances_now()

    def balances_now(self) -> dict[str, AccountBalance]:
        quote_locked, base_locked = self.locked()
        # ``base_locked`` given at construction stands for base the account already had
        # locked by something else (as a foreign resting ask would); it is reported as such.
        return {
            "USDT": AccountBalance(asset="USDT", free=max(0.0, self.quote_balance - quote_locked), locked=quote_locked),
            "BTC": AccountBalance(asset="BTC", free=max(0.0, self.base_balance - base_locked), locked=base_locked + self.base_locked),
        }

    async def get_trades(self, *, limit: int = 100, symbol: str | None = None) -> list[Fill]:
        self.calls.append("trades")
        if self.fail_queries:
            await self._behave(self.fail_queries, "myTrades")
        return sorted(self.trades, key=lambda f: f.filled_at)[-limit:]

    async def get_pnl(self) -> dict[str, float]:
        return {"realized": 0.0, "unrealized": 0.0}

    async def get_portfolio(self) -> PortfolioState:
        state = PortfolioState.initial(max(self.quote_balance, 1e-9))
        state.cash = self.quote_balance
        state.positions = await self.get_positions()
        return state

    async def get_exchange_info(self, symbol: str) -> dict[str, Any]:
        return exchange_info()

    @staticmethod
    def to_venue_symbol(symbol: str) -> str:
        base, _, quote = symbol.partition("-")
        return f"{base}{'USDT' if quote.upper() == 'USD' else quote}".upper()


def exchange_info(*, tick: str = "0.01000000", step: str = "0.00001000", min_qty: str = "0.00001000", min_notional: str = "5.00000000", order_types: tuple[str, ...] = ("LIMIT", "LIMIT_MAKER", "MARKET")) -> dict[str, Any]:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "orderTypes": list(order_types),
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01000000", "maxPrice": "1000000.00000000", "tickSize": tick},
                    {"filterType": "LOT_SIZE", "minQty": min_qty, "maxQty": "9000.00000000", "stepSize": step},
                    {"filterType": "NOTIONAL", "minNotional": min_notional, "applyMinToMarket": True},
                ],
            }
        ]
    }


Behaviour = Callable[[], str]


class FakeUserStream:
    """The account stream, scripted: the test decides what the venue reports and when.

    Mirrors the real stream's contract (``start``, ``close``, ``connected``, ``as_dict``)
    and delivers :class:`ExecutionReport` objects to the same callbacks, so the adapter
    cannot tell the difference and the tests can replay every ordering the venue could
    produce: a report before the REST acknowledgement, a duplicate, a drop.
    """

    def __init__(self, venue: FakeVenue, *, now_ms: Callable[[], int], on_report: Callable[[ExecutionReport, int], None], on_balances: Callable[[list[AccountBalance], int], None] | None = None, on_status: Callable[[bool, str, int], None] | None = None) -> None:
        self.venue = venue
        self._now_ms = now_ms
        self._on_report = on_report
        self._on_balances = on_balances
        self._on_status = on_status
        self.connected = False
        self.started = False
        self.closed = False
        self.reports: list[ExecutionReport] = []

    def start(self) -> None:
        self.started = True
        self.connected = True
        if self._on_status is not None:
            self._on_status(True, "connected", self._now_ms())

    async def close(self) -> None:
        was_up = self.connected
        self.connected = False
        self.closed = True
        if was_up and self._on_status is not None:
            self._on_status(False, "closed", self._now_ms())

    def drop(self, reason: str = "socket closed by the venue") -> None:
        self.connected = False
        if self._on_status is not None:
            self._on_status(False, reason, self._now_ms())

    def reconnect(self) -> None:
        self.connected = True
        if self._on_status is not None:
            self._on_status(True, "reconnected", self._now_ms())

    def push_balances(self) -> None:
        if self._on_balances is not None:
            self._on_balances(list(self.venue.balances_now().values()), self._now_ms())

    def report(
        self,
        client_order_id: str,
        *,
        execution_type: str,
        status: OrderState,
        last_qty: float = 0.0,
        last_price: float | None = None,
        trade_id: str | None = None,
        is_maker: bool | None = True,
        commission: float = 0.0,
        commission_asset: str = "USDT",
        reject_reason: str = "",
        orig_client_order_id: str = "",
        venue_order_id: str | None = None,
        at: datetime | None = None,
        cumulative_qty: float | None = None,
    ) -> ExecutionReport:
        """Deliver one report as the venue would word it. Unknown orders are allowed on
        purpose: that is how a test says 'something this maker did not place'."""
        order = self.venue.orders.get(client_order_id)
        when = at or self.venue.clock.now()
        ms = int(when.timestamp() * 1000)
        report = ExecutionReport(
            event_time_ms=ms,
            transaction_time_ms=ms,
            symbol="BTCUSDT",
            client_order_id=client_order_id,
            orig_client_order_id=orig_client_order_id,
            venue_order_id=venue_order_id if venue_order_id is not None else (order.order_id if order is not None else "999999"),
            side=order.side if order is not None else Side.BUY,
            status=status,
            execution_type=execution_type,
            order_quantity=order.quantity if order is not None else last_qty,
            cumulative_quantity=cumulative_qty if cumulative_qty is not None else (order.filled_quantity if order is not None else last_qty),
            last_quantity=last_qty,
            last_price=last_price if last_price is not None else (order.limit_price or 0.0 if order is not None else 0.0),
            cumulative_quote_quantity=0.0,
            trade_id=trade_id,
            is_maker=is_maker,
            commission=commission,
            commission_asset=commission_asset,
            reject_reason=reject_reason,
            raw_status=status.value.upper(),
        )
        self.reports.append(report)
        self._on_report(report, self._now_ms())
        return report

    def fill_with_report(self, client_order_id: str, quantity: float, *, price: float | None = None, is_maker: bool | None = True, fee_asset: str | None = None, push_balances: bool = True) -> ExecutionReport:
        """The venue matches part or all of a resting order and reports it, as it would:
        the trade appears in the history too, so a later poll sees the same trade id."""
        fill = self.venue.venue_fill(client_order_id, quantity, price=price, is_maker=bool(is_maker), fee_asset=fee_asset)
        order = self.venue.orders[client_order_id]
        report = self.report(
            client_order_id,
            execution_type="trade",
            status=order.state,
            last_qty=quantity,
            last_price=fill.price,
            trade_id=fill.fill_id,
            is_maker=is_maker,
            commission=fill.fee,
            commission_asset=fill.fee_asset,
            at=fill.filled_at,
        )
        if push_balances:
            self.push_balances()
        return report

    def as_dict(self) -> dict[str, Any]:
        return {"fake": True, "connected": self.connected, "started": self.started, "closed": self.closed, "reports": len(self.reports)}


__all__ = ["FakeUserStream", "FakeVenue", "exchange_info"]
