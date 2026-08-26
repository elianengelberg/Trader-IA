"""The Expected Value Engine.

    expected net edge = expected gross edge - round-trip costs

Trade only when the net edge clears a threshold. Otherwise NO_TRADE.

**The hard part is the first term, and this is where trading systems lie to themselves.**

A strategy engine produces a *confidence*. It is tempting to treat that as a probability
and multiply it by a target to get an expected return. That is wrong, and wrong in the
direction that loses money: a confidence is a score on an arbitrary scale until something
has demonstrated that "0.7" means "70% of these worked". An EV engine fed an uncalibrated
confidence is a random number generator with an equals sign in front of it.

So the edge estimate here comes from **realised outcomes**, not from confidence:

* Past trades are bucketed by ``(regime, confidence band, direction)``.
* A bucket must contain at least :data:`MIN_SAMPLES_FOR_EDGE` closed trades before it can
  produce an estimate at all.
* Below that, the estimator may fall back ONE level: every confidence band of the same
  regime and direction pooled together, requiring twice the sample floor and shrunk by
  twice the standard error — a coarser claim, priced as one. Never across regimes or
  directions, and never to a guess: below both floors it returns ``None``, which the
  caller must treat as NO_TRADE.
* The estimate is the bucket's mean realised return, shrunk toward zero by its own
  standard error — so a bucket of eleven trades that averaged +40 bps does not get to
  claim +40 bps.

The consequence, stated plainly: **a fresh system trades nothing until it has evidence.**
That is the correct behaviour and it is the reason the paper-trading and backtesting paths
exist — they are how the evidence is produced without risking money.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from tia.domain.enums import Direction, MarketRegime
from tia.economics.costs import BPS, TradeCosts

#: Below this many closed trades in a bucket, no edge estimate is produced at all.
#: Thirty is the conventional floor for a mean to mean anything; it is not a guarantee,
#: it is the point below which the estimate is certainly noise.
MIN_SAMPLES_FOR_EDGE = 30

#: A pooled (regime+direction, all confidence bands) estimate must rest on this many
#: times the bucket floor. A coarser claim borrowed from neighbouring bands earns trust
#: with MORE data than an exact one, never with less.
POOLED_MIN_MULTIPLE = 2

#: How many standard errors a pooled estimate is shrunk by. Twice the bucket rate: the
#: pooling assumption — that this band behaves like its regime's other bands — is itself
#: a source of error, and it is charged for, not waved through.
POOLED_SHRINK_SE = 2.0

#: Confidence bands. Coarse on purpose: finer bands fill more slowly, and a bucket that
#: never reaches the sample floor is a bucket that never trades.
CONFIDENCE_BANDS: tuple[tuple[float, float], ...] = (
    (0.00, 0.55),
    (0.55, 0.70),
    (0.70, 0.85),
    (0.85, 1.01),
)


def band_of(confidence: float) -> tuple[float, float]:
    for low, high in CONFIDENCE_BANDS:
        if low <= confidence < high:
            return (low, high)
    return CONFIDENCE_BANDS[-1]


@dataclass(frozen=True)
class Outcome:
    """One closed trade, as the estimator consumes it."""

    regime: MarketRegime
    direction: Direction
    confidence: float
    #: Realised return in basis points of the entry notional, **net of the costs actually
    #: paid**. Gross would double-count: costs are subtracted again downstream.
    net_return_bps: float


@dataclass(frozen=True)
class EdgeEstimate:
    """What the evidence supports, with its own uncertainty attached."""

    mean_bps: float
    #: Shrunk toward zero by the standard error. This is the number to use.
    adjusted_bps: float
    standard_error_bps: float
    samples: int
    regime: MarketRegime
    direction: Direction
    confidence_band: tuple[float, float]
    #: "bucket" when the evidence is this exact (regime, direction, confidence band);
    #: "regime" when the band was too thin and the estimate pooled every band of the same
    #: regime and direction. A reader must be able to tell the two apart, because the
    #: second is a coarser claim and is deliberately priced as one.
    level: str = "bucket"
    #: One sentence naming what the number rests on, for the decision's explanation.
    basis: str = ""

    @property
    def is_positive(self) -> bool:
        return self.adjusted_bps > 0.0

    @property
    def is_pooled(self) -> bool:
        return self.level != "bucket"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean_bps": round(self.mean_bps, 4),
            "adjusted_bps": round(self.adjusted_bps, 4),
            "standard_error_bps": round(self.standard_error_bps, 4),
            "samples": self.samples,
            "regime": self.regime.value,
            "direction": self.direction.value,
            "confidence_band": list(self.confidence_band),
            "level": self.level,
            "basis": self.basis,
        }


class EdgeEstimator:
    """Estimates expected gross edge from realised outcomes, or refuses to.

    Fed from the trade journal — backtest results, paper-trading results, and eventually
    live results. It is the *only* source of an edge number in this system; nothing else
    is allowed to invent one.
    """

    def __init__(self, *, min_samples: int = MIN_SAMPLES_FOR_EDGE) -> None:
        self._min_samples = min_samples
        self._buckets: dict[tuple[str, str, tuple[float, float]], list[float]] = defaultdict(list)

    @property
    def min_samples(self) -> int:
        return self._min_samples

    def record(self, outcome: Outcome) -> None:
        key = (outcome.regime.value, outcome.direction.value, band_of(outcome.confidence))
        self._buckets[key].append(outcome.net_return_bps)

    def record_many(self, outcomes: list[Outcome]) -> None:
        for outcome in outcomes:
            self.record(outcome)

    def sample_count(
        self, *, regime: MarketRegime, direction: Direction, confidence: float
    ) -> int:
        return len(self._buckets.get((regime.value, direction.value, band_of(confidence)), []))

    def estimate(
        self, *, regime: MarketRegime, direction: Direction, confidence: float
    ) -> EdgeEstimate | None:
        """The edge the evidence supports, at the finest level that has enough of it.

        Two levels, tried in order:

        1. **The exact bucket** — (regime, direction, confidence band), at the bucket
           floor, shrunk by one standard error. The estimate as it always was.
        2. **The regime pool** — every confidence band of the same regime and direction,
           together. Only when the pool holds :data:`POOLED_MIN_MULTIPLE` times the
           bucket floor, and shrunk by :data:`POOLED_SHRINK_SE` standard errors, because
           "this band behaves like its neighbours" is an assumption and assumptions are
           charged for. The estimate says it is pooled; downstream shows it as such.

        Never across regimes or directions — a long in a trending market and a short in a
        ranging one are different animals, and an estimator that averaged them would be
        smuggling in exactly the guess this class exists to refuse.

        ``None`` still means what it meant: no basis for an expectation at either level,
        and the only honest response is NO_TRADE (or, in paper, an exploration trade).
        """
        band = band_of(confidence)
        exact = self._buckets.get((regime.value, direction.value, band), [])
        if len(exact) >= self._min_samples:
            return self._fit(
                exact,
                regime=regime,
                direction=direction,
                band=band,
                level="bucket",
                shrink_se=1.0,
                basis=f"{len(exact)} closed trades in this exact bucket",
            )

        pooled: list[float] = []
        for pool_band in CONFIDENCE_BANDS:
            pooled.extend(
                self._buckets.get((regime.value, direction.value, pool_band), [])
            )
        if len(pooled) < self._min_samples * POOLED_MIN_MULTIPLE:
            return None

        return self._fit(
            pooled,
            regime=regime,
            direction=direction,
            band=band,
            level="regime",
            shrink_se=POOLED_SHRINK_SE,
            basis=(
                f"pooled {len(pooled)} trades across every confidence band of "
                f"{regime.value}/{direction.value} — the exact band has only "
                f"{len(exact)} — priced at double the uncertainty discount"
            ),
        )

    @staticmethod
    def _fit(
        samples: list[float],
        *,
        regime: MarketRegime,
        direction: Direction,
        band: tuple[float, float],
        level: str,
        shrink_se: float,
        basis: str,
    ) -> EdgeEstimate:
        count = len(samples)
        mean = sum(samples) / count
        variance = sum((value - mean) ** 2 for value in samples) / (count - 1)
        standard_error = math.sqrt(variance / count)

        # Shrink toward zero, floored at zero from whichever side the mean is on. A
        # bucket whose mean is inside its own (scaled) noise gets no credit.
        discount = shrink_se * standard_error
        adjusted = max(0.0, mean - discount) if mean > 0 else min(0.0, mean + discount)

        return EdgeEstimate(
            mean_bps=mean,
            adjusted_bps=adjusted,
            standard_error_bps=standard_error,
            samples=count,
            regime=regime,
            direction=direction,
            confidence_band=band,
            level=level,
            basis=basis,
        )

    def pooled_count(self, *, regime: MarketRegime, direction: Direction) -> int:
        """Closed trades across every confidence band of one regime and direction."""
        return sum(
            len(self._buckets.get((regime.value, direction.value, band), []))
            for band in CONFIDENCE_BANDS
        )

    def coverage(self) -> dict[str, int]:
        """How full each bucket is. Shown in the UI so "why is it not trading?" has an
        answer that is not a shrug."""
        return {
            f"{regime}|{direction}|{band[0]:.2f}-{band[1]:.2f}": len(values)
            for (regime, direction, band), values in sorted(self._buckets.items())
        }


class EVDecision(dict[str, Any]):
    """A dict subclass so the decision serialises straight into the API and the journal."""


@dataclass(frozen=True)
class ExpectedValue:
    """The full arithmetic behind a trade-or-not decision."""

    gross_edge_bps: float
    costs: TradeCosts
    threshold_bps: float
    edge_estimate: EdgeEstimate | None
    reason: str = ""

    @property
    def net_edge_bps(self) -> float:
        return self.gross_edge_bps - self.costs.total_bps

    @property
    def net_edge_currency(self) -> float:
        return self.costs.notional * self.net_edge_bps * BPS

    @property
    def is_tradeable(self) -> bool:
        return self.edge_estimate is not None and self.net_edge_bps >= self.threshold_bps

    @property
    def cost_ratio(self) -> float:
        """Costs as a fraction of gross edge. Above 1.0 the trade is paying to exist."""
        if self.gross_edge_bps <= 0:
            return math.inf
        return self.costs.total_bps / self.gross_edge_bps

    def explain(self) -> str:
        if self.edge_estimate is None:
            return (
                f"NO_TRADE — {self.reason or 'no calibrated edge estimate for these conditions'}. "
                "The system declines rather than guessing."
            )
        verdict = "TRADE" if self.is_tradeable else "NO_TRADE"
        # Spoken in the dollars of this specific trade when its size is priced — basis
        # points stay the decision unit, but nobody outside the engine thinks in them.
        notional = self.costs.notional
        if notional > 0:

            def usd(bps_value: float) -> str:
                value = notional * bps_value * BPS
                return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"

            pooled_note = (
                " The edge is pooled from every confidence band of this regime and "
                "direction, priced at double the uncertainty discount."
                if self.edge_estimate.is_pooled
                else ""
            )
            return (
                f"{verdict} — on a ${notional:,.0f} position: expected gross "
                f"{usd(self.gross_edge_bps)} (from {self.edge_estimate.samples} past "
                f"trades) minus costs {usd(self.costs.total_bps)} "
                f"({self.costs.dominant_component} dominant) = net "
                f"{usd(self.net_edge_bps)}, against a required minimum of "
                f"{usd(self.threshold_bps)}.{pooled_note}"
            )
        return (
            f"{verdict} — expected gross {self.gross_edge_bps:.2f} bps "
            f"(from {self.edge_estimate.samples} past trades) minus costs "
            f"{self.costs.total_bps:.2f} bps ({self.costs.dominant_component} dominant) "
            f"= net {self.net_edge_bps:.2f} bps, against a threshold of "
            f"{self.threshold_bps:.2f} bps."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "gross_edge_bps": round(self.gross_edge_bps, 4),
            "net_edge_bps": round(self.net_edge_bps, 4),
            "net_edge_currency": round(self.net_edge_currency, 6),
            "threshold_bps": round(self.threshold_bps, 4),
            "cost_ratio": None if math.isinf(self.cost_ratio) else round(self.cost_ratio, 4),
            "tradeable": self.is_tradeable,
            "costs": self.costs.as_dict(),
            "edge": self.edge_estimate.as_dict() if self.edge_estimate else None,
            "reason": self.reason,
            "explanation": self.explain(),
        }


@dataclass
class ExpectedValueEngine:
    """Combines an edge estimate with a cost estimate and applies the threshold.

    The threshold is a *margin of safety*, not a formality. Set to zero, the system trades
    every position whose expectation is a fraction of a basis point above its costs — and
    since both terms are estimates, half of those are really below.
    """

    estimator: EdgeEstimator
    #: Minimum net edge, in basis points, before a trade is worth taking.
    threshold_bps: float = 5.0
    #: Costs may not exceed this fraction of the gross edge, independent of the absolute
    #: net. A trade netting 6 bps out of a 200 bps gross is fine; netting 6 out of 11 is a
    #: coin flip on the cost model being right.
    max_cost_ratio: float = 0.6
    _history: list[ExpectedValue] = field(default_factory=list)

    def evaluate(
        self,
        *,
        regime: MarketRegime,
        direction: Direction,
        confidence: float,
        costs: TradeCosts,
    ) -> ExpectedValue:
        if not direction.is_actionable:
            return self._remember(
                ExpectedValue(
                    gross_edge_bps=0.0,
                    costs=costs,
                    threshold_bps=self.threshold_bps,
                    edge_estimate=None,
                    reason=f"direction is {direction.value}",
                )
            )

        estimate = self.estimator.estimate(
            regime=regime, direction=direction, confidence=confidence
        )
        if estimate is None:
            have = self.estimator.sample_count(
                regime=regime, direction=direction, confidence=confidence
            )
            pooled = self.estimator.pooled_count(regime=regime, direction=direction)
            return self._remember(
                ExpectedValue(
                    gross_edge_bps=0.0,
                    costs=costs,
                    threshold_bps=self.threshold_bps,
                    edge_estimate=None,
                    reason=(
                        f"only {have} closed trades for {regime.value}/{direction.value} at "
                        f"this confidence ({self.estimator.min_samples} needed), and "
                        f"{pooled} across all its confidence bands "
                        f"({self.estimator.min_samples * POOLED_MIN_MULTIPLE} would allow "
                        "a pooled estimate at double the uncertainty discount)"
                    ),
                )
            )

        result = ExpectedValue(
            gross_edge_bps=estimate.adjusted_bps,
            costs=costs,
            threshold_bps=self.threshold_bps,
            edge_estimate=estimate,
        )

        if result.is_tradeable and result.cost_ratio > self.max_cost_ratio:
            result = ExpectedValue(
                gross_edge_bps=estimate.adjusted_bps,
                costs=costs,
                threshold_bps=math.inf,  # forces is_tradeable False
                edge_estimate=estimate,
                reason=(
                    f"costs are {result.cost_ratio:.0%} of the expected edge, above the "
                    f"{self.max_cost_ratio:.0%} ceiling — the trade depends on the cost "
                    "model being exactly right"
                ),
            )

        return self._remember(result)

    def _remember(self, result: ExpectedValue) -> ExpectedValue:
        """Record every evaluation, including the refusals.

        All of them, not just the ones that got as far as an edge estimate. An earlier
        version appended only on the path that produced a number, so a system refusing
        every signal for lack of evidence reported ``evaluations: 0`` and an acceptance
        rate of 0/0 — the counters looked identical to a system that was not evaluating
        at all, which is precisely the confusion they exist to prevent.
        """
        self._history.append(result)
        return result

    @property
    def evaluations(self) -> int:
        return len(self._history)

    def acceptance_rate(self) -> float:
        if not self._history:
            return 0.0
        return sum(1 for item in self._history if item.is_tradeable) / len(self._history)


__all__ = [
    "CONFIDENCE_BANDS",
    "MIN_SAMPLES_FOR_EDGE",
    "EVDecision",
    "EdgeEstimate",
    "EdgeEstimator",
    "ExpectedValue",
    "ExpectedValueEngine",
    "Outcome",
    "band_of",
]
