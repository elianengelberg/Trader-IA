"""Journal events dated after now (Phase 1.3, G11): a clock that ran ahead must not
fold into the account as if it had not."""

from __future__ import annotations

from datetime import timedelta

from tests.unit.test_account_journal import SYMBOL, T0, fill_event, mark_event
from tia.portfolio.account_journal import FUTURE_EVENT_TOLERANCE_SECONDS, fold_account_events


def test_an_event_dated_after_now_is_not_folded_and_makes_the_rebuild_incomplete() -> None:
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        fill_event("f2", "sell", 0.1, 51_000.0, 2.55, T0 + timedelta(hours=2)),  # the future
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=5))
    assert restore.complete is False
    assert "dated after now" in restore.error and "1 journal event" in restore.error
    assert restore.checks["future_events"] == 1
    # The fold stops at the present: the leg is still open, the future sell is not booked.
    assert restore.fills_seen == 1 and restore.has_position
    assert restore.position_quantity == 0.1


def test_an_event_within_the_clock_tolerance_is_folded_as_usual() -> None:
    now = T0
    events = [fill_event("f1", "buy", 0.1, 50_000.0, 2.5, now + timedelta(seconds=FUTURE_EVENT_TOLERANCE_SECONDS - 1))]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=now)
    assert restore.complete is True and restore.fills_seen == 1
    assert restore.checks["future_events"] == 0 and restore.error == ""


def test_a_future_mark_alone_is_enough_to_withhold_trust() -> None:
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        mark_event(60_000.0, T0 + timedelta(days=1)),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=1))
    assert restore.complete is False and restore.checks["future_events"] == 1
    assert restore.last_price == 50_000.0, "the future mark did not re-price the position"
