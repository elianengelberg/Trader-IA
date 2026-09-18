"""Inventory skews against the position; the spread never undercuts its costs."""

from __future__ import annotations

import pytest

from tia.mm.features import FeatureVector, TradeFlowWindow
from tia.mm.inventory import InventoryConfig, InventoryManager
from tia.mm.spread import SpreadConfig, SpreadEngine

T0 = 1_789_754_400_000


def _features(spread_bps: float = 1.0, vol_5s: float | None = 0.5) -> FeatureVector:
    flow = {w: TradeFlowWindow(w, 0, 0, 0, 0, 0, None) for w in ("1s", "5s", "15s", "30s", "60s")}
    return FeatureVector(
        t_ms=T0, update_id=1, best_bid=100_000.0, best_ask=100_000.0 * (1 + spread_bps / 1e4), best_bid_size=1, best_ask_size=1,
        mid_price=100_000.0, microprice=100_000.0, microprice_minus_mid=0, microprice_delta_bps=0,
        imbalance_t1=0, imbalance_t5=0, imbalance_t10=0, imbalance_t20=0, spread_abs=spread_bps * 10, spread_bps=spread_bps,
        spread_pct=None, spread_regime="unknown", ofi_last=0, ofi_window=0, ofi_norm=None, bid_additions=0, bid_cancellations=0,
        ask_additions=0, ask_cancellations=0, trade_flow=flow, vol_bps={"5s": vol_5s}, returns_bps={}, data_age_ms=0,
    )


# ------------------------------------------------------------------ 6. inventory adjustment


def test_a_long_position_lowers_both_quotes_and_shrinks_the_bid() -> None:
    manager = InventoryManager(InventoryConfig(max_inventory_btc=0.1, skew_bps_at_limit=4.0, reduce_size_from=0.5))
    flat = manager.assess(0.0)
    assert flat.inventory_adjustment_bps == 0.0 and flat.bid_size_factor == 1.0 and flat.ask_size_factor == 1.0 and flat.reason == "flat"
    half = manager.assess(0.05)
    assert half.inventory_ratio == pytest.approx(0.5) and half.inventory_pressure == pytest.approx(0.25)
    assert half.inventory_adjustment_bps == pytest.approx(-1.0)  # both quotes down: buy less, sell more
    assert half.bid_size_factor == 1.0  # at the threshold, not yet shrinking
    three_quarters = manager.assess(0.075)
    assert three_quarters.bid_size_factor == pytest.approx(0.5) and three_quarters.ask_size_factor == 1.0
    at_limit = manager.assess(0.1)
    assert at_limit.bid_size_factor == 0.0 and at_limit.inventory_adjustment_bps == pytest.approx(-4.0) and not at_limit.over_limit
    beyond = manager.assess(0.13)
    assert beyond.over_limit and beyond.inventory_ratio == 1.0 and "beyond the limit" in beyond.reason


def test_a_short_position_is_the_mirror_image() -> None:
    manager = InventoryManager(InventoryConfig(max_inventory_btc=0.1, skew_bps_at_limit=4.0, reduce_size_from=0.5))
    short = manager.assess(-0.075)
    long = manager.assess(0.075)
    assert short.inventory_adjustment_bps == pytest.approx(-long.inventory_adjustment_bps)
    assert short.inventory_adjustment_bps > 0 > long.inventory_adjustment_bps
    assert short.ask_size_factor == pytest.approx(long.bid_size_factor) and short.bid_size_factor == 1.0
    assert "short" in short.reason and "long" in long.reason


# ------------------------------------------------------------------ 7. spread adjustment


def test_the_spread_is_the_widest_of_its_floors_and_names_the_binding_one() -> None:
    engine = SpreadEngine(SpreadConfig(min_half_spread_bps=0.5, cost_buffer_bps=0.5, vol_multiplier=1.0, market_fraction=0.0))
    quiet = engine.target(_features(vol_5s=0.2), fee_bps=10.0, expected_adverse_bps=1.0, toxicity_widen_bps=0.0)
    assert quiet.binding == "cost_floor" and quiet.half_spread_bps == pytest.approx(11.5)
    assert quiet.components_bps["volatility"] == pytest.approx(0.2) and quiet.components_bps["toxicity_widen"] == 0.0
    wild = engine.target(_features(vol_5s=15.0), fee_bps=10.0, expected_adverse_bps=1.0, toxicity_widen_bps=0.0)
    assert wild.binding == "volatility" and wild.half_spread_bps == pytest.approx(15.0)
    assert wild.half_spread_bps >= quiet.components_bps["cost_floor"]  # never below what a fill costs


def test_toxicity_only_adds_and_the_cap_holds() -> None:
    engine = SpreadEngine(SpreadConfig(max_half_spread_bps=12.0, cost_buffer_bps=0.0))
    plain = engine.target(_features(), fee_bps=10.0, expected_adverse_bps=0.0, toxicity_widen_bps=0.0)
    widened = engine.target(_features(), fee_bps=10.0, expected_adverse_bps=0.0, toxicity_widen_bps=1.5)
    assert widened.half_spread_bps == pytest.approx(plain.half_spread_bps + 1.5)
    negative = engine.target(_features(), fee_bps=10.0, expected_adverse_bps=0.0, toxicity_widen_bps=-3.0)
    assert negative.half_spread_bps == plain.half_spread_bps  # a negative "widen" is ignored, never a narrowing
    capped = engine.target(_features(), fee_bps=10.0, expected_adverse_bps=0.0, toxicity_widen_bps=9.0)
    assert capped.half_spread_bps == 12.0 and capped.binding == "cap"


def test_missing_volatility_and_the_market_term_are_handled() -> None:
    engine = SpreadEngine(SpreadConfig(market_fraction=0.5, cost_buffer_bps=0.0))
    decision = engine.target(_features(spread_bps=40.0, vol_5s=None), fee_bps=1.0, expected_adverse_bps=0.0, toxicity_widen_bps=0.0)
    assert decision.binding == "market" and decision.half_spread_bps == pytest.approx(10.0)
    assert "no 5 s volatility" in decision.reason and decision.components_bps["volatility"] == 0.0
