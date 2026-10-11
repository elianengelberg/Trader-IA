"""The paper account's own record: what it holds, rebuilt from what happened to it.

A paper-live session's account lives in the matching engine's memory. A process that
restarts gets a fresh engine: flat, at base capital, with "today" starting now and the
equity peak set to whatever it opened with. The daily loss limit, the drawdown breaker and
the budget's drawdown state all read that account, so a restart was, in effect, a reset of
every limit that depends on it.

This module is the account's durable form. It is an **event journal**, append-only and
idempotent, written to the existing ``events`` table under four event types:

* ``account.fill`` — a simulated execution, exactly as the engine applied it;
* ``account.adjustment`` — cash moved outside a fill: funding, a liquidation fee;
* ``account.mark`` — the engine's last price for the symbol at a closed bar, so equity,
  its peak and the UTC day's opening equity can be carried across a restart;
* ``account.plan`` — the runtime's exit plan for the open leg (stop, target, kind) and the
  beliefs the entry was taken under, so a restored leg is protected and, when it closes,
  scored like any other.

The rebuild (:func:`fold_account_events`) replays them through the same
:class:`~tia.domain.portfolio.PortfolioState` the engine uses, in order, so cash,
position, realised P&L, fees, peak equity and day-start equity come out exactly as the
engine would hold them had it never restarted. It is a pure function of the events: fed the
same journal twice it gives the same account, and the journal's own idempotency key keeps a
replayed event from landing twice.

What it is **not**: strategy evidence. ``edge_outcomes`` says what each round trip
earned; this says what the account holds. The two are reconciled, never substituted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict

from tia.core.clock import ensure_utc
from tia.domain.enums import Side
from tia.domain.orders import Fill
from tia.domain.portfolio import PortfolioState

ACCOUNT_MODEL_VERSION = 1
#: How far past ``now`` a journal event may be dated and still be folded: the ordinary
#: skew between two clocks on one host. Beyond it the event is a clock problem (G11).
FUTURE_EVENT_TOLERANCE_SECONDS = 60.0
EVENT_FILL = "account.fill"
EVENT_ADJUSTMENT = "account.adjustment"
EVENT_MARK = "account.mark"
EVENT_PLAN = "account.plan"
ACCOUNT_EVENT_TYPES: tuple[str, ...] = (EVENT_FILL, EVENT_ADJUSTMENT, EVENT_MARK, EVENT_PLAN)


class AccountFillPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    fill_id: str
    order_id: str
    side: str
    quantity: float
    price: float
    fee: float
    filled_at: datetime
    model_version: int = ACCOUNT_MODEL_VERSION


class AccountAdjustmentPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    amount: float
    reason: str
    at: datetime
    #: What the movement is (``funding``, ``liquidation``) and, for funding, the period it
    #: settles (``YYYY-MM-DD:k``), so the journal — not a pointer written afterwards — is
    #: what says which settlements were paid (Phase 1.8). Absent in older rows, which
    #: still move cash and are simply not keyed.
    kind: str | None = None
    period: str | None = None
    model_version: int = ACCOUNT_MODEL_VERSION


class AccountMarkPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    price: float
    at: datetime
    #: Informational: what the engine held when the mark was written. The rebuild
    #: recomputes these and a disagreement is a finding, not a value to trust.
    cash: float = 0.0
    position_quantity: float = 0.0
    equity: float = 0.0
    model_version: int = ACCOUNT_MODEL_VERSION


class AccountPlanPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    at: datetime
    stop: float | None = None
    initial_stop: float | None = None
    target: float | None = None
    kind: str | None = None
    direction: str | None = None
    beliefs: dict[str, Any] = {}
    #: The funding this leg has paid (positive) or received (negative) so far, so a
    #: session that adopts the leg after a restart reports the round trip's net of its
    #: whole carry, not of the part it saw (Phase 1.6). The account itself already
    #: carries every settlement as an adjustment; this is attribution, never a charge.
    funding_paid: float = 0.0
    #: The last eight-hour funding period the session accounted for while this leg was
    #: open, as ``YYYY-MM-DD:k`` (k = 0, 1, 2 for the settlements at 00:00, 08:00 and
    #: 16:00 UTC), and the periods it could *not* settle (Phase 1.7). A session that
    #: adopts the leg resumes from the pointer: every period after it is pending, to be
    #: settled from the venue's realised rate and the mark at the settlement, or recorded
    #: as unreconciled — never charged twice, never silently skipped.
    funding_period: str | None = None
    funding_unreconciled_periods: int = 0
    funding_unreconciled: list[dict[str, Any]] = []
    model_version: int = ACCOUNT_MODEL_VERSION


@dataclass(frozen=True)
class AccountEventRecord:
    """One journal row as the rebuild consumes it."""

    event_type: str
    occurred_at: datetime
    sequence: int
    event_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class AccountRestore:
    """The account as the journal says it is, or why it could not be read.

    Only ``complete`` may be trusted blindly: when False nothing else here is usable and a
    runtime must refuse new entries until a complete rebuild replaces it.
    """

    complete: bool
    consulted: bool
    model_version: int = ACCOUNT_MODEL_VERSION
    initial_capital: float = 0.0
    cash: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    peak_equity: float = 0.0
    day_start_equity: float = 0.0
    current_day: str = ""
    equity: float = 0.0
    position_quantity: float = 0.0
    position_average_price: float = 0.0
    position_fees_paid: float = 0.0
    position_opened_at: datetime | None = None
    open_leg_fees: float = 0.0
    last_price: float | None = None
    last_event_at: datetime | None = None
    plan: dict[str, Any] | None = None
    beliefs: dict[str, Any] | None = None
    #: Funding settlements the journal holds, period key -> cash moved (negative when the
    #: account paid). The source of truth for "already settled" after a restart: a plan
    #: pointer written after a settlement can be lost to a crash, a row on disk cannot
    #: (Phase 1.8).
    funding_settled: dict[str, float] = field(default_factory=dict)
    events_seen: int = 0
    fills_seen: int = 0
    source: str = ""
    error: str = ""
    checks: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls, *, initial_capital: float, source: str = "no persistent store") -> AccountRestore:
        """Nothing to restore from: a runtime with no store, or a store with no journal."""
        return cls(
            complete=True, consulted=False, initial_capital=initial_capital,
            cash=initial_capital, peak_equity=initial_capital, day_start_equity=initial_capital,
            equity=initial_capital, source=source,
        )

    @classmethod
    def failed(cls, error: str, *, initial_capital: float = 0.0) -> AccountRestore:
        return cls(
            complete=False, consulted=True, initial_capital=initial_capital, source="store",
            error=error[:500],
        )

    @property
    def has_position(self) -> bool:
        return abs(self.position_quantity) > 1e-12

    def portfolio_state(self) -> PortfolioState:
        """The engine's account, as the journal says it is, ready to be handed to it."""
        from tia.domain.portfolio import Position

        state = PortfolioState.initial(self.initial_capital)
        state.cash = self.cash
        state.realized_pnl = self.realized_pnl
        state.fees_paid = self.fees_paid
        state.peak_equity = self.peak_equity
        state.day_start_equity = self.day_start_equity
        state.current_day = self.current_day
        if self.has_position:
            symbol = str((self.plan or {}).get("symbol") or self.checks.get("symbol") or "")
            position = Position(
                symbol=symbol,
                quantity=self.position_quantity,
                average_price=self.position_average_price,
                fees_paid=self.position_fees_paid,
                last_price=self.last_price or self.position_average_price,
                opened_at=self.position_opened_at,
            )
            # Marked at the journal's own last event time: this module never reads the
            # wall clock (the decision path is deterministic by construction).
            if self.last_price and self.last_event_at is not None:
                position.mark(self.last_price, self.last_event_at)
            state.positions[symbol] = position
        state.updated_at = self.last_event_at
        return state

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "consulted": self.consulted,
            "model_version": self.model_version,
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "fees_paid": round(self.fees_paid, 6),
            "peak_equity": round(self.peak_equity, 6),
            "day_start_equity": round(self.day_start_equity, 6),
            "current_day": self.current_day,
            "equity": round(self.equity, 6),
            "position_quantity": self.position_quantity,
            "position_average_price": self.position_average_price,
            "open_leg_fees": round(self.open_leg_fees, 6),
            "last_price": self.last_price,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "plan": self.plan,
            "beliefs": self.beliefs,
            "funding_settled": dict(self.funding_settled),
            "events_seen": self.events_seen,
            "fills_seen": self.fills_seen,
            "source": self.source,
            "error": self.error,
            "checks": dict(self.checks),
        }


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return ensure_utc(value)


def fold_account_events(
    events: Iterable[AccountEventRecord],
    *,
    initial_capital: float,
    symbol: str,
    now: datetime,
    source: str = "journal",
) -> AccountRestore:
    """Replay the journal through the engine's own portfolio model.

    Events are applied in ``(occurred_at, sequence, event_id)`` order. A fill moves the
    position and cash exactly as :meth:`PortfolioState.apply_fill` does; an adjustment
    moves cash; a mark re-prices the position and refreshes the equity peak and the UTC
    day's opening equity exactly as the engine's own ``mark`` does. After the last event
    the account is marked once more at ``now`` with the last known price, so a restart on
    a later UTC day opens that day at the carried equity, as the running engine would have.
    """
    now = ensure_utc(now)
    ordered = sorted(events, key=lambda e: (_as_utc(e.occurred_at), e.sequence, e.event_id))
    # An event dated after now (beyond a clock's ordinary skew) was written by a clock
    # that was ahead of this one. It is not folded — the day it belongs to cannot be
    # known — and its presence makes the rebuild incomplete below: an account whose
    # record runs ahead of the clock is not one to size entries from (Phase 1.3, G11).
    horizon = now + timedelta(seconds=FUTURE_EVENT_TOLERANCE_SECONDS)
    future = [e for e in ordered if _as_utc(e.occurred_at) > horizon]
    if future:
        future_ids = {e.event_id for e in future}
        ordered = [e for e in ordered if e.event_id not in future_ids]
    state = PortfolioState.initial(initial_capital)
    if ordered:
        # The account opened its first day at base capital, as the engine's first bar
        # would have marked it before any fill; the day boundary logic below then runs
        # exactly as the engine's does on every later day.
        state.current_day = _as_utc(ordered[0].occurred_at).date().isoformat()
    seen: set[str] = set()
    last_price: float | None = None
    last_at: datetime | None = None
    plan: dict[str, Any] | None = None
    beliefs: dict[str, Any] | None = None
    open_leg_fees = 0.0
    fills_seen = 0
    funding_settled: dict[str, float] = {}
    for event in ordered:
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        payload = event.payload
        at = _as_utc(event.occurred_at)
        last_at = at
        if event.event_type == EVENT_FILL:
            if payload.get("symbol") != symbol:
                continue
            fill = Fill(
                fill_id=str(payload["fill_id"]),
                order_id=str(payload["order_id"]),
                sequence=0,
                symbol=symbol,
                side=Side(payload["side"]),
                quantity=float(payload["quantity"]),
                price=float(payload["price"]),
                fee=float(payload.get("fee", 0.0)),
                filled_at=_as_utc(payload.get("filled_at") or event.occurred_at),
            )
            was_flat = state.position(symbol).is_flat
            state.apply_fill(fill)
            fills_seen += 1
            last_price = fill.price
            now_flat = state.position(symbol).is_flat
            if now_flat:
                open_leg_fees = 0.0
                plan = None
                beliefs = None
            elif was_flat:
                open_leg_fees = fill.fee
            else:
                open_leg_fees += fill.fee
        elif event.event_type == EVENT_ADJUSTMENT:
            amount = float(payload.get("amount", 0.0))
            state.cash += amount
            state.updated_at = at
            state._refresh_peaks(at)
            period = payload.get("period")
            if payload.get("kind") == "funding" and period:
                funding_settled[str(period)] = funding_settled.get(str(period), 0.0) + amount
        elif event.event_type == EVENT_MARK:
            if payload.get("symbol") != symbol:
                continue
            last_price = float(payload["price"])
            state.mark(symbol, last_price, at)
        elif event.event_type == EVENT_PLAN:
            if payload.get("symbol") != symbol:
                continue
            plan = {
                "symbol": symbol,
                "stop": payload.get("stop"),
                "initial_stop": payload.get("initial_stop"),
                "target": payload.get("target"),
                "kind": payload.get("kind"),
                "direction": payload.get("direction"),
                # Absent in plans written before Phase 1.6: zero, the only honest value.
                "funding_paid": float(payload.get("funding_paid") or 0.0),
                # Absent before Phase 1.7: no pointer, and the adopting session joins
                # the current period late rather than guessing what was settled.
                "funding_period": payload.get("funding_period") or None,
                "funding_unreconciled_periods": int(payload.get("funding_unreconciled_periods") or 0),
                "funding_unreconciled": list(payload.get("funding_unreconciled") or []),
            }
            beliefs = dict(payload.get("beliefs") or {}) or None
    if last_price is not None:
        state.mark(symbol, last_price, now)
    else:
        state._refresh_peaks(now)
    position = state.positions.get(symbol)
    checks: dict[str, Any] = {"symbol": symbol, "future_events": len(future)}
    error = ""
    if future:
        first = _as_utc(future[0].occurred_at)
        error = (
            f"{len(future)} journal event(s) are dated after now (first at {first.isoformat()}, "
            f"now {now.isoformat()}); the writing clock was ahead — reconcile before trading"
        )
    return AccountRestore(
        complete=not future,
        consulted=True,
        initial_capital=initial_capital,
        cash=state.cash,
        realized_pnl=state.realized_pnl,
        fees_paid=state.fees_paid,
        peak_equity=state.peak_equity,
        day_start_equity=state.day_start_equity,
        current_day=state.current_day,
        equity=state.equity,
        position_quantity=position.quantity if position else 0.0,
        position_average_price=position.average_price if position else 0.0,
        position_fees_paid=position.fees_paid if position else 0.0,
        position_opened_at=position.opened_at if position else None,
        open_leg_fees=open_leg_fees if position and not position.is_flat else 0.0,
        last_price=last_price,
        last_event_at=last_at,
        plan=plan if position and not position.is_flat else None,
        beliefs=beliefs if position and not position.is_flat else None,
        funding_settled=funding_settled,
        events_seen=len(seen),
        fills_seen=fills_seen,
        source=source,
        error=error,
        checks=checks,
    )


def cross_check(restore: AccountRestore, *, fill_rows_net_quantity: float, fill_rows_count: int, fill_rows_fees: float) -> AccountRestore:
    """Reconcile the journal against the ``fills`` table the engine also writes.

    The journal and the fills table are written by the same process from the same fills;
    they may disagree only when one write was lost. A disagreement in net quantity or in
    the count of fills makes the rebuild **incomplete**: an account whose record is
    missing a fill cannot be trusted to hold what it says.
    """
    checks = dict(restore.checks)
    checks.update({
        "fills_in_journal": restore.fills_seen,
        "fills_in_table": fill_rows_count,
        "net_quantity_journal": restore.position_quantity,
        "net_quantity_table": fill_rows_net_quantity,
        "fees_journal": round(restore.fees_paid, 8),
        "fees_table": round(fill_rows_fees, 8),
    })
    problems: list[str] = []
    if restore.fills_seen != fill_rows_count:
        problems.append(f"{restore.fills_seen} fills in the journal, {fill_rows_count} in the fills table")
    if abs(restore.position_quantity - fill_rows_net_quantity) > 1e-9:
        problems.append(
            f"net position {restore.position_quantity} from the journal, {fill_rows_net_quantity} from the fills table"
        )
    if abs(restore.fees_paid - fill_rows_fees) > 1e-6:
        problems.append(f"fees {restore.fees_paid:.6f} in the journal, {fill_rows_fees:.6f} in the fills table")
    if not problems:
        return AccountRestore(**{**restore.__dict__, "checks": checks})
    return AccountRestore(
        **{**restore.__dict__, "complete": False, "checks": checks,
           "error": "account record inconsistent: " + "; ".join(problems)},
    )


__all__ = [
    "ACCOUNT_EVENT_TYPES",
    "ACCOUNT_MODEL_VERSION",
    "EVENT_ADJUSTMENT",
    "EVENT_FILL",
    "EVENT_MARK",
    "EVENT_PLAN",
    "AccountAdjustmentPayload",
    "AccountEventRecord",
    "AccountFillPayload",
    "AccountMarkPayload",
    "AccountPlanPayload",
    "AccountRestore",
    "cross_check",
    "fold_account_events",
]
