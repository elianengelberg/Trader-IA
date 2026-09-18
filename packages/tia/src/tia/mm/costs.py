"""The market maker's costs, itemised and never netted away.

A maker fill pays the maker fee on its notional — 10 bps as the PROVISIONAL_COST_ASSUMPTION
until the account's schedule is verified, evaluated beside an adverse scenario and the
verified rate once it exists. An unwind by a simulated taker order pays the taker fee
plus the impact of walking the visible book. Every figure the ledger shows is broken
into gross, fees, adverse selection, slippage and net; the net is never shown alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketMakerCostConfig:
    maker_fee_bps: float = 10.0
    maker_fee_status: str = "PROVISIONAL_COST_ASSUMPTION"
    maker_fee_verified_bps: float | None = None
    maker_fee_adverse_bps: float = 15.0
    taker_fee_bps: float = 10.0
    scenario: str = "assumed"  # assumed | verified | adverse

    def fee_bps(self, scenario: str | None = None) -> float:
        name = scenario or self.scenario
        if name == "verified":
            if self.maker_fee_verified_bps is None:
                raise ValueError("the verified maker fee is not known: it has not been read from the account")
            return self.maker_fee_verified_bps
        if name == "adverse":
            return self.maker_fee_adverse_bps
        if name == "assumed":
            return self.maker_fee_bps
        raise ValueError(f"unknown fee scenario {name!r}")

    def scenarios(self) -> dict[str, float | None]:
        return {"assumed": self.maker_fee_bps, "verified": self.maker_fee_verified_bps, "adverse": self.maker_fee_adverse_bps}


class MarketMakerCostModel:
    def __init__(self, config: MarketMakerCostConfig | None = None) -> None:
        self.config = config or MarketMakerCostConfig()

    @property
    def maker_fee_bps(self) -> float:
        return self.config.fee_bps()

    def maker_fee_usd(self, notional_usd: float, scenario: str | None = None) -> float:
        return abs(notional_usd) * self.config.fee_bps(scenario) / 10_000.0

    def taker_fee_usd(self, notional_usd: float) -> float:
        return abs(notional_usd) * self.config.taker_fee_bps / 10_000.0

    def unwind_cost_usd(self, notional_usd: float, impact_bps: float | None) -> dict[str, float]:
        """Fee plus impact for flattening by taker; impact None means the visible book
        could not absorb it, reported as such rather than priced."""
        fee = self.taker_fee_usd(notional_usd)
        slippage = abs(notional_usd) * (impact_bps or 0.0) / 10_000.0
        return {"fee_usd": fee, "slippage_usd": slippage, "impact_known": impact_bps is not None}

    def as_dict(self) -> dict[str, Any]:
        return {"maker_fee_bps": self.maker_fee_bps, "status": self.config.maker_fee_status, "scenario": self.config.scenario, "scenarios_bps": self.config.scenarios(), "taker_fee_bps": self.config.taker_fee_bps}


__all__ = ["MarketMakerCostConfig", "MarketMakerCostModel"]
