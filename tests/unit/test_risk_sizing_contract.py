"""The sizing contract (Phase 1.3): the risk budget's multipliers reach the size.

Every scenario checks the **money at the stop**, not only the quantity. Reference numbers
are computed by hand in each test from the formula::

    allowed = min(equity x limit_pct, equity x profile_pct x multipliers) x conviction
    quantity = min(approved, allowed / |entry - stop|), rounded DOWN to the step
    refused when quantity x entry < min_notional  (never raised to reach it)
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.domain.enums import Direction
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.portfolio import PortfolioState
from tia.risk.budget import PROFILES, BudgetInputs, RiskBudgetEngine, RiskProfileName
from tia.risk.engine import RiskEngine
from tia.risk.sizing import apply_risk_budget, compute_size, implied_risk

EQUITY = 10_000.0
ENTRY = 100_000.0
STOP = 99_000.0  # 1,000 per unit at the stop
STEP = 0.000001  # BTC-USD lot
MIN_NOTIONAL = 10.0
LIMIT_RISK = EQUITY * 0.5 / 100.0  # 50: RiskLimits.max_risk_per_trade_pct default


def inputs(*, equity: float = EQUITY, drawdown: float = 0.0, vol: float = 0.0, losses: int = 0,
           trades_today: int = 0, exposure: float = 0.0) -> BudgetInputs:
    return BudgetInputs(
        equity=equity, peak_equity=equity / (1 - drawdown / 100.0) if drawdown else equity,
        drawdown_pct=drawdown, realised_annual_volatility=vol, consecutive_losses=losses,
        trades_today=trades_today, open_gross_exposure_pct=exposure,
    )


def sized(*, approved: float = 0.05, budget_risk: float, conviction: float = 1.0, limit: float = LIMIT_RISK,
          entry: float = ENTRY, stop: float | None = STOP, allows: bool = True, step: float = STEP,
          min_notional: float = MIN_NOTIONAL):  # type: ignore[no-untyped-def]
    return apply_risk_budget(
        approved_quantity=approved, entry_price=entry, stop_price=stop, limit_risk_currency=limit,
        budget_risk_currency=budget_risk, conviction_fraction=conviction, step_size=step,
        min_notional=min_notional, allows_new_trades=allows,
    )


# 1. base risk 0.5 % with a known stop
def test_base_risk_of_half_a_percent_with_a_known_stop() -> None:
    budget = RiskBudgetEngine(RiskProfileName.BALANCED).compute(inputs())  # 0.5 % x 1 x 1 x 1 = 50
    assert budget.risk_currency == pytest.approx(50.0)
    out = sized(budget_risk=budget.risk_currency)
    assert out.quantity == pytest.approx(0.05)  # 50 / 1,000
    assert out.effective_risk_currency == pytest.approx(50.0)
    assert out.limiting_constraint == "risk_engine"  # approved 0.05 was exactly the budget


# 2. a profile whose risk per trade is not the default
def test_the_conservative_profile_risks_a_quarter_percent_not_the_limits_half() -> None:
    budget = RiskBudgetEngine(RiskProfileName.CONSERVATIVE).compute(inputs())  # 0.25 % = 25
    out = sized(budget_risk=budget.risk_currency)
    assert out.quantity == pytest.approx(0.025) and out.effective_risk_currency == pytest.approx(25.0)
    assert out.limiting_constraint == "risk_budget"


def test_the_risk_limit_is_a_ceiling_the_aggressive_profile_cannot_exceed() -> None:
    budget = RiskBudgetEngine(RiskProfileName.AGGRESSIVE).compute(inputs())  # 1.0 % = 100
    assert budget.risk_currency == pytest.approx(100.0)
    out = sized(budget_risk=budget.risk_currency, approved=0.1)
    assert out.allowed_risk_currency == pytest.approx(LIMIT_RISK)
    assert out.effective_risk_currency == pytest.approx(50.0) and out.quantity == pytest.approx(0.05)
    assert out.limiting_constraint == "risk_limit"


# 3. multiplier 1.0
def test_a_multiplier_of_one_changes_nothing() -> None:
    assert sized(budget_risk=50.0 * 1.0).quantity == pytest.approx(0.05)


# 4. multiplier 0.5
def test_a_multiplier_of_a_half_halves_the_money_at_the_stop() -> None:
    out = sized(budget_risk=50.0 * 0.5)
    assert out.quantity == pytest.approx(0.025) and out.effective_risk_currency == pytest.approx(25.0)


# 5. multiplier 0
def test_a_multiplier_of_zero_refuses_the_entry() -> None:
    out = sized(budget_risk=0.0)
    assert not out.accepted and out.refused_reason == "zero_risk_budget"


# 6. drawdown deepening into the emergency state
def test_drawdown_shrinks_the_size_and_the_emergency_state_refuses_it() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)  # defensive 5 %, emergency 10 %, floor 0.5
    normal = sized(budget_risk=engine.compute(inputs(drawdown=0.0)).risk_currency)
    half_way = sized(budget_risk=engine.compute(inputs(drawdown=2.5)).risk_currency)  # 1 - 0.5 x 0.5 = 0.75
    defensive = sized(budget_risk=engine.compute(inputs(drawdown=7.5)).risk_currency)  # 0.5 x 0.5 = 0.25
    assert half_way.effective_risk_currency == pytest.approx(0.75 * normal.effective_risk_currency)
    assert defensive.effective_risk_currency == pytest.approx(0.25 * normal.effective_risk_currency)
    emergency = engine.compute(inputs(drawdown=12.0))
    assert emergency.allows_new_trades is False
    out = sized(budget_risk=emergency.risk_currency, allows=emergency.allows_new_trades)
    assert not out.accepted and out.refused_reason == "budget_blocks_new_trades"


# 7. a losing streak
def test_a_losing_streak_halves_the_budget_and_the_size_follows() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)  # dampener after 4 losses
    before = sized(budget_risk=engine.compute(inputs(losses=3)).risk_currency)
    after = sized(budget_risk=engine.compute(inputs(losses=4)).risk_currency)
    worse = sized(budget_risk=engine.compute(inputs(losses=5)).risk_currency)
    assert after.effective_risk_currency == pytest.approx(0.5 * before.effective_risk_currency)
    assert worse.effective_risk_currency == pytest.approx(0.25 * before.effective_risk_currency)


# 8. elevated volatility
def test_high_volatility_shrinks_the_size_in_proportion_and_low_volatility_never_grows_it() -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)  # target 0.20
    calm = sized(budget_risk=engine.compute(inputs(vol=0.10)).risk_currency)
    target = sized(budget_risk=engine.compute(inputs(vol=0.20)).risk_currency)
    wild = sized(budget_risk=engine.compute(inputs(vol=0.80)).risk_currency)
    assert calm.effective_risk_currency == pytest.approx(target.effective_risk_currency) == pytest.approx(50.0)
    assert wild.effective_risk_currency == pytest.approx(12.5)  # 0.20 / 0.80 = 0.25 x 50


# 9. stop absent, on the wrong side, invalid, too close
def test_an_absent_negative_or_degenerate_stop_refuses_the_entry() -> None:
    assert sized(budget_risk=50.0, stop=None).refused_reason == "no_stop_defined"
    assert sized(budget_risk=50.0, stop=-1.0).refused_reason == "invalid_stop"
    assert sized(budget_risk=50.0, stop=ENTRY).refused_reason == "invalid_stop"
    assert sized(budget_risk=50.0, stop=float("nan")).refused_reason == "no_stop_defined"
    # Too close: the risk engine's own sizing refuses before the budget is consulted.
    too_close = compute_size(
        equity=EQUITY, entry_price=ENTRY, stop_price=ENTRY * (1 - 0.0001), direction=Direction.LONG,
        instrument=DEFAULT_UNIVERSE.get("BTC-USD"), risk_per_trade_pct=0.5, max_position_notional_pct=20.0,
        available_capital=EQUITY,
    )
    assert too_close.quantity_after_limits == 0.0 and too_close.limiting_constraint == "stop_too_close"


# 10. equity absent, non-finite, zero, negative
@pytest.mark.parametrize("equity", [0.0, -5_000.0, float("nan"), float("inf")])
def test_an_unusable_equity_sizes_to_nothing(equity: float) -> None:
    engine = RiskBudgetEngine(RiskProfileName.BALANCED)
    budget = engine.compute(inputs(equity=equity)) if math.isfinite(equity) else None
    budget_risk = budget.risk_currency if budget is not None else equity * 0.005
    out = sized(budget_risk=budget_risk)
    assert not out.accepted
    assert out.refused_reason in {"zero_risk_budget", "invalid_risk_budget"}
    # And the risk engine itself refuses to size a non-positive account at all.
    if math.isfinite(equity):
        with pytest.raises(Exception, match="non-positive equity"):
            compute_size(
                equity=equity, entry_price=ENTRY, stop_price=STOP, direction=Direction.LONG,
                instrument=DEFAULT_UNIVERSE.get("BTC-USD"), risk_per_trade_pct=0.5,
                max_position_notional_pct=20.0, available_capital=EQUITY,
            )


# 11. step size and minimum notional
def test_the_step_rounds_down_and_the_minimum_notional_refuses_rather_than_raises() -> None:
    out = sized(budget_risk=25.7, step=0.001)  # 25.7 / 1,000 = 0.0257 -> 0.025
    assert out.quantity == pytest.approx(0.025)
    assert out.effective_risk_currency == pytest.approx(25.0)
    assert out.effective_risk_currency <= 25.7
    tiny = sized(budget_risk=0.05)  # 0.05 / 1,000 = 0.00005 BTC = $5 < $10 minimum
    assert not tiny.accepted and tiny.refused_reason == "below_min_notional"
    # The same budget with a venue minimum it does meet is accepted at the rounded size.
    assert sized(budget_risk=0.05, min_notional=1.0).quantity == pytest.approx(0.00005)


# 12. notional cap, margin and exposure limits come in through the risk engine's approval
def test_the_risk_engines_approval_is_a_ceiling_the_budget_never_exceeds() -> None:
    from tests.unit.test_risk_engine import NOW, quality, signal

    tight = RiskLimits(max_position_notional_pct=2.0)  # $200 at $10,000: 0.002 BTC
    engine = RiskEngine(tight, DEFAULT_UNIVERSE, SimulatedClock(NOW))
    decision = engine.evaluate(signal=signal(entry=ENTRY, stop=STOP), portfolio=PortfolioState.initial(EQUITY),
                               quality=quality(), now=NOW)
    assert decision.allows_execution and decision.approved_quantity == pytest.approx(0.002)
    out = sized(approved=decision.approved_quantity, budget_risk=50.0)  # the budget would allow 0.05
    assert out.quantity == pytest.approx(0.002) and out.limiting_constraint == "risk_engine"
    assert out.effective_risk_currency == pytest.approx(2.0)
    assert out.effective_risk_currency <= 50.0


# 13. long and short
def test_long_and_short_risk_the_same_money_for_the_same_stop_distance() -> None:
    long = sized(budget_risk=50.0, entry=ENTRY, stop=ENTRY - 1_000.0)
    short = sized(budget_risk=50.0, entry=ENTRY, stop=ENTRY + 1_000.0)
    assert long.quantity == short.quantity == pytest.approx(0.05)
    assert long.effective_risk_currency == short.effective_risk_currency == pytest.approx(50.0)


# 14. the three profiles under identical conditions
def test_the_profiles_order_the_money_at_the_stop_up_to_the_limit() -> None:
    risks = {}
    for name in RiskProfileName:
        budget = RiskBudgetEngine(name).compute(inputs())
        risks[name] = sized(budget_risk=budget.risk_currency, approved=0.1).effective_risk_currency
    assert risks[RiskProfileName.CONSERVATIVE] == pytest.approx(25.0)
    assert risks[RiskProfileName.BALANCED] == pytest.approx(50.0)
    assert risks[RiskProfileName.AGGRESSIVE] == pytest.approx(50.0), "capped by RiskLimits, not 100"
    assert PROFILES[RiskProfileName.AGGRESSIVE].risk_per_trade_pct == 1.0


# 15. conviction (exploration) shrinks, never skips the limits
def test_conviction_shrinks_the_size_and_can_never_grow_it() -> None:
    explore = sized(budget_risk=50.0, conviction=0.25)
    assert explore.quantity == pytest.approx(0.0125) and explore.effective_risk_currency == pytest.approx(12.5)
    assert explore.limiting_constraint == "risk_engine x conviction"
    assert sized(budget_risk=50.0, conviction=1.5).quantity == pytest.approx(0.05), "clamped to one"
    assert sized(budget_risk=50.0, conviction=0.0).refused_reason == "invalid_conviction"
    assert sized(budget_risk=50.0, conviction=float("nan")).refused_reason == "invalid_conviction"
    # An exploration trade on a small budget is refused, not raised to the venue's minimum.
    assert sized(budget_risk=0.3, conviction=0.25).refused_reason == "below_min_notional"


# 16. the loss streak survives a restart: the runtime rebuilds it from the record
def test_a_restored_loss_streak_shrinks_the_first_budget_of_the_new_process() -> None:
    from tests.integration.test_live_runtime import FakeExecution, FakeMarketData, live_settings
    from tia.domain.enums import MarketRegime
    from tia.economics.expected_value import Outcome
    from tia.runtime.live import LiveRuntime

    losses = [
        Outcome(regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.7,
                net_return_bps=-20.0, fees_bps=10.0, gross_return_bps=-10.0, market_data="real")
        for _ in range(4)
    ]
    clock = SimulatedClock(datetime(2026, 8, 14, 12, 0, tzinfo=UTC))
    runtime = LiveRuntime(
        live_settings(risk_profile="balanced"), activation=None, market_data=FakeMarketData([], clock),
        execution=FakeExecution(), clock=clock, prior_outcomes=losses, poll_interval_seconds=0.0,
    )
    assert runtime._consecutive_losses == 4
    budget = runtime._budget.compute(inputs(losses=runtime._consecutive_losses))
    assert budget.streak_multiplier == pytest.approx(0.5)
    assert sized(budget_risk=budget.risk_currency).effective_risk_currency == pytest.approx(25.0)
    assert clock.now() - timedelta(0) == clock.now()


# ------------------------------------------------------------------ invariants


@settings(max_examples=300, deadline=None)
@given(
    equity=st.floats(min_value=500.0, max_value=5_000_000.0),
    entry=st.floats(min_value=1.0, max_value=200_000.0),
    stop_frac=st.floats(min_value=0.001, max_value=0.2),
    approved=st.floats(min_value=1e-6, max_value=100.0),
    low=st.floats(min_value=0.0, max_value=1.0),
    high=st.floats(min_value=0.0, max_value=1.0),
    conviction=st.floats(min_value=0.05, max_value=1.0),
    direction=st.sampled_from([Direction.LONG, Direction.SHORT]),
)
def test_a_smaller_multiplier_never_allows_a_larger_loss_and_the_stop_never_costs_more_than_allowed(
    equity: float, entry: float, stop_frac: float, approved: float, low: float, high: float,
    conviction: float, direction: Direction,
) -> None:
    lo, hi = sorted((low, high))
    stop = entry * (1 - stop_frac) if direction is Direction.LONG else entry * (1 + stop_frac)
    limit = equity * 0.005
    base = equity * 0.005
    smaller = sized(approved=approved, budget_risk=base * lo, conviction=conviction, limit=limit, entry=entry, stop=stop)
    larger = sized(approved=approved, budget_risk=base * hi, conviction=conviction, limit=limit, entry=entry, stop=stop)
    assert smaller.effective_risk_currency <= larger.effective_risk_currency + 1e-9
    for out in (smaller, larger):
        if out.accepted:
            assert out.effective_risk_currency <= out.allowed_risk_currency * (1 + 1e-9) + 1e-12
            assert out.quantity <= approved * (1 + 1e-9)
            assert implied_risk(out.quantity, entry, stop) == pytest.approx(out.effective_risk_currency)
            assert out.quantity * entry >= MIN_NOTIONAL
