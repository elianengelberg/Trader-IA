"""The latency profile: measured or refused. Synthetic stats throughout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tia.mm.latency import LatencyStats
from tia.mm.latency_model import (
    MIN_LATENCY_MS,
    LatencyProfile,
    LatencyProfileError,
    build_latency_profile,
)


def _stats(values: list[float]) -> dict:  # type: ignore[type-arg]
    stats = LatencyStats()
    for v in values:
        stats.add(v)
    return stats.as_dict()


def _stream(depth: list[float], trade: list[float]) -> dict:  # type: ignore[type-arg]
    return {"latency_depth_ms": _stats(depth), "latency_trade_ms": _stats(trade)}


def test_a_profile_is_built_from_measurements_and_names_its_commit(tmp_path: Path) -> None:
    profile = build_latency_profile(
        stream=_stream([40, 45, 50, 60, 120], [38, 41, 44, 55, 90]),
        processing_us=_stats([20, 30, 40, 400]),
        measured_at_utc="2026-09-18T20:00:00Z",
        commit="abc1234",
        duration_s=300.2,
        symbol="BTC-USD",
    )
    assert profile.commit == "abc1234" and profile.duration_s == 300.2
    assert profile.measured["exchange_to_local_depth_ms"].count == 5
    assert profile.measured["exchange_to_local_depth_ms"].p50 == 50.0
    assert profile.pipeline == {"decision_to_simulated_order_ms": None, "simulated_order_to_fill_evaluation_ms": None}
    path = profile.write(tmp_path / "profile.json")
    loaded = LatencyProfile.load(path)
    assert loaded == profile and loaded.profile_id == profile.profile_id
    raw = json.loads(path.read_text())
    assert raw["pipeline"]["decision_to_simulated_order_ms"] is None  # not measured, not invented
    assert "not invented" in raw["note"]


def test_scenarios_come_from_the_measured_path_and_never_reach_zero() -> None:
    profile = build_latency_profile(
        stream=_stream([1, 1, 1, 2, 2], [1, 1, 1, 1, 1]),  # a very fast path
        processing_us=_stats([10, 10, 10]),
        measured_at_utc="2026-09-18T20:00:00Z",
        commit="abc",
        duration_s=60,
        symbol="BTC-USD",
    )
    optimistic = profile.scenario("optimistic")
    baseline = profile.scenario("baseline")
    conservative = profile.scenario("conservative")
    assert optimistic.order_latency_ms == MIN_LATENCY_MS  # floored: p50 was 1 ms
    assert baseline.order_latency_ms == MIN_LATENCY_MS
    assert conservative.order_latency_ms == MIN_LATENCY_MS
    assert all(s.profile_id == profile.profile_id for s in (optimistic, baseline, conservative))
    slow = build_latency_profile(
        stream=_stream([40, 50, 60, 80, 200], [40, 50, 60, 80, 200]),
        processing_us=_stats([100, 200]),
        measured_at_utc="2026-09-18T20:00:00Z",
        commit="abc",
        duration_s=60,
        symbol="BTC-USD",
    )
    assert slow.scenario("optimistic").order_latency_ms == 60.0  # p50
    assert slow.scenario("baseline").order_latency_ms == 200.0  # p95 (nearest rank of 5 samples)
    assert slow.scenario("conservative").order_latency_ms == 400.0  # 2 x p99
    assert slow.scenario("baseline").cancel_latency_ms == 200.0
    with pytest.raises(LatencyProfileError):
        slow.scenario("zero")


def test_a_missing_empty_or_malformed_profile_is_refused(tmp_path: Path) -> None:
    with pytest.raises(LatencyProfileError, match="not found"):
        LatencyProfile.load(tmp_path / "missing.json")
    with pytest.raises(LatencyProfileError, match="no samples"):
        build_latency_profile(
            stream=_stream([], [1]), processing_us=_stats([1]), measured_at_utc="t", commit="c", duration_s=1, symbol="BTC-USD"
        )
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": 1, "measured_at_utc": "t", "duration_s": 1, "measured": {}}))
    with pytest.raises(LatencyProfileError, match="lacks"):
        LatencyProfile.load(bad)
    unordered = build_latency_profile(
        stream=_stream([10, 20, 30], [10, 20, 30]), processing_us=_stats([1, 2]), measured_at_utc="t", commit="c", duration_s=1, symbol="BTC-USD"
    ).as_dict()
    unordered["measured"]["exchange_to_local_depth_ms"]["p50"] = 999.0  # p50 above p95: not a measurement
    with pytest.raises(LatencyProfileError, match="not ordered"):
        LatencyProfile.from_dict(unordered)
    zero = build_latency_profile(
        stream=_stream([10, 20, 30], [10, 20, 30]), processing_us=_stats([1, 2]), measured_at_utc="t", commit="c", duration_s=1, symbol="BTC-USD"
    ).as_dict()
    zero["measured"]["exchange_to_local_trade_ms"]["count"] = 0
    with pytest.raises(LatencyProfileError, match="zero samples"):
        LatencyProfile.from_dict(zero)


def test_the_profile_id_changes_with_the_measurement_not_with_the_path(tmp_path: Path) -> None:
    common = {"processing_us": _stats([10, 20]), "measured_at_utc": "t", "commit": "c", "duration_s": 60, "symbol": "BTC-USD"}
    a = build_latency_profile(stream=_stream([10, 20, 30], [5, 6, 7]), **common)
    b = build_latency_profile(stream=_stream([10, 20, 30], [5, 6, 7]), **common)
    c = build_latency_profile(stream=_stream([10, 20, 31], [5, 6, 7]), **common)
    assert a.profile_id == b.profile_id != c.profile_id
    assert LatencyProfile.load(a.write(tmp_path / "x" / "p.json")).profile_id == a.profile_id
