"""Position sizing.

One function, one responsibility: convert a risk budget and a stop distance into a
quantity. Deterministic, pure, and the *only* place a position size is computed —
sizing logic reinvented in three places gives three different answers, and nobody can
say which one was used for a given trade.

The method is risk-budget sizing:

    quantity = (equity x risk_per_trade_pct / 100) / stop_distance

which means a losing trade costs approximately the configured percentage of equity
regardless of the instrument's price or volatility. That property is what makes a
portfolio of a 62,000-dollar asset and a 5,400-dollar one comparable at all.

Two refusals are built in, both about the same failure:

* **No stop, no size.** A position whose invalidation level is undefined has undefined
  risk. There is no safe quantity for it.
* **A stop too close to the entry produces an unbounded quantity.** A minimum stop
  distance, expressed as a fraction of price, bounds the division.
"""

from __future__ import annotations

from tia.core.errors import RiskError
from tia.domain.enums import Direction
from tia.domain.instruments import Instrument
from tia.domain.risk import PositionSizing

# A stop closer than this fraction of price is treated as no stop at all. At 0.05% the
# quantity implied by a 100k account risking 0.5% would already be ~10x the account.
MIN_STOP_DISTANCE_PCT = 0.05


def compute_size(
    *,
    equity: float,
    entry_price: float,
    stop_price: float | None,
    direction: Direction,
    instrument: Instrument,
    risk_per_trade_pct: float,
    max_position_notional_pct: float,
    available_capital: float,
) -> PositionSizing:
    """Return a sizing decision, including why it was limited.

    Never raises for ordinary "cannot size this" cases — it returns a zero quantity with
    the binding constraint named, so the risk decision can record the reason. It raises
    only on inputs that are structurally impossible (non-positive equity or price),
    which indicate a bug upstream rather than a market condition.
    """
    if equity <= 0 or entry_price <= 0:
        raise RiskError(
            "cannot size a position with non-positive equity or price",
            equity=equity,
            entry_price=entry_price,
        )

    risk_budget = equity * risk_per_trade_pct / 100.0

    if stop_price is None:
        return PositionSizing(
            equity=equity,
            risk_budget_currency=risk_budget,
            stop_distance=0.0,
            raw_quantity=0.0,
            quantity_after_limits=0.0,
            notional=0.0,
            limiting_constraint="no_stop_defined",
        )

    stop_distance = abs(entry_price - stop_price)
    min_distance = entry_price * MIN_STOP_DISTANCE_PCT / 100.0

    if stop_distance < min_distance:
        return PositionSizing(
            equity=equity,
            risk_budget_currency=risk_budget,
            stop_distance=stop_distance,
            raw_quantity=0.0,
            quantity_after_limits=0.0,
            notional=0.0,
            limiting_constraint="stop_too_close",
        )

    # A stop on the wrong side of the entry means the "risk" is actually the profit
    # target. Refuse rather than size a position whose loss is unbounded.
    if direction is Direction.LONG and stop_price >= entry_price:
        return _refuse(equity, risk_budget, stop_distance, "stop_above_entry_for_long")
    if direction is Direction.SHORT and stop_price <= entry_price:
        return _refuse(equity, risk_budget, stop_distance, "stop_below_entry_for_short")

    raw_quantity = risk_budget / stop_distance
    quantity = raw_quantity
    constraint = "risk_budget"

    max_notional = equity * max_position_notional_pct / 100.0
    if quantity * entry_price > max_notional:
        quantity = max_notional / entry_price
        constraint = "max_position_notional"

    # Simulated cash is still a constraint — a paper account that can open a position it
    # could not fund teaches nothing about the strategy's real capacity.
    if quantity * entry_price > available_capital > 0:
        quantity = available_capital / entry_price
        constraint = "available_capital"

    quantity = instrument.round_quantity(quantity)

    if quantity <= 0 or quantity * entry_price < instrument.min_notional:
        return PositionSizing(
            equity=equity,
            risk_budget_currency=risk_budget,
            stop_distance=stop_distance,
            raw_quantity=raw_quantity,
            quantity_after_limits=0.0,
            notional=0.0,
            limiting_constraint="below_min_notional",
        )

    return PositionSizing(
        equity=equity,
        risk_budget_currency=risk_budget,
        stop_distance=stop_distance,
        raw_quantity=raw_quantity,
        quantity_after_limits=quantity,
        notional=quantity * entry_price,
        limiting_constraint=constraint,
    )


def _refuse(
    equity: float, risk_budget: float, stop_distance: float, reason: str
) -> PositionSizing:
    return PositionSizing(
        equity=equity,
        risk_budget_currency=risk_budget,
        stop_distance=stop_distance,
        raw_quantity=0.0,
        quantity_after_limits=0.0,
        notional=0.0,
        limiting_constraint=reason,
    )


def implied_risk(quantity: float, entry_price: float, stop_price: float) -> float:
    """Currency at risk if the stop is hit exactly. Used to verify sizing after the fact."""
    return quantity * abs(entry_price - stop_price)


__all__ = ["MIN_STOP_DISTANCE_PCT", "compute_size", "implied_risk"]
