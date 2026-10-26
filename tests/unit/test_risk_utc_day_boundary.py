"""N-HORA — the risk engine's day is the UTC day, whatever zone a moment is written in and
whatever zone the host runs in.

The per-symbol and per-day caps are restored for a UTC day (``RiskRestore.day``) and roll at UTC
midnight (``RiskState.roll_day``). These pin both sides of the boundary, to the microsecond, with
the moments written in UTC and in the zone this project is operated from
(America/Argentina/Buenos_Aires, UTC-3: 21:00 there is 00:00 UTC). They run the same under any
``TZ`` of the host (the CI runs them under ``TZ=UTC`` and ``TZ=America/Argentina/Buenos_Aires``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.risk.engine import RiskEngine
from tia.risk.restore import RiskRestore, utc_day_start

BUENOS_AIRES = ZoneInfo("America/Argentina/Buenos_Aires")
DAY = datetime(2026, 10, 21, tzinfo=UTC)
LAST_MICROSECOND = DAY + timedelta(days=1) - timedelta(microseconds=1)
MIDNIGHT = DAY + timedelta(days=1)


def _engine_with_five_for(day: datetime) -> RiskEngine:
    engine = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, SimulatedClock(day + timedelta(hours=12)))
    engine.restore(RiskRestore(complete=True, day=day.date().isoformat(), entries_today=5,
                               entries_today_by_symbol={"BTC-USD": 5}, last_entry_at={}, entry_orders_today=5))
    return engine


@pytest.mark.parametrize("zone", [UTC, BUENOS_AIRES], ids=["utc", "buenos_aires"])
def test_the_restored_count_holds_until_the_last_microsecond_of_its_utc_day(zone: object) -> None:
    engine = _engine_with_five_for(DAY)
    engine.record_execution("BTC-USD", LAST_MICROSECOND.astimezone(zone))  # type: ignore[arg-type]
    assert engine.state.current_day == "2026-10-21"
    assert engine.state.trades_today_by_symbol == {"BTC-USD": 6}


@pytest.mark.parametrize("zone", [UTC, BUENOS_AIRES], ids=["utc", "buenos_aires"])
def test_the_count_rolls_at_utc_midnight_even_when_it_is_21_00_where_the_operator_is(zone: object) -> None:
    moment = MIDNIGHT.astimezone(zone)  # type: ignore[arg-type]
    if zone is BUENOS_AIRES:
        assert (moment.hour, moment.date().isoformat()) == (21, "2026-10-21"), "still the 21st locally"
    engine = _engine_with_five_for(DAY)
    engine.record_execution("BTC-USD", moment)
    assert engine.state.current_day == "2026-10-22"
    assert engine.state.trades_today_by_symbol == {"BTC-USD": 1}


def test_the_restore_day_is_computed_on_the_utc_day_too() -> None:
    late_local = datetime(2026, 10, 21, 22, 30, tzinfo=BUENOS_AIRES)  # 01:30 UTC on the 22nd
    assert utc_day_start(late_local) == datetime(2026, 10, 22, tzinfo=UTC)
    early_local = datetime(2026, 10, 21, 20, 59, 59, 999999, tzinfo=BUENOS_AIRES)  # 23:59:59.999999 UTC
    assert utc_day_start(early_local) == DAY


def test_a_naive_moment_is_refused_rather_than_read_in_the_hosts_zone() -> None:
    engine = _engine_with_five_for(DAY)
    with pytest.raises(Exception, match="timezone-aware"):
        engine.record_execution("BTC-USD", datetime(2026, 10, 21, 23, 0))
