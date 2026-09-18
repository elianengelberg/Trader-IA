"""The target half-spread: the widest of what costs demand, what volatility demands
and what the market shows — plus whatever toxicity says to add, never less.

    half_spread = max(min_half, fee + expected_adverse + buffer, k * vol, m * market_half)
                  + toxicity_widen,  capped at max_half

Every term is recorded and the binding one is named, so a quote can say why it is as
wide as it is. Nothing here narrows a spread on the strength of a hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tia.mm.features import FeatureVector


@dataclass(frozen=True)
class SpreadConfig:
    min_half_spread_bps: float = 0.5
    max_half_spread_bps: float = 25.0
    #: The half-spread must cover at least this multiple of the 5 s volatility (bps).
    vol_multiplier: float = 1.0
    vol_window: str = "5s"
    #: Margin above the cost floor (fee + expected adverse selection).
    cost_buffer_bps: float = 0.5
    #: Fraction of the market's own half-spread the target must at least match.
    market_fraction: float = 0.0


@dataclass(frozen=True)
class SpreadDecision:
    half_spread_bps: float
    components_bps: dict[str, float]
    binding: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class SpreadEngine:
    def __init__(self, config: SpreadConfig | None = None) -> None:
        self.config = config or SpreadConfig()

    def target(
        self,
        features: FeatureVector,
        *,
        fee_bps: float,
        expected_adverse_bps: float,
        toxicity_widen_bps: float,
    ) -> SpreadDecision:
        cfg = self.config
        vol = features.vol_bps.get(cfg.vol_window)
        components = {
            "min": cfg.min_half_spread_bps,
            "cost_floor": fee_bps + max(0.0, expected_adverse_bps) + cfg.cost_buffer_bps,
            "volatility": cfg.vol_multiplier * (vol or 0.0),
            "market": cfg.market_fraction * features.spread_bps / 2.0,
        }
        binding = max(components, key=lambda k: components[k])
        base = components[binding]
        widen = max(0.0, toxicity_widen_bps)
        components["toxicity_widen"] = widen
        half = min(cfg.max_half_spread_bps, base + widen)
        capped = base + widen > cfg.max_half_spread_bps
        reason = f"{binding} binds at {base:.2f} bps" + (f" + toxicity {widen:.2f}" if widen else "") + (" (capped)" if capped else "")
        if vol is None:
            reason += "; no 5 s volatility yet"
        return SpreadDecision(half_spread_bps=half, components_bps=components, binding="cap" if capped else binding, reason=reason)


__all__ = ["SpreadConfig", "SpreadDecision", "SpreadEngine"]
