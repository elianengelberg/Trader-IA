"""Money arithmetic for the paths where money settles.

Floats are fine for a simulation and wrong for anything that produces an order a venue
will fill: `0.1 + 0.2` is the famous case, but the one that actually rejects orders is
quantization — a quantity that must be a multiple of `0.00001` and is instead
`0.00000999999999` because it passed through binary floating point on the way.

The policy, stated once:

* **Settlement-critical paths use Decimal.** The capital ledger's internal state and the
  live order builder's quantity/price rounding. These are the numbers that become real
  money movements or bound them.
* **The simulation and analytics layers stay float.** NumPy, the indicators, the backtest
  and the paper simulator are float end to end; converting them would create silent
  float↔Decimal boundaries at every interface, which produces exactly the class of bug
  this module exists to prevent. The schema docstring states the same limitation.
* **Conversion happens through str.** ``Decimal(str(x))`` — never ``Decimal(x)`` from a
  float, which faithfully preserves the float's binary error and defeats the point.
* **Rounding toward the venue is always DOWN for quantities.** Rounding a quantity up can
  exceed the balance or the intended risk; rounding down can only under-fill, and
  under-filling is the recoverable direction.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

#: Eight fractional digits — the finest granularity Binance uses for spot quantities and
#: the precision this system stores. One place, so it cannot drift between modules.
MONEY_PLACES = Decimal("0.00000001")

ZERO = Decimal("0")


def D(value: float | int | str | Decimal) -> Decimal:
    """Convert to Decimal through str, so a float's binary error is not preserved."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: float | int | str | Decimal) -> Decimal:
    """A monetary amount at the system's standard precision, banker's rounding."""
    return D(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)


def quantize_down(value: float | str | Decimal, step: float | str | Decimal) -> Decimal:
    """Round ``value`` down to a multiple of ``step``.

    This is how a desired quantity becomes a venue-legal one. Down, never nearest: the
    nearest multiple can be *above* the desired quantity, and an order for more than was
    sized is a risk-limit violation manufactured by rounding.
    """
    step_d = D(step)
    if step_d <= 0:
        raise ValueError("step must be positive")
    return (D(value) / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d


def format_venue_decimal(value: float | str | Decimal) -> str:
    """Render for a venue API: plain notation, no exponent, no trailing zeros.

    ``1e-05`` in a quantity field is rejected with a message that does not say why.
    """
    text = format(D(value), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def meets_min_notional(
    quantity: float | Decimal, price: float | Decimal, minimum: float | Decimal
) -> bool:
    """Whether an order clears the venue's minimum notional, computed in Decimal."""
    return D(quantity) * D(price) >= D(minimum)


__all__ = [
    "MONEY_PLACES",
    "ZERO",
    "D",
    "format_venue_decimal",
    "meets_min_notional",
    "money",
    "quantize_down",
]
