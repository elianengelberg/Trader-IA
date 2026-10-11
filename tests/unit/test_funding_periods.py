"""Funding periods as the session names them, and the monitor's realised rate for one
(Phase 1.7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tia.core.clock import SimulatedClock
from tia.data.funding import FundingMonitor
from tia.runtime.live import (
    funding_period_from_index,
    funding_period_index,
    funding_period_key,
    funding_period_of,
    funding_period_start,
    parse_funding_period,
)


@pytest.mark.parametrize(
    ("at", "period"),
    [
        (datetime(2026, 10, 11, 0, 0, tzinfo=UTC), ("2026-10-11", 0)),
        (datetime(2026, 10, 11, 7, 59, 59, tzinfo=UTC), ("2026-10-11", 0)),
        (datetime(2026, 10, 11, 8, 0, 0, tzinfo=UTC), ("2026-10-11", 1)),
        (datetime(2026, 10, 11, 15, 59, 59, tzinfo=UTC), ("2026-10-11", 1)),
        (datetime(2026, 10, 11, 16, 0, 0, tzinfo=UTC), ("2026-10-11", 2)),
        (datetime(2026, 10, 11, 23, 59, 59, tzinfo=UTC), ("2026-10-11", 2)),
        (datetime(2026, 12, 31, 23, 30, tzinfo=UTC), ("2026-12-31", 2)),
    ],
)
def test_the_period_of_a_moment_is_its_utc_date_and_eight_hour_index(at, period) -> None:  # type: ignore[no-untyped-def]
    assert funding_period_of(at) == period
    assert funding_period_start(period) <= at < funding_period_start(period) + timedelta(hours=8)


def test_periods_are_consecutive_integers_across_days_and_years() -> None:
    first = ("2026-12-31", 2)
    index = funding_period_index(first)
    assert funding_period_from_index(index) == first
    assert funding_period_from_index(index + 1) == ("2027-01-01", 0)
    assert funding_period_from_index(index + 3) == ("2027-01-01", 2)
    assert funding_period_from_index(index - 2) == ("2026-12-31", 0)
    assert funding_period_index(("2027-01-01", 0)) - index == 1


def test_the_settlement_that_opens_a_period_is_at_a_whole_eight_hours_utc() -> None:
    assert funding_period_start(("2026-10-11", 0)) == datetime(2026, 10, 11, 0, tzinfo=UTC)
    assert funding_period_start(("2026-10-11", 1)) == datetime(2026, 10, 11, 8, tzinfo=UTC)
    assert funding_period_start(("2026-10-11", 2)) == datetime(2026, 10, 11, 16, tzinfo=UTC)


@pytest.mark.parametrize("text", ["2026-10-11:0", "2026-10-11:1", "2026-10-11:2"])
def test_the_key_round_trips(text: str) -> None:
    period = parse_funding_period(text)
    assert period is not None and funding_period_key(period) == text


@pytest.mark.parametrize("text", [None, "", "2026-10-11", "2026-10-11:3", "2026-10-11:-1", "garbage:1", "2026-13-40:1", 42])
def test_anything_malformed_is_no_period_not_a_guess(text) -> None:  # type: ignore[no-untyped-def]
    assert parse_funding_period(text) is None


# ---------------------------------------------------------------- the monitor's history

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)
SETTLED_AT = datetime(2026, 9, 18, 8, tzinfo=UTC)
EARLIER_AT = datetime(2026, 9, 18, 0, tzinfo=UTC)


def _ms(at: datetime) -> int:
    return int(at.timestamp() * 1000)


class _Venue:
    def __init__(self, history: list[dict[str, object]]) -> None:
        self.history = history

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "fundingRate" in request.url.path:
            return httpx.Response(200, content=json.dumps(self.history))
        return httpx.Response(200, content=json.dumps({
            "symbol": "BTCUSDT", "markPrice": "60030.00", "indexPrice": "60000.00",
            "estimatedSettlePrice": "60010", "lastFundingRate": "0.00090000",
            "interestRate": "0.00010000", "nextFundingTime": NOW_MS + 3_600_000, "time": NOW_MS,
        }))


async def test_the_realised_rate_of_a_settlement_comes_from_the_history_never_the_current_reading() -> None:
    venue = _Venue([
        {"symbol": "BTCUSDT", "fundingTime": _ms(EARLIER_AT), "fundingRate": "NaN", "markPrice": "59000"},
        {"symbol": "BTCUSDT", "fundingTime": _ms(SETTLED_AT), "fundingRate": "0.00030000", "markPrice": "60000"},
    ])
    monitor = FundingMonitor(clock=SimulatedClock(start=NOW), client=httpx.AsyncClient(transport=httpx.MockTransport(venue)))
    assert monitor.rate_at(SETTLED_AT) is None, "nothing before the history is loaded"
    await monitor.poll()
    assert monitor.latest_rate() == pytest.approx(0.0009), "the current reading"
    assert monitor.rate_at(SETTLED_AT) == pytest.approx(0.0003), "the settlement's own rate"
    assert monitor.rate_at(SETTLED_AT + timedelta(seconds=30)) == pytest.approx(0.0003), "within a minute"
    assert monitor.rate_at(SETTLED_AT.replace(tzinfo=None)) == pytest.approx(0.0003), "a naive moment is UTC"
    assert monitor.rate_at(EARLIER_AT) is None, "a non-finite settlement is no rate"
    assert monitor.rate_at(SETTLED_AT - timedelta(hours=16)) is None, "a settlement the history lacks"
    assert monitor.rate_at(SETTLED_AT + timedelta(minutes=2)) is None, "two minutes off is another moment"


async def test_the_history_is_refreshed_once_per_period_so_a_new_settlement_becomes_known() -> None:
    """The full record on the first poll; afterwards, when the clock has entered a new
    period, the last few settlements — so ``rate_at`` can answer for a settlement within
    one poll of it, and never from the current reading (Phase 1.8)."""
    calls: list[int] = []

    class _Growing(_Venue):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if "fundingRate" in request.url.path:
                calls.append(int(request.url.params.get("limit", "0")))
                rows = list(self.history)
                if len(calls) > 1:  # the venue has settled once more since the first load
                    rows.append({"symbol": "BTCUSDT", "fundingTime": _ms(NOW.replace(hour=16)), "fundingRate": "0.00050000", "markPrice": "61000"})
                return httpx.Response(200, content=json.dumps(rows))
            return super().__call__(request)

    venue = _Growing([{"symbol": "BTCUSDT", "fundingTime": _ms(SETTLED_AT), "fundingRate": "0.00030000", "markPrice": "60000"}])
    clock = SimulatedClock(start=NOW)  # 12:00, period 1
    monitor = FundingMonitor(clock=clock, client=httpx.AsyncClient(transport=httpx.MockTransport(venue)))
    await monitor.poll()
    await monitor.poll()
    assert calls == [1000], "one full load, no refresh within the period"
    assert monitor.rate_at(NOW.replace(hour=16)) is None, "not settled yet as far as the record knows"
    clock.advance_by(timedelta(hours=4, minutes=5))  # 16:05, period 2: a settlement happened at 16:00
    await monitor.poll()
    assert calls == [1000, 3], "a short refresh, once, on entering the new period"
    assert monitor.rate_at(NOW.replace(hour=16)) == pytest.approx(0.0005)
    assert monitor.rate_at(SETTLED_AT) == pytest.approx(0.0003), "older settlements kept, none duplicated"
    assert monitor.status()["history_settlements"] == 2 and monitor.status()["history_refreshes"] == 1
    await monitor.poll()
    assert calls == [1000, 3], "and not again within the same period"
