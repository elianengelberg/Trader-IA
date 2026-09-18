"""Comparing the local book with the venue's own bookTicker, without pretending they are
one stream.

``depth@100ms`` is batched every 100 ms; ``bookTicker`` is sent on every top-of-book
change. Sampled at the same instant they are at different points in time, and each
carries the venue's sequence id that says which one is fresher. A difference of a few
ticks — even a local top inside the venue's top for one sample — is timing. What cannot
be timing is a local book whose ask is at or below its own bid, or a disagreement that
survives several consecutive samples spaced seconds apart, far beyond the batching.

Only those two are reported as inconsistencies. Everything else is described, not judged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Consecutive samples (each seconds apart) a disagreement must survive to be called
#: persistent. Three samples at 5 s spacing is 15 s: two orders of magnitude past the
#: 100 ms batching of the depth stream.
PERSISTENT_SAMPLES = 3


@dataclass(frozen=True)
class TopOfBookSample:
    t: float
    local_bid: float
    local_ask: float
    local_update_id: int
    venue_bid: float
    venue_ask: float
    venue_update_id: int
    tick_size: float

    @property
    def bid_diff_ticks(self) -> int:
        return round((self.local_bid - self.venue_bid) / self.tick_size)

    @property
    def ask_diff_ticks(self) -> int:
        return round((self.local_ask - self.venue_ask) / self.tick_size)

    @property
    def max_abs_diff_ticks(self) -> int:
        return max(abs(self.bid_diff_ticks), abs(self.ask_diff_ticks))

    @property
    def exact(self) -> bool:
        return self.bid_diff_ticks == 0 and self.ask_diff_ticks == 0

    @property
    def within_1_tick(self) -> bool:
        return self.max_abs_diff_ticks <= 1

    @property
    def local_spread_negative(self) -> bool:
        """Impossible in any timing: the local book itself is crossed."""
        return self.local_ask <= self.local_bid

    @property
    def crossed_vs_venue(self) -> bool:
        """Local top inside the venue's top at this instant. Timing unless persistent."""
        return self.local_bid > self.venue_ask or self.local_ask < self.venue_bid

    @property
    def venue_ahead(self) -> bool:
        """The ticker carries a later sequence id than the book: the book has not yet
        received that batch, so any difference is explained by the stream's timing."""
        return self.venue_update_id > self.local_update_id

    @property
    def id_lag(self) -> int:
        return self.local_update_id - self.venue_update_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "t": self.t,
            "local_bid": self.local_bid,
            "local_ask": self.local_ask,
            "venue_bid": self.venue_bid,
            "venue_ask": self.venue_ask,
            "bid_diff_ticks": self.bid_diff_ticks,
            "ask_diff_ticks": self.ask_diff_ticks,
            "exact": self.exact,
            "within_1_tick": self.within_1_tick,
            "crossed_vs_venue": self.crossed_vs_venue,
            "venue_ahead": self.venue_ahead,
            "id_lag": self.id_lag,
            "local_spread_negative": self.local_spread_negative,
            "explanation": self.explanation,
        }

    @property
    def explanation(self) -> str:
        if self.local_spread_negative:
            return "IMPOSSIBLE: local ask <= local bid"
        if self.exact:
            return "exact match"
        if self.venue_ahead:
            return "timing: bookTicker is ahead of the depth batch the book has applied"
        if self.crossed_vs_venue:
            return "timing at one instant: local top inside the venue's top; inconsistency only if it persists"
        return "timing between two streams (ticks of difference)"


def summarise(samples: list[TopOfBookSample], *, persistent_samples: int = PERSISTENT_SAMPLES) -> dict[str, Any]:
    """What the samples say, and the only two verdicts that mean a real inconsistency."""
    consecutive = 0
    max_consecutive = 0
    consecutive_crossed = 0
    max_consecutive_crossed = 0
    for sample in samples:
        consecutive = 0 if sample.within_1_tick else consecutive + 1
        max_consecutive = max(max_consecutive, consecutive)
        consecutive_crossed = consecutive_crossed + 1 if sample.crossed_vs_venue else 0
        max_consecutive_crossed = max(max_consecutive_crossed, consecutive_crossed)
    worst = sorted(samples, key=lambda x: -x.max_abs_diff_ticks)[:5]
    return {
        "samples": len(samples),
        "exact": sum(1 for x in samples if x.exact),
        "within_1_tick": sum(1 for x in samples if x.within_1_tick),
        "beyond_1_tick": sum(1 for x in samples if not x.within_1_tick),
        "venue_ahead_samples": sum(1 for x in samples if x.venue_ahead),
        "crossed_vs_venue_instants": sum(1 for x in samples if x.crossed_vs_venue),
        "max_consecutive_crossed_vs_venue": max_consecutive_crossed,
        "local_spread_negative": sum(1 for x in samples if x.local_spread_negative),
        "max_abs_diff_ticks": max((x.max_abs_diff_ticks for x in samples), default=None),
        "max_consecutive_disagreements": max_consecutive,
        "persistent_samples_threshold": persistent_samples,
        # The two verdicts. Everything above is description.
        "persistent_inconsistency": max_consecutive >= persistent_samples,
        "impossible_state": any(x.local_spread_negative for x in samples),
        "worst_samples": [x.as_dict() for x in worst],
        "rule": (
            "depth@100ms and bookTicker are separate streams: a difference at one instant, "
            "even a local top inside the venue's top, is timing. Only a local ask <= bid "
            f"(impossible) or a disagreement over {persistent_samples} consecutive samples "
            "(persistent) is an inconsistency."
        ),
    }


__all__ = ["PERSISTENT_SAMPLES", "TopOfBookSample", "summarise"]
