"""The paper matching engine.

Most of these tests assert *pessimism*: that the engine refuses the optimistic
assumption at every point where one was available. A simulator that fills at the
signal bar's close, fills unlimited size in a thin bar, or applies slippage in the
direction that helps you will report an edge that does not survive contact with a real
venue — and the report will look entirely plausible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import ExecutionSimConfig
from tia.core.errors import DuplicateOrderError, LiveActivationError
from tia.core.rng import RngRegistry
from tia.domain.enums import AssetClass, OrderState, OrderType, Side, TimeInForce
from tia.domain.instruments import DEFAULT_UNIVERSE, Instrument, InstrumentUniverse
from tia.domain.market import Candle
from tia.domain.orders import OrderIntent
from tia.execution.paper import PaperExecutionProvider
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider

START = datetime(2026, 1, 5, tzinfo=UTC)

#: Rejections and forced partials are stochastic; the tests that are not *about* them
#: switch them off so a failure means the thing under test broke.
DETERMINISTIC = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)


def bar(
    *,
    index: int = 1,
    symbol: str = "BTC-USD",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10_000.0,
) -> Candle:
    open_time = START + timedelta(minutes=index)
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        trade_count=100,
        provider="test",
    )


def intent(
    *,
    symbol: str = "BTC-USD",
    side: Side = Side.BUY,
    quantity: float = 1.0,
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
    stop_price: float | None = None,
    take_profit_price: float | None = None,
    signal_id: str = "sig-1",
    created_at: datetime = START,
) -> OrderIntent:
    coid = OrderIntent.build_client_order_id(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
    )
    return OrderIntent(
        intent_id=f"int-{signal_id}",
        client_order_id=coid,
        signal_id=signal_id,
        risk_decision_id=f"risk-{signal_id}",
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        time_in_force=TimeInForce.GTC,
        created_at=created_at,
    )


@pytest.fixture
def provider(clock: SimulatedClock, rng: RngRegistry) -> PaperExecutionProvider:
    return PaperExecutionProvider(DETERMINISTIC, DEFAULT_UNIVERSE, clock, rng)


# --------------------------------------------------------------------------- scope rule


def test_a_non_simulated_provider_cannot_be_constructed_from_a_flag_alone() -> None:
    """Declaring liveness is not the same as being allowed to be live.

    A live provider needs a token from the activation gate, which can only be minted when
    every check in :data:`~tia.live.gate.REQUIRED_CHECKS` has passed. So no config flag, no
    environment variable and no later edit to a capabilities object can turn one on: the
    gate has to actually pass first. ``tests/unit/test_scope_boundary.py`` covers the same
    boundary from the package side, including that the token cannot be forged.
    """

    class Live(ExecutionProvider):
        async def submit_order(self, intent):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def cancel_order(self, order_id):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_order(self, order_id):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_orders(self, *, open_only=False):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_positions(self):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_balance(self):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_trades(self, *, limit=100):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_pnl(self):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

        async def get_portfolio(self):  # type: ignore[no-untyped-def]  # pragma: no cover
            raise NotImplementedError

    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        Live(ExecutionCapabilities(name="live-venue", is_simulated=False))

    # A simulator needs nothing at all.
    assert Live(ExecutionCapabilities(name="sim")).capabilities.is_simulated


def test_the_paper_provider_declares_itself_simulated(
    provider: PaperExecutionProvider,
) -> None:
    assert provider.capabilities.is_simulated is True
    assert provider.name == "paper"
    assert "No order book" in provider.capabilities.notes


# --------------------------------------------------------------------------- idempotency


async def test_duplicate_client_order_id_returns_the_same_order(
    provider: PaperExecutionProvider,
) -> None:
    """The retry test. A timeout, a redelivered event or a reconnect must not open a
    second position — which is the failure mode that turns one unit of risk into two."""
    first = await provider.submit_order(intent())
    second = await provider.submit_order(intent())

    assert second.order_id == first.order_id
    assert second is first
    assert len(await provider.get_orders()) == 1


async def test_a_duplicate_retry_does_not_double_the_position(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(quantity=2.0))
    await provider.submit_order(intent(quantity=2.0))  # the retry
    clock.advance_to(START + timedelta(minutes=2))
    provider.on_bar(bar())

    positions = await provider.get_positions()
    assert positions["BTC-USD"].quantity == pytest.approx(2.0)


async def test_different_signals_are_not_deduplicated(
    provider: PaperExecutionProvider,
) -> None:
    a = await provider.submit_order(intent(signal_id="sig-a"))
    b = await provider.submit_order(intent(signal_id="sig-b"))
    assert a.order_id != b.order_id


# --------------------------------------------------------------------------- lifecycle


async def test_a_submitted_order_reaches_acknowledged(
    provider: PaperExecutionProvider,
) -> None:
    order = await provider.submit_order(intent())
    assert order.state is OrderState.ACKNOWLEDGED
    # Latency is recorded on the timestamps rather than slept through.
    assert order.updated_at > order.created_at


async def test_an_unknown_instrument_is_rejected(
    provider: PaperExecutionProvider,
) -> None:
    order = await provider.submit_order(intent(symbol="DOGE-USD"))
    assert order.state is OrderState.REJECTED
    assert order.reject_reason == "unknown instrument"


async def test_shorting_a_non_shortable_instrument_is_rejected(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    universe = InstrumentUniverse(
        instruments=(
            Instrument(
                symbol="NOSHORT",
                asset_class=AssetClass.EQUITY,
                tick_size=0.01,
                lot_size=0.01,
                shortable=False,
            ),
        )
    )
    provider = PaperExecutionProvider(DETERMINISTIC, universe, clock, rng)
    order = await provider.submit_order(intent(symbol="NOSHORT", side=Side.SELL))
    assert order.state is OrderState.REJECTED
    assert order.reject_reason == "short selling not permitted"


async def test_cancelling_an_open_order_moves_it_through_cancel_requested(
    provider: PaperExecutionProvider,
) -> None:
    order = await provider.submit_order(intent())
    cancelled = await provider.cancel_order(order.order_id)
    assert cancelled.state is OrderState.CANCELLED
    assert not (await provider.get_orders(open_only=True))


async def test_cancelling_a_terminal_order_is_a_no_op(
    provider: PaperExecutionProvider,
) -> None:
    order = await provider.submit_order(intent(symbol="DOGE-USD"))
    assert order.state is OrderState.REJECTED
    again = await provider.cancel_order(order.order_id)
    assert again.state is OrderState.REJECTED


async def test_cancelling_an_unknown_order_raises(
    provider: PaperExecutionProvider,
) -> None:
    with pytest.raises(DuplicateOrderError):
        await provider.cancel_order("ord-does-not-exist")


async def test_stale_orders_expire(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """An order resting on a thesis that has since been invalidated is exactly the
    'trade with an expired signal' the platform is built to avoid."""
    order = await provider.submit_order(intent(order_type=OrderType.LIMIT, limit_price=50.0))
    clock.advance_to(START + timedelta(hours=5))
    expired = provider.expire_stale_orders(older_than=timedelta(hours=1))

    assert [o.order_id for o in expired] == [order.order_id]
    assert order.state is OrderState.EXPIRED
    assert order.reject_reason == "order age exceeded TTL"


# --------------------------------------------------------------------------- no look-ahead


async def test_a_market_order_fills_at_the_next_bars_open_not_the_signal_bars_close(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """The single most important property in the file.

    Filling at the close of the bar that produced the signal lets a strategy transact at
    a price it could not have known. Every backtest that does it reports an edge that is
    an artefact of the simulator.
    """
    await provider.submit_order(intent())
    clock.advance_to(START + timedelta(minutes=2))

    next_bar = bar(open_=100.0, high=120.0, low=99.0, close=119.0)
    fills = provider.on_bar(next_bar)

    assert len(fills) == 1
    # Anchored to the open, not the close — and the gap here is large enough that a
    # close-anchored implementation could not pass by coincidence.
    assert fills[0].price < 105.0
    assert fills[0].price >= next_bar.open


async def test_an_order_cannot_be_filled_by_the_bar_that_created_it(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """A decision taken on bar *t*'s close is executed against bar *t+1*. Letting bar
    *t* fill it would be look-ahead by one bar, which is enough to make almost any
    mean-reversion strategy look profitable."""
    same_bar = bar(index=0)
    clock.advance_to(same_bar.close_time)
    await provider.submit_order(intent(created_at=same_bar.close_time))
    assert provider.on_bar(same_bar) == []

    # ...and the following bar does fill it.
    assert len(provider.on_bar(bar(index=1))) == 1


# --------------------------------------------------------------------------- fill prices


async def test_slippage_is_adverse_for_a_buy(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(side=Side.BUY))
    clock.advance_to(START + timedelta(minutes=2))
    reference = bar()
    fill = provider.on_bar(reference)[0]

    assert fill.price > reference.open, "a buy must not be filled below the reference"
    assert fill.slippage_bps > 0


async def test_slippage_is_adverse_for_a_sell(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(side=Side.SELL))
    clock.advance_to(START + timedelta(minutes=2))
    reference = bar()
    fill = provider.on_bar(reference)[0]

    assert fill.price < reference.open, "a sell must not be filled above the reference"
    assert fill.slippage_bps > 0


async def test_a_fill_never_happens_at_a_price_the_bar_did_not_trade(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    """A price outside the bar's range is not a fill, it is a fiction. Forced here with
    an absurd slippage configuration so the clamp is what is being tested."""
    config = ExecutionSimConfig(
        reject_probability=0.0,
        partial_fill_probability=0.0,
        base_slippage_bps=500.0,
        impact_coefficient=10.0,
    )
    provider = PaperExecutionProvider(config, DEFAULT_UNIVERSE, clock, rng)
    await provider.submit_order(intent())
    clock.advance_to(START + timedelta(minutes=2))

    reference = bar(open_=100.0, high=100.2, low=99.8, close=100.1)
    fill = provider.on_bar(reference)[0]
    assert reference.low <= fill.price <= reference.high


async def test_bigger_orders_pay_more_slippage(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    """Impact is sqrt-scaled in participation, so size costs more per unit. Without it a
    backtest reports a capacity the strategy does not have."""
    slippage: list[float] = []
    for quantity in (1.0, 500.0):
        p = PaperExecutionProvider(DETERMINISTIC, DEFAULT_UNIVERSE, SimulatedClock(START), rng)
        await p.submit_order(intent(quantity=quantity, signal_id=f"sig-{quantity}"))
        fill = p.on_bar(bar(volume=10_000.0, high=100.05, low=99.95, close=100.02))[0]
        slippage.append(fill.slippage_bps)

    assert slippage[1] > slippage[0]


async def test_a_limit_order_requires_the_price_to_trade_through_it(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """Touching a limit is not the same as filling at it: at the exact price there is no
    guarantee of queue priority, and assuming otherwise is free money in a backtest."""
    await provider.submit_order(intent(order_type=OrderType.LIMIT, limit_price=99.0))
    clock.advance_to(START + timedelta(minutes=2))

    touched = bar(open_=100.0, high=101.0, low=99.0, close=100.0)
    assert provider.on_bar(touched) == []

    through = bar(index=2, open_=100.0, high=101.0, low=98.5, close=99.5)
    assert len(provider.on_bar(through)) == 1


async def test_a_stop_fills_no_better_than_the_stop_level(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """A stop that gaps through fills at the gap, not at the stop. Modelling it the other
    way makes every stop-loss look like it worked."""
    await provider.submit_order(
        intent(side=Side.SELL, order_type=OrderType.STOP, stop_price=99.0)
    )
    clock.advance_to(START + timedelta(minutes=2))

    gapped = bar(open_=95.0, high=95.5, low=90.0, close=91.0)
    fill = provider.on_bar(gapped)[0]
    assert fill.price <= 95.0, "a gapped stop must not fill at the stop price"


async def test_a_stop_that_is_not_touched_does_not_fill(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(
        intent(side=Side.SELL, order_type=OrderType.STOP, stop_price=90.0)
    )
    clock.advance_to(START + timedelta(minutes=2))
    assert provider.on_bar(bar(open_=100.0, high=101.0, low=99.0)) == []


# --------------------------------------------------------------------------- liquidity


async def test_a_bar_can_only_absorb_a_fraction_of_its_volume(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """Without a participation cap a backtest fills an arbitrarily large order in a
    single thin bar — the most common way reported capacity exceeds the achievable."""
    await provider.submit_order(intent(quantity=1_000.0))
    clock.advance_to(START + timedelta(minutes=2))

    fill = provider.on_bar(bar(volume=1_000.0))[0]
    assert fill.quantity == pytest.approx(100.0)  # 10% of the bar's volume

    order = (await provider.get_orders())[0]
    assert order.state is OrderState.PARTIALLY_FILLED
    assert order.remaining_quantity == pytest.approx(900.0)


async def test_a_large_order_fills_across_several_bars(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(quantity=250.0))
    clock.advance_to(START + timedelta(minutes=2))

    for index in range(1, 6):
        provider.on_bar(bar(index=index, volume=1_000.0))

    order = (await provider.get_orders())[0]
    assert order.state is OrderState.FILLED
    assert order.filled_quantity == pytest.approx(250.0)
    assert len(order.fills) == 3


async def test_a_zero_volume_bar_fills_nothing(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent())
    clock.advance_to(START + timedelta(minutes=2))
    assert provider.on_bar(bar(volume=0.0)) == []


# --------------------------------------------------------------------------- accounting


async def test_fees_are_charged_and_recorded(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(quantity=10.0))
    clock.advance_to(START + timedelta(minutes=2))
    fill = provider.on_bar(bar())[0]

    expected = fill.notional * DETERMINISTIC.taker_fee_bps / 10_000.0
    assert fill.fee == pytest.approx(expected)
    assert fill.liquidity == "taker"

    pnl = await provider.get_pnl()
    assert pnl["fees"] == pytest.approx(expected)


async def test_a_limit_order_pays_the_maker_fee(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(order_type=OrderType.LIMIT, limit_price=99.5))
    clock.advance_to(START + timedelta(minutes=2))
    fill = provider.on_bar(bar(open_=100.0, high=100.5, low=99.0, close=99.2))[0]

    assert fill.liquidity == "maker"
    assert fill.fee == pytest.approx(fill.notional * DETERMINISTIC.maker_fee_bps / 10_000.0)


async def test_cash_moves_against_the_position(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    opening = await provider.get_balance()
    await provider.submit_order(intent(quantity=10.0))
    clock.advance_to(START + timedelta(minutes=2))
    fill = provider.on_bar(bar())[0]

    assert await provider.get_balance() == pytest.approx(
        opening - fill.notional - fill.fee
    )


async def test_a_round_trip_realizes_pnl_net_of_fees(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent(quantity=10.0, signal_id="open"))
    clock.advance_to(START + timedelta(minutes=2))
    entry = provider.on_bar(bar(index=1, open_=100.0, high=100.5, low=99.5))[0]

    await provider.submit_order(intent(quantity=10.0, side=Side.SELL, signal_id="close"))
    clock.advance_to(START + timedelta(minutes=4))
    exit_ = provider.on_bar(bar(index=3, open_=110.0, high=110.5, low=109.5, close=110.2))[0]

    pnl = await provider.get_pnl()
    gross = (exit_.price - entry.price) * 10.0
    assert pnl["realized"] == pytest.approx(gross - entry.fee - exit_.fee)
    assert not await provider.get_positions()


# --------------------------------------------------------------------------- stochastic


async def test_rejections_happen_when_configured(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    config = ExecutionSimConfig(reject_probability=0.5, partial_fill_probability=0.0)
    provider = PaperExecutionProvider(config, DEFAULT_UNIVERSE, clock, rng)

    states = [
        (await provider.submit_order(intent(signal_id=f"sig-{i}"))).state for i in range(40)
    ]
    rejected = [s for s in states if s is OrderState.REJECTED]
    assert 5 <= len(rejected) <= 35, "a 50% reject rate should reject a plausible share"


async def test_partial_fills_happen_when_configured(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    """Forced partials exist so downstream code that assumes 'submitted == filled'
    breaks in a test rather than in a run."""
    config = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=1.0)
    provider = PaperExecutionProvider(config, DEFAULT_UNIVERSE, clock, rng)
    await provider.submit_order(intent(quantity=1.0))
    clock.advance_to(START + timedelta(minutes=2))

    fill = provider.on_bar(bar(volume=1_000_000.0))[0]
    order = (await provider.get_orders())[0]
    assert fill.quantity < 1.0
    assert order.state is OrderState.PARTIALLY_FILLED


# --------------------------------------------------------------------------- determinism


async def test_two_runs_with_the_same_seed_are_identical(universe) -> None:  # type: ignore[no-untyped-def]
    """An experiment that cannot be replayed from its seed is not evidence."""
    config = ExecutionSimConfig(reject_probability=0.2, partial_fill_probability=0.5)

    async def run() -> list[tuple[float, float, float]]:
        provider = PaperExecutionProvider(
            config, universe, SimulatedClock(START), RngRegistry(4242)
        )
        out: list[tuple[float, float, float]] = []
        for i in range(20):
            await provider.submit_order(intent(signal_id=f"sig-{i}", quantity=1.0 + i))
            for fill in provider.on_bar(bar(index=i + 1, volume=5_000.0)):
                out.append((fill.quantity, fill.price, fill.fee))
        return out

    assert await run() == await run()


# --------------------------------------------------------------------------- snapshots


async def test_reset_clears_every_trace_of_the_previous_run(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    await provider.submit_order(intent())
    clock.advance_to(START + timedelta(minutes=2))
    provider.on_bar(bar())
    assert await provider.get_positions()

    provider.reset()
    assert not await provider.get_positions()
    assert not await provider.get_orders()
    assert not await provider.get_trades()
    assert await provider.get_balance() == pytest.approx(100_000.0)

    # A reset provider must accept the same client_order_id again — otherwise the
    # dedup map would leak across backtest runs.
    order = await provider.submit_order(intent())
    assert order.state is OrderState.ACKNOWLEDGED


async def test_the_snapshot_agrees_with_the_public_api(
    provider: PaperExecutionProvider, clock: SimulatedClock
) -> None:
    """A snapshot that disagrees with the query methods would make reconciliation report
    divergence that does not exist — or hide divergence that does."""
    await provider.submit_order(intent(quantity=5.0))
    clock.advance_to(START + timedelta(minutes=2))
    provider.on_bar(bar())

    assert provider.snapshot() == await provider.state_snapshot()
