"""Markouts resolve only from later mids; toxicity only widens or shrinks."""

from __future__ import annotations

import pytest

from tia.mm.adverse_selection import FillObservation, MarkoutTracker, regimes_of
from tia.mm.features import FeatureVector, TradeFlowWindow
from tia.mm.toxicity import ToxicityConfig, ToxicityEngine

T0 = 1_789_754_400_000


def _obs(fill_id: str, side: str, price: float, t: int = T0, **buckets: str) -> FillObservation:
    return FillObservation(fill_id=fill_id, t_fill_ms=t, side=side, price=price, quantity=0.1, mid_at_fill=price + (0.05 if side == "buy" else -0.05), buckets=buckets)


def _resolve(tracker: MarkoutTracker, obs: FillObservation, mids: list[tuple[int, float]]) -> None:
    tracker.register(obs)
    for t, mid in mids:
        tracker.on_mid(t, mid)


# ------------------------------------------------------------------ 9. adverse selection


def test_markouts_are_resolved_only_by_mids_after_each_horizon() -> None:
    tracker = MarkoutTracker()
    tracker.register(_obs("f1", "buy", 100_000.0))
    assert tracker.pending == 1 and len(tracker.resolved) == 0
    assert tracker.on_mid(T0 + 50, 99_990.0) == []  # before every horizon: nothing resolves
    markout = tracker._pending[0]
    assert all(v is None for v in markout.horizons_bps.values())
    tracker.on_mid(T0 + 120, 100_010.0)  # first mid at or after +100 ms
    assert markout.at(100) == pytest.approx(1.0) and markout.at(250) is None
    tracker.on_mid(T0 + 300, 99_980.0)  # resolves 250 ms only: 500 ms has not come yet
    assert markout.at(250) == pytest.approx(-2.0) and markout.at(500) is None
    tracker.on_mid(T0 + 1_100, 99_980.0)  # resolves 500 ms and 1 s with the same (late but in-tolerance) mid
    assert markout.at(500) == pytest.approx(-2.0) and markout.at(1_000) == pytest.approx(-2.0)
    tracker.on_mid(T0 + 2_100, 99_980.0)
    assert markout.at(2_000) == pytest.approx(-2.0) and markout.at(5_000) is None and not markout.resolved
    newly = tracker.on_mid(T0 + 5_100, 100_000.0)
    assert newly == [markout] and markout.resolved and tracker.pending == 0
    assert markout.at(5_000) == pytest.approx(0.0)
    assert markout.adverse_bps_1s == pytest.approx(2.0) and markout.favorable_bps_1s == 0.0
    assert markout.observation.fill_to_mid_bps == pytest.approx(0.005)  # bought 0.05 below the mid


def test_sell_fills_have_the_opposite_sign_and_gaps_expire_unresolved() -> None:
    tracker = MarkoutTracker(tolerance_ms=1_000)
    _resolve(tracker, _obs("s1", "sell", 100_000.0), [(T0 + h, 99_990.0) for h in (100, 250, 500, 1_000, 2_000, 5_000)])
    sold = tracker.resolved[-1]
    assert all(v == pytest.approx(1.0) for v in sold.horizons_bps.values())  # price fell after we sold: favourable
    assert sold.favorable_bps_1s == pytest.approx(1.0) and sold.adverse_bps_1s == 0.0
    tracker.register(_obs("gap", "buy", 100_000.0, t=T0 + 10_000))
    tracker.on_mid(T0 + 10_000 + 1_500, 100_000.0)  # the first mid after +100 ms is 1.4 s late: a gap, not a markout
    assert tracker.expired == 1 and tracker.pending == 0
    summary = tracker.summary()
    assert summary["expired_unresolved"] == 1 and summary["resolved"] == 1


def test_stats_are_split_by_bucket_and_never_include_unresolved_fills() -> None:
    tracker = MarkoutTracker()
    horizons = (100, 250, 500, 1_000, 2_000, 5_000)
    _resolve(tracker, _obs("a", "buy", 100_000.0, spread_regime="tight"), [(T0 + h, 99_995.0) for h in horizons])
    _resolve(tracker, _obs("b", "buy", 100_000.0, t=T0 + 10_000, spread_regime="wide"), [(T0 + 10_000 + h, 100_005.0) for h in horizons])
    tracker.register(_obs("c", "buy", 100_000.0, t=T0 + 20_000, spread_regime="tight"))  # pending
    overall = tracker.stats(1_000)
    assert overall.count == 2 and overall.mean_bps == pytest.approx(0.0) and overall.adverse_share == 0.5
    tight = tracker.stats(1_000, buckets={"spread_regime": "tight"})
    assert tight.count == 1 and tight.mean_bps == pytest.approx(-0.5) and tight.mean_adverse_bps == pytest.approx(0.5)


def test_regime_buckets_come_from_the_features_at_decision_time() -> None:
    flow = {w: TradeFlowWindow(w, 2.0, 0.5, 1.5, 3, 0.83, 0.6) for w in ("1s", "5s", "15s", "30s", "60s")}
    fv = FeatureVector(
        t_ms=T0, update_id=1, best_bid=1.0, best_ask=1.1, best_bid_size=1, best_ask_size=1, mid_price=1.05, microprice=1.05,
        microprice_minus_mid=0, microprice_delta_bps=0, imbalance_t1=0.5, imbalance_t5=0.3, imbalance_t10=0, imbalance_t20=0,
        spread_abs=0.1, spread_bps=1, spread_pct=0.9, spread_regime="wide", ofi_last=0, ofi_window=0, ofi_norm=None,
        bid_additions=0, bid_cancellations=0, ask_additions=0, ask_cancellations=0, trade_flow=flow,
        vol_bps={"5s": 4.0}, returns_bps={}, data_age_ms=0,
    )
    assert regimes_of(fv, "buy") == {"side": "buy", "spread_regime": "wide", "imbalance_regime": "bid_heavy", "vol_regime": "high", "flow_regime": "buying"}


# ------------------------------------------------------------------ 8. toxicity


def _resolved_markout(adverse_bps: float, **buckets: str):  # type: ignore[no-untyped-def]
    tracker = MarkoutTracker(horizons_ms=(1_000,))
    obs = FillObservation("x", T0, "buy", 100_000.0, 0.1, 100_000.0, buckets)
    tracker.register(obs)
    tracker.on_mid(T0 + 1_000, 100_000.0 * (1 - adverse_bps / 1e4))
    return tracker.resolved[-1]


def test_toxicity_needs_evidence_then_only_widens_and_shrinks() -> None:
    engine = ToxicityEngine(ToxicityConfig(min_samples=3, decay=0.5, scale_bps=2.0, max_widen_bps=4.0))
    empty = engine.reading()
    assert empty.score is None and empty.widen_bps == 0.0 and empty.size_factor == 1.0
    for _ in range(3):
        assert engine.observe(_resolved_markout(2.0, side="buy"))
    toxic = engine.reading()
    assert toxic.score == pytest.approx(1.0) and toxic.widen_bps == pytest.approx(4.0) and toxic.size_factor == pytest.approx(0.5)
    for _ in range(6):
        engine.observe(_resolved_markout(-3.0, side="buy"))  # favourable markouts: cost side is zero
    calmer = engine.reading()
    assert calmer.score is not None and calmer.score < toxic.score
    assert calmer.widen_bps >= 0.0 and calmer.size_factor <= 1.0


def test_toxicity_refuses_unresolved_markouts_and_takes_the_stricter_bucket() -> None:
    engine = ToxicityEngine(ToxicityConfig(min_samples=2, decay=0.5, scale_bps=1.0))
    tracker = MarkoutTracker()
    tracker.register(FillObservation("p", T0, "buy", 100_000.0, 0.1, 100_000.0))
    assert engine.observe(tracker._pending[0]) is False  # not resolved: refused
    for _ in range(2):
        engine.observe(_resolved_markout(0.0, side="buy", spread_regime="tight"))
        engine.observe(_resolved_markout(3.0, side="sell", spread_regime="wide"))
    calm = engine.reading({"side": "buy", "spread_regime": "tight"})
    harsh = engine.reading({"side": "sell", "spread_regime": "wide"})
    assert harsh.score == 1.0
    assert calm.score is not None and calm.score >= engine.for_buckets({"side": "buy", "spread_regime": "tight"}).score  # never below the bucket's own reading
    assert engine.as_dict()["overall"]["samples"] == 4
