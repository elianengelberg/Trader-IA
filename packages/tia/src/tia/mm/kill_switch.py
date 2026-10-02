"""The market maker's own kill switch: below the global one, never above it.

It can be engaged by the operator or by any condition the live maker watches (stale data,
a dropped stream, a reconciliation that failed, an order in an unknown state, an expired
activation, a breached limit, a venue reject it did not expect, too many API errors, a
system declared unsafe). Engaged, it does two things and nothing else: it reports itself to
the global safety gate as a reason the system is unsafe — so the engine stops quoting
through the path it already has — and, at the ``cancel_open`` severity, it asks the
execution to cancel every resting order.

Two kinds of engagement. **Sticky** ones stay until a named person releases them (or the
service is stopped and started again, which is a person too). **Transient** ones name a
condition and clear themselves when that condition clears — a stream that reconnects, data
that is fresh again — while remaining in the history with their timestamps.

It never touches the session's ``RiskEngine``, the global kill switch, or the gate.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class KillSeverity(StrEnum):
    #: No new quotes; resting orders are left to their own TTL.
    NO_NEW_QUOTES = "no_new_quotes"
    #: No new quotes and every resting order is cancelled now.
    CANCEL_OPEN = "cancel_open"


_RANK = {KillSeverity.NO_NEW_QUOTES: 1, KillSeverity.CANCEL_OPEN: 2}


@dataclass(frozen=True)
class KillEvent:
    t_ms: int
    action: str  # engage | release | clear
    trigger: str
    reason: str
    severity: str
    sticky: bool
    actor: str
    cancelled: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MMKillSwitch:
    def __init__(
        self,
        *,
        now_ms: Callable[[], int],
        cancel_open: Callable[[int, str], int] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        keep: int = 200,
    ) -> None:
        self._now_ms = now_ms
        self._cancel_open = cancel_open
        self._on_event = on_event
        self.history: deque[KillEvent] = deque(maxlen=keep)
        self.sticky = False
        self.trigger = ""
        self.reason = ""
        self.severity: KillSeverity | None = None
        self.actor = ""
        self.engaged_at_ms: int | None = None
        self._transient: dict[str, str] = {}
        self.engagements = 0
        self.cancelled_total = 0

    # ------------------------------------------------------------------ state

    @property
    def engaged(self) -> bool:
        return self.sticky or bool(self._transient)

    def status(self) -> str:
        """Empty when quoting may proceed; otherwise the reason, for the safety gate."""
        if self.sticky:
            return f"{self.trigger}: {self.reason}"
        if self._transient:
            trigger, reason = next(iter(self._transient.items()))
            return f"{trigger}: {reason}"
        return ""

    # ------------------------------------------------------------------ actions

    def engage(
        self,
        trigger: str,
        reason: str,
        *,
        severity: KillSeverity = KillSeverity.CANCEL_OPEN,
        sticky: bool = True,
        actor: str = "system",
    ) -> KillEvent:
        t = self._now_ms()
        cancelled = 0
        if severity is KillSeverity.CANCEL_OPEN and self._cancel_open is not None:
            cancelled = int(self._cancel_open(t, f"kill switch ({trigger}): {reason}"))
            self.cancelled_total += cancelled
        if sticky:
            if not self.sticky:
                # The first cause is the one the operator needs to see; later ones are
                # in the history and can only raise the severity.
                self.engaged_at_ms = t
                self.trigger, self.reason, self.actor = trigger, reason, actor
            self.sticky = True
            if self.severity is None or _RANK[severity] > _RANK[self.severity]:
                self.severity = severity
        else:
            if not self.engaged:
                self.engaged_at_ms = t
            self._transient[trigger] = reason
            if self.severity is None or _RANK[severity] > _RANK[self.severity]:
                self.severity = severity
        self.engagements += 1
        return self._record(KillEvent(t, "engage", trigger, reason, severity.value, sticky, actor, cancelled))

    def clear(self, trigger: str) -> bool:
        """A transient condition no longer holds. Sticky engagements are untouched."""
        reason = self._transient.pop(trigger, None)
        if reason is None:
            return False
        if not self.engaged:
            self.severity = None
            self.engaged_at_ms = None
        self._record(KillEvent(self._now_ms(), "clear", trigger, reason, "", False, "system"))
        return True

    def release(self, *, approved_by: str) -> KillEvent:
        """Releases the sticky engagement only, and only for a named person."""
        if not approved_by.strip():
            raise ValueError("releasing the market maker kill switch requires naming who approved it")
        event = KillEvent(self._now_ms(), "release", self.trigger, self.reason, self.severity.value if self.severity else "", True, approved_by)
        self.sticky = False
        self.trigger = self.reason = self.actor = ""
        if not self.engaged:
            self.severity = None
            self.engaged_at_ms = None
        return self._record(event)

    def _record(self, event: KillEvent) -> KillEvent:
        self.history.append(event)
        if self._on_event is not None:
            self._on_event({"kind": "kill_switch", "t": event.t_ms, **event.as_dict()})
        return event

    # ------------------------------------------------------------------ reading

    def as_dict(self) -> dict[str, Any]:
        return {
            "engaged": self.engaged,
            "sticky": self.sticky,
            "trigger": self.trigger if self.sticky else (next(iter(self._transient), "") if self._transient else ""),
            "reason": self.status(),
            "severity": self.severity.value if self.severity else None,
            "actor": self.actor,
            "engaged_at_ms": self.engaged_at_ms,
            "transient": dict(self._transient),
            "engagements": self.engagements,
            "cancelled_total": self.cancelled_total,
            "history": [e.as_dict() for e in list(self.history)[-20:]],
            "note": "below the global safety gate: it can only add a reason to stop, never remove one",
        }


__all__ = ["KillEvent", "KillSeverity", "MMKillSwitch"]
