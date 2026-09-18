"""Fair value: named contributions, a confidence that only falls, no fitting."""

from __future__ import annotations

import pytest

from tia.mm.fair_value import FairValueConfig, FairValueEngine
from tia.mm.features import FeatureVector, TradeFlowWindow

T0 = 1_789_754_400_000


def _flow(norm: float | None) -> dict[str, TradeFlowWindow]:
    return {w: TradeFlowWindow(w, 1.0, 1.0, 0.0, 2, 1.0, norm) for w in ("1s", "5s", "15s", "30s", "60s")}


def _features(**overrides) -> FeatureVector:  # type: ignore[no-untyped-def]
    base = {
        "t_ms": T0, "update_id": 10, "best_bid": 100_000.0, "best_ask": 100_000.2, "best_bid_size": 3.0, "best_ask_size": 1.0,
        "mid_price": 100_000.1, "microprice": 100_000.15, "microprice_minus_mid": 0.05, "microprice_delta_bps": 0.005,
        "imbalance_t1": 0.5, "imbalance_t5": 0.4, "imbalance_t10": 0.3, "imbalance_t20": 0.2,
        "spread_abs": 0.2, "spread_bps": 0.02, "spread_pct": 0.5, "spread_regime": "normal",
        "ofi_last": 1.0, "ofi_window": 2.0, "ofi_norm": 0.25, "bid_additions": 1.0, "bid_cancellations": 0.0,
        "ask_additions": 0.0, "ask_cancellations": 0.5, "trade_flow": _flow(0.6),
        "vol_bps": {"1s": 0.5, "5s": 1.0, "15s": 1.5, "30s": 2.0, "60s": 2.5},
        "returns_bps": {"1s": 0.1, "5s": 0.3, "30s": 0.8}, "data_age_ms": 0,
    }
    base.update(overrides)
    return FeatureVector(**base)


def test_by_default_the_fair_value_is_the_microprice_and_every_component_is_named() -> None:
    est = FairValueEngine().estimate(_features())
    assert est.fair_value == pytest.approx(100_000.15, abs=1e-6)
    assert est.fair_value_offset_bps == pytest.approx(0.005)
    assert set(est.components_bps) == {"micro", "imbalance", "ofi", "flow", "momentum"}
    assert est.components_bps["micro"] == pytest.approx(0.005)
    assert all(est.components_bps[k] == 0.0 for k in ("imbalance", "ofi", "flow", "momentum"))
    assert est.raw_offset_bps == pytest.approx(sum(est.components_bps.values()))
    assert est.config_id == FairValueConfig().config_id and len(est.config_id) == 12
    assert 0.0 < est.fair_value_confidence <= 1.0


def test_components_scale_with_their_weights_and_the_offset_is_clamped() -> None:
    cfg = FairValueConfig(w_micro=1.0, w_imbalance=1.0, w_ofi=1.0, w_flow=1.0, w_momentum=1.0, max_offset_bps=0.05)
    est = FairValueEngine(cfg).estimate(_features())
    half = 0.01  # half of 0.02 bps spread
    assert est.components_bps["imbalance"] == pytest.approx(0.4 * half)
    assert est.components_bps["ofi"] == pytest.approx(0.25 * half)
    assert est.components_bps["flow"] == pytest.approx(0.6 * half)
    assert est.components_bps["momentum"] == pytest.approx(0.3)
    assert est.raw_offset_bps > cfg.max_offset_bps and est.fair_value_offset_bps == cfg.max_offset_bps
    assert any("clamped" in r for r in est.reasons)
    assert est.fair_value == pytest.approx(100_000.1 * (1 + 0.05 / 1e4))


def test_missing_inputs_contribute_nothing_rather_than_something_made_up() -> None:
    cfg = FairValueConfig(w_ofi=1.0, w_flow=1.0, w_momentum=1.0)
    est = FairValueEngine(cfg).estimate(_features(ofi_norm=None, trade_flow=_flow(None), returns_bps={"1s": None, "5s": None, "30s": None}))
    assert est.components_bps["ofi"] == 0.0 and est.components_bps["flow"] == 0.0 and est.components_bps["momentum"] == 0.0


def test_confidence_only_falls_with_age_volatility_regime_and_disagreement() -> None:
    engine = FairValueEngine(FairValueConfig(w_momentum=1.0))
    clean = engine.estimate(_features(vol_bps={"1s": 0.0, "5s": 0.0, "15s": 0.0, "30s": 0.0, "60s": 0.0}))
    assert clean.fair_value_confidence == pytest.approx(1.0) and clean.reasons == []
    stale = engine.estimate(_features(data_age_ms=500, vol_bps={"5s": 0.0}))
    assert stale.fair_value_confidence == pytest.approx(0.5) and "500 ms old" in stale.reasons[0]
    dead = engine.estimate(_features(data_age_ms=5_000, vol_bps={"5s": 0.0}))
    assert dead.fair_value_confidence == 0.0
    volatile = engine.estimate(_features(vol_bps={"5s": 5.0}))
    assert volatile.fair_value_confidence == pytest.approx(0.5)
    wide = engine.estimate(_features(spread_regime="wide", vol_bps={"5s": 0.0}))
    assert wide.fair_value_confidence == pytest.approx(0.5) and "wide" in wide.reasons[0]
    unknown = engine.estimate(_features(spread_regime="unknown", vol_bps={"5s": 0.0}))
    assert unknown.fair_value_confidence == pytest.approx(0.9)
    no_vol = engine.estimate(_features(vol_bps={"5s": None}))
    assert no_vol.fair_value_confidence == pytest.approx(0.8)
    disagree = engine.estimate(_features(returns_bps={"5s": -1.0}, vol_bps={"5s": 0.0}))  # micro up, momentum down
    assert disagree.fair_value_confidence == pytest.approx(0.7) and "disagree" in disagree.reasons[0]


def test_the_estimate_is_a_pure_function_of_the_features() -> None:
    engine = FairValueEngine(FairValueConfig(w_imbalance=0.5))
    a, b = engine.estimate(_features()), engine.estimate(_features())
    assert a == b
    assert FairValueConfig(w_imbalance=0.5).config_id != FairValueConfig().config_id
