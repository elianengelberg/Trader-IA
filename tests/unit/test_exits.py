"""Stop management: tighter only, a stop stays a stop, and off means off."""

from __future__ import annotations

import pytest

from tia.domain.enums import Direction
from tia.execution.exits import MIN_STOP_MOVE_PCT, r_multiple, tighten_stop

LONG = {"direction": Direction.LONG, "entry_price": 100.0, "initial_stop": 98.0}
SHORT = {"direction": Direction.SHORT, "entry_price": 100.0, "initial_stop": 102.0}


def test_r_multiple_measures_favourable_excursion_in_units_of_initial_risk() -> None:
    assert r_multiple(**LONG, price=102.0) == pytest.approx(1.0)
    assert r_multiple(**LONG, price=99.0) == pytest.approx(-0.5)
    assert r_multiple(**SHORT, price=96.0) == pytest.approx(2.0)
    assert r_multiple(direction=Direction.LONG, entry_price=100.0, initial_stop=100.0, price=105.0) == 0.0


def test_both_rules_off_leave_the_initial_stop_alone() -> None:
    assert (
        tighten_stop(
            **LONG, current_stop=98.0, best_price=110.0, last_close=110.0, atr=1.0,
            breakeven_after_r=0.0, trail_atr_multiple=0.0,
        )
        is None
    )


def test_break_even_moves_the_stop_to_entry_plus_fees_once_one_r_is_reached() -> None:
    update = tighten_stop(
        **LONG, current_stop=98.0, best_price=102.0, last_close=101.5, atr=0.0,
        breakeven_after_r=1.0, trail_atr_multiple=0.0, fee_buffer_bps=20.0,
    )
    assert update is not None
    assert update.kind == "break-even"
    assert update.stop_price == pytest.approx(100.2)  # entry + 20 bps of fees
    # Not yet: 0.9R is not 1R.
    assert (
        tighten_stop(
            **LONG, current_stop=98.0, best_price=101.8, last_close=101.5, atr=0.0,
            breakeven_after_r=1.0, trail_atr_multiple=0.0,
        )
        is None
    )


def test_the_trailing_stop_follows_the_best_price_at_an_atr_distance() -> None:
    update = tighten_stop(
        **LONG, current_stop=98.0, best_price=106.0, last_close=105.0, atr=1.5,
        breakeven_after_r=0.0, trail_atr_multiple=2.0,
    )
    assert update is not None
    assert update.kind == "trailing"
    assert update.stop_price == pytest.approx(103.0)  # 106 - 2 x 1.5

    short = tighten_stop(
        **SHORT, current_stop=102.0, best_price=94.0, last_close=95.0, atr=1.5,
        breakeven_after_r=0.0, trail_atr_multiple=2.0,
    )
    assert short is not None and short.stop_price == pytest.approx(97.0)


def test_a_stop_only_ever_tightens() -> None:
    """The best price is behind us and the trail would sit BELOW the current stop."""
    assert (
        tighten_stop(
            **LONG, current_stop=104.0, best_price=106.0, last_close=105.0, atr=2.0,
            breakeven_after_r=1.0, trail_atr_multiple=2.0,
        )
        is None  # trail says 102, break-even says 100: both looser than 104
    )
    assert (
        tighten_stop(
            **SHORT, current_stop=96.0, best_price=94.0, last_close=95.0, atr=2.0,
            breakeven_after_r=1.0, trail_atr_multiple=2.0,
        )
        is None
    )


def test_the_tightest_candidate_wins() -> None:
    update = tighten_stop(
        **LONG, current_stop=98.0, best_price=103.0, last_close=102.5, atr=0.5,
        breakeven_after_r=1.0, trail_atr_multiple=2.0,
    )
    assert update is not None
    assert update.kind == "trailing" and update.stop_price == pytest.approx(102.0)


def test_a_stop_stays_a_stop_never_through_the_last_close() -> None:
    """Price ran to 110 then fell to 100.5; a 2-ATR trail would sit above the close."""
    update = tighten_stop(
        **LONG, current_stop=98.0, best_price=110.0, last_close=100.5, atr=0.5,
        breakeven_after_r=0.0, trail_atr_multiple=2.0,
    )
    assert update is not None
    assert update.stop_price < 100.5
    assert update.stop_price == pytest.approx(100.5 * (1 - 0.0001))


def test_a_move_too_small_to_matter_is_not_a_move() -> None:
    tiny = 100.0 * MIN_STOP_MOVE_PCT / 100.0 / 2
    assert (
        tighten_stop(
            **LONG, current_stop=103.0, best_price=105.0 + tiny, last_close=105.0, atr=1.0,
            breakeven_after_r=0.0, trail_atr_multiple=2.0,
        )
        is None
    )


def test_garbage_inputs_change_nothing() -> None:
    assert tighten_stop(direction=Direction.NO_TRADE, entry_price=1, initial_stop=1, current_stop=1,
                        best_price=1, last_close=1, atr=1, breakeven_after_r=1, trail_atr_multiple=1) is None
    assert tighten_stop(**LONG, current_stop=0.0, best_price=105, last_close=105, atr=1,
                        breakeven_after_r=1, trail_atr_multiple=1) is None
