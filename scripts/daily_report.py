#!/usr/bin/env python3
"""Daily report: what the system actually did in a 24-hour window.

    python scripts/daily_report.py                  # the last 24 hours, from TIA_DATABASE_URL
    python scripts/daily_report.py --date 2026-08-13
    python scripts/daily_report.py --db sqlite+aiosqlite:///./data/runtime/demo.db --json

Reads the journal — decisions, orders, fills, incidents, equity, reconciliations — and
prints the day. Every number is a count or a sum over persisted rows; nothing here is a
projection, and the report says nothing about the future because it cannot know it.

Exit codes: 0 report printed (even for a quiet day), 1 the database could not be read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "tia" / "src"))

from sqlalchemy import text

from tia.persistence import Database

DEFAULT_URL = "sqlite+aiosqlite:///./data/runtime/tia.db"


async def scalar(db: Database, sql: str, **params: Any) -> Any:
    async with db.session() as session:
        return (await session.execute(text(sql), params)).scalar()


async def rows(db: Database, sql: str, **params: Any) -> list[Any]:
    async with db.session() as session:
        return list((await session.execute(text(sql), params)).all())


async def build_report(db: Database, start: datetime, end: datetime) -> dict[str, Any]:
    window = {"start": start.isoformat(), "end": end.isoformat()}
    p = {"s": start, "e": end}

    decisions = await scalar(
        db, "SELECT COUNT(*) FROM decisions WHERE decided_at >= :s AND decided_at < :e", **p
    )
    by_verdict = await rows(
        db,
        "SELECT verdict, COUNT(*) FROM decisions "
        "WHERE decided_at >= :s AND decided_at < :e GROUP BY verdict ORDER BY 2 DESC",
        **p,
    )
    orders = await scalar(
        db, "SELECT COUNT(*) FROM orders WHERE created_at >= :s AND created_at < :e", **p
    )
    order_states = await rows(
        db,
        "SELECT state, COUNT(*) FROM orders "
        "WHERE created_at >= :s AND created_at < :e GROUP BY state ORDER BY 2 DESC",
        **p,
    )
    fills = await rows(
        db,
        "SELECT COUNT(*), COALESCE(SUM(quantity * price), 0), COALESCE(SUM(fee), 0) "
        "FROM fills WHERE filled_at >= :s AND filled_at < :e",
        **p,
    )
    fill_count, notional, fees = fills[0] if fills else (0, 0.0, 0.0)

    outcomes = await rows(
        db,
        # net quote P&L is derived, not stored: bps of the entry notional. CASE instead
        # of SUM(bool) so the same SQL runs on SQLite and Postgres.
        "SELECT COUNT(*), COALESCE(SUM(CASE WHEN net_bps > 0 THEN 1 ELSE 0 END), 0), "
        "COALESCE(AVG(net_bps), 0), "
        "COALESCE(SUM(net_bps / 10000.0 * entry_price * quantity), 0) "
        "FROM edge_outcomes WHERE closed_at >= :s AND closed_at < :e",
        **p,
    )
    closed, winners, avg_net_bps, net_quote = outcomes[0] if outcomes else (0, 0, 0.0, 0.0)

    equity = await rows(
        db,
        "SELECT MIN(equity), MAX(equity), MAX(drawdown_pct) FROM equity_points "
        "WHERE at >= :s AND at < :e",
        **p,
    )
    eq_min, eq_max, max_dd = equity[0] if equity else (None, None, None)
    eq_last = await scalar(
        db,
        "SELECT equity FROM equity_points WHERE at >= :s AND at < :e ORDER BY at DESC LIMIT 1",
        **p,
    )

    incidents = await rows(
        db,
        "SELECT kind, COUNT(*) FROM incidents "
        "WHERE at >= :s AND at < :e GROUP BY kind ORDER BY 2 DESC",
        **p,
    )
    reconciliations = await rows(
        db,
        "SELECT CASE WHEN clean THEN 'clean' ELSE 'divergent' END, COUNT(*) "
        "FROM reconciliations WHERE at >= :s AND at < :e GROUP BY clean",
        **p,
    )
    errors = await scalar(
        db,
        "SELECT COUNT(*) FROM logs WHERE at >= :s AND at < :e "
        "AND level IN ('ERROR', 'CRITICAL')",
        **p,
    )
    runs = await rows(
        db,
        "SELECT run_id, mode, started_at, stopped_at FROM runs "
        "WHERE started_at < :e AND (stopped_at IS NULL OR stopped_at >= :s) "
        "ORDER BY started_at",
        **p,
    )

    return {
        "window": window,
        "runs_active": [
            {
                "run_id": r[0],
                "mode": r[1],
                "started_at": str(r[2]),
                "stopped_at": str(r[3]) if r[3] else None,
            }
            for r in runs
        ],
        "decisions": {"total": int(decisions or 0), "by_verdict": dict(by_verdict)},
        "orders": {"total": int(orders or 0), "by_state": dict(order_states)},
        "fills": {
            "count": int(fill_count or 0),
            "notional_quote": round(float(notional or 0.0), 2),
            "fees_quote": round(float(fees or 0.0), 4),
        },
        "closed_round_trips": {
            "count": int(closed or 0),
            "winners": int(winners or 0),
            "win_rate": round(float(winners or 0) / closed, 3) if closed else None,
            "avg_net_bps": round(float(avg_net_bps or 0.0), 2) if closed else None,
            "net_pnl_quote": round(float(net_quote or 0.0), 4) if closed else None,
        },
        "equity": {
            "min": eq_min,
            "max": eq_max,
            "last": eq_last,
            "max_drawdown_pct": max_dd,
        },
        "incidents": dict(incidents),
        "reconciliations": dict(reconciliations),
        "error_log_lines": int(errors or 0),
        "note": (
            "Counts and sums over persisted rows for this window. Past results say "
            "nothing about future ones, and this report makes no claim about either."
        ),
    }


def print_human(report: dict[str, Any]) -> None:
    w = report["window"]
    print(f"Trader-IA daily report — {w['start']} → {w['end']}")
    print()
    if not report["runs_active"]:
        print("  No run was active in this window.")
    for run in report["runs_active"]:
        until = run["stopped_at"] or "still running"
        print(f"  run {run['run_id']}  mode={run['mode']}  {run['started_at']} → {until}")
    print()
    d = report["decisions"]
    print(f"  decisions            {d['total']:>8}   {d['by_verdict']}")
    o = report["orders"]
    print(f"  orders               {o['total']:>8}   {o['by_state']}")
    f = report["fills"]
    print(
        f"  fills                {f['count']:>8}   notional {f['notional_quote']}  "
        f"fees {f['fees_quote']}"
    )
    c = report["closed_round_trips"]
    if c["count"]:
        print(
            f"  closed round trips   {c['count']:>8}   win rate {c['win_rate']}  "
            f"avg {c['avg_net_bps']} bps  net {c['net_pnl_quote']}"
        )
    else:
        print("  closed round trips          0")
    e = report["equity"]
    if e["last"] is not None:
        print(
            f"  equity               min {e['min']}  max {e['max']}  last {e['last']}  "
            f"max drawdown {e['max_drawdown_pct']}%"
        )
    print(f"  incidents            {report['incidents'] or 'none'}")
    print(f"  reconciliations      {report['reconciliations'] or 'none'}")
    print(f"  error log lines      {report['error_log_lines']}")
    print()
    print(f"  {report['note']}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="", help="database URL (default: TIA_DATABASE_URL)")
    parser.add_argument("--date", default="", help="UTC date YYYY-MM-DD (default: last 24h)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    url = args.db or os.environ.get("TIA_DATABASE_URL", DEFAULT_URL)
    if args.date:
        start = datetime.fromisoformat(args.date).replace(tzinfo=UTC)
        end = start + timedelta(days=1)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=1)

    try:
        db = Database(url)
        report = await build_report(db, start, end)
        await db.close()
    except Exception as exc:
        print(f"FAIL  could not read the database: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
