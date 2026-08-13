"""Walk-forward splitting.

A fold schedule is arithmetic, and an off-by-one in arithmetic produces results that look
plausible, publish cleanly, and cannot be reproduced by anyone. These tests exist because
that failure is silent.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise

import pytest

from tia.backtest.walkforward import (
    Fold,
    SplitScheme,
    assert_no_leakage,
    build_plan,
)
from tia.core.errors import BacktestError


def plan(**kwargs: object):  # type: ignore[no-untyped-def]
    defaults = {
        "total_bars": 2000,
        "train_bars": 600,
        "test_bars": 200,
        "purge_bars": 20,
        "embargo_bars": 50,
    }
    defaults.update(kwargs)
    return build_plan(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- shape


@pytest.mark.parametrize("scheme", list(SplitScheme))
def test_a_plan_passes_its_own_leakage_check(scheme: SplitScheme) -> None:
    assert_no_leakage(plan(scheme=scheme))


def test_an_anchored_schedule_keeps_its_start_and_grows() -> None:
    folds = list(plan(scheme=SplitScheme.ANCHORED))
    assert all(f.train_start == 0 for f in folds)
    lengths = [f.train_length for f in folds]
    assert lengths == sorted(lengths)
    assert lengths[-1] > lengths[0]


def test_a_rolling_schedule_keeps_a_constant_training_length() -> None:
    folds = list(plan(scheme=SplitScheme.ROLLING))
    lengths = {f.train_length for f in folds}
    assert len(lengths) == 1, f"rolling folds must be comparable to each other: {lengths}"
    starts = [f.train_start for f in folds]
    assert starts == sorted(starts) and starts[0] < starts[-1]


def test_test_windows_are_contiguous_in_time_and_never_overlap() -> None:
    folds = list(plan())
    for previous, current in pairwise(folds):
        assert current.test_start >= previous.test_end
        assert current.test_start - previous.test_end == 50  # the embargo


def test_every_test_window_is_the_configured_length() -> None:
    assert {f.test_length for f in plan()} == {200}


def test_out_of_sample_coverage_is_reported() -> None:
    p = plan()
    assert p.out_of_sample_bars == sum(f.test_length for f in p.folds)
    assert 0.0 < p.out_of_sample_coverage <= 1.0
    assert "out of sample" in p.describe()


def test_max_folds_truncates_the_schedule() -> None:
    assert len(plan(max_folds=2)) == 2


def test_slicing_helpers_return_the_declared_ranges() -> None:
    items = list(range(2000))
    fold = plan().folds[1]
    assert fold.train_slice(items) == items[fold.train_start : fold.train_end]
    assert fold.test_slice(items) == items[fold.test_start : fold.test_end]


# --------------------------------------------------------------------------- the gap


def test_the_training_window_stops_short_of_its_test_window() -> None:
    """The purge. A feature whose lookback straddles the boundary would otherwise carry
    test-period information into the fit."""
    for fold in plan(purge_bars=30, embargo_bars=0):
        assert fold.test_start - fold.train_end >= 30


def test_the_gap_is_the_larger_of_purge_and_embargo() -> None:
    """Documented behaviour, asserted.

    Taking the maximum is what stops the preceding fold's embargo zone from landing
    inside the next fold's training set — which is what happens in a rolling schedule
    whenever the purge is shorter than the embargo.
    """
    p = plan(purge_bars=10, embargo_bars=80, scheme=SplitScheme.ROLLING)
    for fold in p:
        assert fold.test_start - fold.train_end == 80


def test_no_training_window_reaches_into_the_preceding_embargo_zone() -> None:
    """The specific bug the max() rule exists to prevent, checked directly."""
    for scheme in SplitScheme:
        p = plan(purge_bars=5, embargo_bars=100, scheme=scheme)
        assert_no_leakage(p)
        for previous, current in pairwise(p.folds):
            assert current.train_end <= previous.test_end


def test_a_zero_gap_schedule_is_permitted_but_is_the_unsafe_configuration() -> None:
    """Allowed, because a caller may knowingly want it, and because forbidding it would
    make the protective effect of the default invisible."""
    p = plan(purge_bars=0, embargo_bars=0)
    assert_no_leakage(p)
    assert all(f.train_end == f.test_start for f in p)


# --------------------------------------------------------------------------- refusals


def test_a_purge_that_consumes_the_training_window_is_refused() -> None:
    with pytest.raises(BacktestError, match="consume the entire training window"):
        plan(train_bars=100, purge_bars=100)


def test_an_embargo_that_consumes_the_training_window_is_refused() -> None:
    with pytest.raises(BacktestError, match="consume the entire training window"):
        plan(train_bars=100, purge_bars=0, embargo_bars=150)


def test_too_few_bars_for_one_fold_is_refused() -> None:
    with pytest.raises(BacktestError, match="not enough bars"):
        plan(total_bars=500, train_bars=600, test_bars=200)


@pytest.mark.parametrize(("train", "test"), [(0, 200), (600, 0), (-10, 200)])
def test_non_positive_windows_are_refused(train: int, test: int) -> None:
    with pytest.raises(BacktestError, match="must both be positive"):
        plan(train_bars=train, test_bars=test)


def test_negative_purge_or_embargo_is_refused() -> None:
    with pytest.raises(BacktestError, match="non-negative"):
        plan(purge_bars=-1)


# --------------------------------------------------------------------------- the checker


def test_the_leakage_checker_catches_an_overlapping_fold() -> None:
    """The checker must be able to fail, or it is decoration."""
    bad = Fold(
        index=0,
        train_start=0,
        train_end=700,  # reaches past its own test start
        test_start=600,
        test_end=800,
        purged_bars=20,
        embargoed_bars=50,
    )
    with pytest.raises(BacktestError, match="overlaps its own test window"):
        assert_no_leakage(replace(plan(), folds=(bad,)))


def test_the_leakage_checker_catches_a_shrunken_gap() -> None:
    base = plan(purge_bars=40, embargo_bars=0)
    bad = replace(base.folds[0], train_end=base.folds[0].test_start - 5)
    with pytest.raises(BacktestError, match="smaller than purge/embargo requires"):
        assert_no_leakage(replace(base, folds=(bad,)))


def test_the_leakage_checker_catches_a_training_window_in_the_embargo_zone() -> None:
    """A cross-fold violation the per-fold gap check cannot see.

    Hand-built rather than produced by ``build_plan``, because ``build_plan`` cannot
    produce it — which is the point: the checker guards against a schedule assembled some
    other way, not against its own arithmetic.
    """
    base = plan(purge_bars=10, embargo_bars=100)
    first = Fold(
        index=0,
        train_start=0,
        train_end=500,
        test_start=600,
        test_end=800,
        purged_bars=10,
        embargoed_bars=100,
    )
    # The second fold's own gap is a healthy 100 bars, so the per-fold check passes...
    second = Fold(
        index=1,
        train_start=0,
        train_end=900,
        test_start=1000,
        test_end=1200,
        purged_bars=10,
        embargoed_bars=100,
    )
    # ...but bars 800-900 are the first fold's embargo zone, and this trains on them.
    with pytest.raises(BacktestError, match="embargo zone"):
        assert_no_leakage(replace(base, folds=(first, second)))


def test_a_schedule_from_build_plan_never_trips_the_cross_fold_check() -> None:
    """The arithmetic and the checker must agree, for every scheme and every gap."""
    for scheme in SplitScheme:
        for purge, embargo in ((0, 0), (50, 0), (0, 50), (30, 90), (90, 30)):
            assert_no_leakage(
                plan(scheme=scheme, purge_bars=purge, embargo_bars=embargo)
            )
