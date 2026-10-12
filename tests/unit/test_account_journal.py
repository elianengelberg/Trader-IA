"""The paper account's journal, replayed: the same numbers the engine would hold."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tia.domain.enums import Side
from tia.domain.orders import Fill
from tia.domain.portfolio import PortfolioState
from tia.portfolio.account_journal import (
    EVENT_ADJUSTMENT,
    EVENT_BASELINE,
    EVENT_FILL,
    EVENT_MARK,
    EVENT_PLAN,
    AccountEventRecord,
    AccountRestore,
    check_baseline,
    cross_check,
    fold_account_events,
)

T0 = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
SYMBOL = "BTC-USD"


def fill_event(fid: str, side: str, qty: float, price: float, fee: float, at: datetime, seq: int = 0) -> AccountEventRecord:
    return AccountEventRecord(
        event_type=EVENT_FILL, occurred_at=at, sequence=seq, event_id=f"evt_{fid}",
        payload={"symbol": SYMBOL, "fill_id": fid, "order_id": f"o_{fid}", "side": side,
                 "quantity": qty, "price": price, "fee": fee, "filled_at": at.isoformat()},
    )


def mark_event(price: float, at: datetime, seq: int = 0) -> AccountEventRecord:
    return AccountEventRecord(
        event_type=EVENT_MARK, occurred_at=at, sequence=seq, event_id=f"evt_mark_{at.isoformat()}",
        payload={"symbol": SYMBOL, "price": price, "at": at.isoformat()},
    )


def adj_event(amount: float, at: datetime, key: str) -> AccountEventRecord:
    return AccountEventRecord(
        event_type=EVENT_ADJUSTMENT, occurred_at=at, sequence=0, event_id=f"evt_adj_{key}",
        payload={"symbol": SYMBOL, "amount": amount, "reason": key, "at": at.isoformat()},
    )


def plan_event(at: datetime, **plan: object) -> AccountEventRecord:
    return AccountEventRecord(
        event_type=EVENT_PLAN, occurred_at=at, sequence=0, event_id=f"evt_plan_{at.isoformat()}",
        payload={"symbol": SYMBOL, "at": at.isoformat(), **plan},
    )


def test_an_empty_journal_is_the_base_account_at_now() -> None:
    restore = fold_account_events([], initial_capital=10_000.0, symbol=SYMBOL, now=T0)
    assert restore.complete and restore.cash == 10_000.0 and restore.equity == 10_000.0
    assert restore.peak_equity == 10_000.0 and restore.day_start_equity == 10_000.0
    assert restore.current_day == "2026-10-09" and not restore.has_position


def test_fills_replay_through_the_engines_own_portfolio_model() -> None:
    """Buy 0.1 at 50,000 (fee 2.5), sell 0.1 at 49,000 (fee 2.45): the same numbers
    PortfolioState.apply_fill produces, so the rebuild is the engine's arithmetic."""
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        fill_event("f2", "sell", 0.1, 49_000.0, 2.45, T0 + timedelta(minutes=5)),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=6))
    reference = PortfolioState.initial(10_000.0)
    reference.apply_fill(Fill(fill_id="f1", order_id="o", sequence=0, symbol=SYMBOL, side=Side.BUY, quantity=0.1, price=50_000.0, fee=2.5, filled_at=T0))
    reference.apply_fill(Fill(fill_id="f2", order_id="o", sequence=0, symbol=SYMBOL, side=Side.SELL, quantity=0.1, price=49_000.0, fee=2.45, filled_at=T0 + timedelta(minutes=5)))
    assert restore.cash == pytest.approx(reference.cash)
    assert restore.realized_pnl == pytest.approx(reference.realized_pnl) == pytest.approx(-100.0 - 4.95)
    assert restore.fees_paid == pytest.approx(4.95)
    assert not restore.has_position and restore.open_leg_fees == 0.0
    assert restore.fills_seen == 2


def test_an_open_leg_is_restored_with_its_average_price_its_fees_and_its_plan() -> None:
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        fill_event("f2", "buy", 0.1, 51_000.0, 2.55, T0 + timedelta(minutes=1)),
        plan_event(T0 + timedelta(minutes=2), stop=49_000.0, initial_stop=49_000.0, target=55_000.0,
                   kind="protective", direction="long",
                   beliefs={"regime": "trending_up", "direction": "long", "confidence": 0.8, "signal_id": "sig"}),
        mark_event(52_000.0, T0 + timedelta(minutes=3)),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=4))
    assert restore.has_position and restore.position_quantity == pytest.approx(0.2)
    assert restore.position_average_price == pytest.approx(50_500.0)
    assert restore.open_leg_fees == pytest.approx(5.05)
    assert restore.plan["stop"] == 49_000.0 and restore.plan["target"] == 55_000.0
    assert restore.beliefs["signal_id"] == "sig"
    assert restore.last_price == 52_000.0
    assert restore.equity == pytest.approx(10_000.0 - 5.05 + 0.2 * (52_000.0 - 50_500.0))
    state = restore.portfolio_state()
    assert state.positions[SYMBOL].quantity == pytest.approx(0.2)
    assert state.equity == pytest.approx(restore.equity)


def test_the_equity_peak_and_the_utc_day_opening_equity_survive_a_replay() -> None:
    """A day that peaked and then lost 2.5 %: the rebuild still knows the peak and the
    day's opening equity, which is what the breakers read."""
    events = [
        fill_event("f1", "buy", 0.2, 50_000.0, 2.5, T0),
        mark_event(55_000.0, T0 + timedelta(minutes=1)),   # peak: +1,000 on 0.2
        mark_event(48_700.0, T0 + timedelta(minutes=2)),   # -260 on 0.2
        fill_event("f2", "sell", 0.2, 48_700.0, 2.4, T0 + timedelta(minutes=3)),
    ]
    now = T0 + timedelta(minutes=10)
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=now)
    assert restore.peak_equity == pytest.approx(10_000.0 - 2.5 + 1_000.0)
    assert restore.day_start_equity == pytest.approx(10_000.0), "the day opened at base capital"
    assert restore.equity == pytest.approx(10_000.0 - 260.0 - 4.9)
    state = restore.portfolio_state()
    assert state.day_pnl_pct == pytest.approx((restore.equity - 10_000.0) / 10_000.0 * 100.0)
    assert state.drawdown_pct == pytest.approx((restore.peak_equity - restore.equity) / restore.peak_equity * 100.0)


def test_a_restart_on_the_next_utc_day_opens_that_day_at_the_carried_equity_and_keeps_the_peak() -> None:
    events = [
        fill_event("f1", "buy", 0.2, 50_000.0, 2.5, T0),
        mark_event(55_000.0, T0 + timedelta(minutes=1)),
        fill_event("f2", "sell", 0.2, 48_700.0, 2.4, T0 + timedelta(minutes=3)),
    ]
    tomorrow = datetime(2026, 10, 10, 0, 0, 30, tzinfo=UTC)
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=tomorrow)
    assert restore.current_day == "2026-10-10"
    assert restore.day_start_equity == pytest.approx(restore.equity), "a new day opens at the carried equity"
    assert restore.peak_equity == pytest.approx(10_000.0 - 2.5 + 1_000.0), "the peak is history, not a day"


def test_adjustments_move_cash_and_the_peak_and_day_tracking_see_them() -> None:
    events = [adj_event(-12.5, T0, "funding"), adj_event(-3.0, T0 + timedelta(hours=1), "liquidation fee")]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(hours=2))
    assert restore.cash == pytest.approx(10_000.0 - 15.5) and restore.equity == pytest.approx(10_000.0 - 15.5)
    assert restore.peak_equity == pytest.approx(10_000.0)


def test_replaying_the_journal_twice_or_with_duplicates_is_the_same_account() -> None:
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        mark_event(50_500.0, T0 + timedelta(minutes=1)),
        fill_event("f2", "sell", 0.1, 50_500.0, 2.52, T0 + timedelta(minutes=2)),
    ]
    once = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=3))
    twice = fold_account_events(events + events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=3))
    shuffled = fold_account_events(list(reversed(events)), initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=3))
    assert once.as_dict() == twice.as_dict() == shuffled.as_dict()
    assert once.fills_seen == 2 and once.fees_paid == pytest.approx(5.02)


def test_a_partial_exit_leaves_the_remainder_open_and_its_fees_split_correctly() -> None:
    events = [
        fill_event("f1", "buy", 0.2, 50_000.0, 5.0, T0),
        fill_event("f2", "sell", 0.05, 50_000.0, 1.25, T0 + timedelta(minutes=1)),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    assert restore.position_quantity == pytest.approx(0.15)
    assert restore.open_leg_fees == pytest.approx(6.25), "fees of every fill of the leg so far"
    assert restore.realized_pnl == pytest.approx(-6.25)


def test_the_cross_check_against_the_fills_table_turns_a_lost_write_into_an_incomplete_rebuild() -> None:
    events = [fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0)]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=1))
    agree = cross_check(restore, fill_rows_net_quantity=0.1, fill_rows_count=1, fill_rows_fees=2.5)
    assert agree.complete is True
    missing_in_table = cross_check(restore, fill_rows_net_quantity=0.0, fill_rows_count=0, fill_rows_fees=0.0)
    assert missing_in_table.complete is False and "fills table" in missing_in_table.error
    extra_in_table = cross_check(restore, fill_rows_net_quantity=0.2, fill_rows_count=2, fill_rows_fees=5.0)
    assert extra_in_table.complete is False
    assert extra_in_table.checks["fills_in_table"] == 2


def test_failed_and_empty_restores_say_what_they_are() -> None:
    failed = AccountRestore.failed("database unavailable", initial_capital=10_000.0)
    assert not failed.complete and failed.consulted and "unavailable" in failed.error
    empty = AccountRestore.empty(initial_capital=10_000.0)
    assert empty.complete and not empty.consulted and empty.portfolio_state().cash == 10_000.0


def test_events_of_other_symbols_are_ignored() -> None:
    other = AccountEventRecord(
        event_type=EVENT_FILL, occurred_at=T0, sequence=0, event_id="evt_x",
        payload={"symbol": "ETH-USD", "fill_id": "x", "order_id": "o", "side": "buy", "quantity": 1.0, "price": 3_000.0, "fee": 1.0, "filled_at": T0.isoformat()},
    )
    restore = fold_account_events([other], initial_capital=10_000.0, symbol=SYMBOL, now=T0)
    assert restore.cash == 10_000.0 and restore.fills_seen == 0


def test_the_funding_a_leg_paid_travels_with_its_plan_and_older_plans_read_zero() -> None:
    """Two settlements while open, each followed by the plan the session journals with
    the running tally (Phase 1.6): the rebuild hands the latest tally to the adopting
    session; a plan written before the field existed reads as zero, not as missing."""
    events = [
        fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0),
        plan_event(T0 + timedelta(minutes=1), stop=49_000.0, kind="protective", direction="long",
                   beliefs={"regime": "trending_up", "direction": "long", "confidence": 0.8, "signal_id": "sig"}),
        adj_event(-0.5, T0 + timedelta(hours=8), "funding:2026-10-10:0"),
        plan_event(T0 + timedelta(hours=8, seconds=1), stop=49_000.0, kind="protective", direction="long",
                   beliefs={"signal_id": "sig"}, funding_paid=0.5),
        adj_event(-0.52, T0 + timedelta(hours=16), "funding:2026-10-10:1"),
        plan_event(T0 + timedelta(hours=16, seconds=1), stop=49_500.0, kind="protective", direction="long",
                   beliefs={"signal_id": "sig"}, funding_paid=1.02),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(hours=17))
    assert restore.has_position
    assert restore.plan["funding_paid"] == pytest.approx(1.02)
    assert restore.plan["stop"] == 49_500.0
    # The account carries both settlements as cash, once each: attribution is not a charge.
    assert restore.cash == pytest.approx(10_000.0 - 0.1 * 50_000.0 - 2.5 - 0.5 - 0.52)

    before_the_field = fold_account_events(events[:2], initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    assert before_the_field.plan["funding_paid"] == 0.0

    closed = [*events, fill_event("f2", "sell", 0.1, 51_000.0, 2.55, T0 + timedelta(hours=18))]
    flat = fold_account_events(closed, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(hours=19))
    assert not flat.has_position and flat.plan is None, "a closed leg leaves no tally behind"


# ------------------------------------------------------------ the operator's baseline


def baseline_event(at: datetime, *, symbol: str = SYMBOL, legacy_fills: int = 0, legacy_net: float = 0.0,
                   legacy_fees: float = 0.0, event_id: str | None = None) -> AccountEventRecord:
    return AccountEventRecord(
        event_type=EVENT_BASELINE, occurred_at=at, sequence=0, event_id=event_id or f"evt_base_{at.isoformat()}",
        payload={"symbol": symbol, "at": at.isoformat(), "reason": "fills predate the journal", "actor": "op",
                 "legacy_fills": legacy_fills, "legacy_runs": ["run_old"], "legacy_net_quantity": legacy_net,
                 "legacy_fees": legacy_fees},
    )


def test_a_baseline_opens_the_record_at_base_capital_on_its_own_day() -> None:
    base = baseline_event(T0, legacy_fills=5, legacy_net=-0.276436, legacy_fees=16.993117)
    restore = fold_account_events([base], initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(hours=1))
    assert restore.complete and restore.consulted
    assert restore.baseline_at == T0 and restore.baseline["legacy_fills"] == 5
    assert restore.cash == 10_000.0 and restore.position_quantity == 0.0 and restore.fills_seen == 0
    assert restore.current_day == T0.date().isoformat() and restore.last_event_at == T0
    assert restore.checks["baseline_at"] == T0.isoformat()
    assert restore.as_dict()["baseline_at"] == T0.isoformat()


def test_events_after_the_baseline_fold_exactly_as_they_would_without_one() -> None:
    fills = [fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0 + timedelta(minutes=5)),
             mark_event(50_500.0, T0 + timedelta(minutes=6))]
    plain = fold_account_events(fills, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=7))
    opened = fold_account_events([baseline_event(T0), *fills], initial_capital=10_000.0, symbol=SYMBOL,
                                 now=T0 + timedelta(minutes=7))
    for field in ("cash", "position_quantity", "position_average_price", "fees_paid", "equity", "fills_seen"):
        assert getattr(opened, field) == getattr(plain, field), field
    assert opened.complete and opened.baseline_at == T0 and plain.baseline_at is None


def test_a_baseline_that_follows_a_folded_event_is_refused_and_folds_nothing_away() -> None:
    """A baseline may open a record, never rewrite one: the fill before it stays folded and
    the rebuild is incomplete until a person looks."""
    events = [fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0), baseline_event(T0 + timedelta(minutes=1))]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    assert restore.complete is False and "never rewrite" in restore.error
    assert restore.baseline_at is None and restore.fills_seen == 1
    assert restore.position_quantity == pytest.approx(0.1), "the fill is not hidden behind the baseline"


def test_a_second_baseline_is_refused() -> None:
    events = [baseline_event(T0, event_id="b1"), baseline_event(T0 + timedelta(minutes=1), event_id="b2")]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    assert restore.complete is False and "second baseline" in restore.error
    assert restore.baseline_at == T0, "the first one still marks where the record opened"


def test_a_baseline_of_another_symbol_opens_nothing_here() -> None:
    restore = fold_account_events([baseline_event(T0, symbol="ETH-USD")], initial_capital=10_000.0,
                                  symbol=SYMBOL, now=T0 + timedelta(minutes=1))
    assert restore.complete and restore.baseline_at is None and restore.checks["baseline_at"] is None


def test_the_baseline_check_holds_the_legacy_set_to_what_was_pinned() -> None:
    base = baseline_event(T0, legacy_fills=5, legacy_net=-0.276436, legacy_fees=16.993117)
    restore = fold_account_events([base], initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(hours=1))
    agree = check_baseline(restore, legacy_fill_rows_count=5, legacy_fill_rows_net_quantity=-0.276436,
                           legacy_fill_rows_fees=16.993117)
    assert agree.complete is True
    assert agree.checks["legacy_fills_excluded"] == 5 and agree.checks["legacy_fills_pinned"] == 5
    assert agree.checks["legacy_net_quantity_table"] == pytest.approx(-0.276436)
    grew = check_baseline(restore, legacy_fill_rows_count=6, legacy_fill_rows_net_quantity=-0.3,
                          legacy_fill_rows_fees=20.0)
    assert grew.complete is False and "disagrees with its baseline" in grew.error
    assert "6 fills before the baseline" in grew.error and "20.000000 before the baseline" in grew.error
    # The reconciliation of the rows from the baseline on is untouched by the legacy set.
    reconciled = cross_check(agree, fill_rows_net_quantity=0.0, fill_rows_count=0, fill_rows_fees=0.0)
    assert reconciled.complete is True and reconciled.checks["fills_in_table"] == 0
    assert reconciled.checks["legacy_fills_excluded"] == 5, "the legacy figures stay in view"


def test_without_a_baseline_the_baseline_check_changes_nothing() -> None:
    restore = fold_account_events([fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0)], initial_capital=10_000.0,
                                  symbol=SYMBOL, now=T0 + timedelta(minutes=1))
    assert check_baseline(restore, legacy_fill_rows_count=0, legacy_fill_rows_net_quantity=0.0,
                          legacy_fill_rows_fees=0.0) is restore


def test_a_later_problem_keeps_the_earlier_one_in_the_error() -> None:
    """The cross-check and the baseline check append to what the fold already found, so a
    person reading the error sees every reason the account could not be trusted."""
    events = [fill_event("f1", "buy", 0.1, 50_000.0, 2.5, T0), baseline_event(T0 + timedelta(minutes=1))]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    both = cross_check(restore, fill_rows_net_quantity=0.0, fill_rows_count=0, fill_rows_fees=0.0)
    assert "never rewrite" in both.error and "fills table" in both.error


def test_marks_and_plans_written_before_the_baseline_are_skipped_not_refused() -> None:
    """A journal-aware session that ran over the unverified account (a resumed run after
    the deploy) leaves marks and plans but moves nothing: the baseline still opens the
    record, those rows are skipped and counted, and the account is base capital."""
    events = [
        mark_event(83_000.0, T0 - timedelta(minutes=10)),
        plan_event(T0 - timedelta(minutes=9), stop=None, kind=None, direction=None),
        mark_event(83_100.0, T0 - timedelta(minutes=1)),
        baseline_event(T0, legacy_fills=5, legacy_net=-0.276436, legacy_fees=16.993117),
        mark_event(83_200.0, T0 + timedelta(minutes=1)),
    ]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=2))
    assert restore.complete is True, restore.error
    assert restore.baseline_at == T0 and restore.checks["events_before_baseline"] == 3
    assert restore.cash == 10_000.0 and restore.equity == 10_000.0 and not restore.has_position
    assert restore.last_price == 83_200.0, "the mark after the baseline is folded as usual"
    assert restore.events_seen == 5


def test_an_adjustment_before_the_baseline_is_refused_like_a_fill() -> None:
    events = [adj_event(-1.5, T0 - timedelta(minutes=1), "funding:x"), baseline_event(T0)]
    restore = fold_account_events(events, initial_capital=10_000.0, symbol=SYMBOL, now=T0 + timedelta(minutes=1))
    assert restore.complete is False and "move the account" in restore.error and "never rewrite" in restore.error
    assert restore.baseline_at is None and restore.cash == pytest.approx(9_998.5), "the adjustment stays folded"
