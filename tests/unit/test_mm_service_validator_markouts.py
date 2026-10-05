"""The service validator's raw-markout evidence: the per-fill schema, the per-horizon
summary and the consistency check that judges S8e. Hand-built rows; a test of the
validator, not of Binance."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
T0 = 1_791_178_800_000


@pytest.fixture(scope="module")
def harness():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("validate_mm_live_service_testnet")
    finally:
        sys.path.remove(str(SCRIPTS))


def _horizons(t_fill: int, price: float, qty: float, side: str, mids: dict[int, tuple[int, float] | None]) -> list[dict[str, Any]]:
    sign = 1.0 if side == "buy" else -1.0
    rows = []
    for h in (100, 250, 500, 1_000, 2_000, 5_000):
        mark = mids.get(h)
        if mark is None:
            rows.append({"horizon_ms": h, "target_t_ms": t_fill + h, "mark_t_ms": None, "delay_ms": None, "mid_at_mark": None, "markout_bps": None, "markout_usd": None, "measured": False})
            continue
        t_mark, mid = mark
        bps = sign * (mid - price) / price * 1e4
        rows.append({"horizon_ms": h, "target_t_ms": t_fill + h, "mark_t_ms": t_mark, "delay_ms": t_mark - (t_fill + h), "mid_at_mark": mid, "markout_bps": bps, "markout_usd": bps / 1e4 * price * qty, "measured": True})
    return rows


def _row(fill_id: str, side: str, price: float, qty: float, t_fill: int, mids: dict[int, tuple[int, float] | None], *, shadow: bool = False, registered: int | None = None) -> dict[str, Any]:
    horizons = _horizons(t_fill, price, qty, side, mids)
    for h in horizons:
        late = max(0, registered - h["target_t_ms"]) if registered is not None else None
        h["late_by_ms"] = late
        h["measured_late"] = bool(h["measured"] and late is not None and late > 0)
        h["effective_horizon_ms"] = (h["mark_t_ms"] - t_fill) if h["measured"] else None
    measured = all(h["measured"] for h in horizons)
    return {"fill_id": fill_id, "shadow": shadow, "side": side, "price": price, "quantity": qty, "notional_usd": price * qty, "t_fill_ms": t_fill, "t_registered_ms": registered, "registration_lag_ms": (registered - t_fill) if registered is not None else None, "mid_at_fill": price, "fill_to_mid_bps": 0.0, "buckets": {}, "tolerance_ms": 1_000, "resolved": measured, "expired": not measured, "pending": False, "horizons": horizons}


def _rows() -> list[dict[str, Any]]:
    # buy at 100 that goes to 100.1 (+10 bps) at every horizon; sell at 200 that goes to 200.4 (-20 bps); a sell whose 5 s horizon had a gap
    a = _row("a", "buy", 100.0, 1.0, T0, {h: (T0 + h + 50, 100.1) for h in (100, 250, 500, 1_000, 2_000, 5_000)})
    b = _row("b", "sell", 200.0, 3.0, T0 + 10_000, {h: (T0 + 10_000 + h, 200.4) for h in (100, 250, 500, 1_000, 2_000, 5_000)})
    c = _row("c", "sell", 100.0, 1.0, T0 + 20_000, {**{h: (T0 + 20_000 + h, 99.9) for h in (100, 250, 500, 1_000, 2_000)}, 5_000: None})
    s = _row("shadow-1", "buy", 100.0, 1.0, T0 + 30_000, {h: (T0 + 30_000 + h, 150.0) for h in (100, 250, 500, 1_000, 2_000, 5_000)}, shadow=True)
    return [a, b, c, s]


def test_the_summary_per_horizon_separates_signed_markout_from_the_clipped_cost_and_splits_by_side(harness) -> None:  # type: ignore[no-untyped-def]
    summary = harness._markout_summary(_rows())
    h1 = summary["1000"]
    assert h1["fills"] == 3 and h1["measured"] == 3 and h1["unmeasured"] == 0  # the shadow is not a fill
    m = h1["markout_bps"]
    assert m["count"] == 3 and m["mean"] == pytest.approx((10 - 20 + 10) / 3) and m["median"] == pytest.approx(10.0) and m["min"] == pytest.approx(-20.0) and m["max"] == pytest.approx(10.0)
    assert m["weighted_mean"] == pytest.approx((10 * 100 - 20 * 600 + 10 * 100) / 800)
    assert h1["by_side"]["buy"]["count"] == 1 and h1["by_side"]["buy"]["mean"] == pytest.approx(10.0)
    assert h1["by_side"]["sell"]["count"] == 2 and h1["by_side"]["sell"]["mean"] == pytest.approx(-5.0)
    assert h1["adverse_share"] == pytest.approx(1 / 3) and h1["clipped_adverse_bps_mean"] == pytest.approx(20 / 3) and h1["clipped_favourable_bps_mean"] == pytest.approx(20 / 3)
    assert h1["markout_usd_sum"] == pytest.approx(10 / 1e4 * 100 - 20 / 1e4 * 600 + 10 / 1e4 * 100)
    assert h1["delay_ms"]["max"] == 50 and h1["delay_ms"]["min"] == 0
    h5 = summary["5000"]
    assert h5["measured"] == 2 and h5["unmeasured"] == 1 and h5["markout_bps"]["count"] == 2  # the gap is counted, not guessed
    assert set(summary) == {"100", "250", "500", "1000", "2000", "5000"}


def test_consistent_rows_pass_and_every_kind_of_corruption_is_named(harness) -> None:  # type: ignore[no-untyped-def]
    rows = _rows()
    assert harness._markout_consistency(rows) == []
    mids = [(T0 + h + 50, 100.1) for h in (100, 250, 500, 1_000, 2_000, 5_000)]
    assert harness._markout_consistency([rows[0]], mids) == []
    # the series disagrees: a mid at or after the target was processed before the one the row names
    disagreeing = [(T0 + 120, 100.0), *mids]  # processed first, stamped after the 100 ms target
    assert any("mid series says" in p for p in harness._markout_consistency([rows[0]], disagreeing))
    # the same stamp appended LAST is a stale sample: processed after the mark, it cannot have resolved anything
    assert harness._markout_consistency([rows[0]], [*mids, (T0 + 120, 100.0)]) == []
    assert harness._mid_series_inversions([*mids, (T0 + 120, 100.0)])[0]["backwards_ms"] == 5_050 - 120
    bad = _rows()
    bad[0]["horizons"][0]["mark_t_ms"] = T0 + 50  # a mark before its target
    bad[1]["horizons"][1]["markout_bps"] = +20.0  # the wrong sign for a sell that went against us
    bad[2]["horizons"][5]["markout_bps"] = 1.0  # unmeasured but carrying a value
    bad[1]["horizons"][2]["target_t_ms"] += 1  # target not t_fill + horizon
    problems = harness._markout_consistency(bad)
    assert any("before target" in p for p in problems) and any("markout_bps" in p and "!=" in p for p in problems)
    assert any("unmeasured but carries values" in p for p in problems) and any("target" in p and "t_fill + horizon" in p for p in problems)
    late = _rows()
    late[0]["horizons"][3]["mark_t_ms"] = T0 + 1_000 + 1_500
    late[0]["horizons"][3]["delay_ms"] = 1_500
    assert any("over tolerance" in p for p in harness._markout_consistency(late))


def test_the_fill_evidence_row_has_every_required_field_joined_by_trade_id(harness) -> None:  # type: ignore[no-untyped-def]
    fill_rows = [{"fill_id": "a", "order_id": "tiamm-x-1", "venue_order_id": "9001", "side": "buy", "price": 100.0, "quantity": 1.0, "liquidity": "maker", "attribution_source": "report", "fee": 0.0, "fee_asset": "USDT", "fee_status": "venue", "t_ms": T0, "received_at_ms": T0 + 120, "order_known": True, "order_venue_order_id": "9001", "correlated": True}]
    quote = {"t_decision_ms": T0 - 900, "mid": 100.02, "fair_value": 100.03, "fair_value_offset_bps": 0.1, "fair_value_confidence": 0.8, "bid": 100.0, "ask": 100.06, "bid_size": 1.0, "ask_size": 1.0, "half_spread_bps": 3.0, "spread_binding": "cost_floor", "inventory_btc": 0.0, "inventory_adjustment_bps": 0.0, "toxicity": {"score": None, "adverse_mean_bps": 0.4, "samples": 3}, "data_age_ms": 40, "vol_5s_bps": None}
    records = [{"fill_id": "a", "order_id": "tiamm-x-1", "venue_order_id": "9001", "side": "buy", "price": 100.0, "quantity": 1.0, "notional_usd": 100.0, "t_fill_ms": T0, "t_booked_ms": T0 + 121, "inventory_before_btc": -0.5, "inventory_after_btc": 0.5, "mid_at_fill": 100.01, "mid_used_by_tracker": 100.01, "capture_bps_vs_mid_at_fill": 1.0, "fair_value_at_quote": 100.03, "capture_bps_vs_fair_value_at_quote": 2.9991, "fair_value_at_fill": 100.0, "quote": quote, "toxicity_at_fill": {"score": None, "adverse_mean_bps": 0.4, "samples": 3}, "data_age_at_fill_ms": 12, "t_decision_ms": T0 - 900, "t_enqueued_ms": T0 - 895, "t_ack_ms": T0 - 650, "ack_source": "stream", "resting_ms": 650, "realised_usd": 0.0, "regimes": {"side": "buy"}},
               {"fill_id": "orphan", "order_id": "tiamm-x-9", "side": "sell", "price": 101.0, "quantity": 0.5, "notional_usd": 50.5, "t_fill_ms": T0 + 5, "inventory_before_btc": 0.5, "inventory_after_btc": 0.0}]
    markout_rows = _rows()[:1]
    out = harness._fill_evidence(fill_rows, records, markout_rows)
    assert [r["trade_id"] for r in out] == ["a", "orphan"]
    row = out[0]
    assert set(harness.FILL_EVIDENCE_FIELDS) - {"trade_id", "venue_order_id", "client_order_id"} <= set(row)
    assert row["trade_id"] == "a" and row["venue_order_id"] == "9001" and row["client_order_id"] == "tiamm-x-1" and row["t_fill_ms"] == T0
    assert row["inventory_before_btc"] == -0.5 and row["inventory_after_btc"] == 0.5 and row["bid_quote"] == 100.0 and row["ask_quote"] == 100.06
    assert row["mid_at_fill"] == 100.01 and row["fair_value_at_quote"] == 100.03 and row["fair_value_at_fill"] == 100.0 and row["confidence_at_quote"] == 0.8
    assert row["capture_bps_vs_fair_value_at_quote"] == 2.9991 and row["capture_bps_vs_mid_at_fill"] == 1.0
    assert row["toxicity_at_quote"]["adverse_mean_bps"] == 0.4 and row["toxicity_at_fill"]["samples"] == 3
    assert row["data_age_at_quote_ms"] == 40 and row["data_age_at_fill_ms"] == 12 and row["resting_ms"] == 650
    assert [hz["horizon_ms"] for hz in row["markouts"]] == [100, 250, 500, 1_000, 2_000, 5_000] and row["markouts_resolved"] is True
    assert row["correlated"] is True and row["liquidity"] == "maker"  # the adapter's correlation row is kept whole
    assert out[1]["note"] == "engine record without an adapter fill row" and out[1]["correlated"] is False and out[1]["markouts"] is None


def test_a_fill_without_engine_context_keeps_the_adapter_row_and_says_none_not_a_guess(harness) -> None:  # type: ignore[no-untyped-def]
    fill_rows = [{"fill_id": "z", "order_id": "tiamm-x-2", "venue_order_id": "9002", "side": "sell", "price": 100.0, "quantity": 2.0, "t_ms": T0, "correlated": True}]
    [row] = harness._fill_evidence(fill_rows, [], _rows()[:0])
    assert row["trade_id"] == "z" and row["notional_usd"] == 200.0 and row["inventory_before_btc"] is None and row["fair_value_at_quote"] is None and row["markouts"] is None and row["resting_ms"] is None


# ------------------------------------------------------------------ the 2026-10-05 run on 5ac604e, as fixtures

# Fill 2422185 (buy 0.00016 @ 85772.0): trade time t_fill, confirmation processed 129 ms later.
# The mid series, in processing order, relative to t_fill. Twelve samples at 85778.005 were
# shown between +92 and +120 ms, i.e. before the fill was known; the next one, at +217 ms,
# resolved the 100 ms horizon (late by 29 ms, effective horizon 217 ms).
F1_T = 1_791_228_861_134
F1_MIDS = [(-191, 85778.005), (92, 85778.005), (105, 85778.005), (105, 85778.005), (119, 85778.005), (119, 85778.005), (120, 85778.005), (120, 85778.005), (120, 85778.005), (120, 85778.005), (120, 85778.005), (120, 85778.005), (217, 85742.005), (237, 85742.005), (289, 85742.005), (493, 85742.005), (596, 85742.005), (598, 85742.005), (599, 85742.005), (599, 85742.005), (601, 85742.005), (601, 85742.005), (674, 85742.005), (675, 85742.005), (692, 85742.005), (895, 85742.005), (987, 85742.005), (1069, 85742.005), (1070, 85742.005), (1100, 85742.005), (1106, 85742.005), (1106, 85742.005), (1193, 85742.005), (1711, 85742.005), (2215, 85742.005), (2724, 85742.005), (3229, 85742.005), (3555, 85742.005), (3604, 85742.005), (3611, 85742.005), (3690, 85742.005), (4116, 85742.005), (4119, 85742.005), (4191, 85742.005), (4227, 85742.005), (4227, 85742.005), (4382, 85742.005), (5076, 85742.005), (5088, 85742.005), (5320, 85742.005), (5320, 85742.005), (5385, 85742.005), (5393, 85742.005), (5587, 85742.005)]
F1_MARKS = {100: (217, 85742.005), 250: (289, 85742.005), 500: (596, 85742.005), 1_000: (1069, 85742.005), 2_000: (2215, 85742.005), 5_000: (5076, 85742.005)}

# Fill 2423539 (sell 0.00016 @ 85712.1): confirmation 127 ms late, and a sample stamped +609
# processed after the ones stamped +611 and +783: a reconciliation tick that carried the
# reconciliation's start time. The 500 ms horizon was resolved at +611 (the first sample
# processed with a stamp at or after +500); sorted by stamp, +609 would wrongly come first.
F2_T = 1_791_230_539_143
F2_MIDS = [(-241, 85702.005), (96, 85702.005), (117, 85702.005), (123, 85702.005), (123, 85702.005), (123, 85702.005), (123, 85702.005), (233, 85716.005), (295, 85716.005), (611, 85716.005), (783, 85716.005), (609, 85716.005), (1407, 85716.005), (1794, 85716.005), (1987, 85716.005), (2290, 85716.005), (3271, 85716.005), (3582, 85716.005), (3823, 85716.005), (4088, 85716.005), (4392, 85716.005), (5301, 85716.005), (5591, 85716.005)]
F2_MARKS = {100: (233, 85716.005), 250: (295, 85716.005), 500: (611, 85716.005), 1_000: (1407, 85716.005), 2_000: (2290, 85716.005), 5_000: (5301, 85716.005)}


def _real(fill_id: str, side: str, price: float, t_fill: int, lag: int, marks: dict[int, tuple[int, float]], *, registered: bool = True) -> dict[str, Any]:
    return _row(fill_id, side, price, 0.00016, t_fill, {h: (t_fill + dt, mid) for h, (dt, mid) in marks.items()}, registered=(t_fill + lag) if registered else None)


def _series(t_fill: int, rel: list[tuple[int, float]]) -> list[list[float]]:
    return [[t_fill + dt, mid] for dt, mid in rel]


def test_fill_2422185_is_consistent_under_the_registration_lag_rule_and_flagged_by_the_strict_one(harness) -> None:  # type: ignore[no-untyped-def]
    row = _real("2422185", "buy", 85772.0, F1_T, 129, F1_MARKS)
    assert harness._markout_consistency([row], _series(F1_T, F1_MIDS)) == []
    h100 = row["horizons"][0]
    assert h100["late_by_ms"] == 29 and h100["measured_late"] and h100["effective_horizon_ms"] == 217 and h100["markout_bps"] == pytest.approx(-3.4971, abs=1e-4)
    assert all(not hz["measured_late"] and hz["late_by_ms"] == 0 for hz in row["horizons"][1:])
    # Without the registration time the row looks wrong: that was the S8e FAIL of 2026-10-05
    unknown = _real("2422185", "buy", 85772.0, F1_T, 129, F1_MARKS, registered=False)
    problems = harness._markout_consistency([unknown], _series(F1_T, F1_MIDS))
    assert len(problems) == 1 and "2422185@100" in problems[0] and "registration time unknown" in problems[0]


def test_fill_2423539_is_consistent_in_processing_order_and_the_stale_stamp_is_an_inversion(harness) -> None:  # type: ignore[no-untyped-def]
    row = _real("2423539", "sell", 85712.1, F2_T, 127, F2_MARKS)
    series = _series(F2_T, F2_MIDS)
    assert harness._markout_consistency([row], series) == []
    assert {hz["horizon_ms"]: hz["measured_late"] for hz in row["horizons"]} == {100: True, 250: False, 500: False, 1_000: False, 2_000: False, 5_000: False}
    [inv] = harness._mid_series_inversions(series)
    assert inv == {"index": 11, "t_ms": F2_T + 609, "previous_max_ms": F2_T + 783, "backwards_ms": 174}
    # sorted by stamp, the stale sample would be taken as the 500 ms mark: the old rule's mistake
    first_sorted = next(m for m in sorted(series) if m[0] >= F2_T + 500)
    assert first_sorted[0] == F2_T + 609 and F2_MARKS[500][0] == 611


def test_inversions_are_reported_with_index_stamp_and_how_far_back_and_a_clean_series_has_none(harness) -> None:  # type: ignore[no-untyped-def]
    assert harness._mid_series_inversions([[10, 1.0], [20, 1.0], [20, 1.1], [35, 1.2]]) == []
    found = harness._mid_series_inversions([[10, 1.0], [700, 1.0], [300, 1.0], [800, 1.0], [790, 1.0]])
    assert found == [{"index": 2, "t_ms": 300, "previous_max_ms": 700, "backwards_ms": 400}, {"index": 4, "t_ms": 790, "previous_max_ms": 800, "backwards_ms": 10}]


def test_the_lag_rule_replays_the_tracker_a_stale_sample_cannot_resolve_what_a_fresher_one_already_did(harness) -> None:  # type: ignore[no-untyped-def]
    # registered at 130; samples: 110 (before registration), 190, 700, then a stale 400
    series = [[T0 + 110, 1.0], [T0 + 190, 1.1], [T0 + 700, 1.2], [T0 + 400, 1.2]]
    assert harness._first_mid_seen(series, after_ms=T0 + 130, at_or_after_ms=T0 + 100) == (T0 + 190, 1.1)
    assert harness._first_mid_seen(series, after_ms=T0 + 130, at_or_after_ms=T0 + 500) == (T0 + 700, 1.2)
    assert harness._first_mid_seen(series, after_ms=None, at_or_after_ms=T0 + 100) == (T0 + 110, 1.0)
    # a stale stamp processed after registration can still satisfy a target it is at or after
    assert harness._first_mid_seen([[T0 + 50, 1.0], [T0 + 900, 1.0], [T0 + 400, 1.3]], after_ms=T0 + 850, at_or_after_ms=T0 + 300) == (T0 + 900, 1.0)
    assert harness._first_mid_seen([[T0 + 50, 1.0], [T0 + 900, 1.0]], after_ms=T0 + 950, at_or_after_ms=T0 + 300) is None


def test_the_summary_separates_on_time_from_late_and_reports_the_effective_horizon(harness) -> None:  # type: ignore[no-untyped-def]
    rows = [_real("2422185", "buy", 85772.0, F1_T, 129, F1_MARKS), _real("2423539", "sell", 85712.1, F2_T, 127, F2_MARKS)]
    s100 = harness._markout_summary(rows)["100"]
    assert s100["measured"] == 2 and s100["measured_late"] == 2 and s100["measured_on_time"] == 0
    assert s100["markout_bps_on_time"]["count"] == 0 and s100["markout_bps_late"]["count"] == 2
    assert s100["late_by_ms"]["min"] == 27 and s100["late_by_ms"]["max"] == 29
    assert s100["effective_horizon_ms"]["min"] == 217 and s100["effective_horizon_ms"]["max"] == 233
    s250 = harness._markout_summary(rows)["250"]
    assert s250["measured_late"] == 0 and s250["measured_on_time"] == 2 and s250["effective_horizon_ms"]["min"] == 289 and s250["markout_bps_on_time"]["count"] == 2
