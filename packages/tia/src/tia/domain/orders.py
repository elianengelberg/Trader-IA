"""Order intents, orders and fills."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tia.core.clock import ensure_utc
from tia.core.ids import deterministic_id
from tia.domain.enums import OrderState, OrderType, Side, TimeInForce


class OrderIntent(BaseModel):
    """A risk-approved instruction to the execution simulator.

    ``client_order_id`` is derived deterministically from the semantic content, so a
    retry or duplicate delivery produces the *same* id and the provider can recognise it
    as the same logical order rather than opening a second one.
    """

    model_config = ConfigDict(frozen=True)

    intent_id: str
    client_order_id: str
    signal_id: str
    risk_decision_id: str
    symbol: str
    side: Side
    order_type: OrderType = OrderType.MARKET
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.GTC
    created_at: datetime
    correlation_id: str = ""
    reduce_only: bool = False

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="intent created_at")

    @model_validator(mode="after")
    def _prices_present(self) -> OrderIntent:
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.limit_price is None:
            raise ValueError(f"{self.order_type} requires limit_price")
        if self.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError(f"{self.order_type} requires stop_price")
        if self.order_type is OrderType.TAKE_PROFIT and self.take_profit_price is None:
            raise ValueError("take_profit requires take_profit_price")
        return self

    @staticmethod
    def build_client_order_id(
        *,
        signal_id: str,
        symbol: str,
        side: Side,
        quantity: float,
        order_type: OrderType,
        limit_price: float | None = None,
    ) -> str:
        return deterministic_id(
            "coid", signal_id, symbol, side.value, quantity, order_type.value, limit_price
        )


class Fill(BaseModel):
    """A simulated execution."""

    model_config = ConfigDict(frozen=True)

    fill_id: str
    order_id: str
    sequence: int = Field(ge=0)
    symbol: str
    side: Side
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    slippage_bps: float = 0.0
    latency_ms: int = Field(0, ge=0)
    liquidity: str = Field("taker", pattern="^(maker|taker)$")
    filled_at: datetime

    @field_validator("filled_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="fill time")

    @property
    def notional(self) -> float:
        return self.quantity * self.price

    @property
    def signed_quantity(self) -> float:
        return self.quantity if self.side is Side.BUY else -self.quantity


class Order(BaseModel):
    """An order and its lifecycle.

    Mutable by design (state advances), but every transition goes through the state
    machine in :mod:`tia.execution.state_machine`; nothing assigns ``state`` directly.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    order_id: str
    client_order_id: str
    intent_id: str
    signal_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.GTC
    state: OrderState = OrderState.CREATED
    filled_quantity: float = Field(0.0, ge=0)
    average_fill_price: float = Field(0.0, ge=0)
    fees_paid: float = Field(0.0, ge=0)
    reject_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    fills: list[Fill] = Field(default_factory=list)
    correlation_id: str = ""

    @field_validator("created_at", "updated_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="order time")

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    @property
    def is_terminal(self) -> bool:
        return self.state.is_terminal

    @property
    def notional_filled(self) -> float:
        return self.filled_quantity * self.average_fill_price

    def register_fill(self, fill: Fill) -> None:
        """Apply a fill, updating VWAP and fees. Does not change state — the state
        machine does that, so the two can never disagree about which came first."""
        if fill.quantity > self.remaining_quantity + 1e-9:
            raise ValueError(
                f"fill quantity {fill.quantity} exceeds remaining {self.remaining_quantity}"
            )
        total_qty = self.filled_quantity + fill.quantity
        if total_qty > 0:
            self.average_fill_price = (
                self.average_fill_price * self.filled_quantity + fill.price * fill.quantity
            ) / total_qty
        self.filled_quantity = total_qty
        self.fees_paid += fill.fee
        self.fills.append(fill)
        self.updated_at = fill.filled_at


__all__ = ["Fill", "Order", "OrderIntent"]
