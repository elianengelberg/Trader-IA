"""Reconciliation.

The property under test throughout: **a divergence that could hide exposure stops
trading, and nothing repairs state automatically.** Automatic repair is how a
reconciliation bug becomes a position — a component that "corrects" the ledger to match
a snapshot it misread will invent or erase exposure with more confidence than the
divergence that triggered it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.unit.test_paper_execution import bar, intent
from tia.core.clock import SimulatedClock
from tia.core.config import ExecutionSimConfig, RiskLimits
from tia.core.rng import RngRegistry
from tia.domain.enums import OrderState, OrderType, Side, SystemMode, TimeInForce
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.orders import Fill, Order
from tia.domain.portfolio import PortfolioState
from tia.execution.paper import PaperExecutionProvider
from tia.execution.reconciliation import (
    DiscrepancyKind,
    LedgerSnapshot,
    ReconciliationEngine,
    ReconciliationReport,
    Severity,
)
from tia.risk.engine import RiskEngine

START = datetime(2026, 1, 5, tzinfo=UTC)


def snapshot(
    *,
    source: str = "internal",
    orders: dict[str, OrderState] | None = None,
    positions: dict[str, float] | None = None,
    balance: float = 100_000.0,
    fill_count: int = 0,
    at: datetime = START,
) -> LedgerSnapshot:
    return LedgerSnapshot(
        source=source,
        taken_at=at,
        orders=orders or {},
        positions=positions or {},
        balance=balance,
        fill_count=fill_count,
    )


@pytest.fixture
def engine() -> ReconciliationEngine:
    return ReconciliationEngine()


# --------------------------------------------------------------------------- clean runs


def test_identical_ledgers_reconcile_clean(engine: ReconciliationEngine) -> None:
    internal = snapshot(
        orders={"ord-1": OrderState.FILLED},
        positions={"BTC-USD": 1.5},
        balance=98_500.0,
        fill_count=1,
    )
    external = snapshot(
        source="paper",
        orders={"ord-1": OrderState.FILLED},
        positions={"BTC-USD": 1.5},
        balance=98_500.0,
        fill_count=1,
    )
    report = engine.reconcile(internal, external)

    assert report.is_clean
    assert not report.has_critical
    assert report.worst_severity is None
    assert report.orders_compared == 1
    assert report.positions_compared == 1
    assert "clean" in report.summary()


def test_floating_point_noise_is_not_a_divergence(engine: ReconciliationEngine) -> None:
    """Two ledgers that accumulated the same fills in a different order will differ in
    the last bits. Reporting that as a discrepancy would halt trading on arithmetic."""
    internal = snapshot(positions={"BTC-USD": 0.1 + 0.2}, balance=99_999.999999)
    external = snapshot(source="paper", positions={"BTC-USD": 0.3}, balance=100_000.0)
    assert engine.reconcile(internal, external).is_clean


def test_empty_ledgers_reconcile_clean(engine: ReconciliationEngine) -> None:
    assert engine.reconcile(snapshot(), snapshot(source="paper")).is_clean


# --------------------------------------------------------------------------- positions


def test_a_position_the_system_does_not_know_about_is_critical(
    engine: ReconciliationEngine,
) -> None:
    """The worst case. No stop, no size limit and no exit logic is watching it, because
    as far as every risk check is concerned it does not exist."""
    report = engine.reconcile(
        snapshot(),
        snapshot(source="paper", positions={"ETH-USD": 12.0}),
    )
    found = report.by_kind(DiscrepancyKind.PHANTOM_POSITION)
    assert len(found) == 1
    assert found[0].severity is Severity.CRITICAL
    assert found[0].subject == "ETH-USD"
    assert found[0].magnitude == pytest.approx(12.0)
    assert report.has_critical


def test_a_position_the_venue_does_not_report_is_critical(
    engine: ReconciliationEngine,
) -> None:
    report = engine.reconcile(
        snapshot(positions={"BTC-USD": 2.0}),
        snapshot(source="paper"),
    )
    found = report.by_kind(DiscrepancyKind.ORPHANED_POSITION)
    assert len(found) == 1
    assert found[0].severity is Severity.CRITICAL


def test_a_size_disagreement_beyond_tolerance_is_critical(
    engine: ReconciliationEngine,
) -> None:
    report = engine.reconcile(
        snapshot(positions={"BTC-USD": 1.0}),
        snapshot(source="paper", positions={"BTC-USD": 1.4}),
    )
    found = report.by_kind(DiscrepancyKind.POSITION_QUANTITY_MISMATCH)
    assert len(found) == 1
    assert found[0].magnitude == pytest.approx(0.4)
    assert "size disagrees" in found[0].detail


def test_a_direction_disagreement_is_called_out_separately(
    engine: ReconciliationEngine,
) -> None:
    """Long where the venue is short is categorically worse than a size difference: the
    system would hedge, size and exit in the wrong direction."""
    report = engine.reconcile(
        snapshot(positions={"BTC-USD": 1.0}),
        snapshot(source="paper", positions={"BTC-USD": -1.0}),
    )
    found = report.by_kind(DiscrepancyKind.POSITION_QUANTITY_MISMATCH)
    assert found[0].detail == "position direction disagrees"
    assert found[0].severity is Severity.CRITICAL


def test_position_tolerance_scales_with_size(engine: ReconciliationEngine) -> None:
    """A 1e-6 absolute difference is noise on 10,000 units and a real break on 0.001."""
    big = engine.reconcile(
        snapshot(positions={"BTC-USD": 10_000.0}),
        snapshot(source="paper", positions={"BTC-USD": 10_000.000001}),
    )
    assert big.is_clean

    small = engine.reconcile(
        snapshot(positions={"BTC-USD": 0.001}),
        snapshot(source="paper", positions={"BTC-USD": 0.002}),
    )
    assert small.has_critical


# --------------------------------------------------------------------------- orders


def test_a_fill_the_system_did_not_record_is_critical(
    engine: ReconciliationEngine,
) -> None:
    """Exposure exists that no risk check has seen. Every subsequent sizing decision is
    computed from a portfolio that is missing a position."""
    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.ACKNOWLEDGED}),
        snapshot(source="paper", orders={"ord-1": OrderState.FILLED}),
    )
    found = report.by_kind(DiscrepancyKind.UNRECORDED_FILL)
    assert len(found) == 1
    assert found[0].severity is Severity.CRITICAL
    assert found[0].internal == "acknowledged"
    assert found[0].external == "filled"


def test_an_order_we_think_is_done_but_the_venue_thinks_is_live_is_critical(
    engine: ReconciliationEngine,
) -> None:
    """We have stopped watching something that can still trade."""
    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.CANCELLED}),
        snapshot(source="paper", orders={"ord-1": OrderState.ACKNOWLEDGED}),
    )
    found = report.by_kind(DiscrepancyKind.ORDER_STATE_MISMATCH)
    assert found[0].severity is Severity.CRITICAL


def test_a_benign_state_lag_is_only_a_warning(engine: ReconciliationEngine) -> None:
    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.SUBMITTED}),
        snapshot(source="paper", orders={"ord-1": OrderState.ACKNOWLEDGED}),
    )
    assert not report.has_critical
    assert report.worst_severity is Severity.WARNING


def test_an_unknown_filled_order_is_critical(engine: ReconciliationEngine) -> None:
    report = engine.reconcile(
        snapshot(),
        snapshot(source="paper", orders={"ord-x": OrderState.FILLED}),
    )
    found = report.by_kind(DiscrepancyKind.UNKNOWN_ORDER)
    assert found[0].severity is Severity.CRITICAL


def test_an_unknown_cancelled_order_is_only_a_warning(
    engine: ReconciliationEngine,
) -> None:
    report = engine.reconcile(
        snapshot(),
        snapshot(source="paper", orders={"ord-x": OrderState.CANCELLED}),
    )
    assert report.by_kind(DiscrepancyKind.UNKNOWN_ORDER)[0].severity is Severity.WARNING
    assert not report.has_critical


def test_an_open_order_the_venue_has_lost_is_critical(
    engine: ReconciliationEngine,
) -> None:
    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.ACKNOWLEDGED}),
        snapshot(source="paper"),
    )
    found = report.by_kind(DiscrepancyKind.MISSING_ORDER)
    assert found[0].severity is Severity.CRITICAL


def test_a_terminal_order_the_venue_has_dropped_is_only_a_warning(
    engine: ReconciliationEngine,
) -> None:
    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.FILLED}),
        snapshot(source="paper"),
    )
    assert report.by_kind(DiscrepancyKind.MISSING_ORDER)[0].severity is Severity.WARNING


# --------------------------------------------------------------------------- balances


def test_a_balance_disagreement_is_critical(engine: ReconciliationEngine) -> None:
    """Sizing is derived from the balance, so a wrong balance sizes every subsequent
    trade wrongly — quietly, and in the same direction each time."""
    report = engine.reconcile(
        snapshot(balance=100_000.0),
        snapshot(source="paper", balance=97_500.0),
    )
    found = report.by_kind(DiscrepancyKind.BALANCE_MISMATCH)
    assert found[0].severity is Severity.CRITICAL
    assert found[0].magnitude == pytest.approx(2_500.0)


def test_a_sub_cent_balance_difference_is_ignored(engine: ReconciliationEngine) -> None:
    report = engine.reconcile(
        snapshot(balance=100_000.0),
        snapshot(source="paper", balance=100_000.005),
    )
    assert report.is_clean


def test_fill_count_drift_alone_is_a_warning(engine: ReconciliationEngine) -> None:
    report = engine.reconcile(
        snapshot(fill_count=10),
        snapshot(source="paper", fill_count=11),
    )
    assert report.by_kind(DiscrepancyKind.FILL_COUNT_MISMATCH)[0].severity is Severity.WARNING
    assert not report.has_critical


# --------------------------------------------------------------------------- escalation


def test_a_critical_divergence_enters_safe_mode(clock: SimulatedClock) -> None:
    risk = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, clock)
    engine = ReconciliationEngine(on_critical=risk.enter_safe_mode)

    report = engine.reconcile(
        snapshot(),
        snapshot(source="paper", positions={"BTC-USD": 3.0}),
    )
    assert engine.enforce(report) is True
    assert risk.state.mode is SystemMode.SAFE_MODE
    assert "phantom_position" in risk.state.kill_switch_reason


def test_a_warning_does_not_stop_trading(clock: SimulatedClock) -> None:
    risk = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, clock)
    engine = ReconciliationEngine(on_critical=risk.enter_safe_mode)

    report = engine.reconcile(snapshot(fill_count=1), snapshot(source="paper", fill_count=2))
    assert engine.enforce(report) is False
    assert risk.state.mode is SystemMode.NORMAL


def test_safe_mode_needs_a_named_human_to_leave(clock: SimulatedClock) -> None:
    """Recovery from a reconciliation break is an operator decision, not something the
    next clean run undoes on its own — the clean run may only mean the divergence moved."""
    risk = RiskEngine(RiskLimits(), DEFAULT_UNIVERSE, clock)
    engine = ReconciliationEngine(on_critical=risk.enter_safe_mode)
    engine.enforce(
        engine.reconcile(snapshot(), snapshot(source="paper", positions={"BTC-USD": 1.0}))
    )
    assert risk.state.mode is SystemMode.SAFE_MODE

    # A subsequent clean comparison changes nothing by itself.
    engine.enforce(engine.reconcile(snapshot(), snapshot(source="paper")))
    assert risk.state.mode is SystemMode.SAFE_MODE

    risk.resume(approved_by="operator@example.com")
    assert risk.state.mode is SystemMode.NORMAL


def test_reconciliation_never_repairs_state(engine: ReconciliationEngine) -> None:
    """The comparison is pure. Neither snapshot is touched, so nothing can 'fix' a
    ledger into agreement with a snapshot it misread."""
    internal = snapshot(positions={"BTC-USD": 1.0}, balance=50_000.0)
    external = snapshot(source="paper", positions={"BTC-USD": 9.0}, balance=10.0)
    before = (internal.model_dump(), external.model_dump())

    engine.reconcile(internal, external)
    assert (internal.model_dump(), external.model_dump()) == before


def test_enforce_without_a_hook_still_reports(engine: ReconciliationEngine) -> None:
    """Offline analysis over recorded snapshots has no engine to halt, and must not
    crash for the lack of one."""
    report = engine.reconcile(snapshot(), snapshot(source="paper", positions={"X": 1.0}))
    assert engine.enforce(report) is True


def test_run_ids_are_sequential_and_the_last_report_is_kept(
    engine: ReconciliationEngine,
) -> None:
    engine.reconcile(snapshot(), snapshot(source="paper"))
    second = engine.reconcile(snapshot(), snapshot(source="paper"))
    assert engine.runs == 2
    assert second.run_id == "recon-000002"
    assert engine.last_report is second


def test_negative_tolerances_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        ReconciliationEngine(quantity_tolerance=-1.0)


# --------------------------------------------------------------------------- parsing


def test_a_malformed_provider_snapshot_surfaces_rather_than_crashing(
    engine: ReconciliationEngine,
) -> None:
    """A snapshot is external input even when the venue is a simulator in the same
    process. An engine that crashes on a malformed one cannot report the divergence
    that malformation represents."""
    external = LedgerSnapshot.of_provider_snapshot(
        {"orders": {"ord-1": "not-a-real-state"}, "positions": {}, "balance": 100_000.0},
        at=START,
        source="paper",
    )
    assert external.orders["ord-1"] is OrderState.FAILED

    report = engine.reconcile(
        snapshot(orders={"ord-1": OrderState.ACKNOWLEDGED}), external
    )
    assert report.by_kind(DiscrepancyKind.ORDER_STATE_MISMATCH)


def test_an_empty_snapshot_parses(engine: ReconciliationEngine) -> None:
    parsed = LedgerSnapshot.of_provider_snapshot({}, at=START, source="paper")
    assert parsed.orders == {} and parsed.positions == {}
    assert parsed.balance == 0.0


def test_a_report_serializes_for_the_audit_log(engine: ReconciliationEngine) -> None:
    report = engine.reconcile(
        snapshot(), snapshot(source="paper", positions={"BTC-USD": 1.0})
    )
    payload = report.to_dict()
    assert payload["worst_severity"] == "critical"
    assert payload["discrepancies"][0]["kind"] == "phantom_position"
    assert payload["checked_at"].endswith("+00:00")


# --------------------------------------------------------------------------- end to end


async def test_a_healthy_paper_run_reconciles_clean(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    provider = PaperExecutionProvider(
        ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0),
        DEFAULT_UNIVERSE,
        clock,
        rng,
    )
    await provider.submit_order(intent(quantity=3.0))
    clock.advance_to(START + timedelta(minutes=2))
    provider.on_bar(bar())

    orders = {o.order_id: o for o in await provider.get_orders()}
    engine = ReconciliationEngine()
    report = await engine.run_against(
        provider,
        orders=orders,
        portfolio=await provider.get_portfolio(),
        fill_count=len(await provider.get_trades()),
        at=clock.now(),
    )
    assert report.is_clean, report.summary()


async def test_a_dropped_fill_event_is_caught_end_to_end(
    clock: SimulatedClock, rng: RngRegistry
) -> None:
    """The realistic failure: the provider filled an order and the system's own ledger
    never saw the event. Simulated here by reconciling against a portfolio built as if
    the fill had been missed."""
    provider = PaperExecutionProvider(
        ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0),
        DEFAULT_UNIVERSE,
        clock,
        rng,
    )
    order = await provider.submit_order(intent(quantity=3.0))
    clock.advance_to(START + timedelta(minutes=2))
    provider.on_bar(bar())

    stale_portfolio = PortfolioState.initial(100_000.0)
    stale_order = order.model_copy(
        update={"state": OrderState.ACKNOWLEDGED, "filled_quantity": 0.0, "fills": []}
    )

    calls: list[str] = []
    engine = ReconciliationEngine(on_critical=calls.append)
    report = await engine.run_against(
        provider,
        orders={stale_order.order_id: stale_order},
        portfolio=stale_portfolio,
        fill_count=0,
        at=clock.now(),
    )

    kinds = {d.kind for d in report.discrepancies}
    assert DiscrepancyKind.PHANTOM_POSITION in kinds
    assert DiscrepancyKind.UNRECORDED_FILL in kinds
    assert DiscrepancyKind.BALANCE_MISMATCH in kinds
    assert len(calls) == 1


def test_internal_snapshots_ignore_flat_positions() -> None:
    """A closed position is not a divergence. Comparing flat entries would report a
    break every time a trade completed on one side before the other."""
    portfolio = PortfolioState.initial(100_000.0)
    fill_open = Fill(
        fill_id="f1",
        order_id="o1",
        sequence=0,
        symbol="BTC-USD",
        side=Side.BUY,
        quantity=1.0,
        price=100.0,
        fee=0.0,
        filled_at=START,
    )
    fill_close = fill_open.model_copy(
        update={"fill_id": "f2", "sequence": 1, "side": Side.SELL, "price": 110.0}
    )
    portfolio.apply_fill(fill_open)
    portfolio.apply_fill(fill_close)

    order = Order(
        order_id="o1",
        client_order_id="c1",
        intent_id="i1",
        signal_id="s1",
        symbol="BTC-USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        time_in_force=TimeInForce.GTC,
        state=OrderState.FILLED,
        created_at=START,
        updated_at=START,
    )
    internal = LedgerSnapshot.of_internal(
        orders={"o1": order}, portfolio=portfolio, fill_count=2, at=START
    )
    assert internal.positions == {}

    external = LedgerSnapshot(
        source="paper",
        taken_at=START,
        orders={"o1": OrderState.FILLED},
        positions={},
        balance=portfolio.cash,
        fill_count=2,
    )
    assert ReconciliationEngine().reconcile(internal, external).is_clean


def test_reports_are_immutable() -> None:
    report = ReconciliationReport(
        run_id="recon-000001",
        checked_at=START,
        internal_source="internal",
        external_source="paper",
    )
    with pytest.raises(ValueError, match="frozen"):
        report.run_id = "tampered"
