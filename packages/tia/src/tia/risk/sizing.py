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

import math
from dataclasses import dataclass
from decimal import Decimal

from tia.core.errors import RiskError
from tia.core.money import quantize_down
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


def margin_available(*, equity: float, gross_exposure: float, cash: float, leverage: float) -> float:
    """Capital that may back a new position, with or without leverage.

    At 1x it is the cash on hand — a position cannot be bought with money the account
    does not have. Above 1x the account borrows against its equity: notional may reach
    ``leverage`` times equity, and what is left after the open positions is the room.
    Never negative, and never more than leverage allows: a leveraged account with no
    equity left has no room, whatever its cash says.
    """
    if leverage <= 1.0:
        return max(0.0, cash)
    return max(0.0, equity * leverage - gross_exposure)


def implied_risk(quantity: float, entry_price: float, stop_price: float) -> float:
    """Currency at risk if the stop is hit exactly. Used to verify sizing after the fact."""
    return quantity * abs(entry_price - stop_price)


# --------------------------------------------------------------------------- the budget


@dataclass(frozen=True)
class BudgetedSize:
    """The one size an entry may be sent at, and how it was arrived at.

    The sizing contract shared by the 24/7 session, the scenario engine and the
    backtester (Phase 1.3). ``quantity`` is zero when the entry is refused; every refusal
    names its reason, and ``effective_risk_currency`` is the loss the stop would realise
    at that size — the number the contract is about, not the quantity.
    """

    quantity: float
    #: The risk engine's ceiling: already inside every portfolio limit, already a whole
    #: number of lots. Nothing here may exceed it.
    approved_quantity: float
    #: ``equity x RiskLimits.max_risk_per_trade_pct``: the hard cap on a trade's risk.
    limit_risk_currency: float
    #: The risk budget after its multipliers (profile x drawdown x volatility x streak).
    budget_risk_currency: float
    #: The evidence's say: 1.0 at full conviction, less for an exploration trade. Never
    #: above one.
    conviction_fraction: float
    #: ``min(limit, budget) x conviction``: the most this entry may put at the stop.
    allowed_risk_currency: float
    stop_distance: float
    #: ``quantity x stop_distance``: what the stop would cost at the final size.
    effective_risk_currency: float
    notional: float
    limiting_constraint: str
    refused_reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.quantity > 0

    def quantity_text(self) -> str:
        """The size that was refused, for a message: the budget's quantity before the
        venue's rules, or "a zero quantity" when nothing survived the step."""
        if self.stop_distance > 0 and self.allowed_risk_currency > 0:
            return f"a size of {self.allowed_risk_currency / self.stop_distance:.8f}"
        return "a zero quantity"

    def as_dict(self) -> dict[str, float | str | bool]:
        return {
            "quantity": self.quantity,
            "approved_quantity": self.approved_quantity,
            "limit_risk_currency": round(self.limit_risk_currency, 6),
            "budget_risk_currency": round(self.budget_risk_currency, 6),
            "conviction_fraction": round(self.conviction_fraction, 6),
            "allowed_risk_currency": round(self.allowed_risk_currency, 6),
            "stop_distance": self.stop_distance,
            "effective_risk_currency": round(self.effective_risk_currency, 6),
            "notional": round(self.notional, 6),
            "limiting_constraint": self.limiting_constraint,
            "refused_reason": self.refused_reason,
            "accepted": self.accepted,
        }


def _refused_size(
    reason: str,
    *,
    approved_quantity: float,
    limit_risk: float,
    budget_risk: float,
    conviction: float,
    allowed: float,
    stop_distance: float,
) -> BudgetedSize:
    return BudgetedSize(
        quantity=0.0,
        approved_quantity=approved_quantity,
        limit_risk_currency=limit_risk if math.isfinite(limit_risk) else 0.0,
        budget_risk_currency=budget_risk if math.isfinite(budget_risk) else 0.0,
        conviction_fraction=conviction if math.isfinite(conviction) else 0.0,
        allowed_risk_currency=allowed if math.isfinite(allowed) else 0.0,
        stop_distance=stop_distance if math.isfinite(stop_distance) else 0.0,
        effective_risk_currency=0.0,
        notional=0.0,
        limiting_constraint=f"refused:{reason}",
        refused_reason=reason,
    )


def apply_risk_budget(
    *,
    approved_quantity: float,
    entry_price: float,
    stop_price: float | None,
    limit_risk_currency: float,
    budget_risk_currency: float,
    conviction_fraction: float = 1.0,
    step_size: float | Decimal | None = None,
    min_notional: float | Decimal = 0.0,
    allows_new_trades: bool = True,
) -> BudgetedSize:
    """The final size of an entry: the risk engine's ceiling, shrunk to the risk budget.

    The contract (Phase 1.3), in one place for every engine:

    * the loss the stop would realise never exceeds
      ``min(limit_risk_currency, budget_risk_currency) x conviction_fraction``;
    * the quantity never exceeds ``approved_quantity x conviction_fraction`` (the risk
      engine's limits stand, and conviction is a fraction of the approved size);
    * the quantity is rounded **down** to the venue's step; a size that then falls
      below the minimum notional is **refused**, never raised to reach it — raising it
      would put more at the stop than the budget allows;
    * a budget that forbids new trades, a zero or non-finite budget, an absent or
      invalid stop, or a non-finite conviction refuse the entry outright.

    Each multiplier of the budget therefore reduces the money at risk, not only a
    number in a report — which is what the earlier runtime failed to do: it computed the
    budget and read only whether it allowed trading.
    """
    stop_distance = (
        abs(entry_price - stop_price)
        if stop_price is not None and math.isfinite(stop_price) and math.isfinite(entry_price)
        else float("nan")
    )
    conviction = conviction_fraction

    def refuse(reason: str, allowed: float = 0.0) -> BudgetedSize:
        return _refused_size(
            reason,
            approved_quantity=approved_quantity if math.isfinite(approved_quantity) else 0.0,
            limit_risk=limit_risk_currency,
            budget_risk=budget_risk_currency,
            conviction=conviction,
            allowed=allowed,
            stop_distance=stop_distance,
        )

    if not allows_new_trades:
        return refuse("budget_blocks_new_trades")
    if not (math.isfinite(entry_price) and entry_price > 0):
        return refuse("invalid_entry_price")
    if stop_price is None or not math.isfinite(stop_distance):
        return refuse("no_stop_defined")
    if stop_price <= 0 or stop_distance <= 0:
        return refuse("invalid_stop")
    if not (math.isfinite(approved_quantity) and approved_quantity > 0):
        return refuse("nothing_approved")
    if not (math.isfinite(limit_risk_currency) and math.isfinite(budget_risk_currency)):
        return refuse("invalid_risk_budget")
    if limit_risk_currency <= 0 or budget_risk_currency <= 0:
        return refuse("zero_risk_budget")
    if not math.isfinite(conviction) or conviction <= 0:
        return refuse("invalid_conviction")
    conviction = min(1.0, conviction)

    # Conviction scales the whole size — the risk engine's ceiling included — so that a
    # trade the evidence only half-trusts takes half of what it would otherwise take,
    # whichever bound was binding (its documented semantics: a fraction of the approved
    # size). The money at the stop is then at most ``min(limit, budget) x conviction``.
    allowed = min(limit_risk_currency, budget_risk_currency) * conviction
    quantity = min(approved_quantity, min(limit_risk_currency, budget_risk_currency) / stop_distance)
    quantity *= conviction

    step = Decimal(str(step_size)) if step_size else Decimal(0)
    if step > 0:
        quantity = float(quantize_down(quantity, step))
    if quantity <= 0:
        return refuse("below_lot_step", allowed)
    notional = quantity * entry_price
    if notional < float(min_notional):
        return refuse("below_min_notional", allowed)

    effective = quantity * stop_distance
    if effective > allowed * (1.0 + 1e-9) + 1e-12:  # pragma: no cover - the contract's own guard
        raise RiskError(
            "budgeted size would risk more than the budget allows",
            effective=effective,
            allowed=allowed,
        )
    by_risk = min(limit_risk_currency, budget_risk_currency) / stop_distance
    if approved_quantity <= by_risk * (1.0 + 1e-9):
        bound = "risk_engine"
    elif budget_risk_currency < limit_risk_currency:
        bound = "risk_budget"
    else:
        bound = "risk_limit"
    limiting = bound if conviction >= 1.0 else f"{bound} x conviction"
    return BudgetedSize(
        quantity=quantity,
        approved_quantity=approved_quantity,
        limit_risk_currency=limit_risk_currency,
        budget_risk_currency=budget_risk_currency,
        conviction_fraction=conviction,
        allowed_risk_currency=allowed,
        stop_distance=stop_distance,
        effective_risk_currency=effective,
        notional=notional,
        limiting_constraint=limiting,
    )


__all__ = [
    "MIN_STOP_DISTANCE_PCT",
    "BudgetedSize",
    "apply_risk_budget",
    "compute_size",
    "implied_risk",
    "margin_available",
]
