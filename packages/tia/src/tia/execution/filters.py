"""Order filters: the one place that decides whether a quantity is venue-legal.

Two sources, one rule set. When the venue's own filters are loaded (a live session reads
``exchangeInfo``), ``step_size`` / ``min_qty`` / ``min_notional`` / ``tick_size`` come from
there. When they are not — paper-live, the scenario engine, the backtester — the
instrument's own ``lot_size`` / ``tick_size`` / ``min_notional`` in the universe are the
rule, stated explicitly and never invented from a venue that was not asked.

The checks, in order:

1. the instrument must be known;
2. the quantity must be at least one lot and a whole number of lots (quantization is
   always *down*, so a quantity that is not whole is a quantity nobody quantized);
3. an order that **opens or adds** exposure must clear the minimum notional at the price
   it will be judged at — the limit price for a resting order, the reference price the
   caller supplies for a market order. With no reference price the check cannot be made,
   and an entry that cannot be checked is refused rather than assumed.

Orders that only **reduce** a position (``reduce_only``: exits, protective stops, flattens)
are exempt from the notional minimum on purpose: a position must always be closable, and
the dust a partial exit leaves is the venue's problem to accept, not a reason to stay in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from tia.core.errors import OrderRejectedError
from tia.core.money import STEP_FLOAT_TOLERANCE, D, meets_min_notional, quantize_down
from tia.domain.instruments import Instrument, InstrumentUniverse


class OrderFilterError(OrderRejectedError, ValueError):
    """An intent that no venue — simulated or real — would accept. Deterministic.

    Also a ``ValueError``: that is what callers of the intent builder have always caught."""

    code = "ORDER_FILTER_REJECTED"


@dataclass(frozen=True)
class InstrumentFilters:
    """The rules one symbol is judged by, with where they came from."""

    symbol: str
    step_size: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    tick_size: Decimal
    source: str

    @classmethod
    def from_instrument(cls, instrument: Instrument) -> InstrumentFilters:
        step = D(repr(instrument.lot_size))
        return cls(
            symbol=instrument.symbol,
            step_size=step,
            min_quantity=step,
            min_notional=D(repr(instrument.min_notional)),
            tick_size=D(repr(instrument.tick_size)),
            source="instrument universe (local rule; no venue filters loaded)",
        )

    @classmethod
    def from_venue(cls, symbol: str, venue: dict[str, Any], fallback: Instrument | None) -> InstrumentFilters:
        """Venue filters where present, the instrument's own values for anything absent."""
        base = cls.from_instrument(fallback) if fallback is not None else None
        step = venue.get("step_size")
        min_qty = venue.get("min_qty") or venue.get("min_quantity")
        min_notional = venue.get("min_notional")
        tick = venue.get("tick_size")
        return cls(
            symbol=symbol,
            step_size=D(str(step)) if step else (base.step_size if base else D("1e-8")),
            min_quantity=D(str(min_qty)) if min_qty else (D(str(step)) if step else (base.min_quantity if base else D("1e-8"))),
            min_notional=D(str(min_notional)) if min_notional else (base.min_notional if base else D(0)),
            tick_size=D(str(tick)) if tick else (base.tick_size if base else D("0.01")),
            source="venue filters" + ("" if base is None else " over the instrument universe"),
        )

    def quantize(self, quantity: float) -> float:
        """Down to a whole number of lots. The only rounding direction that cannot exceed
        a risk-approved size."""
        return float(quantize_down(quantity, self.step_size))

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "step_size": str(self.step_size),
            "min_quantity": str(self.min_quantity),
            "min_notional": str(self.min_notional),
            "tick_size": str(self.tick_size),
            "source": self.source,
        }


def filters_for(
    symbol: str,
    universe: InstrumentUniverse,
    venue: dict[str, Any] | None = None,
) -> InstrumentFilters:
    """The filters for ``symbol``: venue values when loaded, else the instrument's own.

    Raises :class:`OrderFilterError` for a symbol the universe does not know and the
    venue did not describe — an order for it cannot be judged, so it cannot be sent.
    """
    instrument = universe.get(symbol)
    if venue:
        return InstrumentFilters.from_venue(symbol, venue, instrument)
    if instrument is None:
        raise OrderFilterError(f"unknown instrument {symbol!r}: no filters to judge it by")
    return InstrumentFilters.from_instrument(instrument)


def validate_quantity(
    filters: InstrumentFilters,
    quantity: float,
    *,
    reference_price: float | None,
    reduce_only: bool,
    notional_required: bool = True,
) -> None:
    """Raise :class:`OrderFilterError` unless ``quantity`` is venue-legal under ``filters``.

    ``reference_price`` is what the notional is judged at; ``None`` means the caller has
    no price, which refuses an entry (``notional_required``, the intent builder's stance)
    or skips the notional check (the simulator's, before it has seen a bar: the intent
    builder already judged it). Irrelevant to a reduce-only order either way.
    """
    if quantity <= 0:
        raise OrderFilterError(f"{filters.symbol}: quantity {quantity} is not positive")
    q = D(repr(quantity))
    whole = quantize_down(q, filters.step_size)
    # A quantity that is not a whole number of lots was never quantized by anyone. The
    # tolerance is a float's rounding, not a lot's worth — the same one quantization uses.
    if abs(q - whole) > filters.step_size * STEP_FLOAT_TOLERANCE:
        raise OrderFilterError(
            f"{filters.symbol}: quantity {quantity} is not a whole multiple of the lot "
            f"step {filters.step_size} ({filters.source})"
        )
    if whole < filters.min_quantity:
        raise OrderFilterError(
            f"{filters.symbol}: quantity {quantity} is below the minimum {filters.min_quantity} "
            f"({filters.source})"
        )
    if reduce_only or filters.min_notional <= 0:
        return
    if (reference_price is None or reference_price <= 0) and not notional_required:
        return
    if reference_price is None or reference_price <= 0:
        raise OrderFilterError(
            f"{filters.symbol}: an entry of {quantity} cannot be checked against the minimum "
            f"notional {filters.min_notional} without a reference price"
        )
    if not meets_min_notional(whole, D(repr(reference_price)), filters.min_notional):
        notional = whole * D(repr(reference_price))
        raise OrderFilterError(
            f"{filters.symbol}: notional {notional:.4f} ({quantity} @ {reference_price}) is below "
            f"the minimum {filters.min_notional} ({filters.source})"
        )


def venue_filters_from_exchange_info(
    payload: dict[str, Any], *, venue_symbol: str, required_order_types: tuple[str, ...] = ("STOP_LOSS",),
) -> dict[str, Any]:
    """The venue grid of ``venue_symbol`` from an ``exchangeInfo`` answer, in the keys a live
    session's ``symbol_filters`` uses (D21, mission v3). Raises :class:`ValueError` for an
    answer that does not describe a tradable symbol completely: no symbol row, a status other
    than TRADING, a missing PRICE_FILTER / LOT_SIZE / notional filter, a non-positive grid, or
    an order type the session needs (its protective stop is a ``STOP_LOSS``) that the venue
    does not list. The values are kept as the venue's strings, so nothing is lost to a float.

    Field names as documented (developers.binance.com, Spot API "Filters", read 2026-10-26);
    REQUIRES VALIDATION against the venue itself."""
    rows = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("exchange information carries no symbols")
    row = next((r for r in rows if isinstance(r, dict) and str(r.get("symbol", "")).upper() == venue_symbol.upper()), None)
    if row is None:
        raise ValueError(f"exchange information does not describe {venue_symbol}")
    status = str(row.get("status", "")).upper()
    if status != "TRADING":
        raise ValueError(f"{venue_symbol} is not trading at the venue: status {status or 'missing'}")
    order_types = tuple(str(x).upper() for x in (row.get("orderTypes") or ()))
    missing = [t for t in required_order_types if t not in order_types]
    if missing:
        raise ValueError(f"{venue_symbol} does not list the order type(s) {missing} this session needs: {order_types}")
    by_type = {str(f.get("filterType", "")): f for f in (row.get("filters") or ()) if isinstance(f, dict)}
    try:
        price, lot = by_type["PRICE_FILTER"], by_type["LOT_SIZE"]
    except KeyError as exc:
        raise ValueError(f"exchange information for {venue_symbol} lacks the {exc.args[0]} filter") from exc
    notional = by_type.get("NOTIONAL") or by_type.get("MIN_NOTIONAL")
    if notional is None:
        raise ValueError(f"exchange information for {venue_symbol} lacks a notional filter")
    out = {
        "tick_size": str(price.get("tickSize", "")),
        "step_size": str(lot.get("stepSize", "")),
        "min_qty": str(lot.get("minQty", "")),
        "min_notional": str(notional.get("minNotional", "")),
        "source": "exchange_info",
        "order_types": list(order_types),
    }
    for key in ("tick_size", "step_size", "min_qty"):
        try:
            if D(out[key]) <= 0:
                raise ValueError
        except (ArithmeticError, ValueError) as exc:
            raise ValueError(f"exchange information for {venue_symbol} has an unusable {key}: {out[key]!r}") from exc
    return out


__all__ = ["InstrumentFilters", "OrderFilterError", "filters_for", "validate_quantity", "venue_filters_from_exchange_info"]
