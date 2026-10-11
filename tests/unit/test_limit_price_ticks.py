"""Limit prices land on the tick grid and never on the aggressive side of it (Phase 1.6).

``quantize_price_passive`` is the one rule: a buy rounds down, a sell rounds up, a price
on the grid stays. The backtester's resting entry goes through it with the instrument
universe's tick (the live session's does the same with the venue's); with no tick there
is nothing to quantize to and the raw price stands, which the parity table says.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.money import D, quantize_price_passive
from tia.domain.enums import Direction, OrderType
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.orders import OrderIntent

SPREAD_BPS = 2.0  # half a spread, 1 bp, is what the entry rests away from the reference


def _on_grid(price: float, tick: float) -> bool:
    return D(price) % D(tick) == 0


@pytest.mark.parametrize(
    ("price", "tick", "buy", "expected"),
    [
        (50_000.005, 0.01, True, Decimal("50000.00")),
        (50_000.005, 0.01, False, Decimal("50000.01")),
        (50_000.00, 0.01, True, Decimal("50000.00")),
        (50_000.00, 0.01, False, Decimal("50000.00")),
        (4_321.13, 0.25, True, Decimal("4321.00")),
        (4_321.13, 0.25, False, Decimal("4321.25")),
        (4_321.25, 0.25, False, Decimal("4321.25")),
        (0.123456789, 0.0001, True, Decimal("0.1234")),
        (0.123456789, 0.0001, False, Decimal("0.1235")),
        (0.1234, 0.0001, True, Decimal("0.1234")),
    ],
)
def test_the_passive_quantization_rounds_towards_our_side_or_not_at_all(price, tick, buy, expected) -> None:  # type: ignore[no-untyped-def]
    assert quantize_price_passive(price, tick, buy=buy) == expected


def test_a_non_positive_tick_is_refused() -> None:
    with pytest.raises(ValueError, match="tick must be positive"):
        quantize_price_passive(100.0, 0.0, buy=True)


def test_over_a_sweep_of_prices_a_buy_never_rounds_up_and_a_sell_never_rounds_down() -> None:
    tick = 0.01
    for i in range(2_000):
        price = 49_990.0 + i * 0.00731  # off-grid by construction, every residue visited
        bought = quantize_price_passive(price, tick, buy=True)
        sold = quantize_price_passive(price, tick, buy=False)
        assert bought <= D(price) < bought + D(tick), (price, bought)
        assert sold - D(tick) < D(price) <= sold, (price, sold)
        assert bought % D(tick) == 0 and sold % D(tick) == 0


def test_the_backtesters_buy_rests_at_or_below_the_raw_price_on_the_grid() -> None:
    reference = 50_000.0
    raw = BacktestEngine._limit_price_for(Direction.LONG, reference, SPREAD_BPS)
    assert raw == pytest.approx(reference * (1.0 - 0.0001))
    quantized = BacktestEngine._limit_price_for(Direction.LONG, reference, SPREAD_BPS, tick_size=0.01)
    assert quantized <= raw + 1e-12 and _on_grid(quantized, 0.01)
    assert raw - quantized < 0.01
    assert quantized < reference, "still on our side of the reference"


def test_the_backtesters_sell_rests_at_or_above_the_raw_price_on_the_grid() -> None:
    reference = 50_000.0
    raw = BacktestEngine._limit_price_for(Direction.SHORT, reference, SPREAD_BPS)
    assert raw == pytest.approx(reference * (1.0 + 0.0001))
    quantized = BacktestEngine._limit_price_for(Direction.SHORT, reference, SPREAD_BPS, tick_size=0.01)
    assert quantized >= raw - 1e-12 and _on_grid(quantized, 0.01)
    assert quantized - raw < 0.01
    assert quantized > reference


@pytest.mark.parametrize("tick", [0.01, 0.25, 0.5, 1.0])
def test_a_coarser_tick_moves_the_price_at_most_one_tick_and_only_our_way(tick: float) -> None:
    for reference in (4_321.13, 4_321.25, 4_999.99, 5_000.0, 5_000.01):
        for direction in (Direction.LONG, Direction.SHORT):
            raw = BacktestEngine._limit_price_for(direction, reference, SPREAD_BPS)
            quantized = BacktestEngine._limit_price_for(direction, reference, SPREAD_BPS, tick_size=tick)
            assert _on_grid(quantized, tick), (tick, reference, direction, quantized)
            if direction is Direction.LONG:
                assert raw - tick < quantized <= raw + 1e-9
            else:
                assert raw - 1e-9 <= quantized < raw + tick


def test_with_no_tick_the_raw_price_stands() -> None:
    raw = BacktestEngine._limit_price_for(Direction.LONG, 50_000.0, SPREAD_BPS)
    assert BacktestEngine._limit_price_for(Direction.LONG, 50_000.0, SPREAD_BPS, tick_size=None) == raw
    assert BacktestEngine._limit_price_for(Direction.LONG, 50_000.0, SPREAD_BPS, tick_size=0.0) == raw


def test_the_engine_sends_every_resting_entry_on_the_instruments_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through the fixture series with limit entries: every intent the engine
    builds carries a limit price on BTC-USD's 0.01 grid, on the passive side of its own
    raw price. The intents are captured at the one place they are built."""
    from tests.unit.test_backtest import SERIES

    seen: list[OrderIntent] = []
    real = BacktestEngine._to_intent

    def capture(decision, direction, *, limit_price=None):  # type: ignore[no-untyped-def]
        intent = real(decision, direction, limit_price=limit_price)
        seen.append(intent)
        return intent

    monkeypatch.setattr(BacktestEngine, "_to_intent", staticmethod(capture))
    config = BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, entry_order_type="limit")
    BacktestEngine(config, DEFAULT_UNIVERSE).run(SERIES)
    limits = [i for i in seen if i.order_type is OrderType.LIMIT]
    assert limits, "the fixture series produced resting entries"
    tick = DEFAULT_UNIVERSE.require("BTC-USD").tick_size
    for intent in limits:
        assert intent.limit_price is not None and _on_grid(intent.limit_price, tick), intent.limit_price
