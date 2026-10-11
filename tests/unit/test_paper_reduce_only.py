"""The paper engine enforces ``reduce_only`` (Phase 1.3, G5).

Before 1.3 the flag only exempted an order from the minimum notional: a "reduce-only"
close sent over a position the protective stop had just taken out opened the position
the other way, and a resting stop whose position another order had closed fired into a
flat book. A futures venue refuses the first and expires the second; so does the engine
now, and the position never fills past flat.
"""

from __future__ import annotations

import pytest

from tests.unit.test_order_filters import START, bar, intent, provider
from tia.domain.enums import OrderState, OrderType, Side, TimeInForce
from tia.domain.orders import OrderIntent


async def _long(engine, quantity: float = 0.01):  # type: ignore[no-untyped-def]
    engine.on_bar(bar(0))
    order = await engine.submit_order(intent(quantity=quantity, signal_id="entry"))
    engine.on_bar(bar(1))
    assert order.state is OrderState.FILLED
    assert (await engine.get_positions())["BTC-USD"].quantity == pytest.approx(quantity)
    return order


async def test_a_reduce_only_order_over_a_flat_position_is_rejected() -> None:
    engine = provider()
    engine.on_bar(bar(0))
    order = await engine.submit_order(intent(quantity=0.01, side=Side.SELL, reduce_only=True))
    assert order.state is OrderState.REJECTED
    assert "would not reduce" in (order.reject_reason or "")
    engine.on_bar(bar(1, price=90_000.0))
    assert await engine.get_positions() == {}, "nothing opened the other way"
    assert order.fills == []


async def test_a_reduce_only_order_on_the_same_side_as_the_position_is_rejected() -> None:
    engine = provider()
    await _long(engine)
    adding = await engine.submit_order(intent(quantity=0.01, side=Side.BUY, reduce_only=True, signal_id="add"))
    assert adding.state is OrderState.REJECTED
    engine.on_bar(bar(2))
    assert (await engine.get_positions())["BTC-USD"].quantity == pytest.approx(0.01)


async def test_a_reduce_only_close_larger_than_the_position_fills_to_flat_and_no_further() -> None:
    engine = provider()
    await _long(engine, 0.01)
    close = await engine.submit_order(intent(quantity=0.03, side=Side.SELL, reduce_only=True, signal_id="close"))
    assert close.state is OrderState.ACKNOWLEDGED
    fills = engine.on_bar(bar(2))
    assert len(fills) == 1 and fills[0].quantity == pytest.approx(0.01)
    assert await engine.get_positions() == {}, "flat, not short 0.02"
    assert close.state is OrderState.EXPIRED, "the unfillable remainder is over, not resting"
    assert close.filled_quantity == pytest.approx(0.01)
    assert engine.on_bar(bar(3, price=80_000.0)) == [], "and never fills later"


async def test_a_resting_reduce_only_stop_expires_once_another_order_closed_the_position() -> None:
    """The protective stop after a market close: the position it protected is gone, and
    the bar through its level must not turn a flat book into a short."""
    engine = provider()
    await _long(engine, 0.01)
    stop = await engine.submit_order(
        OrderIntent(
            intent_id="int-stop", signal_id="stop", risk_decision_id="risk-stop", symbol="BTC-USD",
            side=Side.SELL, order_type=OrderType.STOP, quantity=0.01, stop_price=95_000.0,
            time_in_force=TimeInForce.GTC, created_at=START, reduce_only=True,
            client_order_id=OrderIntent.build_client_order_id(
                signal_id="stop", symbol="BTC-USD", side=Side.SELL, quantity=0.01, order_type=OrderType.STOP,
            ),
        )
    )
    assert stop.state is OrderState.ACKNOWLEDGED
    close = await engine.submit_order(intent(quantity=0.01, side=Side.SELL, reduce_only=True, signal_id="close"))
    fills = engine.on_bar(bar(2))  # the close fills; the stop's level is not reached
    assert [f.order_id for f in fills] == [close.order_id]
    assert await engine.get_positions() == {}
    fills = engine.on_bar(bar(3, price=90_000.0))  # through the stop level, on a flat book
    assert fills == [], "the stop had nothing left to reduce"
    assert stop.state is OrderState.EXPIRED
    assert await engine.get_positions() == {}, "no position the other way"


async def test_an_ordinary_order_can_still_flip_the_position() -> None:
    """Enforcement is tied to the flag: a sell without it over a long still goes through
    flat — the engine's behaviour for every order that is not reduce-only is unchanged."""
    engine = provider()
    await _long(engine, 0.01)
    flip = await engine.submit_order(intent(quantity=0.03, side=Side.SELL, signal_id="flip"))
    engine.on_bar(bar(2))
    assert flip.state is OrderState.FILLED
    assert (await engine.get_positions())["BTC-USD"].quantity == pytest.approx(-0.02)


async def test_the_flag_travels_from_the_intent_to_the_order() -> None:
    engine = provider()
    await _long(engine, 0.01)
    close = await engine.submit_order(intent(quantity=0.01, side=Side.SELL, reduce_only=True, signal_id="close"))
    assert close.reduce_only is True
    plain = await engine.submit_order(intent(quantity=0.01, side=Side.SELL, signal_id="plain"))
    assert plain.reduce_only is False
