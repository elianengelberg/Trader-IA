"""Latency as a distribution, not an average.

A market maker lives or dies by its tail: the p99 is the message that arrived after the
price had already moved. Samples are kept in a bounded window and percentiles are read
from the sorted window on demand — cheap enough for thousands of samples a minute.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any


class LatencyStats:
    """Rolling window of latency samples in milliseconds with p50/p95/p99."""

    def __init__(self, *, window: int = 4000) -> None:
        self._samples: deque[float] = deque(maxlen=max(10, window))
        self._count = 0
        self._last: float | None = None
        self._ema: float | None = None
        self._min: float | None = None
        self._max: float | None = None

    def add(self, sample_ms: float) -> None:
        value = float(sample_ms)
        self._samples.append(value)
        self._count += 1
        self._last = value
        self._ema = value if self._ema is None else 0.95 * self._ema + 0.05 * value
        self._min = value if self._min is None else min(self._min, value)
        self._max = value if self._max is None else max(self._max, value)

    @property
    def count(self) -> int:
        return self._count

    def percentile(self, pct: float) -> float | None:
        if not self._samples:
            return None
        # Nearest-rank definition: the smallest value with at least pct% of samples at
        # or below it. p50 of 1..100 is 50, p99 is 99 — no interpolation, no surprises.
        ordered = sorted(self._samples)
        rank = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
        return ordered[rank]

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self._count,
            "window": len(self._samples),
            "last_ms": round(self._last, 2) if self._last is not None else None,
            "ema_ms": round(self._ema, 2) if self._ema is not None else None,
            "min_ms": round(self._min, 2) if self._min is not None else None,
            "max_ms": round(self._max, 2) if self._max is not None else None,
            "p50_ms": round(self.percentile(50) or 0.0, 2) if self._samples else None,
            "p95_ms": round(self.percentile(95) or 0.0, 2) if self._samples else None,
            "p99_ms": round(self.percentile(99) or 0.0, 2) if self._samples else None,
        }


__all__ = ["LatencyStats"]
