"""Reconciliation for the market maker: the venue's picture against ours, classified.

Pure comparisons, no I/O: the live service fetches the venue's open orders, balances and
trades and hands them here with the adapter's local orders and the ledger's expectations.
The result says what differs and how bad it is. Nothing here repairs anything — the
execution adapter resolves individual orders by asking the venue, the ledger adopts the
venue's balances, and the service stops quoting on anything critical. Binance wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: Every live client order id this market maker ever sends starts with this.
OWN_PREFIX = "tiamm-"


class MMDiscrepancy(StrEnum):
    #: An open order on the account without our prefix: someone or something else trades
    #: this account. The maker cannot know what it is, so it is critical by default.
    FOREIGN_OPEN_ORDER = "foreign_open_order"
    #: An open order with our prefix that this run does not know (a leak from a previous
    #: run, or a lost acknowledgement). Critical: a resting order nobody manages.
    VENUE_ORDER_UNKNOWN_LOCALLY = "venue_order_unknown_locally"
    #: We believe an order rests; the venue does not list it. Resolved by asking; a
    #: warning until the answer arrives.
    LOCAL_ORDER_MISSING_AT_VENUE = "local_order_missing_at_venue"
    #: The venue reports more executed quantity than we have booked from trades.
    EXECUTED_QUANTITY_AHEAD = "executed_quantity_ahead"
    #: An order whose submission or cancel ended in a timeout and is not resolved yet.
    UNKNOWN_ORDER_STATE = "unknown_order_state"
    #: The account's balances differ from what the booked fills imply, beyond tolerance.
    BALANCE_MISMATCH = "balance_mismatch"


CRITICAL = frozenset(
    {
        MMDiscrepancy.FOREIGN_OPEN_ORDER,
        MMDiscrepancy.VENUE_ORDER_UNKNOWN_LOCALLY,
        MMDiscrepancy.UNKNOWN_ORDER_STATE,
        MMDiscrepancy.BALANCE_MISMATCH,
    }
)


@dataclass(frozen=True)
class MMReconciliationReport:
    t_ms: int
    ok: bool
    critical: bool
    discrepancies: tuple[dict[str, Any], ...]
    venue_open: int
    local_open: int
    balances: dict[str, Any]
    trades_seen: int
    initial: bool = False
    note: str = ""

    @property
    def summary(self) -> str:
        if self.ok:
            return "clean"
        kinds: dict[str, int] = {}
        for d in self.discrepancies:
            kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
        return ", ".join(f"{k} x{n}" for k, n in sorted(kinds.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "t_ms": self.t_ms,
            "ok": self.ok,
            "critical": self.critical,
            "summary": self.summary,
            "discrepancies": list(self.discrepancies),
            "venue_open": self.venue_open,
            "local_open": self.local_open,
            "balances": self.balances,
            "trades_seen": self.trades_seen,
            "initial": self.initial,
            "note": self.note,
        }


def compare_orders(
    *,
    local_open: list[Any],
    local_unknown: list[Any],
    venue_open: list[Any],
    own_prefix: str = OWN_PREFIX,
    foreign_is_critical: bool = True,
) -> list[dict[str, Any]]:
    """Local orders carry ``order_id`` (the client id), ``state``, ``filled`` and
    ``venue_executed_qty``; venue orders carry ``client_order_id``, ``order_id`` and
    ``filled_quantity`` (the domain ``Order``)."""
    issues: list[dict[str, Any]] = []
    local_by_id = {o.order_id: o for o in local_open}
    venue_ids: set[str] = set()
    for venue in venue_open:
        cid = str(getattr(venue, "client_order_id", "") or "")
        venue_ids.add(cid)
        local = local_by_id.get(cid)
        if local is not None:
            executed = float(getattr(venue, "filled_quantity", 0.0) or 0.0)
            if executed > float(getattr(local, "filled", 0.0)) + 1e-12:
                issues.append({"kind": MMDiscrepancy.EXECUTED_QUANTITY_AHEAD.value, "severity": "warning", "order_id": cid, "venue_executed": executed, "booked": float(getattr(local, "filled", 0.0)), "detail": "the venue reports executed quantity the trade history has not delivered yet"})
            continue
        if cid.startswith(own_prefix):
            issues.append({"kind": MMDiscrepancy.VENUE_ORDER_UNKNOWN_LOCALLY.value, "severity": "critical", "order_id": cid, "venue_order_id": str(getattr(venue, "order_id", "")), "detail": "an open market-maker order this run does not manage"})
        else:
            issues.append({"kind": MMDiscrepancy.FOREIGN_OPEN_ORDER.value, "severity": "critical" if foreign_is_critical else "warning", "order_id": cid, "venue_order_id": str(getattr(venue, "order_id", "")), "detail": "an open order on the account not placed by this market maker"})
    for local in local_open:
        if getattr(local, "state", "") == "resting" and local.order_id not in venue_ids:
            issues.append({"kind": MMDiscrepancy.LOCAL_ORDER_MISSING_AT_VENUE.value, "severity": "warning", "order_id": local.order_id, "detail": "resting here, absent from the venue's open orders: resolved by asking"})
    for local in local_unknown:
        issues.append({"kind": MMDiscrepancy.UNKNOWN_ORDER_STATE.value, "severity": "critical", "order_id": local.order_id, "detail": str(getattr(local, "unknown_reason", "")) or "unknown"})
    return issues


def compare_balances(
    *,
    expected_quote_usd: float,
    expected_base_btc: float,
    venue_quote_usd: float,
    venue_base_btc: float,
    quote_tolerance_usd: float,
    base_tolerance_btc: float,
) -> dict[str, Any] | None:
    dq, db = venue_quote_usd - expected_quote_usd, venue_base_btc - expected_base_btc
    if abs(dq) <= quote_tolerance_usd and abs(db) <= base_tolerance_btc:
        return None
    return {
        "kind": MMDiscrepancy.BALANCE_MISMATCH.value,
        "severity": "critical",
        "quote_delta_usd": round(dq, 6),
        "base_delta_btc": round(db, 8),
        "quote_tolerance_usd": quote_tolerance_usd,
        "base_tolerance_btc": base_tolerance_btc,
        "detail": "the account's balances differ from what the booked fills imply; the venue's figures are adopted",
    }


def build_report(
    *,
    t_ms: int,
    order_issues: list[dict[str, Any]],
    balance_issue: dict[str, Any] | None,
    venue_open: int,
    local_open: int,
    balances: dict[str, Any],
    trades_seen: int,
    initial: bool = False,
) -> MMReconciliationReport:
    issues = list(order_issues) + ([balance_issue] if balance_issue else [])
    critical = any(i.get("severity") == "critical" for i in issues)
    return MMReconciliationReport(
        t_ms=t_ms,
        ok=not issues,
        critical=critical,
        discrepancies=tuple(issues),
        venue_open=venue_open,
        local_open=local_open,
        balances=balances,
        trades_seen=trades_seen,
        initial=initial,
        note="the venue is the fact; local state is a hypothesis" if issues else "",
    )


__all__ = ["CRITICAL", "OWN_PREFIX", "MMDiscrepancy", "MMReconciliationReport", "build_report", "compare_balances", "compare_orders"]
