"""Order filters: one rule set, applied before an order exists and again at the venue.

Each case is a boundary: just below the minimum, exactly at it, just above; a size that was
legal before quantization and not after; a quantity below one lot; a symbol nobody can
judge. The simulator cases prove the rejection creates no fill, no position and no P&L.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import ExecutionSimConfig
from tia.core.rng import RngRegistry
from tia.domain.enums import AssetClass, OrderState, OrderType, Side, TimeInForce
from tia.domain.instruments import DEFAULT_UNIVERSE, Instrument, InstrumentUniverse
from tia.domain.market import Candle
from tia.domain.orders import OrderIntent
from tia.execution.filters import (
    InstrumentFilters,
    OrderFilterError,
    filters_for,
    validate_quantity,
)
from tia.execution.paper import PaperExecutionProvider

START = datetime(2026, 1, 5, tzinfo=UTC)
BTC = filters_for("BTC-USD", DEFAULT_UNIVERSE)  # lot 1e-6, min notional 10
PRICE = 100_000.0


# ------------------------------------------------------------------ the rule set


def test_the_local_rules_come_from_the_instrument_and_say_so() -> None:
    assert str(BTC.step_size) == "0.000001"
    assert str(BTC.min_notional) == "10.0"
    assert "instrument universe" in BTC.source and "no venue filters" in BTC.source


def test_venue_filters_win_where_present_and_the_instrument_fills_the_gaps() -> None:
    venue = filters_for("BTC-USD", DEFAULT_UNIVERSE, {"step_size": "0.001", "min_notional": "5"})
    assert str(venue.step_size) == "0.001"
    assert str(venue.min_notional) == "5"
    assert str(venue.tick_size) == "0.01", "absent at the venue: the instrument's own"
    assert "venue filters" in venue.source


def test_an_unknown_instrument_cannot_be_judged_and_is_refused() -> None:
    with pytest.raises(OrderFilterError, match="unknown instrument"):
        filters_for("DOGE-USD", DEFAULT_UNIVERSE)


@pytest.mark.parametrize(
    ("quantity", "ok"),
    [
        (0.000099, False),  # 9.90 — just below
        (0.000100, True),   # 10.00 — exactly the minimum: allowed
        (0.000101, True),   # 10.10 — just above
    ],
)
def test_the_minimum_notional_is_a_closed_lower_bound(quantity: float, ok: bool) -> None:
    if ok:
        validate_quantity(BTC, quantity, reference_price=PRICE, reduce_only=False)
    else:
        with pytest.raises(OrderFilterError, match="below the minimum"):
            validate_quantity(BTC, quantity, reference_price=PRICE, reduce_only=False)


def test_quantization_can_push_a_legal_size_below_the_minimum_and_then_it_is_refused() -> None:
    """SPX-IDX: lot 0.01, minimum 25. 0.0199 at 2,000 is 39.80 before rounding and 20.00
    after it — the order the venue would see is the rounded one, and it is illegal."""
    spx = filters_for("SPX-IDX", DEFAULT_UNIVERSE)
    rounded = spx.quantize(0.0199)
    assert rounded == pytest.approx(0.01)
    with pytest.raises(OrderFilterError, match="below the minimum"):
        validate_quantity(spx, rounded, reference_price=2_000.0, reduce_only=False)


def test_a_quantity_that_is_not_a_whole_number_of_lots_was_never_quantized() -> None:
    with pytest.raises(OrderFilterError, match="not a whole multiple"):
        validate_quantity(BTC, 0.0120437523, reference_price=PRICE, reduce_only=False)
    validate_quantity(BTC, BTC.quantize(0.0120437523), reference_price=PRICE, reduce_only=False)


def test_a_quantity_below_one_lot_is_refused_even_when_rich_enough() -> None:
    venue = InstrumentFilters.from_venue(
        "BTC-USD", {"step_size": "0.001", "min_qty": "0.002", "min_notional": "1"}, None
    )
    with pytest.raises(OrderFilterError, match=r"below the minimum 0\.002"):
        validate_quantity(venue, 0.001, reference_price=PRICE, reduce_only=False)


def test_an_entry_without_a_reference_price_is_refused_not_assumed() -> None:
    with pytest.raises(OrderFilterError, match="without a reference price"):
        validate_quantity(BTC, 0.001, reference_price=None, reduce_only=False)
    # The simulator's stance, before it has seen a bar: skip, the builder already judged.
    validate_quantity(BTC, 0.001, reference_price=None, reduce_only=False, notional_required=False)


def test_a_reducing_order_is_exempt_from_the_notional_minimum_but_not_from_the_lot() -> None:
    validate_quantity(BTC, 0.000001, reference_price=PRICE, reduce_only=True)  # dust, closable
    with pytest.raises(OrderFilterError, match="not a whole multiple"):
        validate_quantity(BTC, 0.0000015, reference_price=PRICE, reduce_only=True)


def test_a_non_positive_quantity_is_refused() -> None:
    with pytest.raises(OrderFilterError, match="not positive"):
        validate_quantity(BTC, 0.0, reference_price=PRICE, reduce_only=False)


def test_the_filter_error_is_also_a_value_error_for_existing_callers() -> None:
    with pytest.raises(ValueError):
        validate_quantity(BTC, 0.000001, reference_price=PRICE, reduce_only=False)


# ------------------------------------------------------------- at the simulator


DETERMINISTIC = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)


def bar(index: int, *, price: float = PRICE, symbol: str = "BTC-USD", volume: float = 1_000.0) -> Candle:
    open_time = START + timedelta(minutes=index)
    return Candle(
        symbol=symbol, timeframe="1m", open_time=open_time,
        close_time=open_time + timedelta(minutes=1), open=price, high=price * 1.001,
        low=price * 0.999, close=price, volume=volume, trade_count=10, provider="test",
    )


def intent(
    *, quantity: float, side: Side = Side.BUY, symbol: str = "BTC-USD",
    order_type: OrderType = OrderType.MARKET, limit_price: float | None = None,
    reduce_only: bool = False, signal_id: str = "sig",
) -> OrderIntent:
    return OrderIntent(
        intent_id=f"int-{signal_id}-{quantity}",
        client_order_id=OrderIntent.build_client_order_id(
            signal_id=signal_id, symbol=symbol, side=side, quantity=quantity,
            order_type=order_type, limit_price=limit_price,
        ),
        signal_id=signal_id, risk_decision_id=f"risk-{signal_id}", symbol=symbol, side=side,
        order_type=order_type, quantity=quantity, limit_price=limit_price,
        time_in_force=TimeInForce.GTC, created_at=START, reduce_only=reduce_only,
    )


def provider(universe: InstrumentUniverse = DEFAULT_UNIVERSE) -> PaperExecutionProvider:
    return PaperExecutionProvider(
        DETERMINISTIC, universe, SimulatedClock(START), RngRegistry(1), initial_capital=100_000.0
    )


async def test_the_simulator_rejects_an_entry_below_the_minimum_with_no_fill_position_or_pnl() -> None:
    venue = provider()
    venue.on_bar(bar(0))  # the engine knows a price now
    order = await venue.submit_order(intent(quantity=0.000099))
    assert order.state is OrderState.REJECTED
    assert "below the minimum" in order.reject_reason
    # Bars pass; a rejected order can never fill.
    for i in range(1, 4):
        assert venue.on_bar(bar(i)) == []
    assert order.fills == []
    assert await venue.get_positions() == {}
    pnl = await venue.get_pnl()
    assert pnl["realized"] == 0.0 and pnl["fees"] == 0.0
    assert (await venue.get_balance()) == pytest.approx(100_000.0)


async def test_the_simulator_rejects_a_quantity_that_is_not_whole_lots() -> None:
    venue = provider()
    venue.on_bar(bar(0))
    order = await venue.submit_order(intent(quantity=0.0120437523))
    assert order.state is OrderState.REJECTED and "whole multiple" in order.reject_reason
    assert venue.on_bar(bar(1)) == []


async def test_the_simulator_judges_a_resting_order_at_its_limit_price() -> None:
    venue = provider()
    venue.on_bar(bar(0))
    # 0.0001 BTC is 10.00 at the last close but 9.50 at the limit it would fill at.
    order = await venue.submit_order(
        intent(quantity=0.0001, order_type=OrderType.LIMIT, limit_price=95_000.0)
    )
    assert order.state is OrderState.REJECTED and "below the minimum" in order.reject_reason


async def test_the_simulator_accepts_exactly_the_minimum_and_fills_it() -> None:
    venue = provider()
    venue.on_bar(bar(0))
    order = await venue.submit_order(intent(quantity=0.0001))
    assert order.state is OrderState.ACKNOWLEDGED
    fills = venue.on_bar(bar(1))
    assert len(fills) == 1 and fills[0].quantity == pytest.approx(0.0001)


async def test_a_reducing_order_below_the_minimum_is_still_accepted_so_positions_close() -> None:
    """Open a legal position, then close dust-sized slices: the venue's view of 'reducing'
    is the position itself, so the exemption does not depend on the caller remembering
    to say reduce_only."""
    venue = provider()
    venue.on_bar(bar(0))
    opened = await venue.submit_order(intent(quantity=0.0002, signal_id="open"))
    assert opened.state is OrderState.ACKNOWLEDGED
    assert len(venue.on_bar(bar(1))) == 1
    closing = await venue.submit_order(intent(quantity=0.00005, side=Side.SELL, signal_id="close"))
    assert closing.state is OrderState.ACKNOWLEDGED, closing.reject_reason
    assert len(venue.on_bar(bar(2))) == 1
    held = (await venue.get_positions())["BTC-USD"].quantity
    assert held == pytest.approx(0.00015)


async def test_the_simulator_refuses_an_unknown_instrument_before_the_filters() -> None:
    venue = provider()
    order = await venue.submit_order(intent(quantity=1.0, symbol="DOGE-USD"))
    assert order.state is OrderState.REJECTED and order.reject_reason == "unknown instrument"


async def test_before_any_bar_the_simulator_cannot_judge_the_notional_and_defers_to_the_builder() -> None:
    venue = provider()  # no bar seen: no last price
    order = await venue.submit_order(intent(quantity=0.000001))
    assert order.state is OrderState.ACKNOWLEDGED, "no price to judge at; the builder's check stands"


async def test_a_universe_with_a_coarse_lot_refuses_sizes_the_rounding_would_change() -> None:
    coarse = InstrumentUniverse(
        instruments=(
            Instrument(
                symbol="BTC-USD", asset_class=AssetClass.CRYPTO, tick_size=0.01,
                lot_size=0.001, min_notional=10.0,
            ),
        )
    )
    venue = provider(coarse)
    venue.on_bar(bar(0))
    order = await venue.submit_order(intent(quantity=0.0015))
    assert order.state is OrderState.REJECTED and "whole multiple" in order.reject_reason
