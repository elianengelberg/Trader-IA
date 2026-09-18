"""Fair value: an explicit, conditioned estimate of where the mid belongs — not a
prediction of where it will go.

The estimate is a sum of named contributions, each with a configurable weight:

    fair_value = mid + micro + imbalance + ofi + flow + momentum        (all in bps)

By default only the microprice term is active (``w_micro = 1``): it is the one term
with general empirical support. Every other term is a hypothesis switched on by
configuration and judged downstream by markouts, never by this module. Nothing here
fits a weight to the data it is later evaluated on.

Alongside the value comes a **confidence** in [0, 1] that only ever falls: with stale
data, with a wide or unknown spread regime, with high short-term volatility, and when
active components disagree in sign. Every estimate records its components in bps, the
reasons that lowered its confidence, and the id of the configuration that produced it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from tia.mm.features import FeatureVector


@dataclass(frozen=True)
class FairValueConfig:
    w_micro: float = 1.0
    w_imbalance: float = 0.0
    w_ofi: float = 0.0
    w_flow: float = 0.0
    w_momentum: float = 0.0
    #: The estimate never strays further than this from the mid, whatever the terms say.
    max_offset_bps: float = 5.0
    max_data_age_ms: int = 1_000
    #: Volatility (bps over 5 s) at which confidence is halved.
    vol_half_confidence_bps: float = 5.0
    wide_spread_factor: float = 0.5
    unknown_regime_factor: float = 0.9
    disagreement_factor: float = 0.7
    flow_window: str = "5s"
    momentum_window: str = "5s"

    @property
    def config_id(self) -> str:
        payload = json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class FairValueEstimate:
    t_ms: int
    mid: float
    fair_value: float
    fair_value_offset_bps: float
    fair_value_confidence: float
    components_bps: dict[str, float]
    raw_offset_bps: float  # before the clamp
    reasons: list[str] = field(default_factory=list)
    config_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class FairValueEngine:
    """A pure function of the feature vector, kept as a class for its configuration."""

    def __init__(self, config: FairValueConfig | None = None) -> None:
        self.config = config or FairValueConfig()

    def estimate(self, features: FeatureVector) -> FairValueEstimate:
        cfg = self.config
        mid = features.mid_price
        half_spread_bps = features.spread_bps / 2.0
        flow = features.trade_flow.get(cfg.flow_window)
        flow_norm = flow.flow_norm if flow is not None else None
        momentum = features.returns_bps.get(cfg.momentum_window)

        components = {
            "micro": cfg.w_micro * features.microprice_delta_bps,
            "imbalance": cfg.w_imbalance * (features.imbalance_t5 or 0.0) * half_spread_bps,
            "ofi": cfg.w_ofi * (features.ofi_norm or 0.0) * half_spread_bps,
            "flow": cfg.w_flow * (flow_norm or 0.0) * half_spread_bps,
            "momentum": cfg.w_momentum * (momentum or 0.0),
        }
        raw_offset = sum(components.values())
        offset = _clamp(raw_offset, -cfg.max_offset_bps, cfg.max_offset_bps)

        reasons: list[str] = []
        confidence = 1.0
        if features.data_age_ms > 0:
            age_factor = _clamp(1.0 - features.data_age_ms / cfg.max_data_age_ms, 0.0, 1.0)
            if age_factor < 1.0:
                reasons.append(f"data {features.data_age_ms} ms old")
            confidence *= age_factor
        vol = features.vol_bps.get("5s")
        if vol is None:
            confidence *= 0.8
            reasons.append("no 5 s volatility yet")
        elif vol > 0:
            confidence *= 1.0 / (1.0 + vol / cfg.vol_half_confidence_bps)
            if vol >= cfg.vol_half_confidence_bps:
                reasons.append(f"5 s volatility {vol:.1f} bps")
        if features.spread_regime == "wide":
            confidence *= cfg.wide_spread_factor
            reasons.append("wide spread regime")
        elif features.spread_regime == "unknown":
            confidence *= cfg.unknown_regime_factor
            reasons.append("spread regime unknown")
        active = [v for v in components.values() if abs(v) > 1e-12]
        if active and (max(active) > 0 > min(active)):
            confidence *= cfg.disagreement_factor
            reasons.append("components disagree in sign")
        if offset != raw_offset:
            reasons.append(f"offset clamped from {raw_offset:.2f} to {offset:.2f} bps")

        return FairValueEstimate(
            t_ms=features.t_ms,
            mid=mid,
            fair_value=mid * (1.0 + offset / 10_000.0),
            fair_value_offset_bps=offset,
            fair_value_confidence=_clamp(confidence, 0.0, 1.0),
            components_bps=components,
            raw_offset_bps=raw_offset,
            reasons=reasons,
            config_id=cfg.config_id,
        )


__all__ = ["FairValueConfig", "FairValueEngine", "FairValueEstimate"]
