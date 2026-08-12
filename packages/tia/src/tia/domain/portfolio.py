"""Positions and portfolio state — the single source of truth for exposure and P&L."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import Side
from tia.domain.orders import Fill


class Position(BaseModel):
    """A net position in one instrument.

    Sign convention: ``quantity > 0`` is long, ``< 0`` is short, ``0`` is flat.
    Realized P&L accrues on quantity-reducing fills; unrealized is marked to the last
    price supplied by :meth:`mark`.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    symbol: str
    quantity: float = 0.0
    average_price: float = Field(0.0, ge=0)
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = Field(0.0, ge=0)
    last_price: float = Field(0.0, ge=0)
    opened_at: datetime | None = None
    updated_at: datetime | None = None
    stop_price: float | None = None
    target_price: float | None = None

    @field_validator("opened_at", "updated_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v, field="position time") if v is not None else None

    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-12

    @property
    def is_long(self) -> bool:
        return self.quantity > 1e-12

    @property
    def is_short(self) -> bool:
        return self.quantity < -1e-12

    @property
    def notional(self) -> float:
        return abs(self.quantity) * (self.last_price or self.average_price)

    @property
    def signed_notional(self) -> float:
        return self.quantity * (self.last_price or self.average_price)

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    def duration_seconds(self, now: datetime) -> float:
        if self.opened_at is None:
            return 0.0
        return (ensure_utc(now) - self.opened_at).total_seconds()

    def apply_fill(self, fill: Fill) -> None:
        """Update the position for a fill, accruing realized P&L on reductions."""
        delta = fill.signed_quantity
        prior_qty = self.quantity
        new_qty = prior_qty + delta

        if prior_qty == 0 or (prior_qty > 0) == (delta > 0):
            # Opening or adding: weighted-average entry price.
            total_cost = abs(prior_qty) * self.average_price + abs(delta) * fill.price
            total_qty = abs(prior_qty) + abs(delta)
            self.average_price = total_cost / total_qty if total_qty > 0 else 0.0
            if prior_qty == 0:
                self.opened_at = fill.filled_at
        else:
            # Reducing, closing, or flipping.
            closing_qty = min(abs(delta), abs(prior_qty))
            direction = 1.0 if prior_qty > 0 else -1.0
            self.realized_pnl += direction * closing_qty * (fill.price - self.average_price)
            if abs(delta) > abs(prior_qty):
                # Flipped through zero: the remainder opens a new position at fill price.
                self.average_price = fill.price
                self.opened_at = fill.filled_at
            elif abs(new_qty) < 1e-12:
                self.average_price = 0.0
                self.opened_at = None

        self.quantity = 0.0 if abs(new_qty) < 1e-12 else new_qty
        self.fees_paid += fill.fee
        self.realized_pnl -= fill.fee
        self.last_price = fill.price
        self.updated_at = fill.filled_at
        self.mark(fill.price, fill.filled_at)

    def mark(self, price: float, at: datetime) -> None:
        self.last_price = price
        self.updated_at = ensure_utc(at)
        self.unrealized_pnl = (
            0.0 if self.is_flat else self.quantity * (price - self.average_price)
        )


class PortfolioState(BaseModel):
    """Simulated account state. There is no real capital behind any of these numbers."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    initial_capital: float = Field(gt=0)
    cash: float
    positions: dict[str, Position] = Field(default_factory=dict)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    peak_equity: float = 0.0
    day_start_equity: float = 0.0
    current_day: str = ""
    updated_at: datetime | None = None

    @field_validator("updated_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v, field="portfolio time") if v is not None else None

    @classmethod
    def initial(cls, capital: float) -> PortfolioState:
        return cls(
            initial_capital=capital,
            cash=capital,
            peak_equity=capital,
            day_start_equity=capital,
        )

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + sum(
            p.signed_notional for p in self.positions.values() if not p.is_flat
        )

    @property
    def gross_exposure(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def net_exposure(self) -> float:
        return sum(p.signed_notional for p in self.positions.values())

    @property
    def open_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if not p.is_flat)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)

    @property
    def day_pnl_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity - self.day_start_equity) / self.day_start_equity * 100.0

    def position(self, symbol: str) -> Position:
        pos = self.positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol)
            self.positions[symbol] = pos
        return pos

    def apply_fill(self, fill: Fill) -> None:
        pos = self.position(fill.symbol)
        realized_before = pos.realized_pnl
        pos.apply_fill(fill)
        self.realized_pnl += pos.realized_pnl - realized_before
        self.fees_paid += fill.fee
        # Cash moves opposite to the position change, minus fees.
        self.cash -= fill.signed_quantity * fill.price
        self.cash -= fill.fee
        self.updated_at = fill.filled_at
        self._refresh_peaks(fill.filled_at)

    def mark(self, symbol: str, price: float, at: datetime) -> None:
        pos = self.positions.get(symbol)
        if pos is not None:
            pos.mark(price, at)
        self.updated_at = ensure_utc(at)
        self._refresh_peaks(at)

    def _refresh_peaks(self, at: datetime) -> None:
        equity = self.equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        day = ensure_utc(at).date().isoformat()
        if day != self.current_day:
            self.current_day = day
            self.day_start_equity = equity

    def snapshot_exposures(self) -> dict[str, float]:
        return {s: p.signed_notional for s, p in self.positions.items() if not p.is_flat}

    def available_capital(self) -> float:
        """Cash that may back a new position. Never negative."""
        return max(0.0, self.cash)


class PortfolioSnapshot(BaseModel):
    """Immutable point-in-time record, written on a schedule and on every fill."""

    model_config = ConfigDict(frozen=True)

    taken_at: datetime
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    fees_paid: float
    gross_exposure: float
    net_exposure: float
    open_positions: int
    drawdown_pct: float
    day_pnl_pct: float

    @field_validator("taken_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="snapshot time")

    @classmethod
    def of(cls, state: PortfolioState, at: datetime) -> PortfolioSnapshot:
        return cls(
            taken_at=at,
            equity=state.equity,
            cash=state.cash,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=state.unrealized_pnl,
            fees_paid=state.fees_paid,
            gross_exposure=state.gross_exposure,
            net_exposure=state.net_exposure,
            open_positions=state.open_position_count,
            drawdown_pct=state.drawdown_pct,
            day_pnl_pct=state.day_pnl_pct,
        )


__all__ = ["PortfolioSnapshot", "PortfolioState", "Position", "Side"]
