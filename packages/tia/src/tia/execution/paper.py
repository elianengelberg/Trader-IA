"""The paper execution simulator.

A matching engine that fills orders against historical or synthetic bars, modelling the
costs that separate a backtest from a fantasy: spread, slippage, market impact, fees,
latency, partial fills, liquidity limits and rejections.

**Three honest statements about what this is not.**

1. There is no order book. Fills are modelled against bar OHLCV, so queue position,
   iceberg orders and book-depletion dynamics do not exist here.
2. Our own orders have no effect on the market. A strategy that would move the price is
   modelled as though it would not, which flatters large sizes.
3. There is no venue behaviour — no halts, no auctions, no exchange-specific reject
   reasons, no funding or borrow costs.

Every default is pessimistic. Optimistic fill assumptions are the single easiest way to
manufacture a backtest edge that does not exist, so where a choice was available this
engine takes the worse one: market orders fill at the *next* bar's open plus slippage,
never at the signal bar's close; limit orders require the price to trade *through* the
limit, not merely touch it; and a bar's fillable size is capped at a fraction of its
volume.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from tia.core.clock import Clock, ensure_utc
from tia.core.config import ExecutionSimConfig
from tia.core.errors import DuplicateOrderError
from tia.core.ids import deterministic_id
from tia.core.logging import get_logger
from tia.core.rng import RngRegistry
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.instruments import Instrument, InstrumentUniverse
from tia.domain.market import Candle
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider
from tia.execution.state_machine import resolve_fill_state, transition

_log = get_logger("execution.paper")


class PaperExecutionProvider(ExecutionProvider):
    """Deterministic simulated execution against bar data."""

    def __init__(
        self,
        config: ExecutionSimConfig,
        universe: InstrumentUniverse,
        clock: Clock,
        rng: RngRegistry,
        *,
        initial_capital: float = 100_000.0,
    ) -> None:
        super().__init__(
            ExecutionCapabilities(
                name="paper",
                is_simulated=True,
                notes=(
                    "Bar-based matching engine. No order book, no market impact from our "
                    "own orders, no venue microstructure. Not equivalent to a real market."
                ),
            )
        )
        self._config = config
        self._universe = universe
        self._clock = clock
        self._rng = rng
        self._portfolio = PortfolioState.initial(initial_capital)

        self._orders: dict[str, Order] = {}
        self._by_client_id: dict[str, str] = {}
        self._resting: list[str] = []
        self._fills: list[Fill] = []
        self._last_price: dict[str, float] = {}
        self._fill_sequence = 0

    # ------------------------------------------------------------------ queries

    @property
    def portfolio(self) -> PortfolioState:
        return self._portfolio

    @property
    def config(self) -> ExecutionSimConfig:
        return self._config

    async def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    async def get_orders(self, *, open_only: bool = False) -> list[Order]:
        orders = list(self._orders.values())
        if open_only:
            orders = [o for o in orders if o.state.is_open]
        return sorted(orders, key=lambda o: o.created_at)

    async def get_positions(self) -> dict[str, Position]:
        return {s: p for s, p in self._portfolio.positions.items() if not p.is_flat}

    async def get_balance(self) -> float:
        return self._portfolio.cash

    async def get_trades(self, *, limit: int = 100) -> list[Fill]:
        return self._fills[-limit:]

    async def get_pnl(self) -> dict[str, float]:
        return {
            "realized": self._portfolio.realized_pnl,
            "unrealized": self._portfolio.unrealized_pnl,
            "total": self._portfolio.realized_pnl + self._portfolio.unrealized_pnl,
            "fees": self._portfolio.fees_paid,
            "equity": self._portfolio.equity,
        }

    async def get_portfolio(self) -> PortfolioState:
        return self._portfolio

    # ------------------------------------------------------------------ submission

    async def submit_order(self, intent: OrderIntent) -> Order:
        """Submit an intent, or return the existing order for a duplicate.

        Idempotency is the whole point of ``client_order_id``: a retry after a timeout,
        a redelivered event, or a reconnect must never open a second position.
        """
        existing_id = self._by_client_id.get(intent.client_order_id)
        if existing_id is not None:
            _log.info(
                "duplicate_order_suppressed",
                client_order_id=intent.client_order_id,
                order_id=existing_id,
            )
            return self._orders[existing_id]

        instrument = self._universe.get(intent.symbol)
        now = self._clock.now()
        order = Order(
            order_id=deterministic_id("ord", intent.client_order_id),
            client_order_id=intent.client_order_id,
            intent_id=intent.intent_id,
            signal_id=intent.signal_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            time_in_force=intent.time_in_force,
            created_at=now,
            updated_at=now,
            correlation_id=intent.correlation_id,
        )
        self._orders[order.order_id] = order
        self._by_client_id[intent.client_order_id] = order.order_id

        if instrument is None:
            transition(order, OrderState.REJECTED, at=now, reason="unknown instrument")
            return order

        if intent.side is Side.SELL and not instrument.shortable:
            position = self._portfolio.positions.get(intent.symbol)
            held = position.quantity if position else 0.0
            if held < intent.quantity:
                transition(
                    order, OrderState.REJECTED, at=now, reason="short selling not permitted"
                )
                return order

        transition(order, OrderState.VALIDATED, at=now)
        transition(order, OrderState.RISK_APPROVED, at=now)

        # Latency is modelled as clock offsets on the state timestamps rather than as
        # real sleeping, so a backtest runs at full speed while still recording that a
        # submission was not instantaneous.
        submit_at = now + timedelta(milliseconds=self._config.submit_latency_ms)
        transition(order, OrderState.SUBMITTING, at=submit_at)

        if self._should_reject(order):
            transition(
                order,
                OrderState.REJECTED,
                at=submit_at,
                reason="simulated venue rejection",
            )
            return order

        transition(order, OrderState.SUBMITTED, at=submit_at)
        ack_at = submit_at + timedelta(milliseconds=self._config.ack_latency_ms)
        transition(order, OrderState.ACKNOWLEDGED, at=ack_at)
        self._resting.append(order.order_id)
        return order

    async def cancel_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise DuplicateOrderError(f"unknown order {order_id}", order_id=order_id)
        now = self._clock.now()
        if order.state.is_terminal:
            return order
        transition(order, OrderState.CANCEL_REQUESTED, at=now)
        transition(order, OrderState.CANCELLED, at=now, reason="cancelled by caller")
        if order_id in self._resting:
            self._resting.remove(order_id)
        return order

    # ------------------------------------------------------------------ matching

    def on_bar(self, candle: Candle) -> list[Fill]:
        """Advance the simulation by one bar, returning any fills it produced.

        Called by the runtime and the backtester with each closed bar. Orders submitted
        during bar *t* are matched against bar *t+1*, which is what keeps the engine
        honest about the fact that a decision cannot be executed at the price that
        triggered it.
        """
        self._last_price[candle.symbol] = candle.close
        produced: list[Fill] = []

        for order_id in list(self._resting):
            order = self._orders.get(order_id)
            if order is None or order.state.is_terminal:
                self._resting.remove(order_id)
                continue
            if order.symbol != candle.symbol:
                continue
            # An order created during this very bar cannot be filled by it.
            if order.created_at >= candle.close_time:
                continue

            fill = self._try_fill(order, candle)
            if fill is not None:
                produced.append(fill)

            if order.state.is_terminal and order_id in self._resting:
                self._resting.remove(order_id)

        self._portfolio.mark(candle.symbol, candle.close, candle.close_time)
        return produced

    def _try_fill(self, order: Order, candle: Candle) -> Fill | None:
        instrument = self._universe.get(order.symbol)
        if instrument is None:
            return None

        trigger = self._fill_price(order, candle)
        if trigger is None:
            return None

        available = self._available_quantity(candle)
        if available <= 0:
            return None

        quantity = min(order.remaining_quantity, available)
        if self._should_partially_fill(order) and quantity >= order.remaining_quantity:
            # A partial fill is the normal case for anything non-trivial in size; force
            # one occasionally so downstream code that assumes "submitted == filled"
            # breaks here rather than in production.
            stream = f"execution:partial_size:{order.symbol}"
            quantity *= float(self._rng.get(stream).uniform(0.35, 0.85))

        quantity = instrument.round_quantity(quantity)
        if quantity <= 0:
            return None

        price, slippage_bps = self._apply_slippage(order, trigger, quantity, candle, instrument)
        liquidity = "maker" if order.order_type is OrderType.LIMIT else "taker"
        fee_bps = (
            self._config.maker_fee_bps if liquidity == "maker" else self._config.taker_fee_bps
        )
        fee = abs(quantity * price) * fee_bps / 10_000.0

        self._fill_sequence += 1
        fill = Fill(
            fill_id=deterministic_id("fill", order.order_id, self._fill_sequence),
            order_id=order.order_id,
            sequence=self._fill_sequence,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=price,
            fee=fee,
            slippage_bps=slippage_bps,
            latency_ms=self._config.submit_latency_ms + self._config.ack_latency_ms,
            liquidity=liquidity,
            filled_at=candle.close_time,
        )

        order.register_fill(fill)
        self._fills.append(fill)
        self._portfolio.apply_fill(fill)

        target = resolve_fill_state(order)
        if target != order.state:
            transition(order, target, at=candle.close_time)
        elif target is OrderState.PARTIALLY_FILLED:
            transition(order, OrderState.PARTIALLY_FILLED, at=candle.close_time)

        return fill

    def _fill_price(self, order: Order, candle: Candle) -> float | None:
        """The reference price at which this order would trigger, or ``None``.

        Market orders reference the bar's open — the first price available after the
        decision — rather than its close, which would let a strategy transact at a price
        it could not have known.
        """
        if order.order_type is OrderType.MARKET:
            return candle.open

        if order.order_type is OrderType.LIMIT:
            limit = order.limit_price
            if limit is None:
                return None
            # Require the price to trade through the limit, not merely touch it: at the
            # exact limit there is no guarantee of queue priority.
            if order.side is Side.BUY and candle.low < limit:
                return min(limit, candle.open)
            if order.side is Side.SELL and candle.high > limit:
                return max(limit, candle.open)
            return None

        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            stop = order.stop_price
            if stop is None:
                return None
            triggered = (
                candle.high >= stop if order.side is Side.BUY else candle.low <= stop
            )
            if not triggered:
                return None
            if order.order_type is OrderType.STOP:
                # A stop becomes a market order once triggered, and the fill is at least
                # as bad as the stop level — that gap is the cost of a stop.
                return max(stop, candle.open) if order.side is Side.BUY else min(stop, candle.open)
            limit = order.limit_price
            if limit is None:
                return None
            if order.side is Side.BUY and candle.low < limit:
                return min(limit, max(stop, candle.open))
            if order.side is Side.SELL and candle.high > limit:
                return max(limit, min(stop, candle.open))
            return None

        if order.order_type is OrderType.TAKE_PROFIT:
            target = order.limit_price or order.stop_price
            if target is None:
                return None
            if order.side is Side.SELL and candle.high >= target:
                return target
            if order.side is Side.BUY and candle.low <= target:
                return target
            return None

        return None

    def _available_quantity(self, candle: Candle) -> float:
        """How much of this bar's volume we are allowed to consume.

        Without a participation cap a backtest can fill an arbitrarily large order in a
        single thin bar, which is the most common way a strategy's reported capacity
        exceeds anything achievable.
        """
        if candle.volume <= 0:
            return 0.0
        return candle.volume * self._config.max_participation_rate

    def _apply_slippage(
        self,
        order: Order,
        reference: float,
        quantity: float,
        candle: Candle,
        instrument: Instrument,
    ) -> tuple[float, float]:
        """Return ``(fill_price, slippage_bps)``, always adverse to the order."""
        base = self._config.base_slippage_bps

        # Impact scales with the square root of our participation in the bar — the
        # conventional approximation, and superlinear enough to penalise size.
        participation = quantity / candle.volume if candle.volume > 0 else 1.0
        impact = self._config.impact_coefficient * math.sqrt(min(1.0, participation)) * 100.0

        # A wider bar means a less certain price; scale a little with realised range.
        range_bps = (candle.high - candle.low) / candle.close * 10_000.0 if candle.close > 0 else 0.0
        range_component = min(range_bps * 0.05, 25.0)

        total_bps = base + impact + range_component
        direction = 1.0 if order.side is Side.BUY else -1.0
        price = reference * (1.0 + direction * total_bps / 10_000.0)

        # Never fill outside the bar's actual range — a price that never traded is not a
        # fill, it is a fiction.
        price = max(candle.low, min(candle.high, price))
        price = instrument.round_price(price)
        if price <= 0:
            price = instrument.round_price(candle.close)

        realized_bps = abs(price - reference) / reference * 10_000.0 if reference > 0 else 0.0
        return (price, realized_bps)

    def _should_reject(self, order: Order) -> bool:
        if self._config.reject_probability <= 0:
            return False
        draw = float(self._rng.get(f"execution:reject:{order.symbol}").random())
        return draw < self._config.reject_probability

    def _should_partially_fill(self, order: Order) -> bool:
        if self._config.partial_fill_probability <= 0:
            return False
        draw = float(self._rng.get(f"execution:partial:{order.symbol}").random())
        return draw < self._config.partial_fill_probability

    # ------------------------------------------------------------------ maintenance

    def expire_stale_orders(self, *, older_than: timedelta, now: datetime | None = None) -> list[Order]:
        """Expire resting orders past their useful life.

        An order left resting from a thesis that has since been invalidated is exactly
        the "trade with an expired signal" the platform is built to avoid.
        """
        moment = ensure_utc(now) if now else self._clock.now()
        expired: list[Order] = []
        for order_id in list(self._resting):
            order = self._orders.get(order_id)
            if order is None or order.state.is_terminal:
                continue
            if moment - order.created_at >= older_than:
                transition(order, OrderState.EXPIRED, at=moment, reason="order age exceeded TTL")
                self._resting.remove(order_id)
                expired.append(order)
        return expired

    def mark_all(self, prices: dict[str, float], at: datetime) -> None:
        for symbol, price in prices.items():
            self._portfolio.mark(symbol, price, at)

    def reset(self, *, initial_capital: float | None = None) -> None:
        """Clear all state. Used between backtest runs."""
        capital = initial_capital or self._portfolio.initial_capital
        self._portfolio = PortfolioState.initial(capital)
        self._orders.clear()
        self._by_client_id.clear()
        self._resting.clear()
        self._fills.clear()
        self._last_price.clear()
        self._fill_sequence = 0

    def snapshot(self) -> dict[str, object]:
        """Provider-side state, as the reconciliation engine sees it."""
        return {
            "orders": {oid: o.state.value for oid, o in self._orders.items()},
            "positions": {
                s: p.quantity for s, p in self._portfolio.positions.items() if not p.is_flat
            },
            "balance": self._portfolio.cash,
            "fill_count": len(self._fills),
        }


__all__ = ["PaperExecutionProvider"]
