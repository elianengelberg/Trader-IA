"""The funding monitor: documented shapes parse, failure is a health row, and the
report's percentile and carry arithmetic come from the record."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tia.core.clock import SimulatedClock
from tia.data.funding import (
    CARRY_ROUND_TRIP_FEE_BPS,
    FundingMonitor,
    parse_funding_history,
    parse_premium_index,
    percentile_of,
)

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)

PREMIUM = {
    "symbol": "BTCUSDT", "markPrice": "60030.00", "indexPrice": "60000.00",
    "estimatedSettlePrice": "60010", "lastFundingRate": "0.00030000",
    "interestRate": "0.00010000", "nextFundingTime": NOW_MS + 3_600_000, "time": NOW_MS,
}


def _history(n: int, rate: float, *, ramp: float = 0.0) -> list[dict]:  # type: ignore[type-arg]
    rows = []
    for i in range(n):
        at = NOW - timedelta(hours=8 * (n - i))
        rows.append(
            {
                "symbol": "BTCUSDT", "fundingTime": int(at.timestamp() * 1000),
                "fundingRate": f"{rate + ramp * i:.8f}", "markPrice": "59000.0",
            }
        )
    return rows


def _monitor(handler) -> FundingMonitor:  # type: ignore[no-untyped-def]
    return FundingMonitor(
        clock=SimulatedClock(start=NOW),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_the_premium_index_parses_and_annualises() -> None:
    reading = parse_premium_index(PREMIUM)
    assert reading.funding_rate == pytest.approx(0.0003)
    assert reading.annualised_pct == pytest.approx(0.0003 * 3 * 365 * 100)  # 32.85%
    assert reading.basis_bps == pytest.approx(5.0)
    assert reading.at == NOW


def test_the_history_parses_sorted_oldest_first() -> None:
    rows = parse_funding_history(list(reversed(_history(5, 0.0001))))
    assert [r.at for r in rows] == sorted(r.at for r in rows)
    assert rows[0].mark_price == 59000.0


def test_percentile_is_the_share_at_or_below() -> None:
    assert percentile_of(5.0, [1.0, 2.0, 5.0, 9.0]) == 75.0
    assert percentile_of(1.0, []) is None


async def test_a_poll_loads_history_once_and_reports_carry_and_stance() -> None:
    calls = {"history": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "fundingRate" in str(request.url):
            calls["history"] += 1
            return httpx.Response(200, json=_history(100, 0.0001))  # a placid year
        return httpx.Response(200, json=PREMIUM)  # today: three times the usual

    monitor = _monitor(handler)
    assert await monitor.poll() is not None
    assert await monitor.poll() is not None
    assert calls["history"] == 1

    report = monitor.report()
    assert report["health"]["ok"] is True
    assert report["history_settlements"] == 100
    assert report["latest"]["annualised_pct"] == pytest.approx(32.85)
    assert report["percentile"] == 100.0
    assert report["stance"] == "crowded long"
    assert report["carry"]["net_annualised_pct"] == pytest.approx(32.85 - CARRY_ROUND_TRIP_FEE_BPS / 100)
    assert "predicts crashes" in report["verdict"]
    assert report["mean_annualised_pct_7d"] is not None
    json.dumps(report)
    await monitor.close()


async def test_a_failed_endpoint_is_a_health_row_not_a_number() -> None:
    monitor = _monitor(lambda request: httpx.Response(451, text="unavailable in region"))
    assert await monitor.poll() is None
    report = monitor.report()
    assert report["health"]["ok"] is False and "451" in report["health"]["detail"]
    assert report["latest"] is None
    assert report["stance"] == "unknown"
    assert "No funding reading yet" in report["verdict"]
    await monitor.close()


async def test_negative_funding_at_the_bottom_of_its_range_is_a_crowded_short() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "fundingRate" in str(request.url):
            return httpx.Response(200, json=_history(50, 0.0002))
        return httpx.Response(200, json={**PREMIUM, "lastFundingRate": "-0.00050000"})

    monitor = _monitor(handler)
    await monitor.poll()
    report = monitor.report()
    assert report["percentile"] == 0.0
    assert report["stance"] == "crowded short"
    assert "crowded short" in report["verdict"]
    await monitor.close()
