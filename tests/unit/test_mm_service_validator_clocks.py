"""The service validator's clock evidence: the venue-host offset estimate and the order
lifecycle with host and venue clocks apart. Hand-built rows; a test of the validator."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def harness():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("validate_mm_live_service_testnet")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_the_clock_offset_is_the_median_midpoint_with_half_the_best_round_trip_as_its_error(harness) -> None:  # type: ignore[no-untyped-def]
    est = harness._estimate_clock_offset([(1_000, 1_230, 1_240), (2_000, 2_250, 2_260), (3_000, 3_095, 3_010)])
    assert est["n"] == 3 and est["offset_ms"] == 110.0 and est["min_rtt_ms"] == 10 and est["error_bound_ms"] == 5.0  # offsets 110, 120, 90: median 110; best round trip 10 ms (the third sample)
    assert est["offset_at_min_rtt_ms"] == 90.0 and est["applied"] is False
    wide = harness._estimate_clock_offset([(4_000, 4_400, 4_500)])
    assert wide["offset_ms"] == 150.0 and wide["error_bound_ms"] == 250.0  # a slow round trip bounds the estimate loosely
    assert est["samples"][0] == {"host_before_ms": 1_000, "server_time_ms": 1_230, "host_after_ms": 1_240, "offset_ms": 110.0, "rtt_ms": 240}
    behind = harness._estimate_clock_offset([(1_000, 900, 1_020)])
    assert behind["offset_ms"] == -110.0  # the venue reads behind the host
    assert harness._estimate_clock_offset([])["offset_ms"] is None


class _Fill:
    def __init__(self, t_ms: int, received_at_ms: int | None, quantity: float = 0.0002) -> None:
        self.t_ms, self.quantity = t_ms, quantity
        if received_at_ms is not None:
            self.received_at_ms = received_at_ms


class _LiveLike:
    """An order as the live adapter holds it: host stamps, a venue acceptance time, monotonic stamps."""

    def __init__(self, *, t_ack: int, venue_ack: int | None, fills: list[_Fill], mono_span: float | None = None) -> None:
        self.order_id, self.side, self.price, self.quantity, self.state = "live-1", "sell", 85_000.0, 0.0002, "filled"
        self.t_decision_ms, self.t_decided_host_ms, self.t_enqueued_ms, self.t_submitted_ms = 10_000, 10_982, 10_982, 10_983
        self.t_ack_ms, self.venue_ack_time_ms, self.ack_source = t_ack, venue_ack, "stream"
        self.mono_enqueued_ms, self.mono_ack_ms = 500.0, (500.0 + mono_span) if mono_span is not None else None
        self.t_cancel_requested_ms = self.t_cancel_effective_ms = None
        self.cancel_reason, self.fills, self.venue_order_id = "", fills, "9"


def test_a_venue_trade_time_before_the_host_ack_gives_a_non_negative_host_resting_and_a_venue_resting_on_venue_stamps(harness) -> None:  # type: ignore[no-untyped-def]
    # the 2026-10-06 case: fill reported at venue time 74 ms before the host acknowledgement instant
    order = _LiveLike(t_ack=11_566, venue_ack=11_300, fills=[_Fill(t_ms=11_492, received_at_ms=11_619)], mono_span=584.0)
    lc = harness._order_lifecycle([order])
    [row] = lc["rows"]
    assert row["host_resting_ms"] == 11_619 - 11_566 == 53 and row["resting_ms"] == 53  # host receipt minus host ack, never the venue's trade time
    assert row["venue_resting_ms"] == 11_492 - 11_300 == 192  # venue trade time minus venue acceptance time
    assert row["event_age_at_decision_ms"] == 982 and row["t_decided_host_ms"] == 10_982
    assert row["host_wall_vs_mono_drift_ms"] == (11_566 - 10_982) - 584.0 == 0.0
    assert lc["resting_ms"]["min"] == 53 and lc["venue_resting_ms"]["count"] == 1 and lc["event_age_at_decision_ms"]["max"] == 982 and lc["event_age_at_decision_ms"]["max_order_id"] == "live-1"
    assert lc["event_age_at_decision_ms"]["over_200_ms"] == 1 and lc["host_wall_vs_mono_drift_ms"]["max_abs"] == 0.0


def test_unknown_venue_acceptance_time_leaves_the_venue_resting_null_and_old_objects_still_work(harness) -> None:  # type: ignore[no-untyped-def]
    order = _LiveLike(t_ack=11_566, venue_ack=None, fills=[_Fill(t_ms=11_492, received_at_ms=11_619)])
    [row] = harness._order_lifecycle([order])["rows"]
    assert row["venue_resting_ms"] is None and row["host_resting_ms"] == 53 and row["host_wall_vs_mono_drift_ms"] is None
    # the pre-instrumentation test double: one simulated clock, fills without a receipt stamp
    from tests.unit.test_mm_service_validator_experiment import _Fill as OldFill
    from tests.unit.test_mm_service_validator_experiment import _Order as OldOrder

    old = OldOrder("g", "filled", t_ack=1_300, fills=[OldFill("77", 14_300, 0.0002)])
    [row] = harness._order_lifecycle([old])["rows"]
    assert row["resting_ms"] == 13_000 == row["host_resting_ms"] and row["venue_resting_ms"] is None and row["event_age_at_decision_ms"] is None


def test_a_wall_clock_step_between_enqueue_and_ack_shows_as_drift(harness) -> None:  # type: ignore[no-untyped-def]
    order = _LiveLike(t_ack=12_566, venue_ack=12_300, fills=[_Fill(t_ms=12_492, received_at_ms=12_619)], mono_span=584.0)  # wall span 1584 ms, monotonic 584 ms
    [row] = harness._order_lifecycle([order])["rows"]
    assert row["host_wall_vs_mono_drift_ms"] == 1_000.0


def test_the_clock_measurement_runs_before_the_market_starts_and_s1_is_judged_on_the_picture_at_the_wait(harness) -> None:  # type: ignore[no-untyped-def]
    """The 2026-10-06 05:09Z run: S1 re-read market.usable 1.6 s after the wait, past the
    clock measurement, and Testnet's feed had gone stale in between. The measurement now
    precedes market.start(); between the wait and the S1 judgement nothing is awaited and
    the judgement reads the snapshot taken at the wait."""
    import inspect

    source = inspect.getsource(harness.ServiceValidation.run)
    assert source.index("_measure_clock_offset(self.public)") < source.index("self.market.start()")
    wait = source.index("await _wait_until(lambda: bool(self.market and self.market.usable)")
    judged = source.index('ev.mark("S1.testnet_market_data_usable"')
    between = source[wait + len("await _wait_until"):judged]
    code = "\n".join(line for line in between.splitlines() if not line.strip().startswith("#"))  # comments may say "awaited"
    assert "await" not in code, code
    assert 'usable_at_wait = bool(snap.get("usable"))' in between
