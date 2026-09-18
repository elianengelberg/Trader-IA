"""The market maker's own risk controller: limits on its $10,000 paper account that
can only ever be tightened, and that sit *below* the global safety gate.

It controls inventory, notional, quote size, daily loss, drawdown, quote frequency and
its own kill switch. It has no API to relax a global limit, no reference to the
session's ``RiskEngine``, and no input through which the gate's verdict could be
overridden: the engine that uses it consults the gate first and does not call this
controller when the gate says no.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MarketMakerRiskLimits:
    max_inventory_btc: float = 0.05
    max_notional_usd: float = 6_000.0
    max_quote_size_btc: float = 0.01
    max_daily_loss_usd: float = 100.0
    max_drawdown_pct: float = 3.0
    max_quotes_per_minute: int = 120
    min_quote_interval_ms: int = 250

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")

    def tightened(self, **changes: float | int) -> MarketMakerRiskLimits:
        """A new set of limits where every change is at least as strict. Anything looser raises."""
        for name, value in changes.items():
            current = getattr(self, name)
            if value > current:
                raise ValueError(f"{name}: {value} would loosen the current {current}; limits can only be tightened")
        return MarketMakerRiskLimits(**{**self.__dict__, **changes})

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class LedgerView:
    """What the controller needs to know about the account, as of now."""

    inventory_btc: float
    equity_usd: float
    day_start_equity_usd: float
    peak_equity_usd: float
    mark_price: float


@dataclass(frozen=True)
class RiskAllowance:
    allowed: bool
    reason: str
    max_size_btc: float
    #: Side permissions from inventory and notional, independent of the pacing checks:
    #: what the maker may *hold* resting even when it may not place anything new.
    bid_allowed: bool
    ask_allowed: bool
    kill_switch: bool
    checks: dict[str, bool] = field(default_factory=dict)
    #: True when the only failing checks are the quote rate and/or the minimum
    #: interval: nothing new may be placed, but a resting quote that still fits every
    #: other rule may be held. Never true when a hard rule (kill switch, loss,
    #: drawdown, inventory, notional) failed.
    hold_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MarketMakerRiskController:
    def __init__(self, limits: MarketMakerRiskLimits | None = None) -> None:
        self.limits = limits or MarketMakerRiskLimits()
        self.kill_switch = False
        self.kill_switch_reason = ""
        self._quote_times: deque[int] = deque()
        self.denials = 0

    # ------------------------------------------------------------------ its own switch

    def engage_kill_switch(self, reason: str) -> None:
        self.kill_switch = True
        self.kill_switch_reason = reason

    def release_kill_switch(self, *, approved_by: str) -> None:
        """Releases the maker's own switch only. It has no reach into the session's."""
        if not approved_by:
            raise ValueError("releasing the market maker kill switch requires naming who approved it")
        self.kill_switch = False
        self.kill_switch_reason = ""

    def tighten(self, **changes: float | int) -> None:
        self.limits = self.limits.tightened(**changes)

    # ------------------------------------------------------------------ verdict

    def record_quote(self, t_ms: int) -> None:
        self._quote_times.append(t_ms)
        while self._quote_times and self._quote_times[0] < t_ms - 60_000:
            self._quote_times.popleft()

    def allowance(self, view: LedgerView, t_ms: int) -> RiskAllowance:
        lim = self.limits
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        daily_loss = view.day_start_equity_usd - view.equity_usd
        checks["daily_loss"] = daily_loss < lim.max_daily_loss_usd
        if not checks["daily_loss"]:
            self.engage_kill_switch(f"daily loss {daily_loss:.2f} USD reached the limit {lim.max_daily_loss_usd:.2f}")
        drawdown_pct = (view.peak_equity_usd - view.equity_usd) / view.peak_equity_usd * 100.0 if view.peak_equity_usd > 0 else 0.0
        checks["drawdown"] = drawdown_pct < lim.max_drawdown_pct
        if not checks["drawdown"]:
            self.engage_kill_switch(f"drawdown {drawdown_pct:.2f}% reached the limit {lim.max_drawdown_pct:.2f}%")
        checks["kill_switch"] = not self.kill_switch
        if self.kill_switch:
            reasons.append(f"market maker kill switch: {self.kill_switch_reason}")

        while self._quote_times and self._quote_times[0] < t_ms - 60_000:
            self._quote_times.popleft()
        checks["quote_rate"] = len(self._quote_times) < lim.max_quotes_per_minute
        if not checks["quote_rate"]:
            reasons.append(f"{len(self._quote_times)} quotes in the last minute, limit {lim.max_quotes_per_minute}")
        checks["quote_interval"] = not self._quote_times or t_ms - self._quote_times[-1] >= lim.min_quote_interval_ms
        if not checks["quote_interval"]:
            reasons.append(f"last quote {t_ms - self._quote_times[-1]} ms ago, minimum {lim.min_quote_interval_ms}")

        inventory = view.inventory_btc
        notional = abs(inventory) * view.mark_price
        room_btc = max(0.0, lim.max_inventory_btc - abs(inventory))
        room_notional_btc = max(0.0, (lim.max_notional_usd - notional) / view.mark_price) if view.mark_price > 0 else 0.0
        adding_room = min(room_btc, room_notional_btc)
        checks["inventory"] = abs(inventory) < lim.max_inventory_btc
        checks["notional"] = notional < lim.max_notional_usd
        bid_allowed = ask_allowed = True
        if not (checks["inventory"] and checks["notional"]):
            # At or beyond a limit: only the side that reduces the position may quote.
            bid_allowed, ask_allowed = inventory < 0, inventory > 0
            reasons.append(f"inventory {inventory:+.5f} BTC / {notional:.0f} USD at a limit: reducing side only")
        max_size = min(lim.max_quote_size_btc, adding_room) if adding_room > 0 else lim.max_quote_size_btc

        hard_ok = checks["kill_switch"] and (bid_allowed or ask_allowed)
        pacing_ok = checks["quote_rate"] and checks["quote_interval"]
        allowed = hard_ok and pacing_ok
        if not allowed:
            self.denials += 1
        return RiskAllowance(
            allowed=allowed,
            reason="; ".join(reasons) if reasons else "within limits",
            max_size_btc=max_size,
            bid_allowed=bid_allowed and hard_ok,
            ask_allowed=ask_allowed and hard_ok,
            kill_switch=self.kill_switch,
            checks=checks,
            hold_only=hard_ok and not pacing_ok,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "limits": self.limits.as_dict(),
            "kill_switch": self.kill_switch,
            "kill_switch_reason": self.kill_switch_reason,
            "quotes_last_minute": len(self._quote_times),
            "denials": self.denials,
        }


__all__ = ["LedgerView", "MarketMakerRiskController", "MarketMakerRiskLimits", "RiskAllowance"]
