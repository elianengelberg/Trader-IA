"""Capital accounting.

Separate from position tracking on purpose. Positions answer "what do we hold?"; this
answers "how much of the user's money is at work, where did it come from, and how much of
the change in it did the strategy actually cause?" — which is the question a deposit made
after a losing week silently destroys if the two are merged.
"""

from tia.portfolio.capital import (
    BalanceReconciliation,
    CapitalEvent,
    CapitalEventKind,
    CapitalLedger,
    CapitalPolicy,
    CapitalSnapshot,
)

__all__ = [
    "BalanceReconciliation",
    "CapitalEvent",
    "CapitalEventKind",
    "CapitalLedger",
    "CapitalPolicy",
    "CapitalSnapshot",
]
