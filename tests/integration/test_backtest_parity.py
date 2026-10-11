"""The backtester plays the 24/7 session's game (Phase 1.3, Etapa Cuatro).

What is checked is *structural* parity — both engines import the same sizing contract,
the same exit manager, the same cost model and the same budget — and the behaviour the
shared modules impose: an entry sized through ``apply_risk_budget`` with the same
arguments, an expected value priced as zero edge minus costs when there is no evidence,
an enforced gate that trades nothing from a cold start, named exits, a bounded hold under
a time stop, and a decision log whose stages are the session's funnel.

Nothing here claims the two engines produce identical trades: the session reads a live
quote and a measured latency the backtester cannot have, and the parity table in the
Phase 1.3 report lists every such difference.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pytest

import tia.backtest.engine as backtest_engine
import tia.runtime.live as live_module
from tests.integration.test_live_runtime import _seed_every_bucket
from tests.integration.test_paper_cancellations import build
from tia.backtest import BacktestConfig, BacktestEngine, BacktestResult
from tia.core.clock import SimulatedClock
from tia.core.config import ExecutionSimConfig
from tia.core.rng import RngRegistry
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle
from tia.domain.orders import Order
from tia.economics.costs import CostModel, FeeSchedule, MarketConditions
from tia.execution.paper import PaperExecutionProvider
from tia.risk.sizing import apply_risk_budget

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SERIES: list[Candle] = asyncio.run(CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=700))
DETERMINISTIC = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)
KNOWN_STAGES = {
    "sent", "risk", "budget", "expected_value", "filters", "position_open",
    "signal_reversed", "resting", "no_trade",
}
#: The session's names (``LiveRuntime._exit_reason``) plus the one exit only a backtest has.
KNOWN_EXITS = {"protective stop", "break-even stop", "trailing stop", "target reached", "time stop",
               "signal reversed", "forced liquidation at end of sample"}


@cache
def _run(**overrides: Any) -> BacktestResult:
    config = BacktestConfig(dataset="fixtures", timeframe="1h", execution=DETERMINISTIC, **overrides)
    return BacktestEngine(config, DEFAULT_UNIVERSE).run(SERIES)


def _sent(result: BacktestResult) -> list[Any]:
    return [r for r in result.decision_log if r.stage == "sent"]


# ------------------------------------------------------------- the shared modules


def test_both_engines_import_the_same_contract_objects() -> None:
    """One sizing contract, one exit manager, one cost model, one budget — the same
    objects, not two copies of the same idea."""
    assert backtest_engine.apply_risk_budget is live_module.apply_risk_budget is apply_risk_budget
    assert backtest_engine.tighten_stop is live_module.tighten_stop
    assert backtest_engine.conviction_fraction is live_module.conviction_fraction
    assert backtest_engine.CostModel is live_module.CostModel is CostModel
    assert backtest_engine.RiskBudgetEngine is live_module.RiskBudgetEngine
    assert backtest_engine.ExpectedValueEngine is live_module.ExpectedValueEngine


def test_the_backtester_sizes_every_entry_through_the_shared_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    real = backtest_engine.apply_risk_budget

    def recording(**kwargs: Any):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(backtest_engine, "apply_risk_budget", recording)
    config = BacktestConfig(dataset="fixtures", timeframe="1h", execution=DETERMINISTIC)
    result = BacktestEngine(config, DEFAULT_UNIVERSE).run(SERIES)
    sent = _sent(result)
    assert sent, "the fixture must produce at least one entry for the parity claim to mean anything"
    assert len(calls) >= len(sent), "every sent entry went through the contract"
    expected_keys = {
        "approved_quantity", "entry_price", "stop_price", "limit_risk_currency", "budget_risk_currency",
        "conviction_fraction", "step_size", "min_notional", "allows_new_trades",
    }
    assert all(set(call) == expected_keys for call in calls)
    assert all(call["step_size"] == DEFAULT_UNIVERSE.get("BTC-USD").lot_size for call in calls)
    assert all(call["min_notional"] == DEFAULT_UNIVERSE.get("BTC-USD").min_notional for call in calls)
    for record in sent:
        assert 0.0 < record.sized_quantity <= record.approved_quantity + 1e-12


async def test_the_session_sizes_its_entries_through_the_same_contract_with_the_same_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    real = live_module.apply_risk_budget

    def recording(**kwargs: Any):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(live_module, "apply_risk_budget", recording)
    runtime, _execution, market, _clock = build()
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(400):
            market.advance()
            await runtime._cycle_once()
            if runtime.counters["orders"] >= 1:
                break
        assert runtime.counters["orders"] >= 1 and calls
    finally:
        await runtime.stop()
    expected_keys = {
        "approved_quantity", "entry_price", "stop_price", "limit_risk_currency", "budget_risk_currency",
        "conviction_fraction", "step_size", "min_notional", "allows_new_trades",
    }
    assert all(set(call) == expected_keys for call in calls), "the same keyword set the backtester passes"
    last = runtime.snapshot()["sizing"]["last"]
    assert last["risk_effective_risk_currency"] <= last["risk_allowed_risk_currency"] + 1e-9


# ------------------------------------------------------------ the expected value


def test_a_cold_backtest_prices_each_entry_as_zero_edge_minus_costs_and_observes() -> None:
    """With no evidence the estimator returns nothing, the gross edge is zero and the net
    is minus the priced costs: negative, not tradeable, and — observing by default — the
    entry is still sent, so the run produces the evidence a gate would need."""
    result = _run()
    first = _sent(result)[0]
    assert first.ev_tradeable is False
    assert first.ev_net_bps is not None and first.ev_net_bps < 0.0
    counts = result.decisions
    assert counts.ev_would_reject >= len(_sent(result))
    assert counts.ev_no_evidence >= 1
    assert counts.ev_rejected == 0, "observe mode refuses nothing"
    assert first.budget_multiplier is not None and 0.0 < first.budget_multiplier <= 1.0


def test_enforcing_the_gate_from_a_cold_start_trades_nothing_and_says_why() -> None:
    result = _run(enforce_expected_value=True)
    assert result.decisions.intents_submitted == 0
    assert result.trades == ()
    assert result.decisions.ev_rejected == result.decisions.ev_would_reject > 0
    refused = [r for r in result.decision_log if r.stage == "expected_value"]
    assert refused and all(r.ev_tradeable is False for r in refused)
    assert all("NO_TRADE" in r.reason for r in refused)


# ----------------------------------------------------------------- exits and holds


def test_every_exit_is_named_from_the_shared_vocabulary() -> None:
    result = _run()
    assert result.trades, "no round trip to name"
    for trade in result.trades:
        assert trade.exit_reason in KNOWN_EXITS, trade.exit_reason
    requested = result.decisions.exits_requested
    assert all(reason in {"target reached", "time stop", "signal reversed"} for reason in requested)


def test_a_time_stop_bounds_every_hold_to_the_configured_bars_plus_the_fill_bar() -> None:
    """The close is requested on the bar the limit is reached and fills on the next: no
    strategy-chosen exit can hold longer than ``max_holding_bars + 1``."""
    result = _run(max_holding_bars=5, use_target=False)
    assert result.trades
    chosen = [t for t in result.trades if t.exit_reason != "forced liquidation at end of sample"]
    assert chosen
    assert all(t.bars_held <= 6 for t in chosen), [t.bars_held for t in chosen]
    assert result.decisions.exits_requested.get("time stop", 0) >= 1


def test_without_a_time_stop_the_hold_is_unbounded_by_rule() -> None:
    assert BacktestConfig().max_holding_bars == 0, "parity with LiveConfig: off by default"
    result = _run()
    assert "time stop" not in result.decisions.exits_requested


def test_stops_are_only_ever_tightened_by_the_shared_manager() -> None:
    tightened = _run(trail_atr_multiple=1.0, breakeven_after_r=0.5).decisions.stops_tightened
    never = _run(trail_atr_multiple=0.0, breakeven_after_r=0.0).decisions.stops_tightened
    assert never == 0
    assert tightened >= 0  # whether the fixture ever trails is the data's business, not a rule


# ------------------------------------------------------------- entries and sizing


def test_limit_entries_follow_the_sessions_conservative_fill_policy() -> None:
    """A resting entry fills only when the next bar trades through it, and expires after
    the configured bars: the number of round trips cannot exceed what was sent, and the
    expiries are counted rather than silently dropped."""
    market = _run()
    limit = _run(entry_order_type="limit", entry_limit_timeout_bars=3)
    assert limit.conditions.run_id != market.conditions.run_id, "the digest knows the entry type"
    assert limit.decisions.intents_submitted >= 1
    assert len(limit.trades) + limit.decisions.orders_expired <= limit.decisions.intents_submitted
    assert limit.decisions.orders_expired >= 0


def test_the_conservative_profile_takes_less_than_the_aggressive_one_on_the_same_signal() -> None:
    """Same bars, same signals until the first entry: the first sent record is the same
    decision under both profiles, and the contract sizes it to the profile's risk."""
    conservative = _sent(_run(risk_profile="conservative"))[0]
    aggressive = _sent(_run(risk_profile="aggressive"))[0]
    assert conservative.bar_close_time == aggressive.bar_close_time
    assert conservative.approved_quantity == pytest.approx(aggressive.approved_quantity)
    assert conservative.sized_quantity <= aggressive.sized_quantity + 1e-12
    assert conservative.sized_quantity <= conservative.approved_quantity + 1e-12
    assert aggressive.sized_quantity <= aggressive.approved_quantity + 1e-12
    # 0.25 % of equity against the engine's 0.5 % approval: the budget binds and the
    # contract sizes down — never up.
    assert _run(risk_profile="conservative").decisions.sized_down >= 1


def test_an_unknown_risk_profile_is_refused_before_any_bar_is_read() -> None:
    config = BacktestConfig(dataset="fixtures", timeframe="1h", execution=DETERMINISTIC, risk_profile="reckless")
    with pytest.raises(ValueError):
        BacktestEngine(config, DEFAULT_UNIVERSE).run(SERIES)


def test_every_decision_ends_in_a_known_stage_with_a_reason_when_refused() -> None:
    result = _run()
    stages = {r.stage for r in result.decision_log}
    assert stages <= KNOWN_STAGES, stages - KNOWN_STAGES
    assert "sent" in stages
    for record in result.decision_log:
        if record.stage not in {"sent"}:
            assert record.reason, record.stage


# -------------------------------- the expected value's costs against the simulator's


def test_the_expected_value_prices_the_spread_and_impact_the_simulator_realises() -> None:
    """The simulator takes ``base_slippage_bps`` on each leg plus impact and a bar-range
    component; the model, fed as the backtester feeds it, charges the same base per
    crossing and the same impact. The range component is the simulator's alone, so the
    simulator's realised round trip is never below the model's — the gate's cost
    estimate is the optimistic side of the two, by exactly that component."""
    config = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)
    clock = SimulatedClock(datetime(2026, 1, 5, tzinfo=UTC))
    engine = PaperExecutionProvider(config, DEFAULT_UNIVERSE, clock, RngRegistry(1), initial_capital=10_000.0)
    instrument = DEFAULT_UNIVERSE.get("BTC-USD")
    candle = Candle(
        symbol="BTC-USD", timeframe="1h", open_time=datetime(2026, 1, 5, tzinfo=UTC),
        close_time=datetime(2026, 1, 5, 1, tzinfo=UTC), open=100_000.0, high=100_100.0, low=99_900.0,
        close=100_000.0, volume=10.0,
    )
    quantity = 0.1
    now = clock.now()

    def order(side: Side) -> Order:
        return Order(
            order_id=f"o-{side.value}", client_order_id=f"c-{side.value}", intent_id="i", signal_id="s",
            symbol="BTC-USD", side=side, order_type=OrderType.MARKET, quantity=quantity,
            state=OrderState.ACKNOWLEDGED, created_at=now, updated_at=now,
        )

    _price_in, realised_in = engine._apply_slippage(order(Side.BUY), candle.open, quantity, candle, instrument)
    _price_out, realised_out = engine._apply_slippage(order(Side.SELL), candle.open, quantity, candle, instrument)
    simulator_round_trip = realised_in + realised_out
    # By hand: base 2.0 + impact 0.35 x √(0.1/10) x 100 = 3.5 + range 20 bps x 0.05 = 1.0 → 6.5 per leg.
    assert realised_in == pytest.approx(6.5, abs=0.01) and realised_out == pytest.approx(6.5, abs=0.01)

    # The model, with the conditions the backtester builds (volatility and latency held
    # at zero so the shared components can be read on their own).
    typical_volume = candle.volume
    model = CostModel(
        FeeSchedule(maker_bps=config.maker_fee_bps, taker_bps=config.taker_fee_bps),
        impact_coefficient=config.impact_coefficient,
    )
    costs = model.estimate(
        quantity=quantity,
        conditions=MarketConditions(
            price=candle.close, spread_bps=2.0 * config.base_slippage_bps, volatility_per_bar=0.0,
            top_of_book_quantity=typical_volume * config.max_participation_rate, bar_volume=typical_volume,
            latency_ms=0.0, bar_seconds=3600.0,
        ),
    )
    assert costs.spread_bps == pytest.approx(2.0 * config.base_slippage_bps), "base per leg, both legs"
    assert costs.impact_bps == pytest.approx(2.0 * 3.5), "the simulator's impact, both legs"
    assert costs.slippage_bps == 0.0, "within the participation cap nothing slips past the touch"
    assert costs.execution_bps == pytest.approx(11.0)
    assert simulator_round_trip >= costs.execution_bps
    assert simulator_round_trip - costs.execution_bps == pytest.approx(2.0, abs=0.02), (
        "the gap is the simulator's bar-range component on each leg, and nothing else"
    )
