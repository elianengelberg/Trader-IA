"""The adaptive quoting engine: fair value, adjusted for inventory and adverse
selection, spread out to a target, sized within what the controller allows.

    fair value  →  shift by inventory  →  half-spread (costs, volatility, market,
    toxicity)  →  bid / ask on the tick grid, never crossed  →  sizes scaled by
    confidence, toxicity and inventory, capped by the risk allowance

No formula here is claimed to be profitable; every parameter is configuration and
every decision carries its components and its reason so the journal can explain it.
The engine refuses to quote when the allowance denies, when confidence is below the
floor, or when the arithmetic lands somewhere implausible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from tia.mm.fair_value import FairValueEstimate
from tia.mm.features import FeatureVector
from tia.mm.inventory import InventoryState
from tia.mm.latency_model import LatencyScenario
from tia.mm.risk import RiskAllowance
from tia.mm.spread import SpreadDecision
from tia.mm.toxicity import ToxicityReading


@dataclass(frozen=True)
class QuotingConfig:
    base_quote_size_btc: float = 0.005
    tick_size: float = 0.01
    size_step: float = 0.00001
    min_size_btc: float = 0.0001
    min_confidence: float = 0.2
    scale_size_by_confidence: bool = True
    #: A quote further than this from the mid is a bug, not a strategy.
    max_offset_from_mid_bps: float = 50.0
    quote_ttl_ms: int = 1_000


@dataclass(frozen=True)
class QuoteDecision:
    t_ms: int
    bid_price: float | None
    ask_price: float | None
    bid_size: float
    ask_size: float
    quote_size: float
    spread_target_bps: float
    half_spread_bps: float
    fair_value: float
    quote_confidence: float
    quote_reason: str
    ttl_ms: int
    components: dict[str, Any] = field(default_factory=dict)

    @property
    def is_quote(self) -> bool:
        return self.bid_price is not None or self.ask_price is not None

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "is_quote": self.is_quote}


def _round_to(value: float, step: float, *, up: bool) -> float:
    units = value / step
    rounded = math.ceil(units - 1e-9) if up else math.floor(units + 1e-9)
    return round(rounded * step, 10)


class AdaptiveQuotingEngine:
    def __init__(self, config: QuotingConfig | None = None) -> None:
        self.config = config or QuotingConfig()

    def decide(
        self,
        *,
        features: FeatureVector,
        fair_value: FairValueEstimate,
        inventory: InventoryState,
        spread: SpreadDecision,
        toxicity: ToxicityReading,
        allowance: RiskAllowance,
        latency: LatencyScenario,
        t_ms: int,
    ) -> QuoteDecision:
        cfg = self.config
        components: dict[str, Any] = {
            "fair_value_offset_bps": fair_value.fair_value_offset_bps,
            "fair_value_confidence": fair_value.fair_value_confidence,
            "inventory_adjustment_bps": inventory.inventory_adjustment_bps,
            "half_spread_bps": spread.half_spread_bps,
            "spread_binding": spread.binding,
            "toxicity_widen_bps": toxicity.widen_bps,
            "toxicity_size_factor": toxicity.size_factor,
            "latency_scenario": latency.name,
            "order_latency_ms": latency.order_latency_ms,
            "allowance": allowance.reason,
        }

        def no_quote(reason: str) -> QuoteDecision:
            return QuoteDecision(t_ms, None, None, 0.0, 0.0, 0.0, spread.half_spread_bps * 2, spread.half_spread_bps, fair_value.fair_value, fair_value.fair_value_confidence, reason, cfg.quote_ttl_ms, components)

        if not allowance.allowed:
            return no_quote(f"risk controller: {allowance.reason}")
        if fair_value.fair_value_confidence < cfg.min_confidence:
            return no_quote(f"fair value confidence {fair_value.fair_value_confidence:.2f} below {cfg.min_confidence:.2f}: " + "; ".join(fair_value.reasons))

        center = fair_value.fair_value * (1.0 + inventory.inventory_adjustment_bps / 10_000.0)
        half = spread.half_spread_bps
        bid = _round_to(center * (1.0 - half / 10_000.0), cfg.tick_size, up=False)
        ask = _round_to(center * (1.0 + half / 10_000.0), cfg.tick_size, up=True)
        if bid >= ask:
            ask = round(bid + cfg.tick_size, 10)
        mid = features.mid_price
        if abs(bid - mid) / mid * 10_000.0 > cfg.max_offset_from_mid_bps or abs(ask - mid) / mid * 10_000.0 > cfg.max_offset_from_mid_bps:
            return no_quote(f"quotes {bid}/{ask} further than {cfg.max_offset_from_mid_bps} bps from the mid {mid}: refused as implausible")

        size = cfg.base_quote_size_btc
        if cfg.scale_size_by_confidence:
            size *= fair_value.fair_value_confidence
        size *= toxicity.size_factor
        size = min(size, allowance.max_size_btc)
        bid_size = _round_to(size * inventory.bid_size_factor, cfg.size_step, up=False) if allowance.bid_allowed else 0.0
        ask_size = _round_to(size * inventory.ask_size_factor, cfg.size_step, up=False) if allowance.ask_allowed else 0.0
        bid_price: float | None = bid if bid_size >= cfg.min_size_btc else None
        ask_price: float | None = ask if ask_size >= cfg.min_size_btc else None
        if bid_price is None:
            bid_size = 0.0
        if ask_price is None:
            ask_size = 0.0
        components.update({"center": center, "bid_raw": bid, "ask_raw": ask, "size_before_sides": size})

        if bid_price is None and ask_price is None:
            return no_quote("both sides sized to zero: " + "; ".join(x for x in (inventory.reason, allowance.reason) if x))
        sides = "two-sided" if bid_price is not None and ask_price is not None else ("bid only" if bid_price is not None else "ask only")
        reason = (
            f"{sides}: fv {fair_value.fair_value_offset_bps:+.2f} bps from mid (conf {fair_value.fair_value_confidence:.2f}), "
            f"inventory {inventory.inventory_adjustment_bps:+.2f} bps, half-spread {half:.2f} bps ({spread.binding})"
            + (f", toxicity +{toxicity.widen_bps:.2f} bps x{toxicity.size_factor:.2f}" if toxicity.score else "")
        )
        return QuoteDecision(
            t_ms=t_ms,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=bid_size,
            ask_size=ask_size,
            quote_size=size,
            spread_target_bps=half * 2.0,
            half_spread_bps=half,
            fair_value=fair_value.fair_value,
            quote_confidence=fair_value.fair_value_confidence,
            quote_reason=reason,
            ttl_ms=cfg.quote_ttl_ms,
            components=components,
        )


__all__ = ["AdaptiveQuotingEngine", "QuoteDecision", "QuotingConfig"]
