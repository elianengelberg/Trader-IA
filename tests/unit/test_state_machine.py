"""The order state machine.

The table is the contract. These tests exist so that a future edit to ``TRANSITIONS``
that makes an order un-finishable, or that permits a state jump which skips risk
approval, fails here rather than in a position.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.errors import InvalidStateTransitionError
from tia.domain.enums import (
    OPEN_ORDER_STATES,
    TERMINAL_ORDER_STATES,
    OrderState,
    OrderType,
    Side,
    TimeInForce,
)
from tia.domain.orders import Fill, Order
from tia.execution.state_machine import (
    TRANSITIONS,
    assert_transition,
    can_transition,
    reachable_from,
    resolve_fill_state,
    terminal_states,
    transition,
    validate_table,
)

START = datetime(2026, 1, 5, tzinfo=UTC)


def make_order(state: OrderState = OrderState.CREATED, quantity: float = 1.0) -> Order:
    return Order(
        order_id="ord-1",
        client_order_id="coid-1",
        intent_id="int-1",
        signal_id="sig-1",
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


def test_table_is_well_formed() -> None:
    validate_table()


def test_every_state_appears_in_the_table() -> None:
    assert set(TRANSITIONS) == set(OrderState)


def test_terminal_states_have_no_exit() -> None:
    for state in TERMINAL_ORDER_STATES:
        assert TRANSITIONS[state] == frozenset(), f"{state} is terminal but has exits"
        assert reachable_from(state) == frozenset()


def test_every_non_terminal_state_can_finish() -> None:
    """An order that can never reach a terminal state is an order that never closes."""
    for state in OrderState:
        if state.is_terminal:
            continue
        assert reachable_from(state) & TERMINAL_ORDER_STATES, f"{state} can never finish"


def test_open_states_are_not_terminal() -> None:
    assert not (OPEN_ORDER_STATES & TERMINAL_ORDER_STATES)


def test_terminal_states_helper_matches_enum() -> None:
    assert terminal_states() == TERMINAL_ORDER_STATES


def test_no_state_can_skip_risk_approval() -> None:
    """Nothing may reach the venue without passing through RISK_APPROVED.

    This is the state-machine expression of the rule that the Risk Engine has absolute
    veto: if SUBMITTING were reachable from anywhere else, an order could be sent
    without ever having been evaluated.
    """
    for state, targets in TRANSITIONS.items():
        if OrderState.SUBMITTING in targets:
            assert state is OrderState.RISK_APPROVED, (
                f"{state.value} can reach SUBMITTING without risk approval"
            )


def test_risk_approved_is_only_reachable_from_validated() -> None:
    for state, targets in TRANSITIONS.items():
        if OrderState.RISK_APPROVED in targets:
            assert state is OrderState.VALIDATED


def test_filled_is_only_reachable_from_states_that_can_hold_fills() -> None:
    permitted = {
        OrderState.ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCEL_REQUESTED,
    }
    for state, targets in TRANSITIONS.items():
        if OrderState.FILLED in targets:
            assert state in permitted, f"{state.value} -> FILLED skips acknowledgement"


# --------------------------------------------------------------------------- transitions


def test_legal_transition_updates_state_and_timestamp() -> None:
    order = make_order()
    later = START + timedelta(seconds=5)
    previous, current = transition(order, OrderState.VALIDATED, at=later)
    assert (previous, current) == (OrderState.CREATED, OrderState.VALIDATED)
    assert order.state is OrderState.VALIDATED
    assert order.updated_at == later


def test_illegal_transition_raises_with_context() -> None:
    order = make_order()
    with pytest.raises(InvalidStateTransitionError) as exc:
        transition(order, OrderState.FILLED, at=START)
    assert exc.value.context["order_id"] == "ord-1"
    assert exc.value.context["current"] == "created"
    assert exc.value.context["target"] == "filled"
    assert "validated" in exc.value.context["allowed"]
    # The failed transition left the order untouched.
    assert order.state is OrderState.CREATED


def test_terminal_orders_cannot_move() -> None:
    for state in TERMINAL_ORDER_STATES:
        order = make_order(state)
        for target in OrderState:
            with pytest.raises(InvalidStateTransitionError):
                transition(order, target, at=START)


def test_reason_is_recorded_only_on_failure_states() -> None:
    order = make_order(OrderState.CREATED)
    transition(order, OrderState.REJECTED, at=START, reason="insufficient margin")
    assert order.reject_reason == "insufficient margin"

    other = make_order(OrderState.CREATED)
    transition(other, OrderState.VALIDATED, at=START, reason="looks fine")
    assert other.reject_reason is None


def test_can_transition_matches_assert_transition() -> None:
    for current in OrderState:
        for target in OrderState:
            allowed = can_transition(current, target)
            if allowed:
                assert_transition(current, target)
            else:
                with pytest.raises(InvalidStateTransitionError):
                    assert_transition(current, target)


def test_successive_partial_fills_are_legal() -> None:
    order = make_order(OrderState.PARTIALLY_FILLED)
    transition(order, OrderState.PARTIALLY_FILLED, at=START)
    assert order.state is OrderState.PARTIALLY_FILLED


def test_cancel_racing_a_fill_is_permitted() -> None:
    """A venue can fill an order after we have asked to cancel it. That is a real
    outcome, not a bug, and modelling it as illegal would crash the runtime on a race
    it cannot prevent."""
    order = make_order(OrderState.CANCEL_REQUESTED)
    transition(order, OrderState.FILLED, at=START)
    assert order.state is OrderState.FILLED


# --------------------------------------------------------------------------- fill states


def _fill(order: Order, quantity: float, price: float = 100.0) -> Fill:
    return Fill(
        fill_id=f"f-{quantity}",
        order_id=order.order_id,
        sequence=len(order.fills),
        symbol=order.symbol,
        side=order.side,
        quantity=quantity,
        price=price,
        fee=0.0,
        filled_at=START,
    )


def test_resolve_fill_state_reports_partial_then_full() -> None:
    order = make_order(OrderState.ACKNOWLEDGED, quantity=10.0)
    assert resolve_fill_state(order) is OrderState.ACKNOWLEDGED

    order.register_fill(_fill(order, 4.0))
    assert resolve_fill_state(order) is OrderState.PARTIALLY_FILLED

    order.register_fill(_fill(order, 6.0))
    assert resolve_fill_state(order) is OrderState.FILLED


def test_floating_point_residue_does_not_strand_an_order() -> None:
    """0.1 + 0.2 != 0.3. Without a relative tolerance an order would sit forever at
    PARTIALLY_FILLED with 1e-17 outstanding, and the runtime would keep trying to fill
    a quantity no venue would accept."""
    order = make_order(OrderState.ACKNOWLEDGED, quantity=0.3)
    order.register_fill(_fill(order, 0.1))
    order.register_fill(_fill(order, 0.2))
    assert order.filled_quantity != order.quantity  # the residue is real
    assert resolve_fill_state(order) is OrderState.FILLED


def test_large_quantity_residue_is_also_tolerated() -> None:
    order = make_order(OrderState.ACKNOWLEDGED, quantity=1_000_000.0)
    order.register_fill(_fill(order, 1_000_000.0 - 1e-6))
    assert resolve_fill_state(order) is OrderState.FILLED


def test_a_dust_fill_does_not_count_as_a_partial() -> None:
    order = make_order(OrderState.ACKNOWLEDGED, quantity=1_000_000.0)
    order.register_fill(_fill(order, 1e-13))
    assert resolve_fill_state(order) is OrderState.ACKNOWLEDGED
