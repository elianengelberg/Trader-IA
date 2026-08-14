"""The Cost Engine.

Every trade costs money before it makes any. This module prices that, itemised, for a
**round trip** — because a one-way cost estimate flatters every strategy that has to get
out again.

Five components, each priced separately so the dashboard can show which one is killing an
edge:

* **Fees** — the venue's commission, both legs.
* **Spread** — you buy at the ask and sell at the bid; crossing it is a real, immediate
  loss that no chart shows.
* **Slippage** — the gap between the price you decided on and the price you got, which
  grows with size relative to available liquidity.
* **Latency** — the market moves between deciding and executing. Priced as the expected
  adverse drift over the measured decision-to-fill delay.
* **Impact** — your own order moving the price against you. Small at retail size,
  non-zero, and modelled rather than assumed away.

**On fee accuracy.** The default fee tier here is a *configured value*, not a value read
from the venue. A live account's real tier depends on 30-day volume, BNB discounts and
promotions, and getting it wrong understates costs systematically in the direction that
makes a strategy look better. :meth:`CostModel.requires_verification` is ``True`` until the
fees have been read from the account, and the Live Activation Gate refuses to arm while it
is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: One basis point as a fraction. Named because the number of places a bare `1e-4` could
#: mean something else is exactly the number of places this gets read wrong.
BPS = 1e-4


class FeeSchedule(BaseModel):
    """What the venue charges.

    Defaults are Binance's *published standard spot tier* at the time of writing, which is
    a starting point and not a fact about any particular account. ``verified_at_source``
    stays ``False`` until the values have been read from the account itself.
    """

    model_config = ConfigDict(frozen=True)

    maker_bps: float = Field(10.0, ge=0, le=500)
    taker_bps: float = Field(10.0, ge=0, le=500)
    #: True only when these came from the venue's own account endpoint rather than config.
    verified_at_source: bool = False
    source: str = "configured default — NOT read from a live account"

    def leg_bps(self, *, is_maker: bool) -> float:
        return self.maker_bps if is_maker else self.taker_bps

    def round_trip_bps(self, *, entry_maker: bool = False, exit_maker: bool = False) -> float:
        return self.leg_bps(is_maker=entry_maker) + self.leg_bps(is_maker=exit_maker)


class MarketConditions(BaseModel):
    """What the market looked like when the cost was priced.

    Everything the cost model needs, and nothing else. Passed explicitly rather than
    reached for, so a cost estimate can be recomputed from a stored record — which is what
    makes a past decision auditable.
    """

    model_config = ConfigDict(frozen=True)

    price: float = Field(gt=0)
    spread_bps: float = Field(0.0, ge=0)
    #: Realised volatility per bar, as a fraction (0.001 = 10 bps).
    volatility_per_bar: float = Field(0.0, ge=0)
    #: Quantity available at the touch, in base units. Governs slippage.
    top_of_book_quantity: float = Field(0.0, ge=0)
    #: Recent per-bar traded volume in base units. Governs impact.
    bar_volume: float = Field(0.0, ge=0)
    #: Measured decision-to-fill delay. Not assumed — the runtime records it.
    latency_ms: float = Field(0.0, ge=0)
    bar_seconds: float = Field(60.0, gt=0)


@dataclass(frozen=True)
class TradeCosts:
    """The itemised round-trip cost of a proposed trade, in basis points of notional.

    Basis points rather than currency so the number is comparable across price levels and
    directly subtractable from an expected return expressed the same way.
    """

    fee_bps: float
    spread_bps: float
    slippage_bps: float
    latency_bps: float
    impact_bps: float
    notional: float

    @property
    def total_bps(self) -> float:
        return (
            self.fee_bps
            + self.spread_bps
            + self.slippage_bps
            + self.latency_bps
            + self.impact_bps
        )

    @property
    def total_currency(self) -> float:
        return self.notional * self.total_bps * BPS

    @property
    def dominant_component(self) -> str:
        """Which cost is doing the damage. Shown in the UI next to a NO_TRADE."""
        components = {
            "fees": self.fee_bps,
            "spread": self.spread_bps,
            "slippage": self.slippage_bps,
            "latency": self.latency_bps,
            "impact": self.impact_bps,
        }
        return max(components, key=lambda name: components[name])

    def as_dict(self) -> dict[str, Any]:
        return {
            "fee_bps": round(self.fee_bps, 4),
            "spread_bps": round(self.spread_bps, 4),
            "slippage_bps": round(self.slippage_bps, 4),
            "latency_bps": round(self.latency_bps, 4),
            "impact_bps": round(self.impact_bps, 4),
            "total_bps": round(self.total_bps, 4),
            "total_currency": round(self.total_currency, 6),
            "dominant": self.dominant_component,
        }


class CostModel:
    """Prices a round trip under stated market conditions.

    Deliberately conservative at every choice point. A cost model that underestimates is
    worse than no cost model: it converts "this trade loses money" into "this trade is
    marginal", and marginal trades get taken.
    """

    def __init__(
        self,
        fees: FeeSchedule | None = None,
        *,
        slippage_coefficient: float = 0.5,
        impact_coefficient: float = 0.35,
        latency_safety_factor: float = 1.0,
    ) -> None:
        self._fees = fees or FeeSchedule()
        self._slippage_coefficient = slippage_coefficient
        self._impact_coefficient = impact_coefficient
        self._latency_safety = latency_safety_factor

    @property
    def fees(self) -> FeeSchedule:
        return self._fees

    @property
    def requires_verification(self) -> bool:
        """True while the fee schedule is a configured guess rather than an account fact."""
        return not self._fees.verified_at_source

    def estimate(
        self,
        *,
        quantity: float,
        conditions: MarketConditions,
        entry_maker: bool = False,
        exit_maker: bool = False,
    ) -> TradeCosts:
        """Price the round trip.

        ``quantity`` is in base units. Both legs are priced, because a strategy that only
        counts the entry is measuring half of what it pays.
        """
        notional = abs(quantity) * conditions.price

        fee_bps = self._fees.round_trip_bps(entry_maker=entry_maker, exit_maker=exit_maker)

        # Crossing the spread costs half of it per leg when the mid is the reference —
        # so one full spread for a round trip that crosses both ways. A maker leg does
        # not cross, and is credited accordingly.
        crossings = (0 if entry_maker else 1) + (0 if exit_maker else 1)
        spread_bps = conditions.spread_bps * 0.5 * crossings

        slippage_bps = self._slippage(quantity, conditions) * crossings
        impact_bps = self._impact(quantity, conditions) * crossings
        latency_bps = self._latency(conditions)

        return TradeCosts(
            fee_bps=fee_bps,
            spread_bps=spread_bps,
            slippage_bps=slippage_bps,
            latency_bps=latency_bps,
            impact_bps=impact_bps,
            notional=notional,
        )

    def _slippage(self, quantity: float, conditions: MarketConditions) -> float:
        """Slippage from consuming more than the touch.

        Zero when the order fits at the top of book; growing with the square root of how
        far past it the order reaches. When book depth is unknown, the model does not
        assume it is infinite — it falls back to a volatility-scaled floor, because "we
        could not see the book" is a reason for more caution, not less.
        """
        size = abs(quantity)
        if size <= 0:
            return 0.0

        if conditions.top_of_book_quantity <= 0:
            # No depth information. Price a half-bar move as the cost of that ignorance.
            return max(
                conditions.volatility_per_bar / BPS * 0.5,
                conditions.spread_bps * 0.5,
            )

        overflow = max(0.0, size - conditions.top_of_book_quantity)
        if overflow <= 0:
            return 0.0

        ratio = overflow / conditions.top_of_book_quantity
        return self._slippage_coefficient * math.sqrt(ratio) * max(conditions.spread_bps, 1.0)

    def _impact(self, quantity: float, conditions: MarketConditions) -> float:
        """Our own order moving the price, as sqrt of participation in bar volume.

        The conventional approximation. Small at retail size and deliberately not rounded
        to zero: a model that says a trade is free is the one that gets over-traded.
        """
        if conditions.bar_volume <= 0:
            return 0.0
        participation = min(1.0, abs(quantity) / conditions.bar_volume)
        return self._impact_coefficient * math.sqrt(participation) * 100.0

    def _latency(self, conditions: MarketConditions) -> float:
        """The market moving between the decision and the fill.

        Priced as the expected absolute drift over the measured delay, scaled from
        per-bar volatility by the square root of time. Adverse selection means the moves
        that reach you are disproportionately the ones going against you, so this is
        charged as a cost rather than treated as symmetric noise.
        """
        if conditions.latency_ms <= 0 or conditions.volatility_per_bar <= 0:
            return 0.0
        fraction_of_bar = (conditions.latency_ms / 1000.0) / conditions.bar_seconds
        drift = conditions.volatility_per_bar * math.sqrt(max(0.0, fraction_of_bar))
        return drift / BPS * self._latency_safety


__all__ = [
    "BPS",
    "CostModel",
    "FeeSchedule",
    "MarketConditions",
    "TradeCosts",
]
