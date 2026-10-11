"""Rebuild the risk engine's frequency state from the persisted execution record.

The frequency limits (entries per UTC day, per symbol per day, the cooldown after the last
entry) and the risk budget's daily entry cap live in memory while a session runs. A process
that restarts mid-day and starts those counters at zero can take more entries than the
configuration allows. This module reconstructs them from what the store already holds, so
there is one source of truth: the orders and fills the session persisted as it went.

**What is an entry.** The runtime arms the risk engine once per round trip opened — on the
first fill of the order that opened the position (:meth:`LiveRuntime._track_round_trip`).
The persisted record does not carry a "purpose" column, so the same convention the runtime
uses to *name* its orders is used to *classify* them: exits, protective stops and flattens
carry a ``signal_id`` with one of the prefixes in :data:`NON_ENTRY_PREFIXES`; anything else
is an entry. This is a convention, stated here and tested, not a schema guarantee.

**Idempotence.** The rebuild is a pure function of the rows it is given. Rows are
de-duplicated by order id and fill id, so replaying the same fills twice, or reading the
store twice, yields the same counters.

**Timezone.** Days are UTC calendar days of the fill timestamp, the same convention as
:meth:`tia.risk.engine.RiskState.roll_day`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

from tia.core.clock import ensure_utc


def _as_utc(value: datetime) -> datetime:
    """Rows come back naive from SQLite (it stores no offset); the store is written in UTC
    by every writer in this codebase, so a naive timestamp read back from it *is* UTC. An
    aware one is validated as such — never silently shifted."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return ensure_utc(value)


#: ``signal_id`` prefixes the runtime gives to orders that never open a position.
NON_ENTRY_PREFIXES: tuple[str, ...] = ("exit:", "protective:", "flatten:")
#: How far past ``now`` a row may be dated and still be read: the ordinary skew between
#: two clocks on one host. Beyond it the row is a clock problem (F10).
FUTURE_ROW_TOLERANCE_SECONDS = 60.0


def is_entry_signal_id(signal_id: str | None) -> bool:
    """Whether an order with this ``signal_id`` could have opened a position."""
    text = str(signal_id or "")
    return not any(text.startswith(prefix) for prefix in NON_ENTRY_PREFIXES)


@dataclass(frozen=True)
class PersistedOrder:
    """The slice of an ``orders`` row the rebuild needs."""

    order_id: str
    symbol: str
    signal_id: str
    created_at: datetime
    reduce_only: bool = False


@dataclass(frozen=True)
class PersistedFill:
    """The slice of a ``fills`` row the rebuild needs."""

    fill_id: str
    order_id: str
    symbol: str
    filled_at: datetime


@dataclass(frozen=True)
class RiskRestore:
    """What the store says about today, or why it could not be read.

    ``complete`` is the only field a caller may trust blindly: when it is False the
    counters are meaningless and the runtime must refuse new entries until a complete
    rebuild replaces this object. ``consulted`` distinguishes "the store was read and
    held nothing" (complete, zero everywhere) from "no store exists" (also complete:
    a runtime without persistence has nothing to restore from).
    """

    complete: bool
    day: str
    #: Round trips opened today (UTC): the risk engine's ``trades_today``.
    entries_today: int = 0
    #: The same, by symbol: ``trades_today_by_symbol``.
    entries_today_by_symbol: dict[str, int] = field(default_factory=dict)
    #: The most recent entry fill per symbol, whatever its day: ``last_trade_at``.
    last_entry_at: dict[str, datetime] = field(default_factory=dict)
    #: Entry *orders sent* today, filled or not: the risk budget's ``_trades_today``.
    entry_orders_today: int = 0
    #: Exploration round trips *closed* today, from the outcome record. A lower bound: an
    #: exploration entry still open at the restart is not in it.
    exploration_closed_today: int = 0
    consulted: bool = True
    source: str = ""
    error: str = ""
    #: Rows the rebuild saw, for the snapshot and the report.
    orders_seen: int = 0
    fills_seen: int = 0

    @classmethod
    def empty(cls, *, day: str = "", source: str = "no persistent store") -> RiskRestore:
        """Nothing to restore from: a runtime without persistence, or a fresh store."""
        return cls(complete=True, day=day, consulted=False, source=source)

    @classmethod
    def failed(cls, error: str, *, day: str = "") -> RiskRestore:
        """The store could not be read, or the rebuild raised. Entries must wait."""
        return cls(complete=False, day=day, consulted=True, source="store", error=error[:500])

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "consulted": self.consulted,
            "day": self.day,
            "entries_today": self.entries_today,
            "entries_today_by_symbol": dict(self.entries_today_by_symbol),
            "last_entry_at": {k: v.isoformat() for k, v in self.last_entry_at.items()},
            "entry_orders_today": self.entry_orders_today,
            "exploration_closed_today": self.exploration_closed_today,
            "source": self.source,
            "error": self.error,
            "orders_seen": self.orders_seen,
            "fills_seen": self.fills_seen,
        }


def utc_day_start(moment: datetime) -> datetime:
    moment = ensure_utc(moment)
    return datetime.combine(moment.date(), time.min, tzinfo=UTC)


def rebuild_risk_state(
    *,
    now: datetime,
    orders: Iterable[PersistedOrder],
    fills: Iterable[PersistedFill],
    exploration_closed_today: int = 0,
    source: str = "store",
) -> RiskRestore:
    """The frequency state the risk engine would hold had it never restarted.

    Counting rules, each matching what the running engine does:

    * an **entry** is an order whose ``signal_id`` is not an exit/protective/flatten id;
    * ``entries_today`` counts entry orders with at least one fill whose *first* fill
      landed today (UTC) — one per order, however many partial fills it took, because
      the runtime arms the engine once per round trip opened;
    * ``last_entry_at`` is the first-fill time of the most recent filled entry order per
      symbol, on any day, because a cooldown spans midnight;
    * ``entry_orders_today`` counts entry orders *created* today, filled or not — the
      budget's counter is incremented when an order is sent, not when it fills;
    * duplicate order ids and fill ids are counted once.
    """
    now = ensure_utc(now)
    day_start = utc_day_start(now)
    day = now.date().isoformat()
    horizon = now + timedelta(seconds=FUTURE_ROW_TOLERANCE_SECONDS)

    by_id: dict[str, PersistedOrder] = {}
    for order in orders:
        by_id.setdefault(order.order_id, order)
    # Rows dated after now (beyond a clock's ordinary skew) were written by a clock that
    # was ahead. They are not counted — and their presence makes the rebuild incomplete
    # (F10): a record that runs ahead of the clock is not one to count today's entries
    # from, and the runtime then refuses entries until a person reconciles.
    future_orders = sum(1 for o in by_id.values() if ensure_utc(o.created_at) > horizon)
    entries = {oid: o for oid, o in by_id.items() if is_entry_signal_id(o.signal_id) and not o.reduce_only}

    first_fill_at: dict[str, datetime] = {}
    seen_fills: set[str] = set()
    fills_seen = 0
    future_fills = 0
    for fill in fills:
        if fill.fill_id in seen_fills:
            continue
        seen_fills.add(fill.fill_id)
        fills_seen += 1
        if ensure_utc(fill.filled_at) > horizon:
            future_fills += 1
        if fill.order_id not in entries:
            continue
        at = ensure_utc(fill.filled_at)
        previous = first_fill_at.get(fill.order_id)
        if previous is None or at < previous:
            first_fill_at[fill.order_id] = at

    entries_today = 0
    by_symbol: dict[str, int] = {}
    last_entry_at: dict[str, datetime] = {}
    for order_id, at in first_fill_at.items():
        symbol = entries[order_id].symbol
        if at >= day_start and at <= now:
            entries_today += 1
            by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        if at <= now and (symbol not in last_entry_at or at > last_entry_at[symbol]):
            last_entry_at[symbol] = at

    entry_orders_today = sum(
        1
        for o in entries.values()
        if day_start <= ensure_utc(o.created_at) <= now
    )

    future_rows = future_orders + future_fills
    if future_rows:
        return RiskRestore(
            complete=False,
            day=day,
            consulted=True,
            source=source,
            error=(
                f"{future_rows} execution row(s) are dated after now ({now.isoformat()}); the "
                "writing clock was ahead — today's entries cannot be counted from this record"
            ),
            orders_seen=len(by_id),
            fills_seen=fills_seen,
        )

    return RiskRestore(
        complete=True,
        day=day,
        entries_today=entries_today,
        entries_today_by_symbol=by_symbol,
        last_entry_at=last_entry_at,
        entry_orders_today=entry_orders_today,
        exploration_closed_today=max(0, int(exploration_closed_today)),
        consulted=True,
        source=source,
        orders_seen=len(by_id),
        fills_seen=fills_seen,
    )


def persisted_order_from_row(row: Any) -> PersistedOrder:
    """Adapt an ``OrderRow`` (or any object with the same attributes) to the rebuild."""
    return PersistedOrder(
        order_id=str(row.order_id),
        symbol=str(row.symbol),
        signal_id=str(getattr(row, "signal_id", "") or ""),
        created_at=_as_utc(row.created_at),
        reduce_only=bool(getattr(row, "reduce_only", False)),
    )


def persisted_fill_from_row(row: Any) -> PersistedFill:
    return PersistedFill(
        fill_id=str(row.fill_id),
        order_id=str(row.order_id),
        symbol=str(row.symbol),
        filled_at=_as_utc(row.filled_at),
    )


def persisted_order_from_mapping(values: Mapping[str, Any]) -> PersistedOrder:
    return PersistedOrder(
        order_id=str(values["order_id"]),
        symbol=str(values["symbol"]),
        signal_id=str(values.get("signal_id") or ""),
        created_at=_as_utc(values["created_at"]),
        reduce_only=bool(values.get("reduce_only", False)),
    )


__all__ = [
    "NON_ENTRY_PREFIXES",
    "PersistedFill",
    "PersistedOrder",
    "RiskRestore",
    "is_entry_signal_id",
    "persisted_fill_from_row",
    "persisted_order_from_mapping",
    "persisted_order_from_row",
    "rebuild_risk_state",
    "utc_day_start",
]
