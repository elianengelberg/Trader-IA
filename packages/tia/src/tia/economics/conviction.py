"""Conviction sizing: the money follows the evidence, and only ever downward.

The risk engine sizes every trade so that its stop costs the same fraction of equity.
That is the ceiling. This module decides how much of that ceiling a trade deserves, from
the one thing the system is allowed to believe — the measured edge and how sure it is:

* An exact bucket whose mean is three standard errors from zero is as sure as this
  system gets, and takes the full approved size.
* A bucket whose mean barely clears its own noise takes the floor fraction.
* A **pooled** estimate (the exact band was thin; the regime's other bands stood in) is a
  coarser claim and is capped, whatever its statistics say.
* An **exploration** trade exists to buy a lesson, and a lesson should be cheap.

The multiplier is never above one. The learning layer can shrink a position; it cannot
grow one past what the risk engine approved — the same asymmetry as every other learned
influence in this system.
"""

from __future__ import annotations

from dataclasses import dataclass

from tia.economics.expected_value import EdgeEstimate

#: A t-statistic at or below this earns the floor fraction; at or above ``T_FULL`` the
#: full approved size. Linear between. One SE is "barely not noise"; three is "sure".
T_FLOOR = 1.0
T_FULL = 3.0


@dataclass(frozen=True)
class SizeFraction:
    fraction: float
    reason: str

    def as_dict(self) -> dict[str, float | str]:
        return {"fraction": round(self.fraction, 4), "reason": self.reason}


def conviction_fraction(
    estimate: EdgeEstimate | None,
    *,
    exploring: bool,
    min_fraction: float,
    exploration_fraction: float,
    pooled_cap: float,
) -> SizeFraction:
    """Fraction of the risk-approved size this trade deserves, in ``(0, 1]``.

    Pure. ``min_fraction`` and ``pooled_cap`` are clamped into ``(0, 1]`` so a
    misconfiguration cannot produce a size above the approved one or a zero order.
    """
    floor = min(1.0, max(0.05, min_fraction))
    cap = min(1.0, max(floor, pooled_cap))

    if exploring:
        fraction = min(1.0, max(0.05, exploration_fraction))
        return SizeFraction(fraction, f"exploration trade: {fraction:.0%} of approved size")

    if estimate is None:
        return SizeFraction(floor, f"no estimate to size on: floor {floor:.0%}")

    se = estimate.standard_error_bps
    t = estimate.mean_bps / se if se > 0 else T_FULL
    if t <= T_FLOOR:
        fraction = floor
    elif t >= T_FULL:
        fraction = 1.0
    else:
        fraction = floor + (1.0 - floor) * (t - T_FLOOR) / (T_FULL - T_FLOOR)

    reason = f"t = {t:.1f} over {estimate.samples} trades"
    if estimate.is_pooled and fraction > cap:
        fraction = cap
        reason += f"; pooled evidence capped at {cap:.0%}"
    elif estimate.is_pooled:
        reason += " (pooled)"

    return SizeFraction(min(1.0, fraction), reason)


__all__ = ["T_FLOOR", "T_FULL", "SizeFraction", "conviction_fraction"]
