"""The order state machine.

One transition table, declared once. Anything not in it raises
:class:`~tia.core.errors.InvalidStateTransitionError`. That is the whole design: an order
that reaches an impossible state is a bug that must surface immediately, not a position
that quietly diverges from what the system thinks it holds.

```
                  ┌──────────────┐
                  │   CREATED    │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐        ┌──────────┐
                  │  VALIDATED   │───────▶│ REJECTED │◀── (terminal)
                  └──────┬───────┘        └──────────┘
                         ▼
                  ┌──────────────┐
                  │RISK_APPROVED │
                  └──────┬───────┘
                         ▼
        ┌────────▶┌──────────────┐──────▶┌────────┐
        │         │  SUBMITTING  │       │ FAILED │ (terminal)
        │         └──────┬───────┘       └────────┘
        │                ▼
        │         ┌──────────────┐
        │         │  SUBMITTED   │
        │         └──────┬───────┘
        │                ▼
        │         ┌──────────────┐
        │         │ ACKNOWLEDGED │
        │         └──┬────────┬──┘
        │            ▼        ▼
        │  ┌────────────────┐ ┌────────┐
        │  │PARTIALLY_FILLED│▶│ FILLED │ (terminal)
        │  └───┬────────────┘ └────────┘
        │      ▼
        │  ┌──────────────────┐    ┌───────────┐   ┌─────────┐
        └──│ CANCEL_REQUESTED │───▶│ CANCELLED │   │ EXPIRED │ (terminal)
           └──────────────────┘    └───────────┘   └─────────┘
```
"""

from __future__ import annotations

from datetime import datetime

from tia.core.clock import ensure_utc
from tia.core.errors import InvalidStateTransitionError
from tia.domain.enums import TERMINAL_ORDER_STATES, OrderState
from tia.domain.orders import Order

#: The complete set of legal transitions. Nothing else is permitted.
TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.CREATED: frozenset({OrderState.VALIDATED, OrderState.REJECTED, OrderState.FAILED}),
    OrderState.VALIDATED: frozenset(
        {OrderState.RISK_APPROVED, OrderState.REJECTED, OrderState.FAILED}
    ),
    OrderState.RISK_APPROVED: frozenset(
        {OrderState.SUBMITTING, OrderState.REJECTED, OrderState.EXPIRED, OrderState.FAILED}
    ),
    OrderState.SUBMITTING: frozenset(
        {OrderState.SUBMITTED, OrderState.REJECTED, OrderState.FAILED}
    ),
    OrderState.SUBMITTED: frozenset(
        {
            OrderState.ACKNOWLEDGED,
            OrderState.REJECTED,
            OrderState.CANCEL_REQUESTED,
            OrderState.EXPIRED,
            OrderState.FAILED,
        }
    ),
    OrderState.ACKNOWLEDGED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.EXPIRED,
            OrderState.REJECTED,
            OrderState.FAILED,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,  # successive partials are normal
            OrderState.FILLED,
            OrderState.CANCEL_REQUESTED,
            OrderState.CANCELLED,
            OrderState.EXPIRED,
            OrderState.FAILED,
        }
    ),
    OrderState.CANCEL_REQUESTED: frozenset(
        {
            OrderState.CANCELLED,
            # A cancel racing an in-flight fill is a real venue behaviour, not an error.
            OrderState.FILLED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FAILED,
        }
    ),
    # Terminal states have no outgoing transitions.
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.FAILED: frozenset(),
}


def can_transition(current: OrderState, target: OrderState) -> bool:
    return target in TRANSITIONS.get(current, frozenset())


def assert_transition(current: OrderState, target: OrderState, *, order_id: str = "") -> None:
    """Raise unless ``current -> target`` is a legal transition."""
    if not can_transition(current, target):
        raise InvalidStateTransitionError(
            f"illegal order transition {current.value} -> {target.value}",
            order_id=order_id,
            current=current.value,
            target=target.value,
            allowed=sorted(s.value for s in TRANSITIONS.get(current, frozenset())),
        )


def transition(
    order: Order, target: OrderState, *, at: datetime, reason: str = ""
) -> tuple[OrderState, OrderState]:
    """Move ``order`` to ``target``, returning ``(previous, current)``.

    The only sanctioned way to change an order's state. Direct assignment bypasses the
    table and is what lets an order end up FILLED without a fill.
    """
    previous = order.state
    assert_transition(previous, target, order_id=order.order_id)
    order.state = target
    order.updated_at = ensure_utc(at)
    if reason and target in {OrderState.REJECTED, OrderState.FAILED, OrderState.EXPIRED}:
        order.reject_reason = reason
    return (previous, target)


def resolve_fill_state(order: Order) -> OrderState:
    """The state an order should hold given how much of it has filled.

    Uses a relative tolerance so that floating-point residue on a large quantity does not
    leave an order permanently PARTIALLY_FILLED with 1e-15 outstanding.
    """
    tolerance = max(order.quantity * 1e-9, 1e-12)
    if order.filled_quantity >= order.quantity - tolerance:
        return OrderState.FILLED
    if order.filled_quantity > tolerance:
        return OrderState.PARTIALLY_FILLED
    return order.state


def terminal_states() -> frozenset[OrderState]:
    return TERMINAL_ORDER_STATES


def reachable_from(state: OrderState) -> frozenset[OrderState]:
    """Every state reachable from ``state``. Used by tests and by the dashboard."""
    seen: set[OrderState] = set()
    frontier = [state]
    while frontier:
        current = frontier.pop()
        for nxt in TRANSITIONS.get(current, frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return frozenset(seen)


def validate_table() -> None:
    """Sanity-check the table itself. Called by a test, not at import time.

    Catches the two ways a transition table rots: a state missing from the table
    entirely, and a non-terminal state from which no terminal state is reachable — an
    order that can never finish.
    """
    missing = set(OrderState) - set(TRANSITIONS)
    if missing:
        raise ValueError(f"states missing from the transition table: {sorted(missing)}")

    for state in OrderState:
        if state.is_terminal:
            if TRANSITIONS[state]:
                raise ValueError(f"terminal state {state.value} has outgoing transitions")
            continue
        if not (reachable_from(state) & TERMINAL_ORDER_STATES):
            raise ValueError(f"no terminal state is reachable from {state.value}")


__all__ = [
    "TRANSITIONS",
    "assert_transition",
    "can_transition",
    "reachable_from",
    "resolve_fill_state",
    "terminal_states",
    "transition",
    "validate_table",
]
