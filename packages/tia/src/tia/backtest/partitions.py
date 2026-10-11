"""Chronological partitions for the strategy experiment, with purge and embargo gaps.

Research comes first, then a gap, then validation, then a gap, then the holdout to the
end of the series. Nothing is shuffled. The gap after a partition is ``purge`` bars
(trades that straddle the boundary are not counted twice) plus ``embargo`` bars (a
feature window that reaches back from the next partition does not see the previous one's
last decisions). Both are measured in bars of the horizon being evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Partitions:
    research: tuple[int, int]
    validation: tuple[int, int]
    holdout: tuple[int, int]
    gap: int

    def as_dict(self) -> dict[str, tuple[int, int]]:
        return {"research": self.research, "validation": self.validation, "holdout": self.holdout}

    def __getitem__(self, name: str) -> tuple[int, int]:
        return self.as_dict()[name]

    def items(self):  # type: ignore[no-untyped-def]
        return self.as_dict().items()


def partitions(n: int, *, research: float, validation: float, purge: int, embargo: int) -> Partitions:
    if n <= 0:
        raise ValueError("no bars to partition")
    if not (0.0 < research < 1.0 and 0.0 < validation < 1.0 and research + validation < 1.0):
        raise ValueError("research and validation fractions must be in (0, 1) and sum below 1")
    if purge < 0 or embargo < 0:
        raise ValueError("purge and embargo must be non-negative")
    gap = purge + embargo
    r_end = int(n * research)
    v_start = min(n, r_end + gap)
    v_end = min(n, v_start + int(n * validation))
    h_start = min(n, v_end + gap)
    return Partitions(research=(0, r_end), validation=(v_start, v_end), holdout=(h_start, n), gap=gap)


def window_bounds(start: int, end: int, *, lookback: int, min_warmup: int = 120) -> tuple[int, int]:
    """``(window_start, warmup_bars)`` for a cell over ``bars[start:end]``.

    The window may reach back up to ``lookback`` bars *before* the partition for feature
    warm-up — past data, never future — and the engine takes no decision inside the
    warm-up. When fewer than ``min_warmup`` bars of history exist, the warm-up extends into
    the partition itself, which forfeits decisions, never invents history.
    """
    if start < 0 or end <= start:
        raise ValueError("a cell needs a non-empty [start, end) range")
    lead_in = min(max(0, lookback), start)
    return (start - lead_in, max(min_warmup, lead_in))


__all__ = ["Partitions", "partitions", "window_bounds"]
