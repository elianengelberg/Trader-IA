"""P0, local contract check found in mission v2 — the protective stop's price is on the venue's tick grid.

Binance's PRICE_FILTER refuses any price that is not ``minPrice + k * tickSize``, ``stopPrice``
included ("Filter failure: PRICE_FILTER", code -1013). The runtime sent the planned stop level
as the strategy computed it (an ATR multiple: ``49876.54321…``), formatted to eight decimals: on a
symbol with a 0.01 tick every protective stop would be refused — P0's own failure path (entries
blocked, halt), on every position. The paper engine has no such filter, so no suite saw it.

The level is now quantized to the tick before the intent is built, **toward the market** (up for
the sell stop that protects a long, down for the buy stop that protects a short): the stop can
only end up tighter than planned, by less than one tick, never looser. The same quantized level is
what the next cycle compares with, so a stop on the grid is not cancelled and re-placed each bar.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from tests.integration.test_account_restore import build, open_position
from tests.integration.test_paper_cancellations import working
from tia.domain.enums import OrderType, Side


def _stops_sent(monkeypatch: pytest.MonkeyPatch, execution: Any) -> list[Any]:
    sent: list[Any] = []
    real = execution.submit_order

    async def submit(intent):  # type: ignore[no-untyped-def]
        if intent.order_type is OrderType.STOP:
            sent.append(intent)
        return await real(intent)

    monkeypatch.setattr(execution, "submit_order", submit)
    return sent


def _on_grid(price: float, tick: str) -> bool:
    return (Decimal(repr(price)) / Decimal(tick)) % 1 == 0


async def test_the_protective_stop_is_sent_on_the_tick_grid_tighter_never_looser(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build()
    await runtime.start()
    try:
        sent = _stops_sent(monkeypatch, execution)
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert sent and _on_grid(sent[-1].stop_price, "0.01"), [s.stop_price for s in sent]
        assert runtime._open_trade["side"] is Side.BUY
        planned = float(runtime._planned_exit["stop"]) - 1.0 + 0.004321  # off the grid on purpose
        runtime._planned_exit["stop"] = planned
        market.advance()
        await runtime._cycle_once()
        [stop] = await working(execution, OrderType.STOP)
        assert _on_grid(stop.stop_price, "0.01")
        assert planned <= stop.stop_price < planned + 0.01, "a sell stop rounds up: tighter, by less than a tick"
        # A trailing stop legitimately moves the planned level; while the level that would be
        # sent stays the same, nothing is re-placed.
        before = len(sent)
        last = runtime._protective_stop_level(float(runtime._planned_exit["stop"]), Side.SELL)
        steady = 0
        for _ in range(6):
            market.advance()
            await runtime._cycle_once()
            level = runtime._protective_stop_level(float(runtime._planned_exit["stop"]), Side.SELL)
            if level == last:
                assert len(sent) == before, "a stop already on the grid is not re-placed every bar"
                steady += 1
            else:
                assert _on_grid(sent[-1].stop_price, "0.01")
                before, last = len(sent), level
        assert steady >= 1
    finally:
        await runtime.stop()


async def test_the_venues_own_tick_is_the_grid_when_it_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build()
    await runtime.start()
    try:
        sent = _stops_sent(monkeypatch, execution)
        await open_position(runtime, market)
        runtime._filters = {**runtime._filters, "tick_size": "0.5"}  # what exchangeInfo would say
        runtime._planned_exit["stop"] = float(runtime._planned_exit["stop"]) - 2.0 + 0.123
        market.advance()
        await runtime._cycle_once()
        assert sent and _on_grid(sent[-1].stop_price, "0.5"), sent[-1].stop_price
    finally:
        await runtime.stop()


@pytest.mark.parametrize(("side", "level", "expected"), [
    (Side.SELL, 100.004, 100.01),   # protects a long: up, toward the market
    (Side.BUY, 100.006, 100.00),    # protects a short: down, toward the market
    (Side.SELL, 100.01, 100.01),    # already on the grid: unchanged
    (Side.BUY, 100.01, 100.01),
])
def test_the_direction_of_the_rounding(side: Side, level: float, expected: float) -> None:
    runtime, _execution, _market, _ = build()
    assert runtime._protective_stop_level(level, side) == pytest.approx(expected, abs=1e-12)
