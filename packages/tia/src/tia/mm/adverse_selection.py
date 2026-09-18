"""Adverse selection: what the market did right after our simulated fill.

A maker fill is only good if the price does not immediately move against it. The
markout at horizon ``h`` answers that for one fill:

    buy  fill at p:  markout_h = (mid(t_fill + h) - p) / p * 1e4   (bps)
    sell fill at p:  markout_h = (p - mid(t_fill + h)) / p * 1e4

Negative is adverse. The tracker registers a fill with nothing but what was known at
fill time, and resolves each horizon with the **first mid observed at or after**
``t_fill + h`` — so it can only ever be read after the fact. Nothing here decides
whether a fill happened; nothing here is consulted before a horizon has passed. A fill
whose horizons never see a mid (a data gap) expires as **unresolved**, counted and
excluded, not guessed.

Regime buckets (side, spread, imbalance, volatility, flow) are attached at fill time so
the markouts can be split by the conditions that produced them.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from tia.mm.features import FeatureVector

HORIZONS_MS: tuple[int, ...] = (100, 250, 500, 1_000, 2_000, 5_000)
BUCKET_KEYS = ("side", "spread_regime", "imbalance_regime", "vol_regime", "flow_regime")


@dataclass(frozen=True)
class RegimeConfig:
    imbalance_heavy: float = 0.2
    vol_low_bps: float = 1.0
    vol_high_bps: float = 3.0
    flow_strong: float = 0.3
    vol_window: str = "5s"
    flow_window: str = "5s"


def regimes_of(features: FeatureVector, side: str, config: RegimeConfig | None = None) -> dict[str, str]:
    """The regime labels a fill is filed under, from the features at decision time."""
    cfg = config or RegimeConfig()
    imb = features.imbalance_t5
    if imb is None:
        imbalance = "unknown"
    elif imb > cfg.imbalance_heavy:
        imbalance = "bid_heavy"
    elif imb < -cfg.imbalance_heavy:
        imbalance = "ask_heavy"
    else:
        imbalance = "balanced"
    vol = features.vol_bps.get(cfg.vol_window)
    if vol is None:
        vol_regime = "unknown"
    elif vol < cfg.vol_low_bps:
        vol_regime = "low"
    elif vol > cfg.vol_high_bps:
        vol_regime = "high"
    else:
        vol_regime = "mid"
    flow = features.trade_flow.get(cfg.flow_window)
    norm = flow.flow_norm if flow is not None else None
    if norm is None:
        flow_regime = "unknown"
    elif norm > cfg.flow_strong:
        flow_regime = "buying"
    elif norm < -cfg.flow_strong:
        flow_regime = "selling"
    else:
        flow_regime = "mixed"
    return {
        "side": side,
        "spread_regime": features.spread_regime,
        "imbalance_regime": imbalance,
        "vol_regime": vol_regime,
        "flow_regime": flow_regime,
    }


@dataclass(frozen=True)
class FillObservation:
    """What is known at fill time. Nothing about afterwards."""

    fill_id: str
    t_fill_ms: int
    side: str  # our side: "buy" or "sell"
    price: float
    quantity: float
    mid_at_fill: float
    buckets: dict[str, str] = field(default_factory=dict)

    @property
    def sign(self) -> float:
        return 1.0 if self.side == "buy" else -1.0

    @property
    def fill_to_mid_bps(self) -> float:
        """How far inside the mid the fill was: positive means we bought below / sold above."""
        return self.sign * (self.mid_at_fill - self.price) / self.price * 10_000.0


@dataclass
class Markout:
    observation: FillObservation
    horizons_bps: dict[int, float | None] = field(default_factory=dict)
    resolved_at_ms: dict[int, int] = field(default_factory=dict)
    expired: bool = False

    @property
    def resolved(self) -> bool:
        return not self.expired and all(v is not None for v in self.horizons_bps.values())

    def at(self, horizon_ms: int) -> float | None:
        return self.horizons_bps.get(horizon_ms)

    @property
    def adverse_bps_1s(self) -> float | None:
        """The cost side of the 1 s markout: positive when the market moved against us."""
        value = self.at(1_000)
        return None if value is None else max(0.0, -value)

    @property
    def favorable_bps_1s(self) -> float | None:
        value = self.at(1_000)
        return None if value is None else max(0.0, value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.observation.fill_id,
            "side": self.observation.side,
            "price": self.observation.price,
            "quantity": self.observation.quantity,
            "t_fill_ms": self.observation.t_fill_ms,
            "fill_to_mid_bps": round(self.observation.fill_to_mid_bps, 4),
            "buckets": dict(self.observation.buckets),
            "markout_bps": {str(h): v for h, v in self.horizons_bps.items()},
            "adverse_bps_1s": self.adverse_bps_1s,
            "favorable_bps_1s": self.favorable_bps_1s,
            "resolved": self.resolved,
            "expired": self.expired,
        }


@dataclass(frozen=True)
class HorizonStats:
    horizon_ms: int
    count: int
    mean_bps: float | None
    adverse_share: float | None  # fraction of fills with a negative markout
    mean_adverse_bps: float | None  # mean of max(0, -markout): the cost

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MarkoutTracker:
    """Registers fills, resolves their markouts as mids arrive, keeps the resolved ones."""

    def __init__(self, *, horizons_ms: tuple[int, ...] = HORIZONS_MS, tolerance_ms: int = 1_000, keep: int = 20_000) -> None:
        self.horizons_ms = tuple(sorted(horizons_ms))
        #: A horizon is resolved by the first mid at or after its moment, but only if that
        #: mid arrives within this tolerance; a later one means a data gap, and the
        #: markout is expired rather than measured with the wrong mid.
        self._tolerance_ms = tolerance_ms
        self._pending: list[Markout] = []
        self.resolved: deque[Markout] = deque(maxlen=keep)
        self.expired = 0
        self.registered = 0

    # ------------------------------------------------------------------ inputs

    def register(self, observation: FillObservation) -> None:
        self._pending.append(Markout(observation=observation, horizons_bps=dict.fromkeys(self.horizons_ms)))
        self.registered += 1

    def on_mid(self, t_ms: int, mid: float) -> list[Markout]:
        """A mid observed at ``t_ms`` resolves every horizon whose moment has passed."""
        newly: list[Markout] = []
        still: list[Markout] = []
        for markout in self._pending:
            obs = markout.observation
            for h in self.horizons_ms:
                if markout.horizons_bps[h] is not None or t_ms < obs.t_fill_ms + h:
                    continue
                if t_ms > obs.t_fill_ms + h + self._tolerance_ms:
                    markout.expired = True  # the mid that should have resolved it never came
                    break
                markout.horizons_bps[h] = obs.sign * (mid - obs.price) / obs.price * 10_000.0
                markout.resolved_at_ms[h] = t_ms
            if markout.expired:
                self.expired += 1
            elif markout.resolved:
                self.resolved.append(markout)
                newly.append(markout)
            else:
                still.append(markout)
        self._pending = still
        return newly

    # ------------------------------------------------------------------ reading

    @property
    def pending(self) -> int:
        return len(self._pending)

    def stats(self, horizon_ms: int, *, buckets: dict[str, str] | None = None) -> HorizonStats:
        rows = [
            m.at(horizon_ms)
            for m in self.resolved
            if buckets is None or all(m.observation.buckets.get(k) == v for k, v in buckets.items())
        ]
        values = [v for v in rows if v is not None]
        if not values:
            return HorizonStats(horizon_ms, 0, None, None, None)
        return HorizonStats(
            horizon_ms=horizon_ms,
            count=len(values),
            mean_bps=sum(values) / len(values),
            adverse_share=sum(1 for v in values if v < 0) / len(values),
            mean_adverse_bps=sum(max(0.0, -v) for v in values) / len(values),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "registered": self.registered,
            "pending": self.pending,
            "resolved": len(self.resolved),
            "expired_unresolved": self.expired,
            "horizons": {str(h): self.stats(h).as_dict() for h in self.horizons_ms},
        }


__all__ = [
    "BUCKET_KEYS",
    "HORIZONS_MS",
    "FillObservation",
    "HorizonStats",
    "Markout",
    "MarkoutTracker",
    "RegimeConfig",
    "regimes_of",
]
