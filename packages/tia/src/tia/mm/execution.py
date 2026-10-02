"""Execution for the market maker: one contract, the paper simulator behind it, and a live
adapter that reaches a venue only through the abstract ``ExecutionProvider``.

The engine speaks to ``MMExecution`` and nothing else: place the two sides of a quote,
cancel one order, cancel everything, list what is open, advance on a market event, report
statistics. :class:`~tia.mm.sim.PaperMarketMakerExecution` is that contract over simulated
orders and is unchanged. :class:`LiveMarketMakerExecution` is the same contract over a real
venue, with four rules that a simulator never needed:

* **Only post-only orders.** Every order is ``OrderType.LIMIT_MAKER`` on the venue's tick
  and lot grid, above its minimum notional, and never at or through the local book's
  opposite side. A rejection for "would immediately match" is recorded as a rejection:
  there is no fallback to LIMIT, to MARKET, or to a retry as a taker.
* **The hot path never waits for the network.** ``place``, ``cancel``, ``cancel_all`` and
  ``on_event`` are synchronous: they validate, update the local mirror and hand commands
  to a worker over an ``asyncio.Queue``. The worker does every request; its results come
  back through a deque the hot path drains on the next market event. No HTTP, SQL or
  disk write happens on the market-data callback.
* **A timeout is an unknown state, not a failure.** The order is marked ``unknown``, new
  orders are blocked, and the worker *asks* the venue by client order id. Present: adopted.
  Absent: the intent is dropped (a later decision may quote afresh); it is never resent.
* **Fills come from the venue's trade history**, with the trade id, the order id, the
  maker flag, the fee and the fee asset. A trade for an order this adapter does not know
  is a critical discrepancy; so is an open order it did not place. Binance wins every
  disagreement, and the adapter says so rather than papering over it.

Nothing in this module names a venue, a URL, a credential or a concrete provider class; the
boundary tests check that it never does.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from tia.core.clock import Clock
from tia.core.errors import (
    LiveActivationError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.core.logging import get_logger
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order, OrderIntent
from tia.execution.provider import ExecutionProvider
from tia.mm.latency import LatencyStats
from tia.mm.order_book import LocalOrderBook
from tia.mm.quoting import QuoteDecision
from tia.mm.sim import PaperMarketMakerExecution, SimulatedFill, SimulatedOrder

_log = get_logger("mm.execution")

#: States in which an order is still ours to hold or to cancel.
OPEN_STATES = ("pending_arrival", "resting")
#: States in which nothing further can happen to an order from our side.
TERMINAL_STATES = ("filled", "cancelled", "refused")
#: Every live client order id starts with this; an open order on the account without it
#: was not placed by this market maker.
CLIENT_ID_PREFIX = "tiamm-"
#: The venue's documented code for a post-only order that would have taken liquidity.
#: REQUIRES VALIDATION.
WOULD_TAKE_CODE = -2010


class MMExecution(Protocol):
    """What the engine needs from an execution, paper or live."""

    mode: str
    orders: dict[str, Any]
    last_unresolved: list[tuple[Any, float]]

    def place(self, decision: QuoteDecision, t_ms: int) -> list[Any]: ...

    def cancel(self, order_id: str, t_ms: int, *, reason: str) -> None: ...

    def cancel_all(self, t_ms: int, *, reason: str) -> int: ...

    def open_orders(self) -> list[Any]: ...

    def on_event(self, kind: str, event: Any, book: LocalOrderBook, t_ms: int) -> list[Any]: ...

    def stats(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------- filters


@dataclass(frozen=True)
class SymbolFilters:
    """The venue's grid for one symbol: what an order must round to, and its minimums.

    Read from the venue's exchange information, never assumed. REQUIRES VALIDATION of the
    field names on the real venue.
    """

    symbol: str
    tick_size: float
    step_size: float
    min_qty: float
    max_qty: float
    min_notional: float
    source: str = "exchange_info"
    order_types: tuple[str, ...] = ()

    @classmethod
    def from_exchange_info(cls, payload: dict[str, Any], *, symbol: str, venue_symbol: str) -> SymbolFilters:
        rows = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValueError("exchange information carries no symbols")
        row = next((r for r in rows if str(r.get("symbol", "")).upper() == venue_symbol.upper()), None)
        if row is None:
            if len(rows) != 1:
                raise ValueError(f"exchange information does not describe {venue_symbol}")
            row = rows[0]
        status = str(row.get("status", "")).upper()
        if status and status != "TRADING":
            raise ValueError(f"{venue_symbol} is not trading at the venue: status {status}")
        order_types = tuple(str(x) for x in (row.get("orderTypes") or ()))
        if order_types and "LIMIT_MAKER" not in order_types:
            raise ValueError(f"{venue_symbol} does not accept LIMIT_MAKER orders: {order_types}")
        by_type = {str(f.get("filterType", "")): f for f in (row.get("filters") or ()) if isinstance(f, dict)}
        try:
            price = by_type["PRICE_FILTER"]
            lot = by_type["LOT_SIZE"]
        except KeyError as exc:
            raise ValueError(f"exchange information for {venue_symbol} lacks the {exc.args[0]} filter") from exc
        notional_filter = by_type.get("NOTIONAL") or by_type.get("MIN_NOTIONAL")
        if notional_filter is None:
            raise ValueError(f"exchange information for {venue_symbol} lacks a notional filter")
        filters = cls(
            symbol=symbol,
            tick_size=float(price["tickSize"]),
            step_size=float(lot["stepSize"]),
            min_qty=float(lot["minQty"]),
            max_qty=float(lot.get("maxQty", 1e12)),
            min_notional=float(notional_filter["minNotional"]),
            order_types=order_types,
        )
        if filters.tick_size <= 0 or filters.step_size <= 0 or filters.min_qty <= 0:
            raise ValueError(f"exchange information for {venue_symbol} has a non-positive grid: {filters.as_dict()}")
        return filters

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tick_size": self.tick_size,
            "step_size": self.step_size,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "min_notional": self.min_notional,
            "source": self.source,
            "order_types": list(self.order_types),
        }


def _on_grid(value: float, step: float) -> bool:
    units = value / step
    return abs(units - round(units)) < 1e-6


@dataclass(frozen=True)
class MakerCheck:
    side: str
    ok: bool
    reason: str
    price: float | None
    quantity: float

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def validate_maker_order(
    side: str,
    price: float,
    quantity: float,
    filters: SymbolFilters,
    *,
    best_bid: float | None,
    best_ask: float | None,
) -> MakerCheck:
    """A post-only order the venue will accept and that cannot take liquidity.

    Refuses rather than re-rounds: the quoting engine rounds to its configured grid, and a
    disagreement between that grid and the venue's is a configuration error to surface,
    not to hide at the last moment.
    """

    def refuse(reason: str) -> MakerCheck:
        return MakerCheck(side, False, reason, price, quantity)

    if side not in ("buy", "sell"):
        return refuse(f"unknown side {side!r}")
    if price <= 0 or quantity <= 0:
        return refuse("price and quantity must be positive")
    if not _on_grid(price, filters.tick_size):
        return refuse(f"price {price} is not on the tick grid {filters.tick_size}")
    if not _on_grid(quantity, filters.step_size):
        return refuse(f"quantity {quantity} is not on the lot step {filters.step_size}")
    if quantity < filters.min_qty:
        return refuse(f"quantity {quantity} below the minimum {filters.min_qty}")
    if quantity > filters.max_qty:
        return refuse(f"quantity {quantity} above the maximum {filters.max_qty}")
    if price * quantity < filters.min_notional:
        return refuse(f"notional {price * quantity:.4f} below the minimum {filters.min_notional}")
    if best_bid is None or best_ask is None:
        return refuse("no valid top of book to check for crossing")
    if side == "buy" and price >= best_ask:
        return refuse(f"bid {price} at or through the ask {best_ask}: would take, not make")
    if side == "sell" and price <= best_bid:
        return refuse(f"ask {price} at or through the bid {best_bid}: would take, not make")
    return MakerCheck(side, True, "", price, quantity)


# ---------------------------------------------------------------------------- live orders


@dataclass(frozen=True)
class LiveFill:
    """A confirmed venue trade on one of our orders. The only thing the live ledger books."""

    fill_id: str  # the venue's trade id
    order_id: str  # our client order id
    side: str
    price: float
    quantity: float
    t_ms: int  # venue trade time
    venue_trade_ids: tuple[int, ...]
    queue_ahead_at_arrival: float = 0.0
    mid_at_fill: float | None = None
    resolution: str = "confirmed"
    fee: float = 0.0
    fee_asset: str = ""
    fee_usd: float = 0.0
    #: "venue" (fee in the quote asset), "converted_from_base" (fee in the base asset,
    #: valued at the trade price) or "unconverted:<asset>" (a third asset: the ledger
    #: applies its assumed fee instead and counts the case).
    fee_status: str = "venue"
    liquidity: str = "maker"
    venue_order_id: str = ""
    received_at_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class LiveOrder:
    """Our picture of one order at the venue. Advanced only by venue responses."""

    order_id: str  # client order id
    side: str
    price: float
    quantity: float
    t_decision_ms: int
    ttl_ms: int
    reason: str
    authorization_id: str = ""
    state: str = "pending_arrival"  # resting | filled | cancelled | refused | unknown
    venue_order_id: str = ""
    venue_state: str = ""
    venue_executed_qty: float = 0.0
    t_submitted_ms: int | None = None
    t_ack_ms: int | None = None
    t_cancel_requested_ms: int | None = None
    t_cancel_effective_ms: int | None = None
    cancel_reason: str = ""
    reject_reason: str = ""
    unknown_reason: str = ""
    fills: list[LiveFill] = field(default_factory=list)
    queue: Any = None  # no queue model for a real order; the engine checks for None
    closed: bool = False

    @property
    def filled(self) -> float:
        return sum(f.quantity for f in self.fills)

    @property
    def remaining(self) -> float:
        return max(0.0, self.quantity - self.filled)

    @property
    def unresolved(self) -> float:
        return 0.0

    @property
    def t_arrival_ms(self) -> int:
        return self.t_ack_ms if self.t_ack_ms is not None else (self.t_submitted_ms or self.t_decision_ms)

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "venue_order_id": self.venue_order_id,
            "side": self.side,
            "price": self.price,
            "quantity": self.quantity,
            "filled": self.filled,
            "venue_executed_qty": self.venue_executed_qty,
            "unresolved": 0.0,
            "state": self.state,
            "venue_state": self.venue_state,
            "t_decision_ms": self.t_decision_ms,
            "t_submitted_ms": self.t_submitted_ms,
            "t_arrival_ms": self.t_arrival_ms,
            "t_ack_ms": self.t_ack_ms,
            "t_cancel_requested_ms": self.t_cancel_requested_ms,
            "t_cancel_effective_ms": self.t_cancel_effective_ms,
            "cancel_reason": self.cancel_reason,
            "reject_reason": self.reject_reason,
            "unknown_reason": self.unknown_reason,
            "reason": self.reason,
            "authorization_id": self.authorization_id,
            "queue": None,
        }


# ---------------------------------------------------------------------------- live adapter


_VENUE_TO_LOCAL = {
    OrderState.ACKNOWLEDGED: "resting",
    OrderState.SUBMITTED: "resting",
    OrderState.PARTIALLY_FILLED: "resting",
    OrderState.CANCEL_REQUESTED: "resting",
    OrderState.FILLED: "filled",
    OrderState.CANCELLED: "cancelled",
    OrderState.REJECTED: "refused",
    OrderState.EXPIRED: "cancelled",
    OrderState.FAILED: "refused",
}


class LiveMarketMakerExecution:
    """The market maker's orders at a real venue, through the abstract provider.

    ``provider`` may be simulated (a testnet, or a fake in tests) or live; a live one
    carries the activation token the provider layer demanded at its construction, and this
    class refuses one that claims to be live without it. Before every submission the
    provider is asked again whether it may trade (the token expires).
    """

    mode = "live"

    def __init__(
        self,
        provider: ExecutionProvider,
        *,
        clock: Clock,
        filters: SymbolFilters,
        symbol: str,
        run_tag: str,
        now_ms: Callable[[], int] | None = None,
        fingerprint: str | None = None,
        strict_cancel_replace: bool = True,
        trades_poll_interval_ms: int = 3_000,
        idle_trades_poll_interval_ms: int = 30_000,
        open_sync_interval_ms: int = 10_000,
        closed_poll_grace_ms: int = 30_000,
        trades_limit: int = 200,
        resolve_attempts: int = 3,
        resolve_backoff_s: float = 1.0,
        max_api_errors_per_minute: int = 10,
        foreign_orders_critical: bool = True,
        keep_closed: int = 2_000,
        on_critical: Callable[[str, str], None] | None = None,
    ) -> None:
        if getattr(provider, "is_live", False) and getattr(provider, "activation", None) is None:
            raise LiveActivationError(
                "a live execution provider without an activation token reached the market "
                "maker; refusing to build an execution over it"
            )
        self._provider = provider
        self._clock = clock
        self.filters = filters
        self.symbol = symbol
        self.run_tag = run_tag
        self._now_ms = now_ms or clock.timestamp_ms
        self._fingerprint = fingerprint
        self.strict_cancel_replace = strict_cancel_replace
        self.trades_poll_interval_ms = trades_poll_interval_ms
        self.idle_trades_poll_interval_ms = idle_trades_poll_interval_ms
        self.open_sync_interval_ms = open_sync_interval_ms
        self.closed_poll_grace_ms = closed_poll_grace_ms
        self.trades_limit = trades_limit
        self.resolve_attempts = resolve_attempts
        self.resolve_backoff_s = resolve_backoff_s
        self.max_api_errors_per_minute = max_api_errors_per_minute
        self.foreign_orders_critical = foreign_orders_critical
        self._keep_closed = keep_closed
        self._on_critical = on_critical
        self._trades_by_symbol = "symbol" in inspect.signature(provider.get_trades).parameters
        self._open_by_symbol = "symbol" in inspect.signature(provider.get_orders).parameters

        #: Open or in-flight orders, by client order id; the engine reads this directly.
        self.orders: dict[str, LiveOrder] = {}
        self.closed: deque[LiveOrder] = deque()
        self._all: dict[str, LiveOrder] = {}
        self._by_venue_id: dict[str, str] = {}
        self._worker_acked: set[str] = set()
        self._seq = 0
        self._commands: asyncio.Queue[tuple[str, Any] | None] | None = None
        self._outcomes: deque[tuple[str, Any]] = deque()
        self._worker: asyncio.Task[Any] | None = None
        self._book: LocalOrderBook | None = None
        self._last_t_ms: int | None = None
        self._last_trade_poll_ms: int | None = None
        self._last_open_sync_ms: int | None = None
        self._poll_due = False
        self._last_close_ms: int | None = None
        self._seen_trade_ids: set[str] = set()
        self._seen_trade_order: deque[str] = deque()
        self.trade_baseline_ms: int | None = None
        self._api_error_times: deque[int] = deque()
        self.blocked_reason = ""
        self.critical_reason = ""
        self.last_refusal = ""
        self.last_unresolved: list[tuple[Any, float]] = []  # no queue model: always empty
        self.submit_to_ack_ms = LatencyStats()
        self.cancel_to_ack_ms = LatencyStats()
        self.recent_fills: deque[LiveFill] = deque(maxlen=5_000)
        self.counters: dict[str, int] = dict.fromkeys(("placed", "submitted", "acked", "rejected", "rejected_would_cross", "refused_validation", "refused_blocked", "deferred_cancel_pending", "cancel_requests", "cancelled", "cancelled_before_submit", "cancel_raced_fill", "expired", "unknown", "resolved_present", "resolved_absent", "unresolved", "fills", "maker_fills", "taker_fills", "unknown_fills", "historical_trades", "api_errors", "activation_refusals", "venue_orders_unknown_locally", "foreign_open_orders", "missing_at_venue", "worker_errors"), 0)

    # ------------------------------------------------------------------ identity

    @property
    def is_live(self) -> bool:
        return bool(getattr(self._provider, "is_live", False))

    @property
    def venue(self) -> str:
        return str(getattr(self._provider, "name", "unknown"))

    @property
    def provider(self) -> ExecutionProvider:
        return self._provider

    def _next_client_id(self, t_ms: int) -> str:
        self._seq += 1
        # <= 36 characters, [A-Za-z0-9_-]: "tiamm-" + 8 + "-" + 13 + "-" + 6.
        return f"{CLIENT_ID_PREFIX}{self.run_tag[:8]}-{t_ms}-{self._seq:06d}"

    # ------------------------------------------------------------------ lifecycle

    @property
    def worker_running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    async def start(self) -> None:
        if self.worker_running:
            return
        self._commands = asyncio.Queue()
        self._worker = asyncio.get_running_loop().create_task(self._run(), name="mm-live-execution")

    async def close(self) -> None:
        if self._commands is not None:
            await self._commands.put(None)
        if self._worker is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._worker, timeout=10.0)
            self._worker = None
        self._commands = None

    def _enqueue(self, kind: str, payload: Any) -> bool:
        if self._commands is None:
            return False
        self._commands.put_nowait((kind, payload))
        return True

    # ------------------------------------------------------------------ the hot path

    def place(self, decision: QuoteDecision, t_ms: int) -> list[LiveOrder]:
        """Validate both sides as post-only orders and hand them to the worker. Returns the
        orders accepted for submission (possibly none)."""
        if self.blocked_reason:
            self.counters["refused_blocked"] += 1
            self.last_refusal = f"blocked: {self.blocked_reason}"
            return []
        if self._commands is None:
            self.counters["refused_blocked"] += 1
            self.last_refusal = "execution worker not started"
            return []
        book = self._book
        best_bid = book.best_bid() if book is not None and book.is_valid else None
        best_ask = book.best_ask() if book is not None and book.is_valid else None
        if decision.bid_price is not None and decision.ask_price is not None and decision.bid_price >= decision.ask_price:
            self.counters["refused_validation"] += 1
            self.last_refusal = f"bid {decision.bid_price} >= ask {decision.ask_price}: refused"
            return []
        out: list[LiveOrder] = []
        for side, price, qty in (("buy", decision.bid_price, decision.bid_size), ("sell", decision.ask_price, decision.ask_size)):
            if price is None or qty <= 0:
                continue
            if self.strict_cancel_replace and any(
                o.side == side and o.is_open and (o.t_cancel_requested_ms is not None or o.state == "pending_arrival")
                for o in self.orders.values()
            ):
                # The previous order on this side has not been confirmed gone (or confirmed
                # present): a replacement now would risk two resting orders on one side.
                self.counters["deferred_cancel_pending"] += 1
                self.last_refusal = f"{side}: previous order not yet confirmed by the venue; replacement deferred"
                continue
            check = validate_maker_order(side, price, qty, self.filters, best_bid=best_bid[0] if best_bid else None, best_ask=best_ask[0] if best_ask else None)
            if not check.ok:
                self.counters["refused_validation"] += 1
                self.last_refusal = f"{side}: {check.reason}"
                _log.warning("mm_live_order_refused", side=side, reason=check.reason)
                continue
            order = LiveOrder(
                order_id=self._next_client_id(t_ms),
                side=side,
                price=price,
                quantity=qty,
                t_decision_ms=decision.t_ms,
                ttl_ms=decision.ttl_ms,
                reason=decision.quote_reason,
                authorization_id=f"decision-{decision.t_ms}",
            )
            self.orders[order.order_id] = order
            self._all[order.order_id] = order
            self.counters["placed"] += 1
            self._enqueue("submit", order)
            out.append(order)
        return out

    def cancel(self, order_id: str, t_ms: int, *, reason: str) -> None:
        order = self.orders.get(order_id)
        if order is None or not order.is_open or order.t_cancel_requested_ms is not None:
            return
        order.t_cancel_requested_ms = t_ms
        order.cancel_reason = reason
        self.counters["cancel_requests"] += 1
        self._enqueue("cancel", order)

    def cancel_all(self, t_ms: int, *, reason: str) -> int:
        count = 0
        for order in list(self.orders.values()):
            if order.is_open and order.t_cancel_requested_ms is None:
                self.cancel(order.order_id, t_ms, reason=reason)
                count += 1
        return count

    def open_orders(self) -> list[LiveOrder]:
        return [o for o in self.orders.values() if o.is_open]

    def unknown_orders(self) -> list[LiveOrder]:
        return [o for o in self.orders.values() if o.state == "unknown"]

    def on_event(self, kind: str, event: Any, book: LocalOrderBook, t_ms: int) -> list[LiveFill]:  # noqa: ARG002 - contract
        """Apply what the worker learnt since the last event; expire quotes; schedule polls.
        Returns the fills confirmed by the venue since the last call."""
        self._book = book
        self._last_t_ms = t_ms
        produced = self._drain(t_ms)
        for order in list(self.orders.values()):
            if order.state == "resting" and order.t_cancel_requested_ms is None and order.t_ack_ms is not None and t_ms >= order.t_ack_ms + order.ttl_ms:
                self.counters["expired"] += 1
                self.cancel(order.order_id, t_ms, reason="ttl expired")
        if self._last_trade_poll_ms is None or self._last_open_sync_ms is None:
            # The first event only starts the clocks: the service reconciled at start.
            self._last_trade_poll_ms = self._last_open_sync_ms = t_ms
        elif self._commands is not None:
            recently_closed = self._last_close_ms is not None and t_ms - self._last_close_ms <= self.closed_poll_grace_ms
            busy = self._poll_due or bool(self.orders) or recently_closed
            interval = self.trades_poll_interval_ms if busy else self.idle_trades_poll_interval_ms
            if t_ms - self._last_trade_poll_ms >= interval:
                self._last_trade_poll_ms = t_ms
                self._poll_due = False
                self._enqueue("poll_trades", None)
            if t_ms - self._last_open_sync_ms >= self.open_sync_interval_ms:
                self._last_open_sync_ms = t_ms
                self._enqueue("sync_open", None)
        return produced

    # ------------------------------------------------------------------ absorbing venue facts

    def absorb_open_orders(self, venue_open: list[Order]) -> None:
        """Hand the venue's open orders (read elsewhere) to the next drain."""
        self._outcomes.append(("open_orders", venue_open))

    def absorb_trades(self, trades: list[Fill]) -> None:
        self._outcomes.append(("trades", trades))

    def set_trade_baseline(self, trades: list[Fill], *, at_ms: int) -> int:
        """Trades that existed before this run: remembered by id so they are never booked,
        and the latest venue time among them bounds what counts as historical."""
        latest = 0
        for fill in trades:
            self._remember_trade(fill.fill_id)
            latest = max(latest, _ms(fill))
        self.trade_baseline_ms = max(latest, at_ms - 60_000)  # a minute of clock slack
        self.counters["historical_trades"] += len(trades)
        return len(trades)

    def resolve_now(self, order_id: str) -> bool:
        order = self._all.get(order_id)
        if order is None:
            return False
        return self._enqueue("resolve", order)

    # ------------------------------------------------------------------ applying outcomes

    def _drain(self, t_ms: int) -> list[LiveFill]:
        produced: list[LiveFill] = []
        while self._outcomes:
            kind, payload = self._outcomes.popleft()
            try:
                if kind == "acked":
                    self._apply_ack(payload[0], payload[1], t_ms)
                elif kind == "rejected":
                    self._apply_reject(payload[0], payload[1], payload[2], t_ms)
                elif kind == "unknown":
                    self._apply_unknown(payload[0], payload[1], t_ms)
                elif kind == "resolved":
                    self._apply_resolved(payload[0], payload[1], t_ms)
                elif kind == "unresolved":
                    self._apply_unresolved(payload[0], payload[1], t_ms)
                elif kind == "cancelled":
                    self._apply_cancel_response(payload[0], payload[1], t_ms)
                elif kind == "cancel_rejected":
                    self._apply_cancel_rejected(payload[0], payload[1], payload[2], t_ms)
                elif kind == "cancelled_before_submit":
                    self._apply_cancelled_before_submit(payload, t_ms)
                elif kind == "unavailable":
                    self._apply_unavailable(payload[0], payload[1], t_ms)
                elif kind == "activation_refused":
                    self._apply_activation_refused(payload[0], payload[1], t_ms)
                elif kind == "trades":
                    produced.extend(self._apply_trades(payload, t_ms))
                elif kind == "open_orders":
                    self._apply_open_orders(payload, t_ms)
                elif kind == "api_error":
                    self._note_api_error(payload[0], payload[1], t_ms)
            except Exception as exc:  # an outcome that cannot be applied is a critical fact, not a crash
                self.counters["worker_errors"] += 1
                self._critical("outcome_apply_failed", f"{kind}: {type(exc).__name__}: {str(exc)[:160]}")
        return produced

    def _close(self, order: LiveOrder, t_ms: int) -> None:
        if order.closed:
            return
        order.closed = True
        self.orders.pop(order.order_id, None)
        self.closed.append(order)
        self._last_close_ms = t_ms
        while len(self.closed) > self._keep_closed:
            gone = self.closed.popleft()
            self._all.pop(gone.order_id, None)
            if gone.venue_order_id:
                self._by_venue_id.pop(gone.venue_order_id, None)
        if not self.unknown_orders() and self.blocked_reason.startswith("order "):
            self.blocked_reason = ""

    def _adopt_venue_state(self, order: LiveOrder, venue: Order, t_ms: int) -> None:
        if venue.order_id:
            order.venue_order_id = str(venue.order_id)
            self._by_venue_id[order.venue_order_id] = order.order_id
        order.venue_state = venue.state.value
        if venue.filled_quantity > order.venue_executed_qty:
            order.venue_executed_qty = venue.filled_quantity
        if order.venue_executed_qty > order.filled + 1e-12:
            self._poll_due = True  # the venue says more filled than we have booked: ask for the trades
        if order.closed:
            return  # already terminal here; the venue's later readings cannot reopen it
        local = _VENUE_TO_LOCAL.get(venue.state)
        if local is None:
            self._apply_unknown(order, f"venue state {venue.state.value} has no local meaning", t_ms)
            return
        if local == "refused":
            order.reject_reason = venue.reject_reason or venue.state.value
        order.state = local
        if local in TERMINAL_STATES:
            if local == "cancelled":
                self.counters["cancelled"] += 1
                order.t_cancel_effective_ms = t_ms
                if order.t_cancel_requested_ms is not None:
                    self.cancel_to_ack_ms.add(t_ms - order.t_cancel_requested_ms)
            self._close(order, t_ms)

    def _apply_ack(self, order: LiveOrder, venue: Order, t_ms: int) -> None:
        self.counters["acked"] += 1
        order.t_ack_ms = t_ms
        if order.t_submitted_ms is not None:
            self.submit_to_ack_ms.add(t_ms - order.t_submitted_ms)
        self._adopt_venue_state(order, venue, t_ms)

    def _apply_reject(self, order: LiveOrder, code: Any, message: str, t_ms: int) -> None:
        self.counters["rejected"] += 1
        if code == WOULD_TAKE_CODE:
            self.counters["rejected_would_cross"] += 1
        order.state = "refused"
        order.reject_reason = f"venue rejected (code {code}): {message[:160]}"
        _log.warning("mm_live_order_rejected", order=order.order_id, code=code, detail=message[:160])
        self._close(order, t_ms)

    def _apply_unknown(self, order: LiveOrder, reason: str, t_ms: int) -> None:  # noqa: ARG002 - time kept for symmetry
        if order.state != "unknown":
            self.counters["unknown"] += 1
        order.state = "unknown"
        order.unknown_reason = reason[:200]
        self.blocked_reason = f"order {order.order_id} in UNKNOWN state: {reason[:120]}; reconcile before quoting"
        _log.error("mm_live_order_unknown", order=order.order_id, detail=reason[:200])
        self._critical("unknown_order_state", self.blocked_reason)

    def _apply_resolved(self, order: LiveOrder, venue: Order | None, t_ms: int) -> None:
        if venue is None:
            self.counters["resolved_absent"] += 1
            order.state = "refused"
            order.reject_reason = "never reached the venue (resolved absent); the intent is not resent"
            self._close(order, t_ms)
            return
        self.counters["resolved_present"] += 1
        order.unknown_reason = ""
        if order.t_ack_ms is None:
            order.t_ack_ms = t_ms
        self._adopt_venue_state(order, venue, t_ms)
        if order.is_open and not self.unknown_orders() and self.blocked_reason.startswith("order "):
            self.blocked_reason = ""

    def _apply_unresolved(self, order: LiveOrder, detail: str, t_ms: int) -> None:  # noqa: ARG002
        self.counters["unresolved"] += 1
        order.unknown_reason = f"unresolved after {self.resolve_attempts} attempts: {detail[:120]}"
        self.blocked_reason = f"order {order.order_id} could not be resolved: {detail[:120]}"
        self._critical("unresolved_order", self.blocked_reason)

    def _apply_cancel_response(self, order: LiveOrder, venue: Order, t_ms: int) -> None:
        if venue.state is OrderState.FILLED:
            # The venue answered the cancel with "filled": the print beat the cancel.
            self.counters["cancel_raced_fill"] += 1
        self._adopt_venue_state(order, venue, t_ms)
        if order.is_open and order.t_cancel_requested_ms is not None:
            # The venue answered but did not confirm the cancel (pending): ask again.
            self._enqueue("resolve", order)

    def _apply_cancel_rejected(self, order: LiveOrder, code: Any, message: str, t_ms: int) -> None:  # noqa: ARG002
        # The venue refused to cancel: the order is most likely already closed there.
        order.cancel_reason = f"{order.cancel_reason} | cancel rejected (code {code}): {message[:120]}"
        self._enqueue("resolve", order)

    def _apply_cancelled_before_submit(self, order: LiveOrder, t_ms: int) -> None:
        self.counters["cancelled_before_submit"] += 1
        order.state = "cancelled"
        order.t_cancel_effective_ms = t_ms
        self._close(order, t_ms)

    def _apply_unavailable(self, order: LiveOrder, message: str, t_ms: int) -> None:
        order.state = "refused"
        order.reject_reason = f"not sent: {message[:160]}"
        self._note_api_error("submit", message, t_ms)
        self._close(order, t_ms)

    def _apply_activation_refused(self, order: LiveOrder, message: str, t_ms: int) -> None:
        self.counters["activation_refusals"] += 1
        order.state = "refused"
        order.reject_reason = f"activation refused: {message[:160]}"
        self.blocked_reason = f"activation: {message[:160]}"
        self._close(order, t_ms)
        self._critical("activation", message)

    def _remember_trade(self, trade_id: str) -> None:
        self._seen_trade_ids.add(trade_id)
        self._seen_trade_order.append(trade_id)
        while len(self._seen_trade_order) > 50_000:
            self._seen_trade_ids.discard(self._seen_trade_order.popleft())

    def _apply_trades(self, trades: list[Fill], t_ms: int) -> list[LiveFill]:
        produced: list[LiveFill] = []
        for fill in sorted(trades, key=_ms):
            if fill.fill_id in self._seen_trade_ids:
                continue
            self._remember_trade(fill.fill_id)
            when = _ms(fill)
            if self.trade_baseline_ms is not None and when < self.trade_baseline_ms:
                self.counters["historical_trades"] += 1
                continue
            client_id = self._by_venue_id.get(str(fill.order_id))
            order = self._all.get(client_id) if client_id else None
            if order is None:
                self.counters["unknown_fills"] += 1
                self._critical("unknown_fill", f"venue trade {fill.fill_id} on order {fill.order_id} this maker did not place")
                continue
            live = self._live_fill(order, fill, t_ms)
            order.fills.append(live)
            self.recent_fills.append(live)
            self.counters["fills"] += 1
            self.counters["maker_fills" if live.liquidity == "maker" else "taker_fills"] += 1
            if live.liquidity != "maker":
                _log.error("mm_live_taker_fill", order=order.order_id, trade=live.fill_id)
            produced.append(live)
            if order.is_open and order.remaining <= self.filters.step_size / 2.0:
                order.state = "filled"
                order.venue_state = OrderState.FILLED.value
                self._close(order, t_ms)
        return produced

    def _live_fill(self, order: LiveOrder, fill: Fill, t_ms: int) -> LiveFill:
        asset = (fill.fee_asset or "").upper()
        base, _, quote = self.symbol.partition("-")
        quote_names = {quote.upper(), "USDT"} if quote.upper() == "USD" else {quote.upper()}
        if not asset or asset in quote_names:
            fee_usd, status = fill.fee, "venue"
        elif asset == base.upper():
            fee_usd, status = fill.fee * fill.price, "converted_from_base"
        else:
            fee_usd, status = 0.0, f"unconverted:{asset}"
        book = self._book
        return LiveFill(
            fill_id=str(fill.fill_id),
            order_id=order.order_id,
            side=order.side,
            price=fill.price,
            quantity=fill.quantity,
            t_ms=_ms(fill),
            venue_trade_ids=(int(fill.fill_id),) if str(fill.fill_id).isdigit() else (),
            mid_at_fill=book.mid if book is not None and book.is_valid else None,
            fee=fill.fee,
            fee_asset=asset,
            fee_usd=fee_usd,
            fee_status=status,
            liquidity=fill.liquidity,
            venue_order_id=str(fill.order_id),
            received_at_ms=t_ms,
        )

    def _apply_open_orders(self, venue_open: list[Order], t_ms: int) -> None:
        venue_ids: set[str] = set()
        for venue in venue_open:
            cid = venue.client_order_id or ""
            venue_ids.add(cid)
            local = self._all.get(cid)
            if local is not None:
                if local.state == "pending_arrival" and local.venue_order_id == "":
                    # Acked at the venue before the submit response reached us.
                    self._apply_ack(local, venue, t_ms)
                elif local.is_open:
                    self._adopt_venue_state(local, venue, t_ms)
                continue
            if cid.startswith(CLIENT_ID_PREFIX):
                self.counters["venue_orders_unknown_locally"] += 1
                self._critical("venue_order_unknown_locally", f"the venue holds an open market-maker order {cid} this run does not know")
            else:
                self.counters["foreign_open_orders"] += 1
                if self.foreign_orders_critical:
                    self._critical("foreign_open_order", f"an open order not placed by this market maker is on the account: {cid or venue.order_id}")
        for order in list(self.orders.values()):
            if order.state == "resting" and order.order_id not in venue_ids:
                # Resting here, absent there: filled, cancelled or expired meanwhile. Ask.
                self.counters["missing_at_venue"] += 1
                self._enqueue("resolve", order)

    def _note_api_error(self, what: str, message: str, t_ms: int) -> None:
        self.counters["api_errors"] += 1
        self._api_error_times.append(t_ms)
        while self._api_error_times and self._api_error_times[0] < t_ms - 60_000:
            self._api_error_times.popleft()
        _log.warning("mm_live_api_error", what=what, detail=message[:160])
        if len(self._api_error_times) > self.max_api_errors_per_minute:
            self._critical("excessive_api_errors", f"{len(self._api_error_times)} API errors in the last minute (limit {self.max_api_errors_per_minute}); last: {what}: {message[:100]}")

    def _critical(self, kind: str, reason: str) -> None:
        self.critical_reason = f"{kind}: {reason}"
        if self._on_critical is not None:
            with contextlib.suppress(Exception):
                self._on_critical(kind, reason)

    # ------------------------------------------------------------------ the worker

    async def _run(self) -> None:
        queue = self._commands
        if queue is None:  # pragma: no cover - start() always sets it
            return
        while True:
            item = await queue.get()
            if item is None:
                return
            kind, payload = item
            try:
                if kind == "submit":
                    await self._do_submit(payload)
                elif kind == "cancel":
                    await self._do_cancel(payload)
                elif kind == "resolve":
                    await self._resolve_with_retries(payload)
                elif kind == "poll_trades":
                    self._outcomes.append(("trades", await self.fetch_trades()))
                elif kind == "sync_open":
                    self._outcomes.append(("open_orders", await self.fetch_open_orders()))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._outcomes.append(("api_error", (kind, f"{type(exc).__name__}: {exc}")))

    def _intent(self, order: LiveOrder) -> OrderIntent:
        return OrderIntent(
            intent_id=order.order_id,
            client_order_id=order.order_id,
            signal_id=f"mm-decision-{order.t_decision_ms}",
            risk_decision_id=order.authorization_id or "mm",
            symbol=self.symbol,
            side=Side.BUY if order.side == "buy" else Side.SELL,
            order_type=OrderType.LIMIT_MAKER,
            quantity=order.quantity,
            limit_price=order.price,
            created_at=self._clock.now(),
            correlation_id=self.run_tag,
        )

    async def _do_submit(self, order: LiveOrder) -> None:
        if order.t_cancel_requested_ms is not None:
            self._outcomes.append(("cancelled_before_submit", order))
            return
        intent = self._intent(order)
        try:
            self._provider.assert_may_trade(fingerprint=self._fingerprint)
            order.t_submitted_ms = self._now_ms()
            self.counters["submitted"] += 1
            venue = await self._provider.submit_order(intent)
        except LiveActivationError as exc:
            self._outcomes.append(("activation_refused", (order, str(exc))))
        except OrderRejectedError as exc:
            self._outcomes.append(("rejected", (order, exc.context.get("code"), str(exc))))
        except ProviderUnavailableError as exc:
            if "rate limited" in str(exc):
                self._outcomes.append(("unavailable", (order, str(exc))))  # the venue answered: not sent
            else:
                self._outcomes.append(("unknown", (order, str(exc))))  # a transport fault may have sent it
                await self._resolve_with_retries(order)
        except ReconciliationError as exc:
            self._outcomes.append(("unknown", (order, str(exc))))
            await self._resolve_with_retries(order)
        except Exception as exc:
            self._outcomes.append(("unknown", (order, f"{type(exc).__name__}: {exc}")))
            await self._resolve_with_retries(order)
        else:
            self._worker_acked.add(order.order_id)
            self._outcomes.append(("acked", (order, venue)))

    async def _do_cancel(self, order: LiveOrder) -> None:
        if order.state in TERMINAL_STATES or order.state == "unknown":
            return
        if order.order_id not in self._worker_acked:
            return  # never reached the venue (rejected, unknown or not sent): nothing to cancel
        try:
            venue = await self._provider.cancel_order(order.order_id)
        except LiveActivationError as exc:
            self._outcomes.append(("activation_refused", (order, f"cancel: {exc}")))
        except OrderRejectedError as exc:
            self._outcomes.append(("cancel_rejected", (order, exc.context.get("code"), str(exc))))
        except Exception as exc:
            self._outcomes.append(("unknown", (order, f"cancel: {type(exc).__name__}: {exc}")))
            await self._resolve_with_retries(order)
        else:
            self._outcomes.append(("cancelled", (order, venue)))

    async def _resolve_with_retries(self, order: LiveOrder) -> None:
        resolver = getattr(self._provider, "resolve_unknown_order", None)
        detail = ""
        for attempt in range(max(1, self.resolve_attempts)):
            try:
                if resolver is not None:
                    venue = await resolver(symbol=self.symbol, client_order_id=order.order_id)
                else:
                    venue = await self._provider.get_order(order.order_id)
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                self._outcomes.append(("api_error", ("resolve", detail)))
                await asyncio.sleep(self.resolve_backoff_s * (attempt + 1))
                continue
            if venue is not None:
                self._worker_acked.add(order.order_id)
            self._outcomes.append(("resolved", (order, venue)))
            return
        self._outcomes.append(("unresolved", (order, detail)))

    async def fetch_trades(self) -> list[Fill]:
        if self._trades_by_symbol:
            return list(await self._provider.get_trades(limit=self.trades_limit, symbol=self.symbol))  # type: ignore[call-arg]
        return list(await self._provider.get_trades(limit=self.trades_limit))

    async def fetch_open_orders(self) -> list[Order]:
        if self._open_by_symbol:
            return list(await self._provider.get_orders(open_only=True, symbol=self.symbol))  # type: ignore[call-arg]
        return list(await self._provider.get_orders(open_only=True))

    # ------------------------------------------------------------------ reading

    def stats(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        for order in self.closed:
            states[order.state] = states.get(order.state, 0) + 1
        for order in self.orders.values():
            states[order.state] = states.get(order.state, 0) + 1
        partial = sum(1 for o in list(self.closed) + list(self.orders.values()) if 0 < o.filled < o.quantity)
        c = self.counters
        return {
            "mode": self.mode,
            "venue": self.venue,
            "is_live": self.is_live,
            **c,
            "refused_crossed": c["rejected_would_cross"],
            "partial_orders": partial,
            "unresolved_fill_events": 0,
            "unresolved_quantity": 0.0,
            "states": states,
            "active": len(self.orders),
            "open": len(self.open_orders()),
            "unknown_open": len(self.unknown_orders()),
            "blocked_reason": self.blocked_reason,
            "critical_reason": self.critical_reason,
            "last_refusal": self.last_refusal,
            "worker_running": self.worker_running,
            "queue_depth": self._commands.qsize() if self._commands is not None else None,
            "pending_outcomes": len(self._outcomes),
            "trade_baseline_ms": self.trade_baseline_ms,
            "filters": self.filters.as_dict(),
            "strict_cancel_replace": self.strict_cancel_replace,
            "latency": {
                "submit_to_ack_ms": self.submit_to_ack_ms.as_dict(),
                "cancel_to_ack_ms": self.cancel_to_ack_ms.as_dict(),
                "note": "measured on this host between the command leaving and the venue's answer being applied",
            },
        }


def _ms(fill: Fill) -> int:
    return int(fill.filled_at.timestamp() * 1000)


__all__ = [
    "CLIENT_ID_PREFIX",
    "OPEN_STATES",
    "TERMINAL_STATES",
    "WOULD_TAKE_CODE",
    "LiveFill",
    "LiveMarketMakerExecution",
    "LiveOrder",
    "MMExecution",
    "MakerCheck",
    "PaperMarketMakerExecution",
    "SimulatedFill",
    "SimulatedOrder",
    "SymbolFilters",
    "validate_maker_order",
]
