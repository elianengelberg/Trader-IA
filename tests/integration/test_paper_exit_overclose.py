"""R17 — the remainder of a position while it is being closed (scenario engine, paper).

Definition (new review, row R17): "sin stop para el remanente: presente en live por diseño
mientras la salida está en vuelo; en el motor paper hay riesgo de sobrecierre". What the base
does: ``RuntimeEngine._flatten`` cancels the protective stop and sends a MARKET exit for the
whole position. When that exit fills only in part (the participation cap, or the simulator's
random partial fills, 15 % by default), the fill makes ``_sync_protective_stop`` place a NEW
stop for the remainder while the exit's remainder is still working — two closing orders for
one position. If both execute, the long becomes a short the strategy never chose, and the engine
then "protects" that short with a stop of its own. A second ``_flatten`` (the reversal still
approved on the next bar) adds a third closing order. Reproduced here, deterministically.

The invariant: at every bar end, the closing orders working for a position cover exactly what
is held — never more (over-close), never less while an exit is in progress.
"""

from __future__ import annotations

from tia.core.config import Environment, settings_for_env
from tia.domain.enums import OrderType, Side, TimeInForce
from tia.domain.orders import OrderIntent
from tia.runtime.engine import RuntimeConfig, RuntimeEngine

SYMBOL = "BTC-USD"
CLOSING = ("flatten:", "protective:")


async def engine_with_a_long(quantity: float = 0.05) -> RuntimeEngine:
    """A scenario engine driven bar by bar, holding a long with its protective stop."""
    settings = settings_for_env(Environment.TESTING)
    settings = settings.model_copy(update={"execution": settings.execution.model_copy(
        update={"reject_probability": 0.0, "partial_fill_probability": 0.0})})
    config = RuntimeConfig(scenario="trend_down", symbols=(SYMBOL,), initial_capital=10_000.0, seed=1,
                           bar_interval_seconds=0.0, llm_enabled=False, news_enabled=False)
    engine = RuntimeEngine(settings, config, persist=None)

    async def no_loop() -> None:
        return None

    engine._loop = no_loop  # type: ignore[method-assign]  # the test drives the bars
    await engine.start()
    for _ in range(60):
        await engine._tick()
    engine._new_trades_allowed = False
    await engine._execution.submit_order(OrderIntent(
        intent_id="r17-entry", client_order_id=OrderIntent.build_client_order_id(
            signal_id="r17:entry", symbol=SYMBOL, side=Side.BUY, quantity=quantity, order_type=OrderType.MARKET),
        signal_id="r17:entry", risk_decision_id="r17", symbol=SYMBOL, side=Side.BUY, quantity=quantity,
        order_type=OrderType.MARKET, time_in_force=TimeInForce.GTC, created_at=engine._clock.now(),
    ))
    await engine._tick()
    assert held(engine) == quantity
    engine._stop_price[SYMBOL] = engine._streams[SYMBOL].buffer[-1].close * 0.995
    await engine._sync_protective_stop(SYMBOL)
    return engine


def held(engine: RuntimeEngine) -> float:
    position = engine._execution.portfolio.positions.get(SYMBOL)
    return 0.0 if position is None else round(position.quantity, 9)


async def closing_working(engine: RuntimeEngine) -> float:
    orders = await engine._execution.get_orders()
    return round(sum(o.quantity - o.filled_quantity for o in orders
                     if not o.state.is_terminal and o.signal_id.startswith(CLOSING)), 9)


async def exit_in_three_bars(engine: RuntimeEngine) -> None:
    """The exit's market order fills about a third of the position per bar."""
    bar = engine._streams[SYMBOL].buffer[-1]
    cap = held(engine) / 3 / max(bar.volume, 1e-9)
    engine._execution._config = engine._execution._config.model_copy(update={"max_participation_rate": cap})
    await engine._flatten(SYMBOL, "signal reversed", bar)


async def test_r17_a_partial_exit_and_the_remainder_stop_never_close_more_than_the_position() -> None:
    engine = await engine_with_a_long()
    try:
        await exit_in_three_bars(engine)
        # The remainder's stop is set where it triggers on the next bar: the worst case.
        engine._stop_price[SYMBOL] = engine._streams[SYMBOL].buffer[-1].close * 1.02
        seen: list[tuple[float, float]] = []
        for _ in range(6):
            await engine._tick()
            seen.append((held(engine), await closing_working(engine)))
        assert all(position >= 0.0 for position, _ in seen), f"the long was closed past zero: {seen}"
        assert all(working <= abs(position) + 1e-9 for position, working in seen), f"closing orders exceed the position: {seen}"
        assert held(engine) == 0.0
    finally:
        await engine.stop()


async def test_r17_a_second_flatten_while_the_first_is_working_sends_nothing_more() -> None:
    engine = await engine_with_a_long()
    try:
        await exit_in_three_bars(engine)
        await engine._tick()  # one partial fill
        position = held(engine)
        assert 0 < position < 0.05
        await engine._flatten(SYMBOL, "signal reversed", engine._streams[SYMBOL].buffer[-1])
        exits = [o for o in await engine._execution.get_orders() if o.signal_id.startswith("flatten:")]
        assert len(exits) == 1, "a reversal approved again on the next bar must not send a second exit"
        assert await closing_working(engine) <= position + 1e-9
    finally:
        await engine.stop()


async def test_r17_while_an_exit_works_the_remainder_is_covered_exactly_once() -> None:
    engine = await engine_with_a_long()
    try:
        await exit_in_three_bars(engine)
        for _ in range(5):
            await engine._tick()
            position = held(engine)
            if position == 0.0:
                break
            assert await closing_working(engine) == abs(position), "the remainder is covered once: not twice, not zero"
        assert held(engine) == 0.0
    finally:
        await engine.stop()


async def test_r17_a_stop_out_with_no_exit_working_still_protects_the_whole_position() -> None:
    """Regression guard for the fix: without an exit in flight the stop covers everything held."""
    engine = await engine_with_a_long()
    try:
        await engine._tick()
        assert await closing_working(engine) == held(engine) == 0.05
        orders = [o for o in await engine._execution.get_orders() if not o.state.is_terminal]
        assert [o.order_type for o in orders] == [OrderType.STOP]
    finally:
        await engine.stop()


async def test_r17_an_exit_the_simulator_refuses_leaves_the_position_protected_again_at_once() -> None:
    engine = await engine_with_a_long()
    try:
        # The simulator's own rejection path (``_should_reject``), aimed at the exit alone.
        real = engine._execution._should_reject
        engine._execution._should_reject = lambda order: order.signal_id.startswith("flatten:") or real(order)
        await engine._flatten(SYMBOL, "signal reversed", engine._streams[SYMBOL].buffer[-1])
        [exit_order] = [o for o in await engine._execution.get_orders() if o.signal_id.startswith("flatten:")]
        assert exit_order.state.is_terminal and not exit_order.filled_quantity, "precondition: the exit was refused"
        assert held(engine) == 0.05
        stops = [o for o in await engine._execution.get_orders() if not o.state.is_terminal and o.order_type is OrderType.STOP]
        assert len(stops) == 1 and stops[0].quantity == 0.05, "protected again at once, not at the next fill"
    finally:
        await engine.stop()
