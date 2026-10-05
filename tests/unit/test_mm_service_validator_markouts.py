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


def _row(fill_id: str, side: str, price: float, qty: float, t_fill: int, mids: dict[int, tuple[int, float] | None], *, shadow: bool = False) -> dict[str, Any]:
    horizons = _horizons(t_fill, price, qty, side, mids)
    measured = all(h["measured"] for h in horizons)
    return {"fill_id": fill_id, "shadow": shadow, "side": side, "price": price, "quantity": qty, "notional_usd": price * qty, "t_fill_ms": t_fill, "mid_at_fill": price, "fill_to_mid_bps": 0.0, "buckets": {}, "tolerance_ms": 1_000, "resolved": measured, "expired": not measured, "pending": False, "horizons": horizons}


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
    # the series disagrees: an earlier mid existed at or after the target
    assert any("mid series says" in p for p in harness._markout_consistency([rows[0]], [*mids, (T0 + 120, 100.0)]))
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
