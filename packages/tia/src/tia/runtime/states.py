"""The live runtime's state machine.

A live session's state is the single most safety-relevant fact about it, and the reason it
gets a real state machine rather than a string attribute is that the dangerous bugs here
are all *illegal transitions*: RUNNING reached without STARTING's validation, SAFE_MODE
exited without an operator, STOPPED going back to RUNNING with stale in-memory state. An
attribute permits all of those silently; this machine raises.

Two principles:

**The state never flatters.** ``RUNNING`` is set after the startup validation passed and
the loop's first cycle is scheduled — never before, and never because someone asked for it.
The API reports this machine's state verbatim; there is no code path that reports LIVE as
running while the loop is not.

**Recovery goes through a person.** ``SAFE_MODE`` and ``ERROR`` have no automatic exit.
Every path out of them requires an operator action with a name attached, because the system
entered them precisely when its own judgement came into doubt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from tia.core.clock import Clock
from tia.core.errors import InvalidStateTransitionError


class LiveState(StrEnum):
    """Every state a live session can be in. There is no other."""

    DISARMED = "disarmed"
    ARMING = "arming"
    ARMED = "armed"
    STARTING = "starting"
    RUNNING = "running"
    #: No new positions; open positions keep their protective management.
    HALT_NEW_ORDERS = "halt_new_orders"
    #: Only orders that reduce or close positions may be placed.
    CANCEL_ONLY = "cancel_only"
    PAUSING = "pausing"
    PAUSED = "paused"
    #: Something is unknown or wrong. Nothing trades; a named operator must resolve it.
    SAFE_MODE = "safe_mode"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

    @property
    def accepts_new_orders(self) -> bool:
        return self is LiveState.RUNNING

    @property
    def accepts_reducing_orders(self) -> bool:
        """Whether orders that only close or shrink a position are allowed."""
        return self in {
            LiveState.RUNNING,
            LiveState.HALT_NEW_ORDERS,
            LiveState.CANCEL_ONLY,
        }

    @property
    def is_terminal(self) -> bool:
        return self in {LiveState.STOPPED, LiveState.ERROR}


#: Legal transitions. Everything absent is illegal and raises. SAFE_MODE and ERROR are
#: reachable from anywhere (safety must never be blocked by bookkeeping), which is encoded
#: below rather than listed here per-state.
_TRANSITIONS: dict[LiveState, frozenset[LiveState]] = {
    LiveState.DISARMED: frozenset({LiveState.ARMING}),
    LiveState.ARMING: frozenset({LiveState.ARMED, LiveState.DISARMED}),
    LiveState.ARMED: frozenset({LiveState.STARTING, LiveState.DISARMED}),
    LiveState.STARTING: frozenset({LiveState.RUNNING, LiveState.STOPPING}),
    LiveState.RUNNING: frozenset(
        {
            LiveState.HALT_NEW_ORDERS,
            LiveState.CANCEL_ONLY,
            LiveState.PAUSING,
            LiveState.STOPPING,
        }
    ),
    LiveState.HALT_NEW_ORDERS: frozenset(
        {LiveState.RUNNING, LiveState.CANCEL_ONLY, LiveState.STOPPING}
    ),
    LiveState.CANCEL_ONLY: frozenset({LiveState.HALT_NEW_ORDERS, LiveState.STOPPING}),
    LiveState.PAUSING: frozenset({LiveState.PAUSED, LiveState.STOPPING}),
    LiveState.PAUSED: frozenset({LiveState.RUNNING, LiveState.STOPPING}),
    # Out of SAFE_MODE: only to CANCEL_ONLY (positions being wound down under a person's
    # eye) or STOPPING. Never straight back to RUNNING — the doubt that caused it has to
    # be worked off gradually.
    LiveState.SAFE_MODE: frozenset({LiveState.CANCEL_ONLY, LiveState.STOPPING}),
    LiveState.STOPPING: frozenset({LiveState.STOPPED, LiveState.ERROR}),
    LiveState.STOPPED: frozenset(),
    LiveState.ERROR: frozenset(),
}

#: States that may be entered from anywhere. A safety escalation that could be refused
#: because of the *current* state would be a safety mechanism with a precondition.
_ALWAYS_REACHABLE = frozenset({LiveState.SAFE_MODE, LiveState.ERROR})


@dataclass(frozen=True)
class StateChange:
    at: datetime
    from_state: LiveState
    to_state: LiveState
    reason: str
    actor: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "from": self.from_state.value,
            "to": self.to_state.value,
            "reason": self.reason,
            "actor": self.actor,
        }


@dataclass
class LiveStateMachine:
    """The current state, its full history, and the rules for moving between them."""

    clock: Clock
    state: LiveState = LiveState.DISARMED
    history: list[StateChange] = field(default_factory=list)

    def transition(self, to: LiveState, *, reason: str, actor: str = "") -> StateChange:
        """Move, or raise. Every transition carries a reason and lands in the history.

        A same-state transition is a no-op rather than an error: two components noticing
        the same problem and both demanding SAFE_MODE is normal, and the second demand is
        agreement, not a bug.
        """
        if to is self.state:
            return StateChange(self.clock.now(), self.state, to, reason, actor)

        allowed = to in _ALWAYS_REACHABLE or to in _TRANSITIONS.get(self.state, frozenset())
        if not allowed:
            raise InvalidStateTransitionError(
                f"live runtime may not go {self.state.value} -> {to.value} ({reason!r}); "
                "if this transition should exist, add it to the table deliberately",
                from_state=self.state.value,
                to_state=to.value,
            )

        change = StateChange(self.clock.now(), self.state, to, reason, actor)
        self.state = to
        self.history.append(change)
        return change

    def require(self, *states: LiveState, action: str) -> None:
        if self.state not in states:
            raise InvalidStateTransitionError(
                f"{action} requires state in {[s.value for s in states]}; "
                f"current state is {self.state.value}",
                from_state=self.state.value,
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "accepts_new_orders": self.state.accepts_new_orders,
            "accepts_reducing_orders": self.state.accepts_reducing_orders,
            "history": [change.as_dict() for change in self.history[-50:]],
        }


__all__ = ["LiveState", "LiveStateMachine", "StateChange"]
