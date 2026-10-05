"""Raw markout evidence: the tracker exports what it measured, per fill and per horizon,
the engine records every mid it showed the tracker and one context record per fill, and
none of it changes a single decision. The decision/fill/markout journal of the synthetic
tape is pinned by its SHA-256 as computed before this instrumentation existed."""

from __future__ import annotations

import pytest

from tests.unit.mm.test_engine_replay import _run, _tape
from tia.mm.adverse_selection import HORIZON_RULE, HORIZONS_MS, FillObservation, MarkoutTracker

T0 = 1_789_754_400_000

# journal_hash() of _run(_tape(n)) at commit 76a5173, before any evidence recording was added.
GOLDEN = {
    20: "6eccfa05a693d9ccaf9a2dc43f5778e7c624fb068dfb4135d65b3103a7a6b452",
    40: "cf28cbefda068d0bf4f1399fc64aac41ff777f333c055e144de72413b5a28f51",
}

# ------------------------------------------------------------------ the tracker, raw


def _buy(fill_id: str = "t1", *, t: int = T0, price: float = 100.0, qty: float = 2.0, mid: float = 100.05) -> FillObservation:
    return FillObservation(fill_id=fill_id, t_fill_ms=t, side="buy", price=price, quantity=qty, mid_at_fill=mid, buckets={"side": "buy"})


def test_raw_rows_carry_every_horizon_with_its_mark_delay_mid_and_values() -> None:
    tracker = MarkoutTracker()
    tracker.register(_buy())
    mids = [(T0 + 50, 100.1), (T0 + 300, 100.2), (T0 + 600, 100.3), (T0 + 1_100, 99.9), (T0 + 2_100, 100.5), (T0 + 5_200, 101.0)]
    for t, mid in mids:
        tracker.on_mid(t, mid)
    [row] = tracker.raw_rows()
    assert row["fill_id"] == "t1" and row["resolved"] and not row["expired"] and not row["pending"] and not row["shadow"]
    assert row["mid_at_fill"] == 100.05 and row["fill_to_mid_bps"] == pytest.approx(5.0) and row["notional_usd"] == 200.0 and row["tolerance_ms"] == 1_000
    by_h = {hz["horizon_ms"]: hz for hz in row["horizons"]}
    assert tuple(by_h) == HORIZONS_MS
    # 100 ms: the first mid at or after T0+100 is the one at T0+300 (the +50 one is too early)
    assert by_h[100] == {"horizon_ms": 100, "target_t_ms": T0 + 100, "mark_t_ms": T0 + 300, "delay_ms": 200, "mid_at_mark": 100.2, "markout_bps": pytest.approx(20.0), "markout_usd": pytest.approx(0.4), "measured": True}
    assert by_h[250]["mark_t_ms"] == T0 + 300 and by_h[250]["delay_ms"] == 50
    assert by_h[500]["mark_t_ms"] == T0 + 600 and by_h[500]["markout_bps"] == pytest.approx(30.0)
    assert by_h[1_000]["mark_t_ms"] == T0 + 1_100 and by_h[1_000]["markout_bps"] == pytest.approx(-10.0) and by_h[1_000]["markout_usd"] == pytest.approx(-0.2)
    assert by_h[2_000]["mark_t_ms"] == T0 + 2_100 and by_h[5_000]["mark_t_ms"] == T0 + 5_200 and by_h[5_000]["delay_ms"] == 200
    assert all(hz["measured"] for hz in row["horizons"])


def test_a_sell_fill_with_a_rising_mid_is_adverse_and_negative() -> None:
    tracker = MarkoutTracker()
    tracker.register(FillObservation("s1", T0, "sell", 100.0, 1.0, 99.95, {"side": "sell"}))
    for t, mid in [(T0 + 100, 100.1), (T0 + 250, 100.2), (T0 + 500, 100.3), (T0 + 1_000, 100.4), (T0 + 2_000, 100.5), (T0 + 5_000, 100.6)]:
        tracker.on_mid(t, mid)
    [row] = tracker.raw_rows()
    assert [hz["delay_ms"] for hz in row["horizons"]] == [0] * 6  # a mid exactly at the target resolves it
    assert [round(hz["markout_bps"], 6) for hz in row["horizons"]] == [-10.0, -20.0, -30.0, -40.0, -50.0, -60.0]
    assert row["horizons"][3]["markout_usd"] == pytest.approx(-0.4)


def test_a_data_gap_leaves_the_horizon_unmeasured_and_keeps_the_fill_as_unresolved() -> None:
    tracker = MarkoutTracker()
    tracker.register(_buy("g1"))
    tracker.on_mid(T0 + 100, 100.1)  # resolves 100 ms
    tracker.on_mid(T0 + 260, 100.2)  # resolves 250 ms
    tracker.on_mid(T0 + 3_000, 100.3)  # 500 ms is 1.5 s late: past tolerance -> the fill expires
    assert tracker.expired == 1 and len(tracker.resolved) == 0 and tracker.pending == 0
    [row] = tracker.raw_rows()
    assert row["expired"] and not row["resolved"] and not row["pending"]
    by_h = {hz["horizon_ms"]: hz for hz in row["horizons"]}
    assert by_h[100]["measured"] and by_h[250]["measured"]
    assert not by_h[500]["measured"] and by_h[500] == {"horizon_ms": 500, "target_t_ms": T0 + 500, "mark_t_ms": None, "delay_ms": None, "mid_at_mark": None, "markout_bps": None, "markout_usd": None, "measured": False}
    assert not by_h[5_000]["measured"]


def test_pending_fills_are_exported_as_pending_and_shadows_only_on_request() -> None:
    tracker = MarkoutTracker()
    tracker.register(_buy("p1"))
    tracker.register(FillObservation("shadow-x", T0, "buy", 100.0, 1.0, 100.0, {}, shadow=True))
    tracker.on_mid(T0 + 120, 100.1)
    rows = tracker.raw_rows()
    assert [r["fill_id"] for r in rows] == ["p1"] and rows[0]["pending"] and sum(1 for hz in rows[0]["horizons"] if hz["measured"]) == 1
    assert [r["fill_id"] for r in tracker.raw_rows(include_shadow=True)] == ["p1", "shadow-x"]


def test_the_journal_row_of_a_markout_is_unchanged_and_the_rule_is_stated() -> None:
    tracker = MarkoutTracker()
    tracker.register(_buy("j1"))
    for t in (100, 250, 500, 1_000, 2_000, 5_000):
        tracker.on_mid(T0 + t, 100.1)
    [m] = tracker.resolved
    assert set(m.as_dict()) == {"fill_id", "shadow", "side", "price", "quantity", "t_fill_ms", "fill_to_mid_bps", "buckets", "markout_bps", "adverse_bps_1s", "favorable_bps_1s", "resolved", "expired"}
    assert "FIRST mid observed at or after t_fill + h" in HORIZON_RULE and "tolerance_ms" in HORIZON_RULE and "positive is favourable" in HORIZON_RULE


# ------------------------------------------------------------------ the engine, recording without deciding


@pytest.mark.parametrize("n", [20, 40])
def test_the_decision_fill_and_markout_journal_is_byte_identical_to_the_pre_instrumentation_golden_hash(n: int) -> None:
    engine = _run(_tape(n))
    assert engine.journal_hash() == GOLDEN[n]
    assert engine.ledger.state.fills == 1 and len(engine.fill_records) == 1 and len(engine.mid_samples) > 0


def test_recording_is_passive_the_hash_is_the_same_with_the_evidence_buffers_disabled() -> None:
    from collections import deque

    from tests.unit.mm.test_engine_replay import PROFILE, _config, _gate
    from tia.mm.engine import MarketMakerEngine

    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("optimistic"), gate=_gate())
    engine.mid_samples = deque(maxlen=0)
    engine.fill_records = deque(maxlen=0)
    for kind, event, t in _tape(40):
        engine.on_event(kind, event, t)
    assert engine.journal_hash() == GOLDEN[40] and len(engine.fill_records) == 0 and len(engine.mid_samples) == 0


def test_the_fill_record_has_the_context_and_the_mid_series_reproduces_every_markout() -> None:
    engine = _run(_tape(40))
    [record] = engine.fill_records
    required = {
        "fill_id", "order_id", "venue_order_id", "side", "price", "quantity", "notional_usd", "t_fill_ms", "t_booked_ms",
        "inventory_before_btc", "inventory_after_btc", "mid_at_fill", "mid_used_by_tracker", "capture_bps_vs_mid_at_fill",
        "fair_value_at_quote", "capture_bps_vs_fair_value_at_quote", "fair_value_at_fill", "quote", "toxicity_at_fill",
        "data_age_at_fill_ms", "t_decision_ms", "t_ack_ms", "resting_ms", "realised_usd", "regimes",
    }
    assert required <= set(record) and "error" not in record
    assert record["inventory_before_btc"] == 0.0 and record["inventory_after_btc"] == pytest.approx(record["quantity"])
    quote = record["quote"]
    assert {"t_decision_ms", "fair_value", "fair_value_confidence", "bid", "ask", "bid_size", "ask_size", "half_spread_bps", "toxicity", "data_age_ms"} <= set(quote)
    assert quote["bid"] == record["price"] and record["side"] == "buy"  # the filled order was the bid of that decision
    assert record["capture_bps_vs_fair_value_at_quote"] == pytest.approx((quote["fair_value"] - record["price"]) / quote["fair_value"] * 1e4)
    assert record["resting_ms"] == record["t_fill_ms"] - record["t_ack_ms"] and record["resting_ms"] > 0
    # Every markout the tracker measured is reproduced from the mid series by the stated rule.
    [row] = engine.markouts.raw_rows()
    mids = sorted(engine.mid_samples)
    assert mids == list(engine.mid_samples)  # recorded in time order
    assert all(hz["measured"] for hz in row["horizons"])
    for hz in row["horizons"]:
        first = next(m for m in mids if m[0] >= hz["target_t_ms"])
        assert first[0] == hz["mark_t_ms"] and first[1] == hz["mid_at_mark"]
        assert hz["markout_bps"] == pytest.approx((first[1] - row["price"]) / row["price"] * 1e4)
        assert hz["markout_usd"] == pytest.approx(hz["markout_bps"] / 1e4 * row["price"] * row["quantity"])
        assert 0 <= hz["delay_ms"] <= row["tolerance_ms"]


def test_a_failure_while_recording_never_reaches_the_booking_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.unit.mm.test_engine_replay import PROFILE, _config, _gate
    from tia.mm.engine import MarketMakerEngine

    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("optimistic"), gate=_gate())

    def boom(order_id: str) -> None:
        raise RuntimeError("evidence broke")

    monkeypatch.setattr(engine, "_find_order", boom)
    for kind, event, t in _tape(40):
        engine.on_event(kind, event, t)
    assert engine.journal_hash() == GOLDEN[40] and engine.ledger.state.fills == 1  # booked, journaled, identical
    [record] = engine.fill_records
    assert record["error"].startswith("RuntimeError") and record["fill_id"] == "mmf-00000003"
