"""The hierarchy's middle: a gate that only reads, a controller that only restricts,
a quoting engine that only quotes what both allow."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tia.domain.enums import SystemMode
from tia.mm.fair_value import FairValueConfig, FairValueEngine
from tia.mm.features import FeatureVector, TradeFlowWindow
from tia.mm.inventory import InventoryConfig, InventoryManager
from tia.mm.latency_model import LatencyScenario
from tia.mm.quoting import AdaptiveQuotingEngine, QuotingConfig
from tia.mm.risk import LedgerView, MarketMakerRiskController, MarketMakerRiskLimits, RiskAllowance
from tia.mm.safety import GlobalTradingSafetyGate, SafetyState
from tia.mm.spread import SpreadConfig, SpreadEngine
from tia.mm.toxicity import ToxicityReading
from tia.risk.engine import RiskState

T0 = 1_789_754_400_000
LATENCY = LatencyScenario("baseline", "p-test", 60.0, 60.0, 60.0, 0.1, "test")


def _features(mid: float = 100_000.0, spread_bps: float = 1.0, vol_5s: float | None = 0.5) -> FeatureVector:
    flow = {w: TradeFlowWindow(w, 0, 0, 0, 0, 0, None) for w in ("1s", "5s", "15s", "30s", "60s")}
    half = mid * spread_bps / 2e4
    return FeatureVector(
        t_ms=T0, update_id=1, best_bid=mid - half, best_ask=mid + half, best_bid_size=1, best_ask_size=1, mid_price=mid,
        microprice=mid, microprice_minus_mid=0, microprice_delta_bps=0, imbalance_t1=0, imbalance_t5=0, imbalance_t10=0,
        imbalance_t20=0, spread_abs=2 * half, spread_bps=spread_bps, spread_pct=0.5, spread_regime="normal", ofi_last=0,
        ofi_window=0, ofi_norm=None, bid_additions=0, bid_cancellations=0, ask_additions=0, ask_cancellations=0,
        trade_flow=flow, vol_bps={"5s": vol_5s}, returns_bps={}, data_age_ms=0,
    )


# ------------------------------------------------------------------ 17/23. the gate


def test_the_gate_reads_data_first_then_the_session_risk_engine_and_changes_nothing() -> None:
    state = RiskState()
    data = {"ok": True, "why": ""}
    unsafe = {"reason": ""}
    gate = GlobalTradingSafetyGate(risk_state=lambda: state, data_usable=lambda: (data["ok"], data["why"]), system_unsafe=lambda: unsafe["reason"])
    assert gate.status(T0).state is SafetyState.SAFE and gate.status(T0).allows_quoting
    state.mode = SystemMode.HALTED
    state.kill_switch_reason = "operator"
    halted = gate.status(T0 + 1)
    assert halted.state is SafetyState.HALTED and "operator" in halted.reason and not halted.allows_quoting
    state.mode = SystemMode.SAFE_MODE
    assert gate.status(T0 + 2).state is SafetyState.SAFE_MODE
    state.mode = SystemMode.DEGRADED
    assert gate.status(T0 + 3).state is SafetyState.SYSTEM_UNSAFE
    state.mode = SystemMode.NORMAL
    unsafe["reason"] = "disk full"
    assert gate.status(T0 + 4).state is SafetyState.SYSTEM_UNSAFE
    unsafe["reason"] = ""
    data["ok"], data["why"] = False, "book syncing"
    state.mode = SystemMode.HALTED  # data invalidity is reported before anything else
    invalid = gate.status(T0 + 5)
    assert invalid.state is SafetyState.DATA_INVALID and "book syncing" in invalid.reason
    # Reading never wrote: the session's state is exactly what the test set.
    assert state.mode is SystemMode.HALTED and state.kill_switch_reason == "operator"
    assert gate.transitions >= 5 and gate.unsafe_since_ms == T0 + 5
    for forbidden in ("resume", "release", "engage_kill_switch", "enter_safe_mode", "set_state"):
        assert not hasattr(gate, forbidden)


# ------------------------------------------------------------------ 16/17/23. the controller


def _view(inventory: float = 0.0, equity: float = 10_000.0, day_start: float = 10_000.0, peak: float = 10_000.0, mark: float = 100_000.0) -> LedgerView:
    return LedgerView(inventory, equity, day_start, peak, mark)


def test_limits_can_only_be_tightened() -> None:
    limits = MarketMakerRiskLimits(max_inventory_btc=0.05, max_quotes_per_minute=100)
    tighter = limits.tightened(max_inventory_btc=0.02, max_quotes_per_minute=50)
    assert tighter.max_inventory_btc == 0.02 and tighter.max_quotes_per_minute == 50
    with pytest.raises(ValueError, match="loosen"):
        limits.tightened(max_inventory_btc=0.06)
    with pytest.raises(ValueError, match="positive"):
        MarketMakerRiskLimits(max_daily_loss_usd=0)
    controller = MarketMakerRiskController(limits)
    with pytest.raises(ValueError):
        controller.tighten(max_drawdown_pct=99.0)


def test_the_controller_restricts_by_inventory_notional_loss_drawdown_and_rate() -> None:
    controller = MarketMakerRiskController(MarketMakerRiskLimits(max_inventory_btc=0.05, max_notional_usd=6_000, max_quote_size_btc=0.01, max_daily_loss_usd=100, max_drawdown_pct=3.0, max_quotes_per_minute=3, min_quote_interval_ms=100))
    ok = controller.allowance(_view(), T0)
    assert ok.allowed and ok.bid_allowed and ok.ask_allowed and ok.max_size_btc == 0.01 and ok.reason == "within limits"
    near = controller.allowance(_view(inventory=0.045), T0)
    assert near.allowed and near.max_size_btc == pytest.approx(0.005)  # only the room that is left
    long_limit = controller.allowance(_view(inventory=0.05), T0)
    assert long_limit.allowed and not long_limit.bid_allowed and long_limit.ask_allowed and "reducing side only" in long_limit.reason
    short_limit = controller.allowance(_view(inventory=-0.05), T0)
    assert short_limit.bid_allowed and not short_limit.ask_allowed
    notional = controller.allowance(_view(inventory=0.04, mark=200_000.0), T0)  # 8,000 USD > 6,000
    assert not notional.bid_allowed and notional.ask_allowed
    for i in range(3):
        controller.record_quote(T0 + 1_000 * i)
    rate = controller.allowance(_view(), T0 + 3_000)
    assert not rate.allowed and "quotes in the last minute" in rate.reason
    later = controller.allowance(_view(), T0 + 61_500)
    assert later.allowed
    controller.record_quote(T0 + 61_500)
    soon = controller.allowance(_view(), T0 + 61_550)
    assert not soon.allowed and "minimum" in soon.reason


def test_daily_loss_and_drawdown_latch_the_makers_own_kill_switch() -> None:
    controller = MarketMakerRiskController(MarketMakerRiskLimits(max_daily_loss_usd=100, max_drawdown_pct=3.0))
    loss = controller.allowance(_view(equity=9_899.0), T0)
    assert not loss.allowed and loss.kill_switch and "daily loss" in controller.kill_switch_reason
    recovered = controller.allowance(_view(equity=10_000.0), T0 + 1)  # the loss went away; the switch did not
    assert not recovered.allowed and "kill switch" in recovered.reason
    with pytest.raises(ValueError):
        controller.release_kill_switch(approved_by="")
    controller.release_kill_switch(approved_by="operator")
    assert controller.allowance(_view(), T0 + 2).allowed
    drawdown = controller.allowance(_view(equity=9_690.0, peak=10_000.0), T0 + 3)
    assert not drawdown.allowed and "drawdown" in controller.kill_switch_reason
    controller.engage_kill_switch("manual")
    assert controller.as_dict()["kill_switch_reason"] == "manual"


# ------------------------------------------------------------------ 5-8. quoting


def _decision(*, inventory_btc: float = 0.0, allowance: RiskAllowance | None = None, toxicity: ToxicityReading | None = None, confidence_features: FeatureVector | None = None, config: QuotingConfig | None = None):  # type: ignore[no-untyped-def]
    features = confidence_features or _features()
    fv = FairValueEngine(FairValueConfig()).estimate(features)
    inv = InventoryManager(InventoryConfig(max_inventory_btc=0.05, skew_bps_at_limit=4.0)).assess(inventory_btc)
    spread = SpreadEngine(SpreadConfig(cost_buffer_bps=0.0)).target(features, fee_bps=10.0, expected_adverse_bps=0.0, toxicity_widen_bps=(toxicity or ToxicityReading(None, None, 0, 0.0, 1.0, "")).widen_bps)
    tox = toxicity or ToxicityReading(None, None, 0, 0.0, 1.0, "no evidence")
    allow = allowance or RiskAllowance(True, "within limits", 0.01, True, True, False)
    return AdaptiveQuotingEngine(config).decide(features=features, fair_value=fv, inventory=inv, spread=spread, toxicity=tox, allowance=allow, latency=LATENCY, t_ms=T0)


def test_quotes_sit_a_half_spread_around_the_inventory_shifted_fair_value_on_the_tick_grid() -> None:
    flat = _decision()
    assert flat.is_quote and flat.bid_price is not None and flat.ask_price is not None
    assert flat.half_spread_bps == pytest.approx(10.0)  # the fee floor binds
    assert flat.bid_price == pytest.approx(100_000.0 * (1 - 10 / 1e4), abs=0.01) and flat.ask_price == pytest.approx(100_000.0 * (1 + 10 / 1e4), abs=0.01)
    assert flat.bid_price < flat.ask_price and round(flat.bid_price / 0.01) == pytest.approx(flat.bid_price / 0.01)
    assert flat.bid_size == flat.ask_size == pytest.approx(0.005 * flat.quote_confidence, abs=1e-5)
    long = _decision(inventory_btc=0.025)
    assert long.bid_price is not None and long.ask_price is not None and flat.bid_price is not None and flat.ask_price is not None
    assert long.bid_price < flat.bid_price and long.ask_price < flat.ask_price  # both quotes shifted down
    assert long.components["inventory_adjustment_bps"] == pytest.approx(-1.0)
    assert "two-sided" in long.quote_reason and long.ttl_ms == 1_000 and long.components["order_latency_ms"] == 60.0


def test_sizes_shrink_with_toxicity_inventory_and_the_allowance_and_sides_can_drop() -> None:
    toxic = _decision(toxicity=ToxicityReading(0.8, 1.6, 30, 3.0, 0.6, "toxic"))
    plain = _decision()
    assert toxic.half_spread_bps == pytest.approx(plain.half_spread_bps + 3.0)
    assert toxic.bid_size == pytest.approx(plain.bid_size * 0.6, abs=1e-5)
    capped = _decision(allowance=RiskAllowance(True, "within limits", 0.001, True, True, False))
    assert capped.bid_size == pytest.approx(0.001) and capped.ask_size == pytest.approx(0.001)
    ask_only = _decision(allowance=RiskAllowance(True, "reducing side only", 0.01, False, True, False))
    assert ask_only.bid_price is None and ask_only.bid_size == 0.0 and ask_only.ask_price is not None and "ask only" in ask_only.quote_reason
    at_limit = _decision(inventory_btc=0.05)  # bid size factor 0 -> bid side gone
    assert at_limit.bid_price is None and at_limit.ask_price is not None


def test_the_engine_refuses_when_the_allowance_denies_or_confidence_is_low_or_the_arithmetic_is_absurd() -> None:
    denied = _decision(allowance=RiskAllowance(False, "kill switch", 0.01, False, False, True))
    assert not denied.is_quote and "risk controller" in denied.quote_reason and denied.bid_size == 0.0
    stale = _decision(confidence_features=replace(_features(), data_age_ms=950))  # confidence 0.05
    assert not stale.is_quote and "confidence" in stale.quote_reason
    absurd = _decision(config=QuotingConfig(max_offset_from_mid_bps=5.0))  # a 10 bps half-spread is "too far" here
    assert not absurd.is_quote and "implausible" in absurd.quote_reason
