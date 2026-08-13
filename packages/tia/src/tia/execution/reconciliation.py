"""Reconciliation — proving that what the system believes it holds is what it holds.

Every trading system carries two pictures of the same account: its own ledger, built
from the events it processed, and the venue's, built from what the venue actually did.
They drift. A dropped event, a fill that arrived after a restart, a retry that was not
idempotent, an order cancelled by the venue for a reason we never saw — each one leaves
the two pictures disagreeing, and every one of them is silent.

Reconciliation is the check that makes that drift loud.

**This module never repairs state.** It compares, classifies and escalates. Automatic
repair is how a reconciliation bug turns into a position: a component that "corrects"
the ledger to match a snapshot it misread will happily invent or erase exposure, and it
will do so with more confidence than the divergence that triggered it. When the two
pictures disagree about anything that implies risk, the correct action is to stop
trading and involve a human — which is exactly what :meth:`ReconciliationEngine.enforce`
does by putting the Risk Engine into safe mode.

That preference is the §64 rule applied to state: ``NO_TRADE`` beats
``TRADE_WITH_UNKNOWN_STATE``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.core.logging import get_logger
from tia.domain.enums import OrderState
from tia.domain.orders import Order
from tia.domain.portfolio import PortfolioState

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tia.execution.provider import ExecutionProvider

_log = get_logger("execution.reconciliation")


class Severity(StrEnum):
    """How much a divergence matters.

    ``CRITICAL`` means the system cannot state its own exposure. Nothing below that
    stops trading on its own.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class DiscrepancyKind(StrEnum):
    """The taxonomy of ways two pictures of an account can disagree."""

    #: The venue holds a position the system knows nothing about. Unmanaged risk: no
    #: stop, no size limit, no exit logic is watching it.
    PHANTOM_POSITION = "phantom_position"
    #: The system believes it holds a position the venue does not. Whatever risk the
    #: strategy thinks it has on is not actually on.
    ORPHANED_POSITION = "orphaned_position"
    #: Both hold the position, in different sizes.
    POSITION_QUANTITY_MISMATCH = "position_quantity_mismatch"
    #: The venue knows an order the system does not.
    UNKNOWN_ORDER = "unknown_order"
    #: The system knows an order the venue does not.
    MISSING_ORDER = "missing_order"
    #: Both know the order, in different states.
    ORDER_STATE_MISMATCH = "order_state_mismatch"
    #: The order filled at the venue and the system has not recorded it.
    UNRECORDED_FILL = "unrecorded_fill"
    #: Cash balances disagree.
    BALANCE_MISMATCH = "balance_mismatch"
    #: Different numbers of executions seen.
    FILL_COUNT_MISMATCH = "fill_count_mismatch"


class Discrepancy(BaseModel):
    """One disagreement between the two ledgers."""

    model_config = ConfigDict(frozen=True)

    kind: DiscrepancyKind
    severity: Severity
    subject: str = Field(description="symbol or order_id the discrepancy concerns")
    internal: str = Field(default="", description="what the system believed")
    external: str = Field(default="", description="what the provider reported")
    magnitude: float = Field(
        default=0.0, description="size of the divergence in the natural unit of the kind"
    )
    detail: str = ""

    @property
    def is_critical(self) -> bool:
        return self.severity is Severity.CRITICAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity.value,
            "subject": self.subject,
            "internal": self.internal,
            "external": self.external,
            "magnitude": self.magnitude,
            "detail": self.detail,
        }


class LedgerSnapshot(BaseModel):
    """One side's picture of the account at a moment in time.

    Deliberately narrow: order states, position quantities, cash and a fill count. These
    are the four things whose disagreement can hide exposure. Richer comparisons (P&L,
    average prices) are derived quantities — they diverge as a *consequence* of these,
    so checking them adds noise rather than coverage.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    taken_at: datetime
    orders: dict[str, OrderState] = Field(default_factory=dict)
    positions: dict[str, float] = Field(default_factory=dict)
    balance: float = 0.0
    fill_count: int = Field(default=0, ge=0)

    @field_validator("taken_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="ledger snapshot time")

    @classmethod
    def of_internal(
        cls,
        *,
        orders: Mapping[str, Order],
        portfolio: PortfolioState,
        fill_count: int,
        at: datetime,
        source: str = "internal",
    ) -> LedgerSnapshot:
        """Build the system's own picture from its ledger objects."""
        return cls(
            source=source,
            taken_at=at,
            orders={oid: order.state for oid, order in orders.items()},
            positions={
                symbol: position.quantity
                for symbol, position in portfolio.positions.items()
                if not position.is_flat
            },
            balance=portfolio.cash,
            fill_count=fill_count,
        )

    @classmethod
    def of_provider_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        at: datetime,
        source: str = "provider",
    ) -> LedgerSnapshot:
        """Build the venue's picture from an :meth:`ExecutionProvider` snapshot dict.

        Parsed defensively: a snapshot is external input even when the "venue" is a
        simulator in the same process, and a reconciliation engine that crashes on a
        malformed snapshot cannot report the divergence that malformation represents.
        """
        raw_orders = snapshot.get("orders") or {}
        orders: dict[str, OrderState] = {}
        for order_id, state in dict(raw_orders).items():
            try:
                orders[str(order_id)] = OrderState(state)
            except ValueError:
                _log.error(
                    "reconciliation_unparseable_order_state",
                    order_id=str(order_id),
                    reported=str(state),
                )
                # An unreadable state is not a missing order; record it as FAILED so it
                # surfaces as a mismatch rather than vanishing from the comparison.
                orders[str(order_id)] = OrderState.FAILED

        raw_positions = snapshot.get("positions") or {}
        positions = {str(k): float(v) for k, v in dict(raw_positions).items()}

        return cls(
            source=source,
            taken_at=at,
            orders=orders,
            positions=positions,
            balance=float(snapshot.get("balance", 0.0)),
            fill_count=int(snapshot.get("fill_count", 0)),
        )


class ReconciliationReport(BaseModel):
    """The outcome of one comparison."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    checked_at: datetime
    internal_source: str
    external_source: str
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    orders_compared: int = 0
    positions_compared: int = 0

    @field_validator("checked_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="reconciliation time")

    @property
    def is_clean(self) -> bool:
        return not self.discrepancies

    @property
    def critical(self) -> list[Discrepancy]:
        return [d for d in self.discrepancies if d.is_critical]

    @property
    def has_critical(self) -> bool:
        return any(d.is_critical for d in self.discrepancies)

    @property
    def worst_severity(self) -> Severity | None:
        for level in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
            if any(d.severity is level for d in self.discrepancies):
                return level
        return None

    def by_kind(self, kind: DiscrepancyKind) -> list[Discrepancy]:
        return [d for d in self.discrepancies if d.kind is kind]

    def summary(self) -> str:
        if self.is_clean:
            return (
                f"clean: {self.orders_compared} orders and "
                f"{self.positions_compared} positions agree"
            )
        counts: dict[str, int] = {}
        for d in self.discrepancies:
            counts[d.kind.value] = counts.get(d.kind.value, 0) + 1
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        return f"{len(self.discrepancies)} discrepancies ({parts})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_at": self.checked_at.isoformat(),
            "internal_source": self.internal_source,
            "external_source": self.external_source,
            "is_clean": self.is_clean,
            "worst_severity": self.worst_severity.value if self.worst_severity else None,
            "orders_compared": self.orders_compared,
            "positions_compared": self.positions_compared,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
        }


class ReconciliationEngine:
    """Compares the system's ledger against a provider's and escalates divergence.

    ``on_critical`` is the escalation hook — in the runtime it is
    ``risk_engine.enter_safe_mode``. It is a plain callable rather than a hard
    dependency on :class:`~tia.risk.engine.RiskEngine` so that reconciliation can also be
    run offline over recorded snapshots, where there is no engine to halt.
    """

    def __init__(
        self,
        *,
        quantity_tolerance: float = 1e-8,
        quantity_relative_tolerance: float = 1e-6,
        balance_tolerance: float = 0.01,
        balance_relative_tolerance: float = 1e-6,
        on_critical: Callable[[str], None] | None = None,
    ) -> None:
        if quantity_tolerance < 0 or balance_tolerance < 0:
            raise ValueError("tolerances must be non-negative")
        self._qty_abs = quantity_tolerance
        self._qty_rel = quantity_relative_tolerance
        self._bal_abs = balance_tolerance
        self._bal_rel = balance_relative_tolerance
        self._on_critical = on_critical
        self._runs = 0
        self._last_report: ReconciliationReport | None = None

    @property
    def runs(self) -> int:
        return self._runs

    @property
    def last_report(self) -> ReconciliationReport | None:
        return self._last_report

    # ------------------------------------------------------------------ comparison

    def reconcile(
        self, internal: LedgerSnapshot, external: LedgerSnapshot
    ) -> ReconciliationReport:
        """Compare two snapshots. Pure: mutates neither side."""
        self._runs += 1
        discrepancies: list[Discrepancy] = []
        discrepancies.extend(self._compare_positions(internal, external))
        discrepancies.extend(self._compare_orders(internal, external))
        discrepancies.extend(self._compare_balance(internal, external))
        discrepancies.extend(self._compare_fill_counts(internal, external))

        report = ReconciliationReport(
            run_id=f"recon-{self._runs:06d}",
            checked_at=external.taken_at,
            internal_source=internal.source,
            external_source=external.source,
            discrepancies=discrepancies,
            orders_compared=len(set(internal.orders) | set(external.orders)),
            positions_compared=len(set(internal.positions) | set(external.positions)),
        )
        self._last_report = report

        if report.is_clean:
            _log.debug("reconciliation_clean", run_id=report.run_id)
        else:
            _log.warning(
                "reconciliation_divergence",
                run_id=report.run_id,
                summary=report.summary(),
                critical=len(report.critical),
            )
        return report

    def _compare_positions(
        self, internal: LedgerSnapshot, external: LedgerSnapshot
    ) -> list[Discrepancy]:
        found: list[Discrepancy] = []
        for symbol in sorted(set(internal.positions) | set(external.positions)):
            ours = internal.positions.get(symbol)
            theirs = external.positions.get(symbol)

            if ours is None and theirs is not None:
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.PHANTOM_POSITION,
                        severity=Severity.CRITICAL,
                        subject=symbol,
                        internal="flat",
                        external=f"{theirs:.10g}",
                        magnitude=abs(theirs),
                        detail=(
                            "the provider reports a position the system is not tracking; "
                            "no stop, size limit or exit logic is watching it"
                        ),
                    )
                )
                continue

            if ours is not None and theirs is None:
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.ORPHANED_POSITION,
                        severity=Severity.CRITICAL,
                        subject=symbol,
                        internal=f"{ours:.10g}",
                        external="flat",
                        magnitude=abs(ours),
                        detail=(
                            "the system believes it holds a position the provider does "
                            "not report; the risk it thinks is on is not on"
                        ),
                    )
                )
                continue

            if ours is None or theirs is None:  # pragma: no cover - unreachable
                continue

            delta = abs(ours - theirs)
            if delta > self._tolerance(self._qty_abs, self._qty_rel, ours, theirs):
                # A sign flip is categorically worse than a size difference: the system
                # would hedge in the wrong direction.
                flipped = (ours > 0) != (theirs > 0)
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.POSITION_QUANTITY_MISMATCH,
                        severity=Severity.CRITICAL,
                        subject=symbol,
                        internal=f"{ours:.10g}",
                        external=f"{theirs:.10g}",
                        magnitude=delta,
                        detail=(
                            "position direction disagrees"
                            if flipped
                            else "position size disagrees beyond tolerance"
                        ),
                    )
                )
        return found

    def _compare_orders(
        self, internal: LedgerSnapshot, external: LedgerSnapshot
    ) -> list[Discrepancy]:
        found: list[Discrepancy] = []
        for order_id in sorted(set(internal.orders) | set(external.orders)):
            ours = internal.orders.get(order_id)
            theirs = external.orders.get(order_id)

            if ours is None and theirs is not None:
                # An order the venue knows and we do not is only benign if it is already
                # terminal *and* produced nothing — and we cannot tell that from a state
                # alone, so an unknown filled order is treated as unrecorded exposure.
                severity = (
                    Severity.CRITICAL
                    if theirs in {OrderState.FILLED, OrderState.PARTIALLY_FILLED}
                    else Severity.WARNING
                )
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.UNKNOWN_ORDER,
                        severity=severity,
                        subject=order_id,
                        internal="absent",
                        external=theirs.value,
                        detail="the provider knows an order the system has no record of",
                    )
                )
                continue

            if ours is not None and theirs is None:
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.MISSING_ORDER,
                        severity=(
                            Severity.CRITICAL if ours.is_open else Severity.WARNING
                        ),
                        subject=order_id,
                        internal=ours.value,
                        external="absent",
                        detail=(
                            "the system is tracking an open order the provider does not "
                            "report"
                            if ours.is_open
                            else "the system has an order record the provider has dropped"
                        ),
                    )
                )
                continue

            if ours is None or theirs is None or ours is theirs:
                continue

            # A fill we did not record is the single most dangerous state disagreement:
            # it means real (simulated) exposure exists that no risk check has seen.
            if theirs in {OrderState.FILLED, OrderState.PARTIALLY_FILLED} and ours not in {
                OrderState.FILLED,
                OrderState.PARTIALLY_FILLED,
            }:
                found.append(
                    Discrepancy(
                        kind=DiscrepancyKind.UNRECORDED_FILL,
                        severity=Severity.CRITICAL,
                        subject=order_id,
                        internal=ours.value,
                        external=theirs.value,
                        detail="the provider filled an order the system does not consider filled",
                    )
                )
                continue

            found.append(
                Discrepancy(
                    kind=DiscrepancyKind.ORDER_STATE_MISMATCH,
                    severity=(
                        # We think it is done, they think it is live: we have stopped
                        # watching something that can still trade.
                        Severity.CRITICAL
                        if ours.is_terminal and theirs.is_open
                        else Severity.WARNING
                    ),
                    subject=order_id,
                    internal=ours.value,
                    external=theirs.value,
                    detail="order states disagree",
                )
            )
        return found

    def _compare_balance(
        self, internal: LedgerSnapshot, external: LedgerSnapshot
    ) -> list[Discrepancy]:
        delta = abs(internal.balance - external.balance)
        tolerance = self._tolerance(
            self._bal_abs, self._bal_rel, internal.balance, external.balance
        )
        if delta <= tolerance:
            return []
        return [
            Discrepancy(
                kind=DiscrepancyKind.BALANCE_MISMATCH,
                severity=Severity.CRITICAL,
                subject="cash",
                internal=f"{internal.balance:.10g}",
                external=f"{external.balance:.10g}",
                magnitude=delta,
                detail=(
                    "cash balances disagree beyond tolerance; position sizing derived "
                    "from the wrong balance would size every subsequent trade wrongly"
                ),
            )
        ]

    def _compare_fill_counts(
        self, internal: LedgerSnapshot, external: LedgerSnapshot
    ) -> list[Discrepancy]:
        if internal.fill_count == external.fill_count:
            return []
        # On its own this is a lagging-feed symptom rather than a risk event; the fills
        # that matter show up as position or order divergence, which are already
        # critical. Reported so a persistent drift is visible before it becomes one.
        return [
            Discrepancy(
                kind=DiscrepancyKind.FILL_COUNT_MISMATCH,
                severity=Severity.WARNING,
                subject="fills",
                internal=str(internal.fill_count),
                external=str(external.fill_count),
                magnitude=float(abs(internal.fill_count - external.fill_count)),
                detail="the two ledgers have seen different numbers of executions",
            )
        ]

    @staticmethod
    def _tolerance(absolute: float, relative: float, a: float, b: float) -> float:
        """Absolute floor plus a relative allowance scaled to the larger magnitude."""
        return absolute + relative * max(abs(a), abs(b))

    # ------------------------------------------------------------------ escalation

    def enforce(self, report: ReconciliationReport) -> bool:
        """Escalate a report. Returns ``True`` if it triggered safe mode.

        Called separately from :meth:`reconcile` so that an offline analysis can compare
        ledgers without halting anything, and so the halt decision is one auditable line
        rather than a side effect buried in a comparison.
        """
        if not report.has_critical:
            return False

        reason = (
            f"reconciliation {report.run_id}: {len(report.critical)} critical "
            f"discrepancies — {report.critical[0].kind.value} on "
            f"{report.critical[0].subject}"
        )
        _log.critical(
            "reconciliation_critical_divergence",
            run_id=report.run_id,
            reason=reason,
            discrepancies=[d.to_dict() for d in report.critical],
        )
        if self._on_critical is not None:
            self._on_critical(reason)
        return True

    async def run(
        self,
        provider: ExecutionProvider,
        *,
        orders: Mapping[str, Order],
        portfolio: PortfolioState,
        fill_count: int,
        at: datetime,
        enforce: bool = True,
    ) -> ReconciliationReport:
        """Snapshot both sides, compare, and optionally escalate."""
        internal = LedgerSnapshot.of_internal(
            orders=orders, portfolio=portfolio, fill_count=fill_count, at=at
        )
        raw = provider.snapshot() if hasattr(provider, "snapshot") else {}
        external = LedgerSnapshot.of_provider_snapshot(
            raw, at=at, source=provider.name
        )
        report = self.reconcile(internal, external)
        if enforce:
            self.enforce(report)
        return report

    async def run_against(
        self,
        provider: ExecutionProvider,
        *,
        orders: Mapping[str, Order],
        portfolio: PortfolioState,
        fill_count: int,
        at: datetime,
        enforce: bool = True,
    ) -> ReconciliationReport:
        """As :meth:`run`, but querying the provider through its public interface.

        This is the form the runtime uses. It goes through ``get_orders`` /
        ``get_positions`` / ``get_balance`` rather than an internals dump, so the
        comparison exercises the same API any other consumer would see — a snapshot
        method that quietly disagrees with the query methods is itself a divergence
        worth catching.
        """
        external = LedgerSnapshot.of_provider_snapshot(
            await provider.state_snapshot(), at=at, source=provider.name
        )
        internal = LedgerSnapshot.of_internal(
            orders=orders, portfolio=portfolio, fill_count=fill_count, at=at
        )
        report = self.reconcile(internal, external)
        if enforce:
            self.enforce(report)
        return report


__all__ = [
    "Discrepancy",
    "DiscrepancyKind",
    "LedgerSnapshot",
    "ReconciliationEngine",
    "ReconciliationReport",
    "Severity",
]
