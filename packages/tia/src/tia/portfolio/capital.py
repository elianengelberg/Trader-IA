"""Capital accounting, and the distinction that makes P&L meaningful.

An account balance goes up for two completely different reasons: the strategy made money,
or you deposited some. Conflating them produces a performance number that is flattering and
false — and the direction of the error is always the same, because people deposit after
losses far more often than they withdraw after gains.

So this module tracks:

    equity = allocated capital + realised P&L + unrealised P&L - fees

with **deposits and withdrawals recorded separately and never counted as return**.

It also enforces :attr:`CapitalPolicy.max_live_capital`, which is the single most important
number in a live deployment: the venue holds the whole balance, and this is the slice the
system is permitted to touch. Everything above it is out of reach by construction.

**On external balance changes.** The venue is the source of truth for the balance, and the
user can move money at any time without telling the system. A difference between what the
system expects and what the venue reports is therefore *normal* — but it must never be
assumed to be trading P&L. :meth:`CapitalLedger.classify_external_change` labels it, and an
unexplained difference halts trading rather than being absorbed into the return.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tia.core.clock import Clock, SystemClock, ensure_utc


class CapitalEventKind(StrEnum):
    """Why the capital base changed. Never a guess — an unexplained change says so."""

    ALLOCATION = "allocation"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    #: Detected at the venue, cause not determinable. Halts trading.
    UNEXPLAINED = "unexplained"
    FEE = "fee"
    REALISED_PNL = "realised_pnl"


class CapitalPolicy(BaseModel):
    """The hard ceiling on what the system may risk.

    Immutable. A policy that could be raised at runtime — by the system, by a model, or by
    a UI control — is not a ceiling.
    """

    model_config = ConfigDict(frozen=True)

    #: The most the strategy may ever have at work, in quote currency. Everything in the
    #: venue account above this is untouchable.
    max_live_capital: float = Field(gt=0)
    #: Largest single position, as a fraction of allocated capital.
    max_position_pct: float = Field(0.25, gt=0, le=1.0)
    #: Hard stop on cumulative loss against allocated capital.
    max_total_loss_pct: float = Field(20.0, gt=0, le=100.0)

    def __setattr__(self, name: str, value: Any) -> None:  # pragma: no cover - guard
        raise AttributeError(
            "CapitalPolicy is immutable. Changing the capital ceiling is a deliberate "
            "operator action taken through configuration, not a runtime mutation."
        )


@dataclass(frozen=True)
class CapitalEvent:
    """One change to the capital base, with its cause recorded."""

    at: datetime
    kind: CapitalEventKind
    amount: float
    note: str = ""
    venue_balance_after: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "kind": self.kind.value,
            "amount": round(self.amount, 8),
            "note": self.note,
            "venue_balance_after": self.venue_balance_after,
        }


@dataclass
class CapitalSnapshot:
    """Everything the dashboard's capital panel shows, computed rather than stored."""

    allocated_capital: float
    deposits: float
    withdrawals: float
    realised_pnl: float
    unrealised_pnl: float
    fees_paid: float
    available_capital: float
    used_capital: float
    max_live_capital: float

    @property
    def equity(self) -> float:
        return self.allocated_capital + self.realised_pnl + self.unrealised_pnl

    @property
    def net_contributed(self) -> float:
        """What the user put in, net. The denominator for any honest return figure."""
        return self.deposits - self.withdrawals

    @property
    def net_return_pct(self) -> float:
        """Return on contributed capital, excluding deposits and withdrawals entirely.

        This is the number that is allowed to be called "return". Dividing equity by the
        starting balance instead would count a deposit as a gain.
        """
        base = self.net_contributed
        if base <= 0:
            return 0.0
        return (self.realised_pnl + self.unrealised_pnl) / base * 100.0

    @property
    def headroom(self) -> float:
        """How much of the live-capital ceiling is unused."""
        return max(0.0, self.max_live_capital - self.used_capital)

    @property
    def utilisation_pct(self) -> float:
        if self.max_live_capital <= 0:
            return 0.0
        return self.used_capital / self.max_live_capital * 100.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "allocated_capital": round(self.allocated_capital, 8),
            "deposits": round(self.deposits, 8),
            "withdrawals": round(self.withdrawals, 8),
            "net_contributed": round(self.net_contributed, 8),
            "realised_pnl": round(self.realised_pnl, 8),
            "unrealised_pnl": round(self.unrealised_pnl, 8),
            "fees_paid": round(self.fees_paid, 8),
            "equity": round(self.equity, 8),
            "available_capital": round(self.available_capital, 8),
            "used_capital": round(self.used_capital, 8),
            "max_live_capital": round(self.max_live_capital, 8),
            "headroom": round(self.headroom, 8),
            "utilisation_pct": round(self.utilisation_pct, 4),
            "net_return_pct": round(self.net_return_pct, 6),
        }


@dataclass
class BalanceReconciliation:
    """What to do about a difference between our books and the venue's."""

    expected: float
    observed: float
    difference: float
    kind: CapitalEventKind
    explanation: str
    halts_trading: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": round(self.expected, 8),
            "observed": round(self.observed, 8),
            "difference": round(self.difference, 8),
            "kind": self.kind.value,
            "explanation": self.explanation,
            "halts_trading": self.halts_trading,
        }


class CapitalLedger:
    """The capital base and its history.

    Deliberately not the same object as the portfolio: the portfolio tracks *positions*,
    this tracks *money the user put in and took out*. Keeping them separate is what makes
    "did the strategy make money?" answerable at all.
    """

    #: Differences below this are venue rounding, not a movement worth classifying.
    DUST = 1e-6

    def __init__(
        self,
        policy: CapitalPolicy,
        *,
        allocated: float = 0.0,
        clock: Clock | None = None,
    ) -> None:
        self._policy = policy
        self._clock = clock or SystemClock()
        self._allocated = 0.0
        self._deposits = 0.0
        self._withdrawals = 0.0
        self._realised_pnl = 0.0
        self._fees = 0.0
        self._events: list[CapitalEvent] = []
        self._halted_reason = ""

        if allocated > 0:
            self.allocate(allocated, at=None, note="initial allocation")

    @property
    def policy(self) -> CapitalPolicy:
        return self._policy

    @property
    def events(self) -> tuple[CapitalEvent, ...]:
        return tuple(self._events)

    @property
    def is_halted(self) -> bool:
        return bool(self._halted_reason)

    @property
    def halted_reason(self) -> str:
        return self._halted_reason

    # ------------------------------------------------------------------ movements

    def allocate(self, amount: float, *, at: datetime | None, note: str = "") -> None:
        """Put capital under the system's control, up to the policy ceiling.

        Refuses rather than truncating: silently allocating less than asked is how someone
        ends up believing the system is trading twice what it is.
        """
        if amount <= 0:
            raise ValueError("allocation must be positive")
        if self._allocated + amount > self._policy.max_live_capital + self.DUST:
            raise ValueError(
                f"allocating {amount} would take the total to "
                f"{self._allocated + amount}, above the max_live_capital ceiling of "
                f"{self._policy.max_live_capital}. Raise the ceiling deliberately in "
                "configuration, or allocate less."
            )
        self._allocated += amount
        self._deposits += amount
        self._record(CapitalEventKind.DEPOSIT, amount, at, note or "capital allocated")

    def withdraw_allocation(self, amount: float, *, at: datetime | None, note: str = "") -> None:
        """Take capital back out of the system's control.

        This does **not** move money at the venue — the system has no withdrawal permission
        and never will. It reduces what the strategy is allowed to use.
        """
        if amount <= 0:
            raise ValueError("withdrawal must be positive")
        if amount > self._allocated + self.DUST:
            raise ValueError(
                f"cannot deallocate {amount}; only {self._allocated} is allocated"
            )
        self._allocated -= amount
        self._withdrawals += amount
        self._record(CapitalEventKind.WITHDRAWAL, -amount, at, note or "allocation reduced")

    def record_realised_pnl(self, amount: float, *, at: datetime | None = None) -> None:
        self._realised_pnl += amount
        self._record(CapitalEventKind.REALISED_PNL, amount, at, "")

    def record_fee(self, amount: float, *, at: datetime | None = None) -> None:
        if amount < 0:
            raise ValueError("a fee is a positive cost")
        self._fees += amount
        self._record(CapitalEventKind.FEE, -amount, at, "")

    # ------------------------------------------------------------------ views

    def snapshot(
        self, *, unrealised_pnl: float = 0.0, used_capital: float = 0.0
    ) -> CapitalSnapshot:
        equity = self._allocated + self._realised_pnl + unrealised_pnl
        return CapitalSnapshot(
            allocated_capital=self._allocated,
            deposits=self._deposits,
            withdrawals=self._withdrawals,
            realised_pnl=self._realised_pnl,
            unrealised_pnl=unrealised_pnl,
            fees_paid=self._fees,
            available_capital=max(0.0, equity - used_capital),
            used_capital=used_capital,
            max_live_capital=self._policy.max_live_capital,
        )

    def loss_breached(self, *, unrealised_pnl: float = 0.0) -> bool:
        """Whether cumulative loss has passed the policy's hard stop."""
        if self._deposits <= 0:
            return False
        loss_pct = -(self._realised_pnl + unrealised_pnl) / self._deposits * 100.0
        return loss_pct >= self._policy.max_total_loss_pct

    # ------------------------------------------------------------------ reconciliation

    def classify_external_change(
        self,
        *,
        venue_balance: float,
        expected_balance: float,
        at: datetime | None = None,
        tolerance: float = 1e-4,
    ) -> BalanceReconciliation:
        """Explain a difference between our books and the venue's, or refuse to.

        The critical rule: a difference is **never** assumed to be trading P&L. Trading
        P&L arrives through fills, which the system already knows about. Anything left
        over came from somewhere else, and if it cannot be attributed it halts trading —
        because a system that does not know how much money it has cannot size a position.
        """
        difference = venue_balance - expected_balance

        if abs(difference) <= max(tolerance, self.DUST):
            return BalanceReconciliation(
                expected=expected_balance,
                observed=venue_balance,
                difference=difference,
                kind=CapitalEventKind.ALLOCATION,
                explanation="balances agree within tolerance",
                halts_trading=False,
            )

        # A clean increase with no unaccounted fills is a deposit; a clean decrease is a
        # withdrawal. Both are the user's own action and neither is a return.
        if difference > 0:
            kind = CapitalEventKind.DEPOSIT
            explanation = (
                f"the venue reports {difference:.8f} more than expected. Recorded as a "
                "deposit, not as profit — a balance increase the system did not cause "
                "through a fill is money the user moved."
            )
            halts = False
        else:
            kind = CapitalEventKind.WITHDRAWAL
            explanation = (
                f"the venue reports {abs(difference):.8f} less than expected. Recorded as "
                "a withdrawal, not as a loss. The system cannot withdraw, so this was the "
                "user or another process."
            )
            halts = False

        # A movement large enough to change what the strategy is doing is not something to
        # absorb quietly, whichever direction it went.
        if abs(difference) > self._policy.max_live_capital * 0.10:
            kind = CapitalEventKind.UNEXPLAINED
            explanation = (
                f"the balance moved by {difference:+.8f}, more than 10% of the live-capital "
                "ceiling, with no corresponding fill. Trading is halted until an operator "
                "confirms the cause; the system will not size positions against a balance "
                "it cannot explain."
            )
            halts = True
            self._halted_reason = explanation

        self._record(kind, difference, at, explanation, venue_balance_after=venue_balance)
        if kind is CapitalEventKind.DEPOSIT:
            self._deposits += difference
            self._allocated = min(
                self._policy.max_live_capital, self._allocated + difference
            )
        elif kind is CapitalEventKind.WITHDRAWAL:
            self._withdrawals += abs(difference)
            self._allocated = max(0.0, self._allocated + difference)

        return BalanceReconciliation(
            expected=expected_balance,
            observed=venue_balance,
            difference=difference,
            kind=kind,
            explanation=explanation,
            halts_trading=halts,
        )

    def clear_halt(self, *, approved_by: str) -> None:
        """Resume after an unexplained movement. Requires naming who accepted it."""
        if not approved_by.strip():
            raise ValueError("clearing a capital halt requires a named approver")
        self._halted_reason = ""

    def _record(
        self,
        kind: CapitalEventKind,
        amount: float,
        at: datetime | None,
        note: str,
        *,
        venue_balance_after: float | None = None,
    ) -> None:
        moment = ensure_utc(at) if at is not None else self._clock.now()
        self._events.append(
            CapitalEvent(
                at=moment,
                kind=kind,
                amount=amount,
                note=note,
                venue_balance_after=venue_balance_after,
            )
        )


__all__ = [
    "BalanceReconciliation",
    "CapitalEvent",
    "CapitalEventKind",
    "CapitalLedger",
    "CapitalPolicy",
    "CapitalSnapshot",
]
