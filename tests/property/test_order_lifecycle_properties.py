"""Properties of the order lifecycle.

The example-based tests in ``tests/unit/test_state_machine.py`` check the transitions
someone thought of. These check the ones nobody did: random walks through the table,
adversarial sequences, and the invariants that must hold no matter which path an order
took to get where it is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tia.core.errors import InvalidStateTransitionError
from tia.domain.enums import TERMINAL_ORDER_STATES, OrderState, OrderType, Side, TimeInForce
from tia.domain.orders import Fill, Order
from tia.execution.state_machine import (
    TRANSITIONS,
    can_transition,
    reachable_from,
    resolve_fill_state,
    transition,
)

START = datetime(2026, 1, 5, tzinfo=UTC)

order_states = st.sampled_from(list(OrderState))


def make_order(state: OrderState = OrderState.CREATED, quantity: float = 100.0) -> Order:
    return Order(
        order_id="ord-prop",
        client_order_id="coid-prop",
        intent_id="int-prop",
        signal_id="sig-prop",
        symbol="BTC-USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        time_in_force=TimeInForce.GTC,
        state=state,
        created_at=START,
        updated_at=START,
    )


# --------------------------------------------------------------------------- the table


@given(current=order_states, target=order_states)
def test_a_transition_succeeds_exactly_when_the_table_permits_it(
    current: OrderState, target: OrderState
) -> None:
    """No path around the table. If ``can_transition`` says no, ``transition`` raises —
    for every pair, not just the ones with a hand-written test."""
    order = make_order(current)
    if can_transition(current, target):
        transition(order, target, at=START)
        assert order.state is target
    else:
        with pytest.raises(InvalidStateTransitionError):
            transition(order, target, at=START)
        assert order.state is current


@given(sequence=st.lists(order_states, min_size=1, max_size=25))
def test_a_random_walk_never_leaves_a_legal_state(sequence: list[OrderState]) -> None:
    """Feed the machine arbitrary target states. Every accepted step must be in the
    table, every rejected step must leave the order exactly as it was, and the order
    must never end up somewhere it could not have walked to."""
    order = make_order()
    visited = [order.state]

    for target in sequence:
        before = order.state
        try:
            transition(order, target, at=START)
        except InvalidStateTransitionError:
            assert order.state is before
            continue
        assert target in TRANSITIONS[before]
        visited.append(target)

    for previous, current in pairwise(visited):
        assert current in TRANSITIONS[previous]


@given(sequence=st.lists(order_states, min_size=1, max_size=25))
def test_terminal_is_forever(sequence: list[OrderState]) -> None:
    """Once an order is done it stays done. An order that leaves a terminal state is a
    position that reappears after the system stopped accounting for it."""
    order = make_order()
    for target in sequence:
        was_terminal = order.state.is_terminal
        try:
            transition(order, target, at=START)
        except InvalidStateTransitionError:
            continue
        assert not was_terminal, "an order escaped a terminal state"


@given(start=order_states)
def test_every_order_can_still_finish_from_wherever_it_is(start: OrderState) -> None:
    assume(not start.is_terminal)
    assert reachable_from(start) & TERMINAL_ORDER_STATES


@given(start=order_states)
def test_reachability_is_transitively_closed(start: OrderState) -> None:
    reachable = reachable_from(start)
    for state in reachable:
        assert reachable_from(state) <= reachable


@given(sequence=st.lists(order_states, min_size=1, max_size=40))
def test_an_order_never_reaches_submitting_without_risk_approval(
    sequence: list[OrderState],
) -> None:
    """The Risk Engine's veto expressed as a reachability property: whatever random
    sequence is applied, the step *into* SUBMITTING can only ever come from
    RISK_APPROVED."""
    order = make_order()
    for target in sequence:
        before = order.state
        try:
            transition(order, target, at=START)
        except InvalidStateTransitionError:
            continue
        if target is OrderState.SUBMITTING:
            assert before is OrderState.RISK_APPROVED


# --------------------------------------------------------------------------- timestamps


@given(
    offsets=st.lists(st.integers(min_value=0, max_value=86_400), min_size=1, max_size=10),
)
def test_updated_at_tracks_the_last_accepted_transition(offsets: list[int]) -> None:
    order = make_order()
    last_accepted: datetime | None = None
    for offset, target in zip(offsets, TRANSITIONS[OrderState.CREATED], strict=False):
        moment = START + timedelta(seconds=offset)
        try:
            transition(order, target, at=moment)
        except InvalidStateTransitionError:
            continue
        last_accepted = moment
        break
    if last_accepted is not None:
        assert order.updated_at == last_accepted


# --------------------------------------------------------------------------- fills


@given(
    quantity=st.floats(min_value=1e-6, max_value=1e9, allow_nan=False, allow_infinity=False),
    fraction=st.floats(min_value=0.0, max_value=1.0),
)
@settings(suppress_health_check=[HealthCheck.filter_too_much])
def test_fill_state_is_monotone_in_filled_quantity(quantity: float, fraction: float) -> None:
    """More filled never means *less* filled, in state terms. A partial that resolves
    back to ACKNOWLEDGED would make the runtime re-submit quantity already executed."""
    filled = quantity * fraction
    assume(filled > 0)
    assume(filled <= quantity)

    order = make_order(OrderState.ACKNOWLEDGED, quantity=quantity)
    order.register_fill(
        Fill(
            fill_id="f",
            order_id=order.order_id,
            sequence=0,
            symbol=order.symbol,
            side=order.side,
            quantity=filled,
            price=100.0,
            fee=0.0,
            filled_at=START,
        )
    )

    resolved = resolve_fill_state(order)
    tolerance = max(quantity * 1e-9, 1e-12)
    if filled >= quantity - tolerance:
        assert resolved is OrderState.FILLED
    elif filled > tolerance:
        assert resolved is OrderState.PARTIALLY_FILLED
    else:
        assert resolved is OrderState.ACKNOWLEDGED


@given(
    quantity=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    parts=st.integers(min_value=2, max_value=12),
)
def test_a_fully_filled_order_always_resolves_to_filled(quantity: float, parts: int) -> None:
    """However many pieces a quantity is chopped into, the accumulated floating-point
    residue must not leave the order stranded as partially filled."""
    order = make_order(OrderState.ACKNOWLEDGED, quantity=quantity)
    slice_size = quantity / parts
    for i in range(parts):
        remaining = order.remaining_quantity
        amount = min(slice_size, remaining) if i < parts - 1 else remaining
        if amount <= 0:
            continue
        order.register_fill(
            Fill(
                fill_id=f"f{i}",
                order_id=order.order_id,
                sequence=i,
                symbol=order.symbol,
                side=order.side,
                quantity=amount,
                price=100.0,
                fee=0.0,
                filled_at=START,
            )
        )
    assert resolve_fill_state(order) is OrderState.FILLED


@given(
    quantity=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    overfill=st.floats(min_value=1.001, max_value=5.0),
)
def test_an_order_can_never_be_overfilled(quantity: float, overfill: float) -> None:
    """A fill larger than what is outstanding means the system is about to record more
    exposure than it approved. Rejected at the boundary, loudly."""
    order = make_order(OrderState.ACKNOWLEDGED, quantity=quantity)
    with pytest.raises(ValueError, match="exceeds remaining"):
        order.register_fill(
            Fill(
                fill_id="f",
                order_id=order.order_id,
                sequence=0,
                symbol=order.symbol,
                side=order.side,
                quantity=quantity * overfill,
                price=100.0,
                fee=0.0,
                filled_at=START,
            )
        )
    assert order.filled_quantity == 0.0
