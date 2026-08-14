"""Capital accounting — separating what the strategy earned from what the user deposited.

The error this module exists to prevent has a direction. People deposit after losses far
more often than they withdraw after gains, so a system that counts a balance increase as
profit does not produce a *noisy* performance figure — it produces a systematically
flattering one, and it flatters most exactly when the strategy is doing worst.

The other half is the ceiling. ``max_live_capital`` is the slice of a venue account the
system may touch; everything above it must be unreachable by construction rather than by
intention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.core.clock import FrozenClock, SimulatedClock
from tia.portfolio.capital import (
    CapitalEventKind,
    CapitalLedger,
    CapitalPolicy,
)

START = datetime(2026, 8, 13, tzinfo=UTC)


def ledger(*, allocated: float = 1_000.0, ceiling: float = 1_000.0) -> CapitalLedger:
    return CapitalLedger(
        CapitalPolicy(max_live_capital=ceiling),
        allocated=allocated,
        clock=FrozenClock(START),
    )


# --------------------------------------------------------------------------- the ceiling


def test_allocating_above_the_ceiling_is_refused_rather_than_truncated() -> None:
    """Silently allocating less than asked is how someone ends up believing the system is
    trading half of what it is — or twice."""
    book = ledger(allocated=600.0, ceiling=1_000.0)

    with pytest.raises(ValueError, match="max_live_capital ceiling"):
        book.allocate(500.0, at=None)

    assert book.snapshot().allocated_capital == 600.0
    book.allocate(400.0, at=None)
    assert book.snapshot().allocated_capital == 1_000.0


def test_the_capital_policy_cannot_be_raised_at_runtime() -> None:
    """§17: nothing in the running system — including a model output or a UI control —
    may raise the ceiling. A ceiling that can be raised at runtime is not a ceiling."""
    policy = CapitalPolicy(max_live_capital=500.0)

    with pytest.raises(AttributeError, match="immutable"):
        policy.max_live_capital = 50_000.0  # type: ignore[misc]


def test_deallocating_does_not_move_money_at_the_venue() -> None:
    """The system has no withdrawal permission and never will. Reducing an allocation
    reduces what the strategy may use; the funds do not go anywhere."""
    book = ledger(allocated=1_000.0)
    book.withdraw_allocation(400.0, at=None)

    snapshot = book.snapshot()
    assert snapshot.allocated_capital == 600.0
    assert snapshot.withdrawals == 400.0
    assert [event.kind for event in book.events][-1] is CapitalEventKind.WITHDRAWAL

    with pytest.raises(ValueError, match="only"):
        book.withdraw_allocation(10_000.0, at=None)


# --------------------------------------------------------------------------- return


def test_a_deposit_never_becomes_profit() -> None:
    """The test this module exists for.

    Equity rises by the deposit, realised P&L does not move, and the reported return
    *falls* — because the denominator grew and the numerator did not. A system that
    counted the deposit would have reported a gain.
    """
    book = ledger(allocated=500.0, ceiling=1_000.0)
    book.record_realised_pnl(50.0)
    before = book.snapshot()
    assert before.net_return_pct == pytest.approx(10.0)

    reconciliation = book.classify_external_change(
        venue_balance=650.0, expected_balance=550.0
    )
    after = book.snapshot()

    assert reconciliation.kind is CapitalEventKind.DEPOSIT
    assert after.equity == pytest.approx(650.0)
    assert after.realised_pnl == pytest.approx(50.0)  # unchanged
    assert after.net_return_pct == pytest.approx(8.333, abs=0.01)
    assert after.net_return_pct < before.net_return_pct


def test_a_withdrawal_never_becomes_a_loss() -> None:
    book = ledger(allocated=1_000.0)
    book.record_realised_pnl(100.0)

    reconciliation = book.classify_external_change(
        venue_balance=1_050.0, expected_balance=1_100.0
    )

    assert reconciliation.kind is CapitalEventKind.WITHDRAWAL
    assert book.snapshot().realised_pnl == pytest.approx(100.0)
    assert book.snapshot().withdrawals == pytest.approx(50.0)


def test_return_is_measured_against_contributed_capital_not_starting_balance() -> None:
    book = ledger(allocated=1_000.0)
    book.record_realised_pnl(200.0)
    snapshot = book.snapshot()

    assert snapshot.net_contributed == pytest.approx(1_000.0)
    assert snapshot.net_return_pct == pytest.approx(20.0)


def test_return_is_zero_rather_than_infinite_when_nothing_was_contributed() -> None:
    book = CapitalLedger(CapitalPolicy(max_live_capital=1_000.0), clock=FrozenClock(START))
    assert book.snapshot().net_return_pct == 0.0


def test_unrealised_pnl_is_included_in_equity_but_kept_separately_labelled() -> None:
    book = ledger(allocated=1_000.0)
    snapshot = book.snapshot(unrealised_pnl=75.0, used_capital=400.0)

    assert snapshot.equity == pytest.approx(1_075.0)
    assert snapshot.unrealised_pnl == 75.0
    assert snapshot.realised_pnl == 0.0
    assert snapshot.available_capital == pytest.approx(675.0)
    assert snapshot.utilisation_pct == pytest.approx(40.0)
    assert snapshot.headroom == pytest.approx(600.0)


# --------------------------------------------------------------------------- the halt


def test_a_large_unexplained_movement_halts_trading() -> None:
    """A system that does not know how much money it has cannot size a position.

    Anything above 10% of the ceiling with no corresponding fill is not absorbed into the
    return — it stops the system and waits for a person.
    """
    book = ledger(allocated=1_000.0, ceiling=1_000.0)
    reconciliation = book.classify_external_change(
        venue_balance=400.0, expected_balance=1_000.0
    )

    assert reconciliation.kind is CapitalEventKind.UNEXPLAINED
    assert reconciliation.halts_trading is True
    assert book.is_halted
    assert "no corresponding fill" in book.halted_reason


def test_a_large_unexplained_increase_halts_too() -> None:
    """Direction does not matter. An unexplained *gain* is equally a sign that the system's
    picture of the account is wrong, and it is the more tempting one to wave through."""
    book = ledger(allocated=500.0, ceiling=1_000.0)
    reconciliation = book.classify_external_change(
        venue_balance=900.0, expected_balance=500.0
    )

    assert reconciliation.kind is CapitalEventKind.UNEXPLAINED
    assert book.is_halted


def test_clearing_a_halt_requires_a_named_approver() -> None:
    book = ledger()
    book.classify_external_change(venue_balance=100.0, expected_balance=1_000.0)

    for anonymous in ("", "   ", "\t"):
        with pytest.raises(ValueError, match="named approver"):
            book.clear_halt(approved_by=anonymous)

    book.clear_halt(approved_by="elian")
    assert not book.is_halted


def test_balances_that_agree_within_tolerance_produce_no_event() -> None:
    """Venue rounding is not a capital movement, and recording it as one would fill the
    ledger with noise that hides the movement that matters."""
    book = ledger(allocated=1_000.0)
    before = len(book.events)

    reconciliation = book.classify_external_change(
        venue_balance=1_000.00001, expected_balance=1_000.0
    )

    assert reconciliation.difference != 0.0
    assert not reconciliation.halts_trading
    assert len(book.events) == before


# --------------------------------------------------------------------------- loss stop


def test_the_total_loss_stop_fires_at_the_configured_percentage() -> None:
    book = ledger(allocated=1_000.0)
    assert book.policy.max_total_loss_pct == 20.0

    book.record_realised_pnl(-150.0)
    assert not book.loss_breached()

    book.record_realised_pnl(-60.0)
    assert book.loss_breached()


def test_the_loss_stop_counts_open_positions_too() -> None:
    """A 19% realised loss with a 5% open loss is a 24% loss. Waiting for it to be
    realised before reacting is how a stop becomes advisory."""
    book = ledger(allocated=1_000.0)
    book.record_realised_pnl(-150.0)

    assert not book.loss_breached()
    assert book.loss_breached(unrealised_pnl=-60.0)


# --------------------------------------------------------------------------- bookkeeping


def test_fees_are_recorded_as_costs_and_must_be_positive() -> None:
    book = ledger()
    book.record_fee(12.5)

    assert book.snapshot().fees_paid == pytest.approx(12.5)
    assert book.events[-1].amount == pytest.approx(-12.5)
    with pytest.raises(ValueError, match="positive cost"):
        book.record_fee(-1.0)


def test_events_are_stamped_from_the_injected_clock_not_the_wall_clock() -> None:
    """So a replayed session produces the same ledger, with the same timestamps."""
    clock = SimulatedClock(START)
    book = CapitalLedger(
        CapitalPolicy(max_live_capital=1_000.0), allocated=100.0, clock=clock
    )
    clock.advance_by(timedelta(hours=3))
    book.record_realised_pnl(5.0)

    assert book.events[0].at == START
    assert book.events[-1].at == START + timedelta(hours=3)


def test_the_snapshot_serialises_every_term_the_capital_panel_shows() -> None:
    payload = ledger(allocated=800.0, ceiling=1_000.0).snapshot(
        unrealised_pnl=10.0, used_capital=200.0
    ).as_dict()

    assert set(payload) >= {
        "allocated_capital", "deposits", "withdrawals", "net_contributed",
        "realised_pnl", "unrealised_pnl", "fees_paid", "equity",
        "available_capital", "used_capital", "max_live_capital",
        "headroom", "utilisation_pct", "net_return_pct",
    }
