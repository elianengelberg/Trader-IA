"""The funding monitor's reading policy (Phase 1.5): a rate is a finite number the monitor
read recently; anything else is *not a rate* and says why.

Every case is driven through a mock transport and a simulated clock: valid, zero, absent,
stale, NaN, infinite, and consecutive polling failures.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tia.core.clock import SimulatedClock
from tia.data.funding import FundingMonitor

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)


def _premium(rate: str) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT", "markPrice": "60030.00", "indexPrice": "60000.00",
        "estimatedSettlePrice": "60010", "lastFundingRate": rate,
        "interestRate": "0.00010000", "nextFundingTime": NOW_MS + 3_600_000, "time": NOW_MS,
    }


class _Venue:
    """A scripted venue: each premium-index call takes the next scripted response."""

    def __init__(self, *responses: httpx.Response | str) -> None:
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "fundingRate" in request.url.path:
            return httpx.Response(200, json=[])  # history: empty is fine
        self.calls += 1
        step = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(step, httpx.Response):
            return step
        return httpx.Response(200, content=json.dumps(_premium(step)))


def _monitor(venue: _Venue, *, max_age_seconds: float = 3600.0) -> tuple[FundingMonitor, SimulatedClock]:
    clock = SimulatedClock(start=NOW)
    monitor = FundingMonitor(
        clock=clock,
        client=httpx.AsyncClient(transport=httpx.MockTransport(venue)),
        max_age_seconds=max_age_seconds,
    )
    return monitor, clock


async def test_a_valid_reading_is_the_rate_and_says_ok() -> None:
    monitor, _clock = _monitor(_Venue("0.00030000"))
    assert monitor.status()["state"] == "absent" and monitor.latest_rate() is None
    await monitor.poll()
    status = monitor.status()
    assert status["state"] == "ok"
    assert status["rate"] == pytest.approx(0.0003) and monitor.latest_rate() == pytest.approx(0.0003)
    assert status["age_seconds"] == 0.0 and status["consecutive_failures"] == 0
    assert monitor.report()["status"]["state"] == "ok"


async def test_a_zero_rate_is_a_rate_not_a_missing_one() -> None:
    monitor, _clock = _monitor(_Venue("0.00000000"))
    await monitor.poll()
    assert monitor.status()["state"] == "ok"
    assert monitor.latest_rate() == 0.0


async def test_a_reading_older_than_the_shelf_life_is_stale_and_not_a_rate() -> None:
    monitor, clock = _monitor(_Venue("0.00030000"), max_age_seconds=600.0)
    await monitor.poll()
    clock.advance_by(timedelta(seconds=599))
    assert monitor.status()["state"] == "ok" and monitor.latest_rate() == pytest.approx(0.0003)
    clock.advance_by(timedelta(seconds=2))
    status = monitor.status()
    assert status["state"] == "stale" and status["rate"] is None
    assert monitor.latest_rate() is None, "a stale reading is not a rate"
    assert status["age_seconds"] == pytest.approx(601.0)
    assert status["max_age_seconds"] == 600.0


async def test_the_default_shelf_life_is_one_hour() -> None:
    monitor, clock = _monitor(_Venue("0.00030000"))
    await monitor.poll()
    clock.advance_by(timedelta(seconds=3600))
    assert monitor.status()["state"] == "ok"
    clock.advance_by(timedelta(seconds=1))
    assert monitor.status()["state"] == "stale"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
async def test_a_non_finite_rate_never_becomes_the_rate(bad: str) -> None:
    monitor, _clock = _monitor(_Venue(bad))
    assert await monitor.poll() is None
    status = monitor.status()
    assert status["state"] == "absent" and monitor.latest_rate() is None
    assert status["invalid_readings"] == 1 and status["consecutive_failures"] == 1
    assert monitor.report()["health"]["ok"] is False
    assert "invalid" in monitor.report()["health"]["detail"]


async def test_an_invalid_reading_after_a_valid_one_keeps_the_valid_one_and_lets_it_age() -> None:
    monitor, clock = _monitor(_Venue("0.00030000", "NaN", "NaN"))
    await monitor.poll()
    await monitor.poll()  # NaN
    assert monitor.status()["state"] == "ok" and monitor.latest_rate() == pytest.approx(0.0003)
    assert monitor.status()["invalid_readings"] == 1
    clock.advance_by(timedelta(hours=2))
    await monitor.poll()  # NaN again: the old reading is now stale, nothing replaced it
    assert monitor.status()["state"] == "stale" and monitor.latest_rate() is None


async def test_consecutive_polling_failures_are_counted_and_a_success_resets_them() -> None:
    down = httpx.Response(503, text="maintenance")
    monitor, clock = _monitor(_Venue(down, down, down, "0.00020000"))
    for _ in range(3):
        assert await monitor.poll() is None
    status = monitor.status()
    assert status["state"] == "absent" and status["consecutive_failures"] == 3 and status["failures"] == 3
    clock.advance_by(timedelta(minutes=5))
    assert await monitor.poll() is not None
    status = monitor.status()
    assert status["state"] == "ok" and status["consecutive_failures"] == 0 and status["failures"] == 3
    assert monitor.latest_rate() == pytest.approx(0.0002)


async def test_failures_after_a_valid_reading_do_not_refresh_its_age() -> None:
    down = httpx.Response(503, text="maintenance")
    monitor, clock = _monitor(_Venue("0.00030000", down, down), max_age_seconds=600.0)
    await monitor.poll()
    clock.advance_by(timedelta(seconds=400))
    await monitor.poll()  # fails
    assert monitor.status()["state"] == "ok", "still within the shelf life"
    clock.advance_by(timedelta(seconds=400))
    await monitor.poll()  # fails again
    assert monitor.status()["state"] == "stale", "a failed poll is not a fresh reading"
    assert monitor.status()["consecutive_failures"] == 2
