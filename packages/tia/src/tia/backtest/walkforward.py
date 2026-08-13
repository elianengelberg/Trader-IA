"""Walk-forward splitting, with purging and embargo.

A single train/test split answers one question badly. Walk-forward answers it repeatedly:
fit on a window, evaluate on the window that follows, roll forward, and never once let a
model see data from its own evaluation period.

Two protections that a naive split lacks, both aimed at the same failure — information
crossing the boundary in a way that inflates out-of-sample results into something
unreproducible:

* **Purge.** Bars immediately before a test window are dropped from training. A feature
  computed over a lookback that straddles the boundary would otherwise carry test-period
  information into the fit.
* **Embargo.** Bars immediately after a test window are skipped, so the next test window
  does not begin on bars that are near-duplicates of the previous one through serial
  correlation.

**How the two combine, stated precisely**, because getting this wrong is silent: each
training window ends ``max(purge_bars, embargo_bars)`` bars before its test window
begins. The purge accounts for feature lookback; taking the maximum additionally
guarantees that the preceding fold's embargo zone never lands inside the next fold's
training set, which is exactly what happens in a rolling schedule when the purge is
shorter than the embargo. Fold 0 has no preceding embargo zone, so the same cut is
slightly conservative there — deliberately, since folds with unequal training lengths are
not comparable to each other.

**What is not a leak.** Earlier *test* windows do appear in later training windows. That
is what walk-forward is: as time passes, the evaluated period becomes history and a real
system would refit on it. The protection is against a model seeing its *own* evaluation
period, not against it seeing an earlier one.

Both controls are expressed in bars. A split with a zero purge and a zero embargo will
report better numbers than the strategy can reproduce.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from tia.core.errors import BacktestError


class SplitScheme(StrEnum):
    """How the training window moves.

    ``ANCHORED`` keeps the start fixed and grows the training set — appropriate when more
    history is believed to help. ``ROLLING`` keeps the training length fixed and slides
    it — appropriate when old regimes are believed to mislead. They frequently disagree,
    and that disagreement is itself informative, so both are supported and a report that
    quotes only one should say which.
    """

    ANCHORED = "anchored"
    ROLLING = "rolling"


@dataclass(frozen=True)
class Fold:
    """One train/test pair, as index ranges into the original bar list."""

    index: int
    train_start: int
    train_end: int  # exclusive, already purged
    test_start: int
    test_end: int  # exclusive
    purged_bars: int
    embargoed_bars: int

    @property
    def train_length(self) -> int:
        return max(0, self.train_end - self.train_start)

    @property
    def test_length(self) -> int:
        return max(0, self.test_end - self.test_start)

    def train_slice(self, items: Sequence[object]) -> list[object]:
        return list(items[self.train_start : self.train_end])

    def test_slice(self, items: Sequence[object]) -> list[object]:
        return list(items[self.test_start : self.test_end])

    def describe(self) -> str:
        return (
            f"fold {self.index}: train[{self.train_start}:{self.train_end}] "
            f"({self.train_length} bars) → test[{self.test_start}:{self.test_end}] "
            f"({self.test_length} bars), purge={self.purged_bars}, "
            f"embargo={self.embargoed_bars}"
        )


@dataclass(frozen=True)
class WalkForwardPlan:
    """The full schedule, computed before anything runs.

    Materialised up front so the split can be inspected, logged and asserted on. A
    generator that yields folds lazily makes it easy to change the schedule between runs
    without noticing.
    """

    scheme: SplitScheme
    folds: tuple[Fold, ...]
    total_bars: int
    purge_bars: int
    embargo_bars: int

    def __len__(self) -> int:
        return len(self.folds)

    def __iter__(self) -> Iterator[Fold]:
        return iter(self.folds)

    @property
    def out_of_sample_bars(self) -> int:
        return sum(f.test_length for f in self.folds)

    @property
    def out_of_sample_coverage(self) -> float:
        """Share of the dataset that is ever evaluated out of sample."""
        return self.out_of_sample_bars / self.total_bars if self.total_bars else 0.0

    def describe(self) -> str:
        return (
            f"{self.scheme.value} walk-forward: {len(self.folds)} folds over "
            f"{self.total_bars} bars, {self.out_of_sample_bars} evaluated out of sample "
            f"({self.out_of_sample_coverage:.0%}), purge={self.purge_bars}, "
            f"embargo={self.embargo_bars}"
        )


def build_plan(
    total_bars: int,
    *,
    train_bars: int,
    test_bars: int,
    scheme: SplitScheme = SplitScheme.ANCHORED,
    purge_bars: int = 0,
    embargo_bars: int = 0,
    max_folds: int | None = None,
) -> WalkForwardPlan:
    """Compute the fold schedule.

    ``purge_bars`` are removed from the *end* of each training window; ``embargo_bars``
    are skipped after each test window before the next one begins.
    """
    if train_bars <= 0 or test_bars <= 0:
        raise BacktestError(
            "train and test windows must both be positive",
            train_bars=train_bars,
            test_bars=test_bars,
        )
    if purge_bars < 0 or embargo_bars < 0:
        raise BacktestError("purge and embargo must be non-negative")
    if max(purge_bars, embargo_bars) >= train_bars:
        raise BacktestError(
            "the purge/embargo gap would consume the entire training window",
            purge_bars=purge_bars,
            embargo_bars=embargo_bars,
            train_bars=train_bars,
        )
    if total_bars < train_bars + test_bars:
        raise BacktestError(
            "not enough bars for even one fold",
            total_bars=total_bars,
            needed=train_bars + test_bars,
        )

    folds: list[Fold] = []
    anchor = 0
    test_start = train_bars
    index = 0

    # See the module docstring: the cut is the maximum of the two so that the preceding
    # fold's embargo zone can never land inside the next fold's training window.
    boundary_gap = max(purge_bars, embargo_bars)

    while test_start + test_bars <= total_bars:
        if max_folds is not None and index >= max_folds:
            break
        train_start = anchor if scheme is SplitScheme.ANCHORED else test_start - train_bars
        train_end = test_start - boundary_gap
        if train_end - train_start <= 0:
            break

        folds.append(
            Fold(
                index=index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_start + test_bars,
                purged_bars=purge_bars,
                embargoed_bars=embargo_bars,
            )
        )
        index += 1
        test_start += test_bars + embargo_bars

    if not folds:
        raise BacktestError(
            "the schedule produced no usable folds",
            total_bars=total_bars,
            train_bars=train_bars,
            test_bars=test_bars,
        )

    return WalkForwardPlan(
        scheme=scheme,
        folds=tuple(folds),
        total_bars=total_bars,
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
    )


def assert_no_leakage(plan: WalkForwardPlan) -> None:
    """Verify the schedule's own guarantees.

    Cheap to run and worth running: an off-by-one in a fold schedule produces results
    that look plausible, publish cleanly, and cannot be reproduced by anyone.
    """
    required_gap = max(plan.purge_bars, plan.embargo_bars)
    for fold in plan.folds:
        if fold.train_end > fold.test_start:
            raise BacktestError(
                "training window overlaps its own test window", fold=fold.describe()
            )
        if fold.test_start - fold.train_end < required_gap:
            raise BacktestError(
                "the gap before the test window is smaller than purge/embargo requires",
                fold=fold.describe(),
                required=required_gap,
            )
        if fold.train_length <= 0 or fold.test_length <= 0:
            raise BacktestError("a fold has an empty window", fold=fold.describe())

    for previous, current in pairwise(plan.folds):
        # The embargo zone is the gap between one test window and the next. No training
        # window may reach into it — the property the max(purge, embargo) cut exists to
        # provide, asserted here rather than assumed from the arithmetic.
        if current.train_end > previous.test_end:
            raise BacktestError(
                "a training window extends into the preceding fold's embargo zone",
                previous=previous.describe(),
                current=current.describe(),
            )

        if current.test_start < previous.test_end:
            raise BacktestError(
                "test windows overlap; a bar would be evaluated twice",
                first=previous.describe(),
                second=current.describe(),
            )
        gap = current.test_start - previous.test_end
        if gap < plan.embargo_bars:
            raise BacktestError(
                "the embargo gap between consecutive test windows is too small",
                gap=gap,
                required=plan.embargo_bars,
            )
        if plan.scheme is SplitScheme.ANCHORED and current.train_start != previous.train_start:
            raise BacktestError("an anchored schedule moved its training start")


__all__ = [
    "Fold",
    "SplitScheme",
    "WalkForwardPlan",
    "assert_no_leakage",
    "build_plan",
]
