"""The global trading safety gate: read-only, and above everything the maker does.

It reads three things and writes nothing: the state of the session's existing
``RiskEngine`` (kill switch, safe mode, halted, degraded), whether the market data is
usable, and whether anything else declares the system unsafe. From those it reports one
of ``SAFE``, ``SAFE_MODE``, ``HALTED``, ``DATA_INVALID`` or ``SYSTEM_UNSAFE``.

When the state is not ``SAFE`` the market maker cancels its paper quotes, generates no
new ones, records the reason and waits. There is no method here that could resume,
relax or reset anything: the gate holds callables that *return* state, never the
engines themselves, so the strongest thing this module can do is say no.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SafetyState(StrEnum):
    SAFE = "safe"
    SAFE_MODE = "safe_mode"
    HALTED = "halted"
    DATA_INVALID = "data_invalid"
    SYSTEM_UNSAFE = "system_unsafe"


@dataclass(frozen=True)
class SafetyStatus:
    state: SafetyState
    reason: str
    checked_at_ms: int
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def allows_quoting(self) -> bool:
        return self.state is SafetyState.SAFE

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state.value, "reason": self.reason, "checked_at_ms": self.checked_at_ms, "allows_quoting": self.allows_quoting, **self.details}


class GlobalTradingSafetyGate:
    """Reads state; never holds an engine; never changes anything."""

    def __init__(
        self,
        *,
        risk_state: Callable[[], Any | None],
        data_usable: Callable[[], tuple[bool, str]],
        system_unsafe: Callable[[], str] | None = None,
    ) -> None:
        self._risk_state = risk_state
        self._data_usable = data_usable
        self._system_unsafe = system_unsafe or (lambda: "")
        self.last_status: SafetyStatus | None = None
        self.transitions = 0
        self.unsafe_since_ms: int | None = None

    def status(self, t_ms: int) -> SafetyStatus:
        # Data validity is judged first: nothing downstream may reason on bad data.
        usable, why = self._data_usable()
        if not usable:
            return self._note(SafetyStatus(SafetyState.DATA_INVALID, f"market data not usable: {why}", t_ms, {"data": why}))
        state = self._risk_state()
        mode = getattr(getattr(state, "mode", None), "value", None) if state is not None else None
        kill_reason = getattr(state, "kill_switch_reason", "") if state is not None else ""
        if mode == "halted":
            return self._note(SafetyStatus(SafetyState.HALTED, f"session risk engine halted: {kill_reason or 'kill switch'}", t_ms, {"mode": mode}))
        if mode == "safe_mode":
            return self._note(SafetyStatus(SafetyState.SAFE_MODE, f"session risk engine in safe mode: {kill_reason or 'breaker'}", t_ms, {"mode": mode}))
        if mode == "degraded":
            return self._note(SafetyStatus(SafetyState.SYSTEM_UNSAFE, "session risk engine degraded", t_ms, {"mode": mode}))
        unsafe = self._system_unsafe()
        if unsafe:
            return self._note(SafetyStatus(SafetyState.SYSTEM_UNSAFE, unsafe, t_ms, {"mode": mode}))
        return self._note(SafetyStatus(SafetyState.SAFE, "", t_ms, {"mode": mode}))

    def _note(self, status: SafetyStatus) -> SafetyStatus:
        if self.last_status is None or self.last_status.state is not status.state:
            self.transitions += 1
            self.unsafe_since_ms = None if status.allows_quoting else status.checked_at_ms
        self.last_status = status
        return status


__all__ = ["GlobalTradingSafetyGate", "SafetyState", "SafetyStatus"]
