"""Execution — the order lifecycle, the paper matching engine and reconciliation.

Every provider in this package is a simulator, and
:class:`~tia.execution.provider.ExecutionProvider` refuses to be constructed with
``is_simulated=False``. That is the scope rule from ``docs/ARCHITECTURE.md`` §1 expressed
as code rather than as a comment.
"""

from tia.execution.paper import PaperExecutionProvider
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider
from tia.execution.reconciliation import (
    Discrepancy,
    DiscrepancyKind,
    LedgerSnapshot,
    ReconciliationEngine,
    ReconciliationReport,
    Severity,
)
from tia.execution.state_machine import (
    TRANSITIONS,
    assert_transition,
    can_transition,
    reachable_from,
    resolve_fill_state,
    terminal_states,
    transition,
    validate_table,
)

__all__ = [
    "TRANSITIONS",
    "Discrepancy",
    "DiscrepancyKind",
    "ExecutionCapabilities",
    "ExecutionProvider",
    "LedgerSnapshot",
    "PaperExecutionProvider",
    "ReconciliationEngine",
    "ReconciliationReport",
    "Severity",
    "assert_transition",
    "can_transition",
    "reachable_from",
    "resolve_fill_state",
    "terminal_states",
    "transition",
    "validate_table",
]
