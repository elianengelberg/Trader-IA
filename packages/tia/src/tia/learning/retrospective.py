"""The Retrospective Engine — the system's memory of its own mistakes.

The Expected Value Engine already learns in the way that matters most: it estimates edge
from *realised* outcomes and refuses to trade a bucket it has no evidence for. But it
learns silently. It revises a bucket's mean downward after a bad trade without ever saying
"that direction, in that regime, has now disappointed four times." A number quietly moving
is not a lesson anyone can read.

This engine is the readable layer on top of that. For every closed round trip it compares
what the system **expected** (``expected_net_bps``, formed at entry) against what actually
**happened** (``realised net_bps``), classifies the gap, and files a durable lesson. Over
many trades those lessons aggregate into per-pattern memory — how often a
``(regime, direction, confidence-band)`` bucket has disappointed, by how much, and whether
the disappointment is recurring.

From that memory it derives a **guardrail**: a data-driven penalty applied to exactly the
buckets that have repeatedly been too optimistic. The penalty raises the edge threshold and
shrinks size where the system has been wrong before — and it *decays on its own* as new
trades come back in line with expectation, because it is recomputed from the running mean
error, never latched. That is the whole point the user asked for, stated precisely: when a
mistake recurs it is logged, not hidden, and the guard tightens; when the pattern reforms,
the guard eases.

Two honesty boundaries this module keeps:

* It invents no edge. It can only ever make the system **more** cautious (raise a
  threshold, shrink a size), never less. A retrospective that could talk the system into a
  trade would be a confidence generator wearing a lab coat.
* It is pure and deterministic. No I/O, no clock, no model call. The same trades in produce
  the same lessons out, which is what lets it be rebuilt exactly from the persisted trade
  record after a restart, and what lets a test pin its every branch.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from tia.domain.enums import Direction, MarketRegime
from tia.economics.expected_value import band_of


class LessonCategory(StrEnum):
    """How a closed trade landed against the expectation it was taken on."""

    #: Realised return tracked the expectation and stayed positive. The reinforcing case —
    #: evidence the bucket's edge is real, worth saying out loud alongside the failures.
    EDGE_CONFIRMED = "edge_confirmed"
    #: The system expected a profit and took a loss. The most serious miss: the trade
    #: should not have cleared the gate, and the bucket was materially miscalibrated.
    UNEXPECTED_LOSS = "unexpected_loss"
    #: Realised came in materially below expectation but still non-negative. The edge was
    #: there, just smaller than claimed — optimism, not a catastrophe.
    EDGE_OVERESTIMATED = "edge_overestimated"
    #: Realised came in materially above expectation. A miss in the pleasant direction, but
    #: still a calibration error worth recording so the estimate catches up.
    EDGE_UNDERESTIMATED = "edge_underestimated"


#: Calibration tolerance, in basis points. A gap between expected and realised smaller than
#: this is noise, not a lesson — every fill has slippage the model never promised to nail.
DEFAULT_TOLERANCE_BPS = 8.0

#: How much a bucket's realised fees may exceed its modelled cost before the overrun is
#: flagged on the review. Not a category of its own — cost is a *reason* a trade
#: disappointed, recorded alongside the calibration verdict rather than competing with it.
DEFAULT_COST_TOLERANCE_BPS = 5.0

#: A single bad trade is variance; a guardrail reacts only once a pattern has this many
#: closed trades behind it. Below the floor the lesson is still filed and still readable —
#: it just does not yet move risk.
DEFAULT_MIN_REVIEWS_FOR_GUARDRAIL = 5

#: The mean calibration error must be at least this negative before a bucket is penalised.
#: Keeps a bucket that is merely a hair optimistic from being handed a threshold penalty.
DEFAULT_ERROR_FLOOR_BPS = 3.0

#: The guardrail reflects *recent* behaviour, over this many of a bucket's latest trades.
#: The full lesson history is never forgotten — the report keeps every trade — but the
#: penalty is derived from the window so it eases fully once a punished pattern reforms,
#: instead of being dragged forever by an old bad streak diluted in a lifetime mean.
DEFAULT_GUARDRAIL_WINDOW = 30


@dataclass(frozen=True)
class TradeReview:
    """One closed trade, judged against what it was expected to do."""

    pattern: str
    regime: MarketRegime
    direction: Direction
    confidence: float
    expected_net_bps: float
    realised_net_bps: float
    fees_bps: float
    #: ``realised - expected``. Negative means the trade disappointed.
    calibration_error_bps: float
    category: LessonCategory
    #: True when fees alone overran their modelled budget by more than the tolerance.
    cost_overrun: bool
    #: A one-line, human-readable statement of what happened.
    headline: str
    #: What the memory takes forward — reinforce this, or be warier of it next time.
    lesson: str
    closed_at: datetime
    signal_id: str
    symbol: str
    #: Dollars at work on the trade (entry price x quantity). Basis points are the honest
    #: unit for *learning* — they compare trades of different sizes — but nobody thinks in
    #: them, so the record keeps the notional that turns each bps figure back into money.
    notional_usd: float = 0.0

    @property
    def is_win(self) -> bool:
        return self.realised_net_bps > 0.0

    @property
    def is_concern(self) -> bool:
        """A trade the system should have judged better — the kind a guardrail reacts to."""
        return self.category in (
            LessonCategory.UNEXPECTED_LOSS,
            LessonCategory.EDGE_OVERESTIMATED,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "regime": self.regime.value,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 4),
            "expected_net_bps": round(self.expected_net_bps, 4),
            "realised_net_bps": round(self.realised_net_bps, 4),
            "fees_bps": round(self.fees_bps, 4),
            "calibration_error_bps": round(self.calibration_error_bps, 4),
            "category": self.category.value,
            "cost_overrun": self.cost_overrun,
            "headline": self.headline,
            "lesson": self.lesson,
            "closed_at": self.closed_at.isoformat(),
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "notional_usd": round(self.notional_usd, 2),
            "is_win": self.is_win,
            "is_concern": self.is_concern,
        }


@dataclass(frozen=True)
class Guardrail:
    """A data-driven adjustment a pattern has earned by how it has actually behaved.

    Only ever tightens: ``threshold_add_bps`` is non-negative and ``size_multiplier`` is at
    most 1.0. A pattern that behaves gets the no-op guardrail (:meth:`neutral`).
    """

    pattern: str
    threshold_add_bps: float
    size_multiplier: float
    reason: str
    based_on_trades: int

    @property
    def is_active(self) -> bool:
        return self.threshold_add_bps > 0.0 or self.size_multiplier < 1.0

    @classmethod
    def neutral(cls, pattern: str, *, based_on_trades: int = 0) -> Guardrail:
        return cls(
            pattern=pattern,
            threshold_add_bps=0.0,
            size_multiplier=1.0,
            reason="no adjustment — this pattern is tracking its expectation",
            based_on_trades=based_on_trades,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "threshold_add_bps": round(self.threshold_add_bps, 4),
            "size_multiplier": round(self.size_multiplier, 4),
            "reason": self.reason,
            "based_on_trades": self.based_on_trades,
            "active": self.is_active,
        }


@dataclass
class PatternMemory:
    """The running record for one ``(regime, direction, confidence-band)`` bucket.

    Lifetime counters (``reviews``, ``wins``, ``mean_error_bps`` …) are the durable record —
    the report shows all of it and forgets nothing. The bounded ``_recent`` window is what
    the guardrail reads, so the *penalty* reflects recent behaviour even though the *record*
    is complete.
    """

    pattern: str
    regime: MarketRegime
    direction: Direction
    window: int = DEFAULT_GUARDRAIL_WINDOW
    reviews: int = 0
    wins: int = 0
    losses: int = 0
    concerns: int = 0
    cost_overruns: int = 0
    _error_sum: float = 0.0
    _realised_sum: float = 0.0
    category_counts: dict[str, int] = field(default_factory=dict)
    last_seen: datetime | None = None
    last_headline: str = ""
    #: (calibration_error_bps, is_concern) for the last ``window`` trades in this bucket.
    _recent: deque[tuple[float, bool]] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self._recent.maxlen != self.window:
            self._recent = deque(self._recent, maxlen=self.window)

    @property
    def mean_error_bps(self) -> float:
        return self._error_sum / self.reviews if self.reviews else 0.0

    @property
    def mean_realised_bps(self) -> float:
        return self._realised_sum / self.reviews if self.reviews else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.reviews if self.reviews else 0.0

    @property
    def recent_reviews(self) -> int:
        return len(self._recent)

    @property
    def recent_mean_error_bps(self) -> float:
        return sum(error for error, _ in self._recent) / len(self._recent) if self._recent else 0.0

    @property
    def recent_concerns(self) -> int:
        return sum(1 for _, concern in self._recent if concern)

    @property
    def recent_concern_ratio(self) -> float:
        if not self._recent:
            return 0.0
        return self.recent_concerns / len(self._recent)

    def observe(self, review: TradeReview) -> None:
        self.reviews += 1
        self._error_sum += review.calibration_error_bps
        self._realised_sum += review.realised_net_bps
        if review.is_win:
            self.wins += 1
        else:
            self.losses += 1
        if review.is_concern:
            self.concerns += 1
        if review.cost_overrun:
            self.cost_overruns += 1
        self.category_counts[review.category.value] = (
            self.category_counts.get(review.category.value, 0) + 1
        )
        self.last_seen = review.closed_at
        self.last_headline = review.headline
        self._recent.append((review.calibration_error_bps, review.is_concern))

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "regime": self.regime.value,
            "direction": self.direction.value,
            "reviews": self.reviews,
            "wins": self.wins,
            "losses": self.losses,
            "concerns": self.concerns,
            "cost_overruns": self.cost_overruns,
            "win_rate": round(self.win_rate, 4),
            "mean_error_bps": round(self.mean_error_bps, 4),
            "mean_realised_bps": round(self.mean_realised_bps, 4),
            "category_counts": dict(self.category_counts),
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "last_headline": self.last_headline,
        }


class RetrospectiveEngine:
    """Files a lesson per closed trade and derives guardrails from the accumulated record.

    Pure and deterministic: feed it the same closed trades in the same order and it produces
    the same lessons and the same guardrails, which is what lets the runtime rebuild it from
    the persisted trade record on startup.
    """

    def __init__(
        self,
        *,
        tolerance_bps: float = DEFAULT_TOLERANCE_BPS,
        cost_tolerance_bps: float = DEFAULT_COST_TOLERANCE_BPS,
        min_reviews_for_guardrail: int = DEFAULT_MIN_REVIEWS_FOR_GUARDRAIL,
        error_floor_bps: float = DEFAULT_ERROR_FLOOR_BPS,
        threshold_gain: float = 0.5,
        threshold_cap_bps: float = 40.0,
        size_floor: float = 0.4,
        guardrail_window: int = DEFAULT_GUARDRAIL_WINDOW,
        history_limit: int = 500,
    ) -> None:
        self._tolerance = tolerance_bps
        self._cost_tolerance = cost_tolerance_bps
        self._min_reviews = max(1, min_reviews_for_guardrail)
        self._error_floor = error_floor_bps
        self._threshold_gain = threshold_gain
        self._threshold_cap = threshold_cap_bps
        self._size_floor = size_floor
        self._window = max(1, guardrail_window)
        self._history_limit = history_limit
        self._memory: dict[str, PatternMemory] = {}
        self._history: list[TradeReview] = []

    # ------------------------------------------------------------------ ingestion

    def review(
        self,
        *,
        regime: MarketRegime,
        direction: Direction,
        confidence: float,
        expected_net_bps: float,
        realised_net_bps: float,
        fees_bps: float,
        closed_at: datetime,
        signal_id: str = "",
        symbol: str = "",
        expected_cost_bps: float | None = None,
        notional_usd: float = 0.0,
    ) -> TradeReview:
        """Judge one closed trade, file the lesson, and fold it into the pattern memory."""
        pattern = self._pattern(regime, direction, confidence)
        error = realised_net_bps - expected_net_bps
        cost_overrun = (
            expected_cost_bps is not None
            and fees_bps - expected_cost_bps >= self._cost_tolerance
        )
        category = self._classify(expected_net_bps, realised_net_bps, error)
        headline, lesson = self._narrate(
            regime,
            direction,
            category,
            expected_net_bps,
            realised_net_bps,
            cost_overrun,
            notional_usd=max(0.0, notional_usd),
        )

        review = TradeReview(
            pattern=pattern,
            regime=regime,
            direction=direction,
            confidence=confidence,
            expected_net_bps=expected_net_bps,
            realised_net_bps=realised_net_bps,
            fees_bps=fees_bps,
            calibration_error_bps=error,
            category=category,
            cost_overrun=cost_overrun,
            headline=headline,
            lesson=lesson,
            closed_at=closed_at,
            signal_id=signal_id,
            symbol=symbol,
            notional_usd=max(0.0, notional_usd),
        )

        memory = self._memory.get(pattern)
        if memory is None:
            memory = PatternMemory(
                pattern=pattern, regime=regime, direction=direction, window=self._window
            )
            self._memory[pattern] = memory
        memory.observe(review)

        self._history.append(review)
        if len(self._history) > self._history_limit:
            del self._history[: len(self._history) - self._history_limit]

        return review

    def _classify(
        self, expected: float, realised: float, error: float
    ) -> LessonCategory:
        if realised < 0.0 <= expected:
            return LessonCategory.UNEXPECTED_LOSS
        if error <= -self._tolerance:
            return LessonCategory.EDGE_OVERESTIMATED
        if error >= self._tolerance:
            return LessonCategory.EDGE_UNDERESTIMATED
        return LessonCategory.EDGE_CONFIRMED

    @staticmethod
    def _amount(bps: float, notional_usd: float) -> str:
        """A per-trade return, spoken in dollars when the trade's size is on record.

        Falls back to basis points with no notional — inventing a dollar figure would be
        worse than an unfamiliar unit. The engine's arithmetic stays in bps either way.
        """
        if notional_usd > 0:
            value = bps * notional_usd / 10_000.0
            return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"
        return f"{bps:+.1f} bps"

    def _narrate(
        self,
        regime: MarketRegime,
        direction: Direction,
        category: LessonCategory,
        expected: float,
        realised: float,
        cost_overrun: bool,
        notional_usd: float = 0.0,
    ) -> tuple[str, str]:
        where = f"{direction.value} in {regime.value.replace('_', ' ')}"
        exp = self._amount(expected, notional_usd)
        real = self._amount(realised, notional_usd)
        cost_note = " Fees ran over their modelled budget." if cost_overrun else ""
        if category is LessonCategory.UNEXPECTED_LOSS:
            return (
                f"{where}: expected {exp}, lost {real}.",
                f"A {where} trade that cleared the gate still lost money. Demand a larger "
                f"margin of safety here until the bucket re-earns trust.{cost_note}",
            )
        if category is LessonCategory.EDGE_OVERESTIMATED:
            return (
                f"{where}: expected {exp}, made only {real}.",
                f"The edge for {where} is real but smaller than claimed; the estimate is "
                f"optimistic and is being revised down.{cost_note}",
            )
        if category is LessonCategory.EDGE_UNDERESTIMATED:
            return (
                f"{where}: expected {exp}, made {real}.",
                f"{where} did better than the estimate; the bucket may be under-credited, "
                "which the running mean will correct as more close.",
            )
        return (
            f"{where}: expected {exp}, made {real} — on target.",
            f"{where} behaved as expected. Evidence the bucket's edge is calibrated; "
            "reinforce, do not touch.",
        )

    def record_many(self, outcomes: list[dict[str, Any]]) -> None:
        """Rebuild the memory from persisted edge outcomes (rows of the trade record).

        Each mapping needs ``regime``/``direction`` (enum values), ``confidence``,
        ``expected_net_bps``, ``net_bps``, ``fees_bps`` and ``closed_at``. Anything the
        estimator persisted has these, so the retrospective survives a restart exactly.
        """
        for row in outcomes:
            self.review(
                regime=MarketRegime(row["regime"]),
                direction=Direction(row["direction"]),
                confidence=float(row["confidence"]),
                expected_net_bps=float(row.get("expected_net_bps", 0.0)),
                realised_net_bps=float(row["net_bps"]),
                fees_bps=float(row.get("fees_bps", 0.0)),
                closed_at=row["closed_at"],
                signal_id=str(row.get("signal_id", "")),
                symbol=str(row.get("symbol", "")),
                notional_usd=(
                    float(row.get("entry_price") or 0.0) * float(row.get("quantity") or 0.0)
                ),
            )

    # ------------------------------------------------------------------ guardrails

    def guardrail_for(
        self, *, regime: MarketRegime, direction: Direction, confidence: float
    ) -> Guardrail:
        """The adjustment this bucket has earned, or a no-op if it is behaving.

        Recomputed from the running mean every call, so it eases as the pattern reforms —
        there is no latched penalty to reset.
        """
        pattern = self._pattern(regime, direction, confidence)
        memory = self._memory.get(pattern)
        if memory is None or memory.recent_reviews < self._min_reviews:
            recent = memory.recent_reviews if memory else 0
            return Guardrail.neutral(pattern, based_on_trades=recent)

        mean_error = memory.recent_mean_error_bps
        if mean_error >= -self._error_floor:
            return Guardrail.neutral(pattern, based_on_trades=memory.recent_reviews)

        shortfall = -mean_error  # positive magnitude of the average disappointment
        threshold_add = min(self._threshold_cap, self._threshold_gain * shortfall)
        # Size shrinks with how large a share of recent trades were genuine concerns,
        # floored so the pattern is dampened, never switched off outright.
        concern_ratio = memory.recent_concern_ratio
        size_multiplier = max(self._size_floor, 1.0 - concern_ratio)
        usd = self.typical_notional_usd
        return Guardrail(
            pattern=pattern,
            threshold_add_bps=threshold_add,
            size_multiplier=size_multiplier,
            reason=(
                f"{memory.recent_concerns}/{memory.recent_reviews} recent trades here "
                f"disappointed; mean miss {self._amount(mean_error, usd)} per trade — "
                f"demanding {self._amount(threshold_add, usd)} more profit and size "
                f"x{size_multiplier:.2f} until it re-earns trust"
            ),
            based_on_trades=memory.recent_reviews,
        )

    # ------------------------------------------------------------------ reporting

    def memory(self) -> list[PatternMemory]:
        """Every pattern seen, worst calibration first — the buckets to worry about on top."""
        return sorted(self._memory.values(), key=lambda m: m.mean_error_bps)

    def recent(self, limit: int = 40) -> list[TradeReview]:
        """The most recent lessons, newest first."""
        return list(reversed(self._history[-limit:]))

    @property
    def reviews(self) -> int:
        return len(self._history)

    @property
    def typical_notional_usd(self) -> float:
        """The median dollars-at-work of recent trades — the honest conversion factor
        between a basis-point figure and "about how many dollars is that per trade".

        Median, not mean: one oversized trade must not inflate what every threshold
        appears to cost. Zero when no trade carried a notional (nothing to convert with).
        """
        notionals = sorted(r.notional_usd for r in self._history if r.notional_usd > 0)
        if not notionals:
            return 0.0
        mid = len(notionals) // 2
        if len(notionals) % 2:
            return notionals[mid]
        return (notionals[mid - 1] + notionals[mid]) / 2.0

    def report(self, *, recent_limit: int = 40) -> dict[str, Any]:
        """Everything the dashboard shows: overall calibration, patterns, guards, lessons.

        The headline numbers aggregate the pattern memories' **lifetime** counters, not
        the bounded recent-lessons list — an earlier version summed the capped list, so a
        system that had reviewed 3,200 trades reported "500 reviewed", which read as the
        page being stale rather than the buffer being bounded.
        """
        memories = list(self._memory.values())
        total = sum(memory.reviews for memory in memories)
        wins = sum(memory.wins for memory in memories)
        concerns = sum(memory.concerns for memory in memories)
        mean_error = (
            sum(memory.mean_error_bps * memory.reviews for memory in memories) / total
            if total
            else 0.0
        )
        category_counts: dict[str, int] = defaultdict(int)
        for memory in memories:
            for category, count in memory.category_counts.items():
                category_counts[category] += count

        guardrails = [
            self._guardrail_for_memory(memory).as_dict()
            for memory in self.memory()
            if self._guardrail_for_memory(memory).is_active
        ]

        return {
            "reviews": total,
            "wins": wins,
            "losses": total - wins,
            "concerns": concerns,
            "win_rate": round(wins / total, 4) if total else 0.0,
            "mean_calibration_error_bps": round(mean_error, 4),
            "typical_notional_usd": round(self.typical_notional_usd, 2),
            "category_counts": dict(category_counts),
            "patterns": [memory.as_dict() for memory in self.memory()],
            "active_guardrails": guardrails,
            "recent_lessons": [review.as_dict() for review in self.recent(recent_limit)],
            "explanation": (
                "Each closed trade is scored against the edge it was taken on. Recurring "
                "disappointments raise the threshold and shrink the size for that exact "
                "pattern, and the penalty eases as the pattern comes back in line. The "
                "system only ever grows more cautious from what it learns here — it never "
                "talks itself into a trade."
            ),
        }

    # ------------------------------------------------------------------ internals

    def _guardrail_for_memory(self, memory: PatternMemory) -> Guardrail:
        return self.guardrail_for(
            regime=memory.regime,
            direction=memory.direction,
            confidence=self._confidence_for(memory.pattern),
        )

    @staticmethod
    def _confidence_for(pattern: str) -> float:
        """Recover a confidence that lands in the pattern's own band, from the band edge."""
        band = pattern.rsplit("|", 1)[-1]
        low = float(band.split("-")[0])
        return low + 0.001

    @staticmethod
    def _pattern(regime: MarketRegime, direction: Direction, confidence: float) -> str:
        low, high = band_of(confidence)
        return f"{regime.value}|{direction.value}|{low:.2f}-{high:.2f}"


__all__ = [
    "DEFAULT_COST_TOLERANCE_BPS",
    "DEFAULT_ERROR_FLOOR_BPS",
    "DEFAULT_MIN_REVIEWS_FOR_GUARDRAIL",
    "DEFAULT_TOLERANCE_BPS",
    "Guardrail",
    "LessonCategory",
    "PatternMemory",
    "RetrospectiveEngine",
    "TradeReview",
]
