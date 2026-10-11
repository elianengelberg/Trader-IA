"""F10 (Phase 1.3): a record that runs ahead of the clock is not one to count today from.

Rows dated after ``now`` beyond a clock's ordinary skew were written by a clock that was
ahead. Before F10 they were silently dropped and the rebuild reported itself complete;
now they make it incomplete, which the engine refuses — entries wait for a person.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.core.errors import RiskError
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.risk.engine import RiskEngine
from tia.risk.restore import (
    FUTURE_ROW_TOLERANCE_SECONDS,
    PersistedFill,
    PersistedOrder,
    rebuild_risk_state,
)

NOON = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _order(oid: str, at: datetime) -> PersistedOrder:
    return PersistedOrder(order_id=oid, symbol="BTC-USD", signal_id="sig", created_at=at)


def _fill(fid: str, oid: str, at: datetime) -> PersistedFill:
    return PersistedFill(fill_id=fid, order_id=oid, symbol="BTC-USD", filled_at=at)


def test_the_tolerance_is_one_minute_of_ordinary_skew() -> None:
    assert FUTURE_ROW_TOLERANCE_SECONDS == 60.0


def test_a_row_an_hour_ahead_makes_the_rebuild_incomplete_and_counts_nothing() -> None:
    ahead = NOON + timedelta(hours=1)
    restore = rebuild_risk_state(now=NOON, orders=[_order("e1", ahead)], fills=[_fill("f1", "e1", ahead)])
    assert restore.complete is False
    assert restore.consulted is True
    assert "after now" in restore.error and "clock was ahead" in restore.error
    assert restore.entries_today == 0 and restore.last_entry_at == {}
    assert restore.orders_seen == 1 and restore.fills_seen == 1


def test_a_future_fill_alone_is_enough() -> None:
    restore = rebuild_risk_state(
        now=NOON,
        orders=[_order("e1", NOON - timedelta(minutes=5))],
        fills=[_fill("f1", "e1", NOON + timedelta(minutes=10))],
    )
    assert restore.complete is False and "1 execution row" in restore.error


def test_a_row_within_the_skew_tolerance_keeps_the_rebuild_complete() -> None:
    """Thirty seconds ahead is two clocks on one host, not a record from the future."""
    slightly = NOON + timedelta(seconds=30)
    restore = rebuild_risk_state(now=NOON, orders=[_order("e1", slightly)], fills=[_fill("f1", "e1", slightly)])
    assert restore.complete is True
    assert restore.entries_today == 0, "not counted as today's either: it has not happened yet"


def test_past_rows_beside_a_future_one_are_not_counted_as_a_partial_truth() -> None:
    """Half a record is not a record: the whole rebuild is refused, not the future half."""
    restore = rebuild_risk_state(
        now=NOON,
        orders=[_order("e1", NOON - timedelta(hours=1)), _order("e2", NOON + timedelta(hours=2))],
        fills=[_fill("f1", "e1", NOON - timedelta(hours=1)), _fill("f2", "e2", NOON + timedelta(hours=2))],
    )
    assert restore.complete is False
    assert restore.entries_today == 0, "the valid entry is not reported either"


def test_the_engine_refuses_the_incomplete_rebuild() -> None:
    ahead = NOON + timedelta(hours=1)
    restore = rebuild_risk_state(now=NOON, orders=[_order("e1", ahead)], fills=[_fill("f1", "e1", ahead)])
    engine = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, SimulatedClock(NOON))
    with pytest.raises(RiskError, match="incomplete"):
        engine.restore(restore)
    assert engine.state.trades_today == 0
