"""Rebuilding the risk engine's frequency state from the persisted execution record.

Every rule the rebuild applies is one the running engine applies: an entry is counted once
when its first fill lands, exits never count, days are UTC, and a cooldown spans midnight.
The rebuild is a pure function, so these tests feed it rows directly; the store-backed
path is covered by the integration tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import RiskLimits
from tia.core.errors import RiskError
from tia.domain.enums import Direction, MarketRegime
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.portfolio import PortfolioState
from tia.domain.signals import SignalCandidate
from tia.risk.engine import RiskEngine
from tia.risk.restore import (
    PersistedFill,
    PersistedOrder,
    RiskRestore,
    is_entry_signal_id,
    rebuild_risk_state,
)

NOON = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)


def order(oid: str, signal_id: str, at: datetime, symbol: str = "BTC-USD") -> PersistedOrder:
    return PersistedOrder(order_id=oid, symbol=symbol, signal_id=signal_id, created_at=at)


def fill(fid: str, oid: str, at: datetime, symbol: str = "BTC-USD") -> PersistedFill:
    return PersistedFill(fill_id=fid, order_id=oid, symbol=symbol, filled_at=at)


# ----------------------------------------------------------------------- classification


def test_only_the_runtimes_exit_prefixes_are_non_entries() -> None:
    assert is_entry_signal_id("sig_01HZX")
    assert is_entry_signal_id("")
    assert is_entry_signal_id(None)
    assert not is_entry_signal_id("exit:target-reached:12")
    assert not is_entry_signal_id("protective:BTC-USD")
    assert not is_entry_signal_id("flatten:BTC-USD:live_x")


# ---------------------------------------------------------------------------- counting


def test_an_entry_counts_once_on_its_first_fill_and_exits_never_count() -> None:
    """One entry filled in two partials, its protective stop filled (the exit), a second
    entry open: two round trips opened today, one of them still open."""
    t0 = NOON
    orders = [
        order("e1", "sig_a", t0),
        order("stop1", "protective:BTC-USD", t0 + timedelta(minutes=1)),
        order("e2", "sig_b", t0 + timedelta(minutes=10)),
    ]
    fills = [
        fill("f1", "e1", t0 + timedelta(minutes=1)),
        fill("f2", "e1", t0 + timedelta(minutes=2)),  # second partial of the same entry
        fill("f3", "stop1", t0 + timedelta(minutes=5)),  # the exit
        fill("f4", "e2", t0 + timedelta(minutes=11)),
    ]
    restore = rebuild_risk_state(now=t0 + timedelta(minutes=20), orders=orders, fills=fills)
    assert restore.complete is True
    assert restore.entries_today == 2
    assert restore.entries_today_by_symbol == {"BTC-USD": 2}
    assert restore.last_entry_at == {"BTC-USD": t0 + timedelta(minutes=11)}
    assert restore.entry_orders_today == 2
    assert restore.orders_seen == 3 and restore.fills_seen == 4


def test_a_terminal_entry_without_a_fill_counts_as_sent_but_not_as_opened() -> None:
    """An expired resting entry was sent (the budget counts it) but opened nothing (the
    engine does not)."""
    orders = [order("e1", "sig_a", NOON), order("e2", "sig_b", NOON + timedelta(minutes=5))]
    fills = [fill("f1", "e1", NOON + timedelta(minutes=1))]
    restore = rebuild_risk_state(now=NOON + timedelta(minutes=10), orders=orders, fills=fills)
    assert restore.entries_today == 1
    assert restore.entry_orders_today == 2


def test_duplicate_rows_are_counted_once_and_the_rebuild_is_idempotent() -> None:
    orders = [order("e1", "sig_a", NOON)] * 3
    fills = [fill("f1", "e1", NOON + timedelta(minutes=1))] * 4
    once = rebuild_risk_state(now=NOON + timedelta(minutes=5), orders=orders, fills=fills)
    twice = rebuild_risk_state(
        now=NOON + timedelta(minutes=5), orders=orders + orders, fills=fills + fills
    )
    assert once.entries_today == twice.entries_today == 1
    assert once.entry_orders_today == twice.entry_orders_today == 1
    assert once.as_dict() == twice.as_dict()


def test_the_day_boundary_is_utc_midnight_and_the_cooldown_anchor_survives_it() -> None:
    """Entries at 23:58 and 23:59 belong to yesterday at 00:00:30; the most recent one is
    still the cooldown anchor, because a cooldown does not care what day it is."""
    orders = [
        order("e1", "sig_a", MIDNIGHT - timedelta(minutes=2)),
        order("e2", "sig_b", MIDNIGHT - timedelta(minutes=1)),
    ]
    fills = [
        fill("f1", "e1", MIDNIGHT - timedelta(minutes=2)),
        fill("f2", "e2", MIDNIGHT - timedelta(seconds=30)),
    ]
    before = rebuild_risk_state(now=MIDNIGHT - timedelta(seconds=1), orders=orders, fills=fills)
    after = rebuild_risk_state(now=MIDNIGHT + timedelta(seconds=30), orders=orders, fills=fills)
    assert before.entries_today == 2 and before.day == "2026-10-09"
    assert after.entries_today == 0 and after.day == "2026-10-10"
    assert after.entry_orders_today == 0
    assert after.last_entry_at == {"BTC-USD": MIDNIGHT - timedelta(seconds=30)}


def test_rows_from_the_future_are_ignored() -> None:
    """A clock that went backwards must not count tomorrow's rows as today's."""
    orders = [order("e1", "sig_a", NOON + timedelta(hours=1))]
    fills = [fill("f1", "e1", NOON + timedelta(hours=1))]
    restore = rebuild_risk_state(now=NOON, orders=orders, fills=fills)
    assert restore.entries_today == 0 and restore.last_entry_at == {}


def test_a_fill_for_an_unknown_order_is_ignored_not_guessed() -> None:
    restore = rebuild_risk_state(now=NOON, orders=[], fills=[fill("f1", "ghost", NOON)])
    assert restore.entries_today == 0 and restore.fills_seen == 1


def test_empty_and_failed_restores_say_what_they_are() -> None:
    empty = RiskRestore.empty(day="2026-10-09")
    failed = RiskRestore.failed("database unavailable", day="2026-10-09")
    assert empty.complete and not empty.consulted
    assert not failed.complete and failed.consulted and "unavailable" in failed.error
    assert failed.as_dict()["complete"] is False


# ------------------------------------------------------------ seeding the risk engine


def _signal(symbol: str = "BTC-USD", at: datetime = NOON) -> SignalCandidate:
    return SignalCandidate(
        signal_id=f"sig_{symbol}_{at.timestamp():.0f}",
        symbol=symbol,
        direction=Direction.LONG,
        confidence=0.8,
        base_confidence=0.8,
        created_at=at,
        expires_at=at + timedelta(minutes=5),
        market_snapshot_id="snap",
        entry_reference=60_000.0,
        stop_reference=58_000.0,
        target_reference=63_000.0,
        strategy_id="trend_following",
        strategy_version="1.0.0",
        regime=MarketRegime.TRENDING_UP,
        data_quality_score=1.0,
        data_freshness_score=1.0,
    )


def _engine(clock: SimulatedClock) -> RiskEngine:
    limits = RiskLimits(max_trades_per_symbol_per_day=5, trade_cooldown_seconds=300)
    return RiskEngine(limits, DEFAULT_UNIVERSE, clock)


def test_restoring_five_entries_for_the_symbol_makes_the_per_symbol_cap_bind_at_once() -> None:
    """The failure a restore exists to prevent: five entries before the restart, and the
    sixth must be refused by the per-symbol daily cap exactly as it would have been."""
    clock = SimulatedClock(NOON)
    engine = _engine(clock)
    engine.restore(
        RiskRestore(
            complete=True,
            day=NOON.date().isoformat(),
            entries_today=5,
            entries_today_by_symbol={"BTC-USD": 5},
            last_entry_at={"BTC-USD": NOON - timedelta(hours=1)},
        )
    )
    decision = engine.evaluate(signal=_signal(), portfolio=PortfolioState.initial(100_000.0), now=NOON)
    assert not decision.allows_execution
    assert any("per-symbol daily trade limit" in r for r in decision.reasons)


def test_a_cooldown_active_before_the_restart_is_still_active_after_it() -> None:
    clock = SimulatedClock(NOON)
    engine = _engine(clock)
    engine.restore(
        RiskRestore(
            complete=True,
            day=NOON.date().isoformat(),
            entries_today=1,
            entries_today_by_symbol={"BTC-USD": 1},
            last_entry_at={"BTC-USD": NOON - timedelta(seconds=60)},
        )
    )
    refused = engine.evaluate(signal=_signal(), portfolio=PortfolioState.initial(100_000.0), now=NOON)
    assert not refused.allows_execution
    assert any("cooldown active" in r for r in refused.reasons)
    later = NOON + timedelta(seconds=241)
    allowed = engine.evaluate(signal=_signal(at=later), portfolio=PortfolioState.initial(100_000.0), now=later)
    assert not any("cooldown" in r for r in allowed.reasons)


def test_restored_counters_roll_over_at_the_next_utc_midnight() -> None:
    clock = SimulatedClock(NOON)
    engine = _engine(clock)
    engine.restore(
        RiskRestore(
            complete=True, day=NOON.date().isoformat(), entries_today=5,
            entries_today_by_symbol={"BTC-USD": 5},
        )
    )
    tomorrow = MIDNIGHT + timedelta(minutes=1)
    decision = engine.evaluate(signal=_signal(at=tomorrow), portfolio=PortfolioState.initial(100_000.0), now=tomorrow)
    assert engine.state.trades_today == 0
    assert not any("per-symbol" in r for r in decision.reasons)


def test_an_incomplete_rebuild_is_refused_by_the_engine() -> None:
    engine = _engine(SimulatedClock(NOON))
    with pytest.raises(RiskError, match="incomplete"):
        engine.restore(RiskRestore.failed("store unreadable"))
    assert engine.state.trades_today == 0
