"""Stop management after entry: break-even and trailing, and never looser.

A protective stop placed at entry answers one question — how much can this trade lose —
and then goes stale. Two rules move it, and both are pure arithmetic on facts the bar
already carries, so the paper engine and the 24/7 session apply them identically and the
evidence one produces describes the game the other plays:

* **Break-even.** Once the trade has moved ``breakeven_after_r`` multiples of its initial
  risk in its favour, the stop moves to the entry price plus a buffer that covers the
  round-trip fees. A trade that was a winner should not be allowed to become a loser.
* **Trailing.** The stop follows the best price seen since entry at a distance of
  ``trail_atr_multiple`` average true ranges. Volatility sets the distance, so the stop
  is tight in a quiet market and gives room in a violent one.

Three invariants, enforced here rather than trusted to callers:

* A stop only ever **tightens**. A long's stop never moves down; a short's never moves up.
* A stop stays a **stop**: below the last close for a long, above it for a short. A stop
  the wrong side of the market is a market order with a misleading name.
* A move too small to matter is **not a move**. Replacing a resting order costs a cancel
  and a submit; below ``min_move_pct`` the old stop stands.

Both rules are off when their setting is zero, which leaves the initial stop exactly as
the risk engine approved it.
"""

from __future__ import annotations

from dataclasses import dataclass

from tia.domain.enums import Direction

#: A candidate stop that improves on the current one by less than this fraction of the
#: price is ignored: not worth a cancel-and-replace on the venue.
MIN_STOP_MOVE_PCT = 0.02

#: How far inside the last close a stop is kept, as a fraction of price, so that it is
#: a stop and not an immediate market order.
STOP_INSIDE_CLOSE_PCT = 0.01


@dataclass(frozen=True)
class StopUpdate:
    """A tighter stop and why. ``kind`` is what the exit will be called if it fills."""

    stop_price: float
    kind: str  # "break-even" | "trailing"
    reason: str


def r_multiple(*, direction: Direction, entry_price: float, initial_stop: float, price: float) -> float:
    """How far the trade has moved in its favour, in multiples of its initial risk."""
    risk = abs(entry_price - initial_stop)
    if risk <= 0 or entry_price <= 0:
        return 0.0
    favourable = (price - entry_price) if direction is Direction.LONG else (entry_price - price)
    return favourable / risk


def tighten_stop(
    *,
    direction: Direction,
    entry_price: float,
    initial_stop: float,
    current_stop: float,
    best_price: float,
    last_close: float,
    atr: float,
    breakeven_after_r: float,
    trail_atr_multiple: float,
    fee_buffer_bps: float = 0.0,
) -> StopUpdate | None:
    """The tightest stop the rules support, or ``None`` when the current one stands.

    ``best_price`` is the most favourable price seen since entry (highest high for a
    long, lowest low for a short); ``atr`` is in price units. Either rule switched off
    (zero) contributes no candidate.
    """
    if direction not in (Direction.LONG, Direction.SHORT):
        return None
    if entry_price <= 0 or current_stop <= 0 or last_close <= 0:
        return None
    long = direction is Direction.LONG

    candidates: list[tuple[float, str, str]] = []

    if breakeven_after_r > 0 and initial_stop > 0:
        reached = r_multiple(
            direction=direction, entry_price=entry_price, initial_stop=initial_stop, price=best_price
        )
        if reached >= breakeven_after_r:
            buffer = entry_price * fee_buffer_bps / 10_000.0
            level = entry_price + buffer if long else entry_price - buffer
            candidates.append(
                (
                    level,
                    "break-even",
                    f"moved {reached:.1f}R in favour; stop to entry "
                    f"{'+' if long else '-'} fees",
                )
            )

    if trail_atr_multiple > 0 and atr > 0 and best_price > 0:
        distance = trail_atr_multiple * atr
        level = best_price - distance if long else best_price + distance
        candidates.append(
            (
                level,
                "trailing",
                f"{trail_atr_multiple:g} ATR ({distance:.2f}) behind the best price {best_price:.2f}",
            )
        )

    if not candidates:
        return None

    # The tightest candidate: highest for a long, lowest for a short.
    level, kind, reason = max(candidates, key=lambda c: c[0]) if long else min(
        candidates, key=lambda c: c[0]
    )

    # A stop must stay a stop: inside the last close, never through it.
    inside = last_close * STOP_INSIDE_CLOSE_PCT / 100.0
    level = min(level, last_close - inside) if long else max(level, last_close + inside)

    # Only ever tighter, and only by enough to be worth a replacement.
    improvement = (level - current_stop) if long else (current_stop - level)
    if improvement <= entry_price * MIN_STOP_MOVE_PCT / 100.0:
        return None

    return StopUpdate(stop_price=level, kind=kind, reason=reason)


__all__ = ["MIN_STOP_MOVE_PCT", "STOP_INSIDE_CLOSE_PCT", "StopUpdate", "r_multiple", "tighten_stop"]
