"""Toxicity: how much the resolved markouts say the flow has been costing us.

A rolling, exponentially-weighted mean of the **adverse** 1 s markout (the cost side
only) over resolved fills, overall and per regime bucket. The score is in [0, 1] and
the only things it can do are **widen** the target spread, **shrink** the quote size,
or say there is not enough evidence yet. It never narrows, never enlarges, and never
sees a markout before its horizon has passed — it is fed by the tracker's resolved
list, which is lagged by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tia.mm.adverse_selection import BUCKET_KEYS, Markout


@dataclass(frozen=True)
class ToxicityConfig:
    horizon_ms: int = 1_000
    min_samples: int = 20
    decay: float = 0.98  # weight kept per new observation
    #: Mean adverse markout (bps) at which the score reaches 1.
    scale_bps: float = 2.0
    max_widen_bps: float = 5.0
    min_size_factor: float = 0.5


@dataclass(frozen=True)
class ToxicityReading:
    score: float | None  # None: not enough evidence
    adverse_mean_bps: float | None
    samples: int
    widen_bps: float  # >= 0 always
    size_factor: float  # in [min_size_factor, 1]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class _Ewma:
    def __init__(self, decay: float) -> None:
        self._decay = decay
        self.value: float | None = None
        self.samples = 0

    def add(self, x: float) -> None:
        self.value = x if self.value is None else self._decay * self.value + (1.0 - self._decay) * x
        self.samples += 1


class ToxicityEngine:
    def __init__(self, config: ToxicityConfig | None = None) -> None:
        self.config = config or ToxicityConfig()
        self._overall = _Ewma(self.config.decay)
        self._by_bucket: dict[tuple[tuple[str, str], ...], _Ewma] = {}

    def observe(self, markout: Markout) -> bool:
        """Feed one **resolved** markout. Unresolved or expired ones are refused."""
        if not markout.resolved:
            return False
        value = markout.at(self.config.horizon_ms)
        if value is None:
            return False
        adverse = max(0.0, -value)
        self._overall.add(adverse)
        key = tuple((k, markout.observation.buckets.get(k, "unknown")) for k in BUCKET_KEYS)
        self._by_bucket.setdefault(key, _Ewma(self.config.decay)).add(adverse)
        return True

    def _reading(self, ewma: _Ewma, label: str) -> ToxicityReading:
        cfg = self.config
        if ewma.samples < cfg.min_samples or ewma.value is None:
            return ToxicityReading(None, ewma.value, ewma.samples, 0.0, 1.0, f"{label}: {ewma.samples}/{cfg.min_samples} resolved fills, no verdict")
        score = max(0.0, min(1.0, ewma.value / cfg.scale_bps))
        return ToxicityReading(
            score=score,
            adverse_mean_bps=ewma.value,
            samples=ewma.samples,
            widen_bps=score * cfg.max_widen_bps,
            size_factor=1.0 - (1.0 - cfg.min_size_factor) * score,
            reason=f"{label}: adverse 1s markout {ewma.value:.2f} bps over {ewma.samples} fills",
        )

    def overall(self) -> ToxicityReading:
        return self._reading(self._overall, "overall")

    def for_buckets(self, buckets: dict[str, str]) -> ToxicityReading:
        key = tuple((k, buckets.get(k, "unknown")) for k in BUCKET_KEYS)
        ewma = self._by_bucket.get(key)
        if ewma is None:
            return ToxicityReading(None, None, 0, 0.0, 1.0, "bucket: no resolved fills yet")
        return self._reading(ewma, "bucket")

    def reading(self, buckets: dict[str, str] | None = None) -> ToxicityReading:
        """The stricter of the overall and the bucket reading: toxicity never nets out."""
        overall = self.overall()
        if buckets is None:
            return overall
        bucket = self.for_buckets(buckets)
        candidates = [r for r in (overall, bucket) if r.score is not None]
        if not candidates:
            return overall if overall.samples >= bucket.samples else bucket
        return max(candidates, key=lambda r: r.score or 0.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall().as_dict(),
            "buckets": {
                " ".join(f"{k}={v}" for k, v in key): self._reading(ewma, "bucket").as_dict()
                for key, ewma in self._by_bucket.items()
            },
        }


__all__ = ["ToxicityConfig", "ToxicityEngine", "ToxicityReading"]
