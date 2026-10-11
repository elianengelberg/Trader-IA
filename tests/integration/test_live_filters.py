"""The instrument filters on the paper-live path itself.

The runtime sizes an entry, quantizes it and judges it against the instrument's own lot and
minimum notional before an intent exists; the simulator judges the same intent again on
arrival. What is tested here is the runtime's half through the same ``_build_intent`` /
``_submit`` path a 24/7 session uses, with the same fakes as the other live-runtime tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import tia.runtime.live as live_module
from tests.integration.test_live_runtime import (
    FakeExecution,
    FakeMarketData,
    _open_a_position,
    live_settings,
)
from tia.core.clock import SimulatedClock
from tia.domain.enums import AssetClass, OrderType, Side
from tia.domain.instruments import Instrument, InstrumentUniverse
from tia.execution.filters import OrderFilterError
from tia.runtime.live import LiveRuntime
from tia.runtime.scenarios import generate_series, get_scenario
from tia.runtime.states import LiveState


def build(*, symbol_filters: dict[str, Any] | None = None, **live_overrides: Any):  # type: ignore[no-untyped-def]
    scenario = get_scenario("trend_up")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m",
        start=datetime.now(UTC) - timedelta(minutes=scenario.total_bars + 5), seed=9,
    )
    clock = SimulatedClock(candles[149].close_time + timedelta(seconds=1))
    market = FakeMarketData(candles, clock)
    execution = FakeExecution()
    runtime = LiveRuntime(
        live_settings(**live_overrides), activation=None, market_data=market,
        execution=execution, clock=clock, poll_interval_seconds=0.0,
        symbol_filters=symbol_filters,
    )
    return runtime, execution, market


def _universe(min_notional: float) -> InstrumentUniverse:
    return InstrumentUniverse(
        instruments=(
            Instrument(
                symbol="BTC-USD", asset_class=AssetClass.CRYPTO, tick_size=0.01,
                lot_size=1e-6, min_notional=min_notional,
            ),
        )
    )


async def test_an_entry_below_the_minimum_notional_is_refused_at_the_filters_stage_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no venue filters loaded, the instrument's own minimum is the rule.

    The risk engine already refuses a size that is below the minimum *when it sizes it*;
    what it cannot see is the scaling that happens after it — conviction sizing, the
    exploration fraction, the tide's halving — which can push an approved size under
    the minimum. Here an exploration entry at 5 % of the approved size does exactly
    that. The result is a refusal in the funnel — counted, named — and never a runtime
    error: the session stays RUNNING and sends nothing."""
    monkeypatch.setattr(live_module, "DEFAULT_UNIVERSE", _universe(min_notional=40.0))
    runtime, execution, market = build(
        exploration_trades_per_day=10, exploration_size_fraction=0.05, conviction_sizing=True,
    )
    await runtime.start()
    try:
        for _ in range(300):
            market.advance()
            await runtime._cycle_once()
            if runtime.funnel["filters"] > 0:
                break
        assert runtime.funnel["filters"] > 0
        assert runtime.counters["filter_rejected"] == runtime.funnel["filters"]
        assert execution.submissions == 0, "a refused size is never sent"
        assert runtime.state is LiveState.RUNNING, "a filter refusal is not a runtime failure"
        refusal = next(r for r in runtime.recent_refusals if r["stage"] == "filters")
        assert "below the minimum" in refusal["reason"]
        assert refusal["strategy_id"], "the refusal names the strategy whose size it refused"
        assert runtime.counters["orders"] == 0 and runtime.counters["fills"] == 0
    finally:
        await runtime.stop()


async def test_the_minimum_notional_check_uses_the_instrument_when_no_venue_filters_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directly through the builder the 24/7 session uses, no venue filters loaded."""
    monkeypatch.setattr(live_module, "DEFAULT_UNIVERSE", _universe(min_notional=10.0))
    runtime, _, _ = build()
    # 0.0001 @ 100,000 = 10.00: exactly the minimum, allowed; one lot less: refused.
    ok = runtime._build_intent(
        symbol="BTC-USD", side=Side.BUY, quantity=0.0001, signal_id="sig-ok",
        order_type=OrderType.MARKET, reference_price=100_000.0,
    )
    assert ok.quantity == pytest.approx(0.0001)
    with pytest.raises(OrderFilterError, match="below the minimum"):
        runtime._build_intent(
            symbol="BTC-USD", side=Side.BUY, quantity=0.000099, signal_id="sig-low",
            order_type=OrderType.MARKET, reference_price=100_000.0,
        )
    # Quantization first, judgement after: 0.0001009 rounds down to 0.000100 and passes;
    # 0.0000999 rounds down to 0.000099 and fails although it was 9.99 before rounding
    # too — the point is that the rounded size is what is judged.
    assert runtime._build_intent(
        symbol="BTC-USD", side=Side.BUY, quantity=0.0001009, signal_id="sig-round",
        order_type=OrderType.MARKET, reference_price=100_000.0,
    ).quantity == pytest.approx(0.0001)


async def test_an_entry_with_no_reference_price_is_refused_rather_than_assumed() -> None:
    runtime, _, _ = build()
    with pytest.raises(OrderFilterError, match="without a reference price"):
        runtime._build_intent(
            symbol="BTC-USD", side=Side.BUY, quantity=0.0001, signal_id="sig",
            order_type=OrderType.MARKET, reference_price=None,
        )


async def test_venue_filters_when_loaded_set_the_lot_and_the_minimum() -> None:
    runtime, _, _ = build(symbol_filters={"step_size": "0.001", "min_notional": "100", "last_price": 50_000.0})
    intent = runtime._build_intent(
        symbol="BTC-USD", side=Side.BUY, quantity=0.0123456, signal_id="sig",
        order_type=OrderType.MARKET,
    )
    assert intent.quantity == pytest.approx(0.012), "quantized to the venue's step, down"
    with pytest.raises(OrderFilterError, match="below the minimum 100"):
        runtime._build_intent(
            symbol="BTC-USD", side=Side.BUY, quantity=0.001, signal_id="sig-2",
            order_type=OrderType.MARKET,
        )


async def test_an_unknown_symbol_is_refused_by_the_builder() -> None:
    runtime, _, _ = build()
    with pytest.raises(OrderFilterError, match="unknown instrument"):
        runtime._build_intent(
            symbol="DOGE-USD", side=Side.BUY, quantity=1.0, signal_id="sig",
            order_type=OrderType.MARKET, reference_price=1.0,
        )


async def test_exits_are_never_blocked_by_the_minimum_notional(monkeypatch: pytest.MonkeyPatch) -> None:
    """A position opened under the normal rules must close even when the minimum could
    not be met by the closing size: reduce-only orders are exempt by design."""
    runtime, execution, market = build(max_holding_bars=1)
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        monkeypatch.setattr(live_module, "DEFAULT_UNIVERSE", _universe(min_notional=1e9))
        sent_before = execution.submissions
        for _ in range(5):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is None:
                break
        assert runtime._open_trade is None, "the time stop closed the position"
        assert execution.submissions > sent_before
        assert runtime.counters["exits_time"] == 1
        assert runtime.state is LiveState.RUNNING
    finally:
        await runtime.stop()
