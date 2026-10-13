"""Quantization tolerates a float's rounding, never a lot's worth.

The 12-hour paper session of 2026-10-12 (run ``live_01M4RXRXKHE1HXJQDQTEYY0HC1``) opened a
short with two partial maker fills of 0.001932 and 0.002064 BTC. Their float sum is
``0.0039959999999999996``, not 0.003996. Every quantization rounded that *down* to
0.003995 lots-worth, so:

* the protective stop for the full position was refused as "not a whole multiple of the
  lot" and the leg ran unprotected;
* the exit closed 0.003995 and left ``9.999999999992654e-07`` BTC in the simulator;
* every later exit of that residue quantized to zero, was refused by the filters, and
  halted new orders for the rest of the session — and the deadline close with it.

These tests pin the exact production values. A quantity within a millionth of a lot of a
whole number of lots *is* that number of lots; anything further away still rounds down.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tia.core.money import STEP_FLOAT_TOLERANCE, quantize_down
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.filters import OrderFilterError, filters_for, validate_quantity

SYMBOL = "BTC-USD"
LOT = 1e-6
#: The two partial entry fills of the session's fourth trade, as the fills table holds them.
PARTIALS = (0.001932, 0.002064)
#: Their float sum, as the orders table and /api/live reported it.
ENTRY_SUM = 0.0039959999999999996
#: What the simulator held after the exit closed 0.003995 of it.
RESIDUE = 9.999999999992654e-07


def test_the_production_values_are_what_the_session_saw() -> None:
    assert sum(PARTIALS) == ENTRY_SUM and ENTRY_SUM != 0.003996
    residue = ENTRY_SUM - 0.003995
    assert residue == pytest.approx(RESIDUE, abs=1e-18)
    assert DEFAULT_UNIVERSE.get(SYMBOL).lot_size == LOT


def test_a_float_sum_of_whole_lots_quantizes_to_the_whole_lots_it_is() -> None:
    assert quantize_down(ENTRY_SUM, LOT) == Decimal("0.003996")
    assert filters_for(SYMBOL, DEFAULT_UNIVERSE).quantize(ENTRY_SUM) == 0.003996
    assert DEFAULT_UNIVERSE.get(SYMBOL).round_quantity(ENTRY_SUM) == 0.003996


def test_the_residue_a_float_left_behind_is_one_whole_lot_and_closable() -> None:
    filters = filters_for(SYMBOL, DEFAULT_UNIVERSE)
    assert quantize_down(RESIDUE, LOT) == Decimal("0.000001")
    assert filters.quantize(RESIDUE) == 1e-6
    assert DEFAULT_UNIVERSE.get(SYMBOL).round_quantity(RESIDUE) == 1e-6
    assert DEFAULT_UNIVERSE.get(SYMBOL).round_quantity(-RESIDUE) == -1e-6
    # A reduce-only order for it is legal: no notional minimum, one whole lot.
    validate_quantity(filters, RESIDUE, reference_price=83_560.83, reduce_only=True)


def test_the_full_position_is_a_legal_protective_stop() -> None:
    """The stop is sent with the position's own quantity; it was refused before."""
    validate_quantity(
        filters_for(SYMBOL, DEFAULT_UNIVERSE), ENTRY_SUM, reference_price=82_075.31, reduce_only=True,
    )


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (0.0039955, "0.003995"),       # half a lot short: still down, never nearest
        (0.0039959, "0.003995"),       # a tenth of a lot short: still down
        (0.003996000000000001, "0.003996"),
        (5e-07, "0"),                  # genuinely below one lot
    ],
)
def test_anything_further_than_a_float_from_a_whole_lot_still_rounds_down(quantity: float, expected: str) -> None:
    assert quantize_down(quantity, LOT) == Decimal(expected)


def test_genuine_dust_and_genuinely_unquantized_sizes_are_still_refused() -> None:
    filters = filters_for(SYMBOL, DEFAULT_UNIVERSE)
    with pytest.raises(OrderFilterError, match="not a whole multiple"):
        validate_quantity(filters, 5e-07, reference_price=80_000.0, reduce_only=True)
    with pytest.raises(OrderFilterError, match="not a whole multiple"):
        validate_quantity(filters, 0.0039955, reference_price=80_000.0, reduce_only=True)


def test_every_float_sum_of_two_whole_lot_partials_is_whole() -> None:
    """Whatever split the simulator draws, the position it adds up to is whole lots."""
    total = 3_996
    for first in range(1, total):
        a, b = first * LOT, round((total - first) * LOT, 6)
        assert quantize_down(a + b, LOT) == Decimal("0.003996"), (a, b)
        assert DEFAULT_UNIVERSE.get(SYMBOL).round_quantity(a + b) == 0.003996, (a, b)


def test_the_tolerance_is_a_float_s_rounding_not_a_lot_s_worth() -> None:
    assert Decimal(0) < STEP_FLOAT_TOLERANCE <= Decimal("1e-6")
