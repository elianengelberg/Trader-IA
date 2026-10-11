"""Chronological partitions: no overlap, gaps where promised, warm-up from the past only."""

from __future__ import annotations

import pytest

from tia.backtest.partitions import partitions, window_bounds


def test_partitions_are_ordered_disjoint_and_separated_by_the_gap() -> None:
    parts = partitions(1000, research=0.5, validation=0.3, purge=20, embargo=30)
    r, v, h = parts.research, parts.validation, parts.holdout
    assert r == (0, 500)
    assert v[0] == r[1] + 50 and v == (550, 850)
    assert h[0] == v[1] + 50 and h == (900, 1000)
    assert r[1] <= v[0] and v[1] <= h[0], "no overlap, ever"
    assert parts.gap == 50
    assert dict(parts.items()) == parts.as_dict()
    assert parts["validation"] == v


def test_no_bar_of_validation_or_holdout_is_reachable_from_research_and_vice_versa() -> None:
    parts = partitions(2000, research=0.6, validation=0.2, purge=10, embargo=10)
    research = set(range(*parts.research))
    validation = set(range(*parts.validation))
    holdout = set(range(*parts.holdout))
    assert research.isdisjoint(validation) and validation.isdisjoint(holdout) and research.isdisjoint(holdout)
    assert max(research) < min(validation) < max(validation) < min(holdout)


def test_a_short_series_degenerates_to_empty_later_partitions_never_to_overlap() -> None:
    parts = partitions(100, research=0.5, validation=0.3, purge=40, embargo=40)
    assert parts.research == (0, 50)
    assert parts.validation == (100, 100)
    assert parts.holdout == (100, 100)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"research": 0.0, "validation": 0.3},
        {"research": 0.5, "validation": 0.5},
        {"research": 0.7, "validation": 0.4},
    ],
)
def test_invalid_fractions_are_refused(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        partitions(1000, purge=0, embargo=0, **kwargs)


def test_negative_gaps_and_empty_series_are_refused() -> None:
    with pytest.raises(ValueError):
        partitions(1000, research=0.5, validation=0.3, purge=-1, embargo=0)
    with pytest.raises(ValueError):
        partitions(0, research=0.5, validation=0.3, purge=0, embargo=0)


def test_the_window_reaches_back_only_into_the_past_and_never_decides_in_the_warm_up() -> None:
    # Validation starts at 550 with a 300-bar lookback: the window starts at 250 and the
    # first 300 bars of it are warm-up — exactly the bars before the partition.
    assert window_bounds(550, 850, lookback=300) == (250, 300)
    # Research starts at 0: nothing before it; the warm-up eats the partition's first 120.
    assert window_bounds(0, 500, lookback=300) == (0, 120)
    # Little history: warm-up is at least the minimum, never invented.
    assert window_bounds(50, 500, lookback=300) == (0, 120)
    with pytest.raises(ValueError):
        window_bounds(10, 10, lookback=300)


def test_the_window_never_extends_past_the_cell_end() -> None:
    start, _ = window_bounds(550, 850, lookback=300)
    assert start < 850
