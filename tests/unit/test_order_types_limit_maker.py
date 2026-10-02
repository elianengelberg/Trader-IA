"""``OrderType.LIMIT_MAKER``: a post-only limit in the domain and in the simulators.

It did not exist before the market maker needed it; these tests pin what it means."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.rng import RngRegistry
from tia.domain.enums import OrderType, Side
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.orders import Fill, OrderIntent
from tia.execution.paper import PaperExecutionProvider

START = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _intent(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "intent_id": "int-1",
        "client_order_id": "coid-1",
        "signal_id": "sig-1",
        "risk_decision_id": "risk-1",
        "symbol": "BTC-USD",
        "side": Side.BUY,
        "order_type": OrderType.LIMIT_MAKER,
        "quantity": 1.0,
        "limit_price": 99.5,
        "created_at": START,
    }
    values.update(overrides)
    return OrderIntent(**values)


def test_limit_maker_is_a_distinct_order_type_that_requires_a_limit_price() -> None:
    assert OrderType.LIMIT_MAKER.value == "limit_maker"
    assert OrderType("limit_maker") is OrderType.LIMIT_MAKER
    assert _intent().order_type is OrderType.LIMIT_MAKER
    with pytest.raises(ValueError, match="requires limit_price"):
        _intent(limit_price=None)


def test_the_client_order_id_distinguishes_a_post_only_order_from_a_plain_limit() -> None:
    plain = OrderIntent.build_client_order_id(signal_id="s", symbol="BTC-USD", side=Side.BUY, quantity=1.0, order_type=OrderType.LIMIT, limit_price=99.5)
    post_only = OrderIntent.build_client_order_id(signal_id="s", symbol="BTC-USD", side=Side.BUY, quantity=1.0, order_type=OrderType.LIMIT_MAKER, limit_price=99.5)
    assert plain != post_only


def test_a_fill_carries_the_fee_asset_when_known_and_defaults_to_unknown() -> None:
    fill = Fill(fill_id="f", order_id="o", sequence=0, symbol="BTC-USD", side=Side.BUY, quantity=1.0, price=100.0, fee=0.1, filled_at=START)
    assert fill.fee_asset == ""
    assert Fill(**{**fill.model_dump(), "fee_asset": "BNB"}).fee_asset == "BNB"


async def test_the_paper_provider_rests_a_post_only_order_and_fills_it_as_a_maker() -> None:
    from tests.unit.test_paper_execution import DETERMINISTIC, bar
    from tests.unit.test_paper_execution import START as BAR_START

    clock = SimulatedClock(BAR_START)
    provider = PaperExecutionProvider(DETERMINISTIC, DEFAULT_UNIVERSE, clock, RngRegistry(7))
    order = await provider.submit_order(_intent(created_at=BAR_START))
    assert not order.state.is_terminal
    clock.advance_to(BAR_START + timedelta(minutes=2))
    assert provider.on_bar(bar(open_=100.0, high=100.5, low=99.8, close=100.2)) == []  # never traded through 99.5
    clock.advance_to(BAR_START + timedelta(minutes=3))
    fill = provider.on_bar(bar(index=2, open_=100.0, high=100.5, low=99.0, close=99.2))[0]
    assert fill.liquidity == "maker"
    assert fill.fee == pytest.approx(fill.notional * DETERMINISTIC.maker_fee_bps / 10_000.0)
