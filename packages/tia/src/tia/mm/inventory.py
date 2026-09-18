"""Inventory: the position the maker is carrying, and what it does to the quotes.

A maker that keeps buying accumulates a long it did not choose; the remedy is to make
the next buy less attractive and the next sell more attractive, and past a point to
stop buying altogether. This module turns inventory into:

* ``inventory_ratio`` — inventory over its limit, clamped to [-1, 1];
* ``inventory_pressure`` — ratio times its magnitude, so pressure grows faster near
  the limit;
* ``inventory_adjustment_bps`` — a shift applied to **both** quotes: negative when
  long (lower bid, lower ask: buys less likely, sells more likely), positive when
  short;
* size factors per side — the same-side size shrinks to zero at the limit.

The limit here is the maker's own; the risk controller's limits sit above it and can
only be tighter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InventoryConfig:
    max_inventory_btc: float = 0.05
    #: Quote shift, in bps, at full inventory ratio.
    skew_bps_at_limit: float = 3.0
    #: Above this ratio the same-side size shrinks linearly, reaching zero at 1.0.
    reduce_size_from: float = 0.6


@dataclass(frozen=True)
class InventoryState:
    inventory_btc: float
    inventory_limit_btc: float
    inventory_ratio: float
    inventory_pressure: float
    inventory_adjustment_bps: float
    bid_size_factor: float
    ask_size_factor: float
    over_limit: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class InventoryManager:
    def __init__(self, config: InventoryConfig | None = None) -> None:
        self.config = config or InventoryConfig()

    def assess(self, inventory_btc: float) -> InventoryState:
        cfg = self.config
        limit = cfg.max_inventory_btc
        raw_ratio = inventory_btc / limit if limit > 0 else 0.0
        ratio = max(-1.0, min(1.0, raw_ratio))
        pressure = ratio * abs(ratio)
        adjustment = -pressure * cfg.skew_bps_at_limit
        over = abs(raw_ratio) > 1.0

        def same_side_factor(r: float) -> float:
            # r is the ratio on the side that would add to the position (positive).
            if r <= cfg.reduce_size_from:
                return 1.0
            span = 1.0 - cfg.reduce_size_from
            return max(0.0, 1.0 - (r - cfg.reduce_size_from) / span) if span > 0 else 0.0

        bid_factor = same_side_factor(ratio) if ratio > 0 else 1.0
        ask_factor = same_side_factor(-ratio) if ratio < 0 else 1.0
        if over:
            reason = f"inventory {inventory_btc:+.5f} BTC beyond the limit {limit:.5f}: only reducing quotes"
        elif ratio > cfg.reduce_size_from:
            reason = f"long {ratio:.0%} of limit: bid size x{bid_factor:.2f}, quotes shifted {adjustment:+.2f} bps"
        elif ratio < -cfg.reduce_size_from:
            reason = f"short {-ratio:.0%} of limit: ask size x{ask_factor:.2f}, quotes shifted {adjustment:+.2f} bps"
        elif abs(ratio) > 1e-12:
            reason = f"inventory {ratio:+.0%} of limit: quotes shifted {adjustment:+.2f} bps"
        else:
            reason = "flat"
        return InventoryState(
            inventory_btc=inventory_btc,
            inventory_limit_btc=limit,
            inventory_ratio=ratio,
            inventory_pressure=pressure,
            inventory_adjustment_bps=adjustment,
            bid_size_factor=bid_factor,
            ask_size_factor=ask_factor,
            over_limit=over,
            reason=reason,
        )


__all__ = ["InventoryConfig", "InventoryManager", "InventoryState"]
