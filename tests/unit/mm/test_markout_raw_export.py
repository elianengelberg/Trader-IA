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
    assert by_h[100] == {"horizon_ms": 100, "target_t_ms": T0 + 100, "mark_t_ms": T0 + 300, "mark_seq": 2, "delay_ms": 200, "mid_at_mark": 100.2, "markout_bps": pytest.approx(20.0), "markout_usd": pytest.approx(0.4), "measured": True, "late_by_ms": None, "measured_late": False, "effective_horizon_ms": 300}
    assert row["t_registered_ms"] is None and row["registration_lag_ms"] is None  # registered without a clock: unknown, never guessed
    assert row["mid_seq_at_registration"] == 0 and [hz["mark_seq"] for hz in row["horizons"]] == [2, 2, 3, 4, 5, 6]  # registered before any mid; the second mid resolved 100 and 250
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
    assert not by_h[500]["measured"] and by_h[500] == {"horizon_ms": 500, "target_t_ms": T0 + 500, "mark_t_ms": None, "mark_seq": None, "delay_ms": None, "mid_at_mark": None, "markout_bps": None, "markout_usd": None, "measured": False, "late_by_ms": None, "measured_late": False, "effective_horizon_ms": None}
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


def test_a_fill_registered_after_its_100_ms_horizon_is_marked_late_with_the_horizon_it_really_measured() -> None:
    """The live path: the venue's trade time is t_fill, the confirmation is processed ~130 ms
    later. Mids shown before registration cannot resolve anything; the 100 ms horizon is
    resolved by the first mid after registration, flagged measured_late, and its effective
    horizon is what was measured. Nothing is back-filled from earlier mids."""
    tracker = MarkoutTracker()
    tracker.on_mid(T0 + 50, 100.0)
    tracker.on_mid(T0 + 110, 100.1)  # at or after t_fill + 100, but the fill is not known yet
    tracker.register(_buy("late", t=T0), t_registered_ms=T0 + 130)
    for t, mid in [(T0 + 190, 100.3), (T0 + 260, 100.4), (T0 + 510, 100.5), (T0 + 1_010, 100.6), (T0 + 2_010, 100.7), (T0 + 5_010, 100.8)]:
        tracker.on_mid(t, mid)
    [row] = tracker.raw_rows()
    assert row["t_registered_ms"] == T0 + 130 and row["registration_lag_ms"] == 130
    by_h = {hz["horizon_ms"]: hz for hz in row["horizons"]}
    h100 = by_h[100]
    assert h100["mark_t_ms"] == T0 + 190 and h100["mid_at_mark"] == 100.3  # not the +110 mid: it was seen before the fill was known
    assert h100["late_by_ms"] == 30 and h100["measured_late"] is True and h100["effective_horizon_ms"] == 190 and h100["delay_ms"] == 90
    assert h100["markout_bps"] == pytest.approx(30.0)
    h250 = by_h[250]
    assert h250["mark_t_ms"] == T0 + 260 and h250["late_by_ms"] == 0 and h250["measured_late"] is False and h250["effective_horizon_ms"] == 260
    assert all(by_h[h]["late_by_ms"] == 0 and not by_h[h]["measured_late"] for h in (250, 500, 1_000, 2_000, 5_000))


def test_late_by_is_measured_against_the_target_not_the_fill_and_an_unmeasured_late_horizon_is_not_measured_late() -> None:
    tracker = MarkoutTracker()
    tracker.register(_buy("l2", t=T0), t_registered_ms=T0 + 400)  # 100 and 250 ms already past
    tracker.on_mid(T0 + 450, 100.1)
    [row] = tracker.raw_rows()
    by_h = {hz["horizon_ms"]: hz for hz in row["horizons"]}
    assert by_h[100]["late_by_ms"] == 300 and by_h[250]["late_by_ms"] == 150 and by_h[500]["late_by_ms"] == 0
    assert by_h[100]["measured_late"] and by_h[250]["measured_late"] and by_h[100]["effective_horizon_ms"] == 450 and by_h[250]["effective_horizon_ms"] == 450
    assert not by_h[500]["measured"] and not by_h[500]["measured_late"] and by_h[500]["effective_horizon_ms"] is None  # pending, not late


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
    # Each sample carries the number the tracker gave it: consecutive from 1, in processing order.
    assert [m[2] for m in engine.mid_samples] == list(range(1, len(engine.mid_samples) + 1)) and engine.markouts.mids_seen == len(engine.mid_samples)
    assert all(hz["measured"] for hz in row["horizons"])
    # The paper path registers the fill on the event that produced it: no registration lag,
    # nothing late, the effective horizon is the nominal one plus the series' own delay.
    assert row["t_registered_ms"] == row["t_fill_ms"] and row["registration_lag_ms"] == 0
    assert all(hz["late_by_ms"] == 0 and not hz["measured_late"] and hz["effective_horizon_ms"] == hz["horizon_ms"] + hz["delay_ms"] for hz in row["horizons"])
    # The fill was registered on the event that produced it, before that event's mid was shown.
    assert row["mid_seq_at_registration"] == sum(1 for m in mids if m[0] < row["t_registered_ms"])
    for hz in row["horizons"]:
        first = next(m for m in mids if m[2] > row["mid_seq_at_registration"] and m[0] >= hz["target_t_ms"])
        assert first[0] == hz["mark_t_ms"] and first[1] == hz["mid_at_mark"] and first[2] == hz["mark_seq"]
        assert first == next(m for m in mids if m[0] >= hz["target_t_ms"])  # one clock, in order: the stamp rule agrees here
        assert hz["markout_bps"] == pytest.approx((first[1] - row["price"]) / row["price"] * 1e4)
        assert hz["markout_usd"] == pytest.approx(hz["markout_bps"] / 1e4 * row["price"] * row["quantity"])
        assert 0 <= hz["delay_ms"] <= row["tolerance_ms"]


# ------------------------------------------------------------------ the tracker numbers the mids it sees


def _engine_like(tracker: MarkoutTracker, series: list[tuple[int, float, int]], t: int, mid: float) -> None:
    """One market event as the engine does it: the tracker consumes the sample, the series
    keeps that very sample with the number the tracker gave it."""
    tracker.on_mid(t, mid)
    series.append((t, mid, tracker.mids_seen))


def test_mids_are_numbered_in_the_order_the_tracker_sees_them_and_a_fill_remembers_how_many_it_had_seen() -> None:
    tracker = MarkoutTracker()
    series: list[tuple[int, float, int]] = []
    assert tracker.mids_seen == 0
    _engine_like(tracker, series, T0 - 500, 100.0)
    _engine_like(tracker, series, T0 - 200, 100.0)  # numbered even with nothing pending
    tracker.register(_buy("n1", t=T0), t_registered_ms=T0 + 5)
    for dt, mid in [(110, 100.1), (260, 100.2), (510, 100.3), (1_010, 100.4), (2_010, 100.5), (5_010, 100.6)]:
        _engine_like(tracker, series, T0 + dt, mid)
    assert [s[2] for s in series] == [1, 2, 3, 4, 5, 6, 7, 8]
    [m] = tracker.resolved
    assert m.mid_seq_at_registration == 2 and m.mark_seq == {100: 3, 250: 4, 500: 5, 1_000: 6, 2_000: 7, 5_000: 8}
    [row] = tracker.raw_rows()
    assert row["mid_seq_at_registration"] == 2 and [hz["mark_seq"] for hz in row["horizons"]] == [3, 4, 5, 6, 7, 8]
    # the journal row is untouched: the numbering is evidence, like t_registered
    assert "mark_seq" not in m.as_dict() and "mid_seq_at_registration" not in m.as_dict()
    assert "mid_seq" in HORIZON_RULE and "mark_seq" in HORIZON_RULE


def test_a_horizon_never_measured_has_no_mark_seq_and_a_shadow_is_numbered_like_any_fill() -> None:
    tracker = MarkoutTracker()
    series: list[tuple[int, float, int]] = []
    _engine_like(tracker, series, T0 + 50, 100.0)
    tracker.register(_buy("gap", t=T0), t_registered_ms=T0 + 60)
    _engine_like(tracker, series, T0 + 120, 100.1)
    _engine_like(tracker, series, T0 + 1_500, 100.2)  # a gap: 250 and 500 expire, 1000 is measured (within tolerance)
    [row] = tracker.raw_rows()
    by_h = {hz["horizon_ms"]: hz for hz in row["horizons"]}
    assert row["expired"] and row["mid_seq_at_registration"] == 1
    assert by_h[100]["mark_seq"] == 2 and by_h[250]["mark_seq"] is None and not by_h[250]["measured"]


# ------------------------------------------------------------------ the 2026-10-06 60-minute run on 9bd4b17: two fills, one pattern

# Fills 2447364 (buy) and 2447492 (sell), both with the 100 ms horizon measured late (registration
# lag 120-156 ms on every fill of that run). The series held a sample stamped at or after the target
# and at or after the registration stamp that the tracker had ALREADY consumed when the fill's
# confirmation was processed. The depth update caused by the trade that filled us and the execution
# report of that same trade leave the venue together and arrive on two connections, each stamped
# by its own receive clock (the market stream by ReceiveClock, the account stream by the wall clock);
# the market one was processed first. Stamps and mids below are the run's; the fill prices are
# illustrative (the run's are in its evidence file) and the lag is placed inside the observed band.
RUN_60M = [
    ("2447364", "buy", 85_290.0, (1_791_267_584_380, 85_298.775), (1_791_267_584_469, 85_298.775), (1_791_267_584_532, 85_289.455)),
    ("2447492", "sell", 85_276.0, (1_791_267_741_060, 85_281.275), (1_791_267_741_150, 85_281.275), (1_791_267_741_230, 85_267.495)),
]


@pytest.mark.parametrize(("fill_id", "side", "price", "before", "consumed_first", "used"), RUN_60M)
@pytest.mark.parametrize("skew_ms", [0, 9], ids=["same_millisecond", "fill_clock_9ms_behind"])
def test_the_two_fills_of_the_60_minute_run_are_resolved_by_the_mid_numbered_after_registration_whatever_the_stamps_say(fill_id: str, side: str, price: float, before: tuple[int, float], consumed_first: tuple[int, float], used: tuple[int, float], skew_ms: int) -> None:
    t_registered = consumed_first[0] - skew_ms  # stamped in the same millisecond as the sample processed just before it, or earlier
    t_fill = t_registered - 130
    tracker = MarkoutTracker()
    series: list[tuple[int, float, int]] = []
    _engine_like(tracker, series, *before)
    _engine_like(tracker, series, *consumed_first)  # processed first: the fill is not known yet
    tracker.register(FillObservation(fill_id, t_fill, side, price, 0.0002, consumed_first[1]), t_registered_ms=t_registered)
    _engine_like(tracker, series, *used)
    [row] = tracker.raw_rows()
    h100 = row["horizons"][0]
    assert h100["measured_late"] and (h100["mark_t_ms"], h100["mid_at_mark"]) == used
    assert row["mid_seq_at_registration"] == 2 and h100["mark_seq"] == 3
    # By number, the series reproduces the mark exactly; by stamps, it cannot: the sample the
    # tracker consumed before the fill was known is stamped at or after both the target and the
    # registration, and nothing in a stamp says it was processed first.
    target = t_fill + 100
    by_number = next(s for s in series if s[2] > row["mid_seq_at_registration"] and s[0] >= target)
    assert by_number == (*used, 3)
    by_stamp = next(s for s in series if s[0] >= t_registered and s[0] >= target)
    assert (by_stamp[0], by_stamp[1]) == consumed_first != used


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
