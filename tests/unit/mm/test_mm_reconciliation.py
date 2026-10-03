"""The live ledger (real balances in, venue fees booked, the venue adopted on a
disagreement) and the reconciliation classifier (orders and balances, severities)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Order
from tia.mm.costs import MarketMakerCostConfig, MarketMakerCostModel
from tia.mm.execution import LiveFill
from tia.mm.live_ledger import LiveLedger
from tia.mm.reconciliation import MMDiscrepancy, build_report, compare_balances, compare_orders

T0 = 1_789_754_400_000
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _fill(side: str = "buy", qty: float = 0.001, price: float = 100_000.0, *, fee: float = 0.1, fee_usd: float = 0.1, status: str = "venue", asset: str = "USDT", liquidity: str = "maker") -> LiveFill:
    return LiveFill(fill_id="501", order_id="tiamm-x-1-000001", side=side, price=price, quantity=qty, t_ms=T0, venue_trade_ids=(501,), fee=fee, fee_asset=asset, fee_usd=fee_usd, fee_status=status, liquidity=liquidity)


def _ledger() -> LiveLedger:
    ledger = LiveLedger(MarketMakerCostModel(MarketMakerCostConfig(maker_fee_bps=10.0)))
    ledger.seed(quote_free=5_000.0, quote_locked=0.0, base_free=0.04, base_locked=0.01, mark_price=100_000.0, t_ms=T0)
    return ledger


# ------------------------------------------------------------------ the live ledger


def test_the_ledger_starts_from_the_account_and_the_base_held_before_is_a_baseline_not_inventory() -> None:
    ledger = _ledger()
    s = ledger.state
    assert ledger.seeded and s.starting_equity_usd == 5_000.0 and s.cash_usd == 5_000.0 and s.inventory_btc == 0.0
    assert ledger.baseline_base_btc == pytest.approx(0.05)
    assert ledger.balances() == (5_000.0, pytest.approx(0.04))  # the venue's free figures: the locked 0.01 funds nothing new
    assert ledger.equity_usd == 5_000.0 and ledger.net_pnl_usd == 0.0
    snap = ledger.snapshot()
    assert snap["mode"] == "live" and snap["account_equity_usd"] == pytest.approx(5_000.0 + 0.05 * 100_000.0) and snap["base_held_btc"] == pytest.approx(0.05)
    with pytest.raises(ValueError, match="seeded once"):
        ledger.seed(quote_free=1.0, quote_locked=0.0, base_free=0.0, base_locked=0.0, mark_price=1.0, t_ms=T0)
    with pytest.raises(ValueError, match="never restored"):
        LiveLedger.restore({"starting_equity_usd": 1.0})
    assert LiveLedger().balances() == (None, None)


def test_a_fill_is_booked_with_the_venues_fee_in_the_quote_asset() -> None:
    ledger = _ledger()
    booked = ledger.apply_fill(_fill())
    assert booked["fee_usd"] == 0.1 and booked["fee_status"] == "venue"
    s = ledger.state
    assert s.cash_usd == pytest.approx(5_000.0 - 100.0 - 0.1) and s.inventory_btc == 0.001 and s.fees_usd == 0.1
    assert ledger.fees_venue_usd == 0.1 and ledger.fills_by_liquidity == {"maker": 1, "taker": 0}
    assert ledger.expected_balances() == (pytest.approx(4_899.9), pytest.approx(0.051))


def test_a_fee_charged_in_the_base_asset_is_valued_at_the_fill_and_reduces_the_base_held() -> None:
    ledger = _ledger()
    ledger.apply_fill(_fill(fee=0.000001, fee_usd=0.1, status="converted_from_base", asset="BTC"))
    assert ledger.fees_converted_usd == 0.1 and ledger.base_fees_btc == 0.000001
    quote, base = ledger.expected_balances()
    assert quote == pytest.approx(4_899.9 + 0.1) and base == pytest.approx(0.051 - 0.000001)  # the venue kept the quote, took base
    assert ledger.balances()[1] == pytest.approx(0.04)  # still the venue's last word, until it reports again
    ledger.note_venue_balances(quote_free=4_900.0, quote_locked=0.0, base_free=0.050999, base_locked=0.0, t_ms=T0 + 1)
    assert ledger.balances() == (4_900.0, 0.050999) and ledger.venue_balances_at_ms == T0 + 1


def test_a_fee_in_a_third_asset_is_not_booked_as_quote_currency_but_at_the_assumed_rate_and_counted() -> None:
    ledger = _ledger()
    booked = ledger.apply_fill(_fill(fee=0.00002, fee_usd=0.0, status="unconverted:BNB", asset="BNB"))
    assert booked["fee_usd"] == pytest.approx(100.0 * 10.0 / 10_000.0) and booked["fee_status"] == "unconverted:BNB"
    assert ledger.fills_unconverted == 1 and ledger.fees_assumed_usd == pytest.approx(0.1)
    assert ledger.expected_balances()[0] == pytest.approx(ledger.state.cash_usd + 0.1)
    assert ledger.snapshot()["fills_unconverted_fee"] == 1


def test_reconciliation_within_tolerance_adopts_nothing_and_beyond_it_the_venue_wins() -> None:
    ledger = _ledger()
    ledger.apply_fill(_fill())
    clean = ledger.reconcile_balances(quote_free=4_899.9, quote_locked=0.0, base_free=0.041, base_locked=0.01, t_ms=T0 + 1, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002)
    assert clean["ok"] and not clean["adopted"] and ledger.discrepancies == 0 and ledger.reconciliations == 1
    # The venue says we hold 0.002 more base and 120 USD less than the fills explain.
    off = ledger.reconcile_balances(quote_free=4_679.9, quote_locked=100.0, base_free=0.043, base_locked=0.01, t_ms=T0 + 2, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002)  # totals are what count
    assert not off["ok"] and off["adopted"] and off["quote_delta_usd"] == pytest.approx(-120.0) and off["base_delta_btc"] == pytest.approx(0.002)
    assert ledger.discrepancies == 1 and ledger.state.cash_usd == pytest.approx(4_779.9) and ledger.state.inventory_btc == pytest.approx(0.003)
    assert ledger.last_reconciliation is off and ledger.adjustments[-1]["note"].startswith("venue wins")
    snap = ledger.snapshot()
    assert snap["venue_quote_free"] == 4_679.9 and snap["venue_quote_locked"] == 100.0 and snap["available_for_bid_usd"] == 4_679.9
    assert ledger.export()["discrepancies"] == 1


def test_an_adjustment_that_flips_or_opens_inventory_costs_it_at_the_mark() -> None:
    ledger = _ledger()
    ledger.mark(T0 + 1, bid=99_999.0, ask=100_001.0)
    ledger.reconcile_balances(quote_free=5_000.0, quote_locked=0.0, base_free=0.052, base_locked=0.0, t_ms=T0 + 2, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002)
    assert ledger.state.inventory_btc == pytest.approx(0.002) and ledger.state.average_cost == 100_000.0
    ledger.reconcile_balances(quote_free=5_000.0, quote_locked=0.0, base_free=0.05, base_locked=0.0, t_ms=T0 + 3, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002)
    assert ledger.state.inventory_btc == 0.0 and ledger.state.average_cost == 0.0


# ------------------------------------------------------------------ the classifier


def _venue(cid: str, *, order_id: str = "77", filled: float = 0.0) -> Order:
    return Order(order_id=order_id, client_order_id=cid, intent_id="", signal_id="", symbol="BTC-USD", side=Side.BUY, order_type=OrderType.LIMIT_MAKER, quantity=0.001, limit_price=99_000.0, state=OrderState.ACKNOWLEDGED, filled_quantity=filled, created_at=NOW, updated_at=NOW)


def _local(cid: str, *, state: str = "resting", filled: float = 0.0, unknown_reason: str = "", t_ack_ms: int | None = T0 - 5_000) -> SimpleNamespace:
    return SimpleNamespace(order_id=cid, state=state, filled=filled, venue_executed_qty=0.0, unknown_reason=unknown_reason, t_ack_ms=t_ack_ms)


def test_orders_are_classified_by_who_placed_them_and_who_still_knows_them() -> None:
    issues = compare_orders(
        local_open=[_local("tiamm-run-1-000001"), _local("tiamm-run-1-000002"), _local("tiamm-run-1-000003", state="pending_arrival")],
        local_unknown=[_local("tiamm-run-1-000009", state="unknown", unknown_reason="timeout")],
        venue_open=[_venue("tiamm-run-1-000001", filled=0.0004), _venue("someone-else"), _venue("tiamm-old-1-000001")],
    )
    kinds = {(i["kind"], i["severity"]) for i in issues}
    assert (MMDiscrepancy.EXECUTED_QUANTITY_AHEAD.value, "warning") in kinds
    assert (MMDiscrepancy.FOREIGN_OPEN_ORDER.value, "critical") in kinds
    assert (MMDiscrepancy.VENUE_ORDER_UNKNOWN_LOCALLY.value, "critical") in kinds
    assert (MMDiscrepancy.LOCAL_ORDER_MISSING_AT_VENUE.value, "warning") in kinds
    assert (MMDiscrepancy.UNKNOWN_ORDER_STATE.value, "critical") in kinds
    assert sum(1 for i in issues if i["kind"] == MMDiscrepancy.LOCAL_ORDER_MISSING_AT_VENUE.value) == 1  # pending_arrival is not expected at the venue yet
    lenient = compare_orders(local_open=[], local_unknown=[], venue_open=[_venue("someone-else")], foreign_is_critical=False)
    assert lenient[0]["severity"] == "warning"
    assert compare_orders(local_open=[_local("tiamm-run-1-000001")], local_unknown=[], venue_open=[_venue("tiamm-run-1-000001")]) == []


def test_the_snapshots_age_is_told_apart_from_a_real_discrepancy() -> None:
    """The venue's open orders are a picture taken at one instant; the local lists are read
    later, and the maker kept quoting in between. An order the picture lists open that the
    run has since closed is the picture's age, not an order nobody manages; an order
    acknowledged after the picture cannot be expected in it. Both were classified as
    findings before, and the first one as critical — the false positive that engaged the
    sticky kill switch on Testnet (2026-10-04)."""
    closed_since = _local("tiamm-run-1-000007", state="cancelled")
    issues = compare_orders(
        local_open=[_local("tiamm-run-1-000008", state="resting", t_ack_ms=T0 + 10)],  # acked after the snapshot
        local_unknown=[],
        venue_open=[_venue("tiamm-run-1-000007")],  # open in the snapshot, closed here since
        local_closed=[closed_since],
        snapshot_t_ms=T0,
    )
    assert [(i["kind"], i["severity"]) for i in issues] == [(MMDiscrepancy.LOCAL_CLOSED_VENUE_OPEN.value, "warning")]
    assert issues[0]["order_id"] == "tiamm-run-1-000007" and issues[0]["local_state"] == "cancelled"
    # Without the closed list the same picture is an order this run does not know: critical.
    strict = compare_orders(local_open=[], local_unknown=[], venue_open=[_venue("tiamm-run-1-000007")])
    assert [(i["kind"], i["severity"]) for i in strict] == [(MMDiscrepancy.VENUE_ORDER_UNKNOWN_LOCALLY.value, "critical")]
    # A resting order acknowledged before the snapshot and absent from it is still asked about.
    older = compare_orders(local_open=[_local("tiamm-run-1-000008", t_ack_ms=T0 - 10)], local_unknown=[], venue_open=[], snapshot_t_ms=T0)
    assert [i["kind"] for i in older] == [MMDiscrepancy.LOCAL_ORDER_MISSING_AT_VENUE.value]


def test_balances_within_tolerance_are_clean_and_beyond_it_critical() -> None:
    assert compare_balances(expected_quote_usd=100.0, expected_base_btc=0.01, venue_quote_usd=100.3, venue_base_btc=0.010001, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002) is None
    issue = compare_balances(expected_quote_usd=100.0, expected_base_btc=0.01, venue_quote_usd=99.0, venue_base_btc=0.01, quote_tolerance_usd=0.5, base_tolerance_btc=0.00002)
    assert issue is not None and issue["kind"] == MMDiscrepancy.BALANCE_MISMATCH.value and issue["severity"] == "critical" and issue["quote_delta_usd"] == -1.0


def test_the_report_summarises_and_decides_criticality() -> None:
    clean = build_report(t_ms=T0, order_issues=[], balance_issue=None, venue_open=1, local_open=1, balances={}, trades_seen=3)
    assert clean.ok and not clean.critical and clean.summary == "clean" and clean.as_dict()["note"] == ""
    warn = build_report(t_ms=T0, order_issues=[{"kind": "local_order_missing_at_venue", "severity": "warning"}], balance_issue=None, venue_open=0, local_open=1, balances={}, trades_seen=0)
    assert not warn.ok and not warn.critical and warn.summary == "local_order_missing_at_venue x1"
    bad = build_report(t_ms=T0, order_issues=[{"kind": "foreign_open_order", "severity": "critical"}, {"kind": "foreign_open_order", "severity": "critical"}], balance_issue={"kind": "balance_mismatch", "severity": "critical"}, venue_open=2, local_open=0, balances={}, trades_seen=0, initial=True)
    assert bad.critical and bad.summary == "balance_mismatch x1, foreign_open_order x2" and bad.initial and "venue is the fact" in bad.note
