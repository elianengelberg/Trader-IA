#!/usr/bin/env python3
"""Open the paper account's journal over a legacy record — by hand, once, dry run first.

    python scripts/account_baseline.py                       # dry run: what is there, what would be written
    python scripts/account_baseline.py --apply --reason "fills predate the account journal"
    python scripts/account_baseline.py --db sqlite+aiosqlite:///./data/runtime/tia.db --symbol BTC-USD

Why this exists. Deployments up to ``ab68d1c`` wrote fills to the ``fills`` table but kept
no account journal: every session began at base capital and a position left open when a
session ended was never closed in the record. The journal-aware runtime (``1c914c5`` on)
rebuilds the account from ``account.*`` events and cross-checks them against ``fills``; over
a store whose fills predate the journal the cross-check finds N fills and 0 events, calls
the account inconsistent and — correctly — refuses new entries. The fix is not to delete
the fills nor to silence the check: it is one ``account.baseline`` event, written by an
operator, that says where the account's record starts and pins the legacy set it sets
aside (count, net quantity, fees). Everything is still there; everything is still checked.

Reads ``TIA_DATABASE_URL`` unless ``--db`` is given, and prints the URL with its password
redacted. Deletes nothing. The only write is the one baseline event, and only with
``--apply``; without it the same code path runs and is rolled back, so the dry run shows
exactly what ``--apply`` would do, including every refusal.

Exit codes: 0 the dry run printed, or the rebuild is complete after ``--apply``;
            1 the baseline was refused, or the rebuild is still incomplete afterwards;
            2 the database could not be read.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "tia" / "src"))

from sqlalchemy import select

from tia.persistence import AccountJournalRepository, Database
from tia.persistence.models import RunRecord

DEFAULT_URL = "sqlite+aiosqlite:///./data/runtime/tia.db"
DEFAULT_SYMBOL = os.environ.get("TIA_LIVE__SYMBOL", "BTC-USD")
DEFAULT_CAPITAL = float(os.environ.get("TIA_LIVE__PAPER_CAPITAL", "10000"))
#: The runtime rebuilds the paper account from ``paper-live`` runs only (a live run's
#: fills belong to the venue's account); the baseline is pinned over the same set.
DEFAULT_MODES = "paper-live"


class _DryRun(Exception):
    """Raised inside the write session to roll it back and carry out what it would have written."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("dry run")
        self.result = result


def redact(url: str) -> str:
    if "://" in url and "@" in url:
        scheme, _, rest = url.partition("://")
        return f"{scheme}://***@{rest.rsplit('@', 1)[-1]}"
    return url


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _print_restore(label: str, restore: Any, *, as_json: bool) -> None:
    if as_json:
        return
    print(f"\n{label}")
    print(f"  complete: {restore.complete}")
    if restore.error:
        print(f"  error:    {restore.error}")
    print(f"  cash {restore.cash:.6f}  realized {restore.realized_pnl:.6f}  fees {restore.fees_paid:.6f}  "
          f"position {restore.position_quantity}  events {restore.events_seen}  fills {restore.fills_seen}")
    for key in sorted(restore.checks):
        print(f"  checks.{key}: {restore.checks[key]}")


async def run(args: argparse.Namespace) -> int:
    url = args.db or os.environ.get("TIA_DATABASE_URL", DEFAULT_URL)
    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    now = datetime.now(UTC)
    at = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else now
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    report: dict[str, Any] = {
        "database": redact(url), "symbol": args.symbol, "modes": list(modes), "baseline_at": at.isoformat(),
        "apply": bool(args.apply),
    }
    try:
        db = Database(url)
    except Exception as exc:
        print(f"FAIL  the database could not be opened: {str(exc)[:300]}", file=sys.stderr)
        return 2
    try:
        try:
            async with db.session() as session:
                repo = AccountJournalRepository(session)
                before = await repo.rebuild(now=now, initial_capital=args.capital, symbol=args.symbol, modes=modes)
                fills = await repo.fill_rows(symbol=args.symbol, modes=modes)
                events = await repo.account_event_count(modes=modes)
                moving = await repo.account_event_count(modes=modes, moving_only=True)
                runs = (
                    await session.execute(
                        select(RunRecord).where(RunRecord.mode.in_(list(modes))).order_by(RunRecord.started_at)
                    )
                ).scalars().all()
        except Exception as exc:  # the store could not be read: say so, change nothing
            print(f"FAIL  the database could not be read: {str(exc)[:300]}", file=sys.stderr)
            return 2

        report["before"] = before.as_dict()
        report["account_events"] = events
        report["account_events_moving"] = moving
        report["account_events_informational"] = events - moving
        report["runs"] = [
            {"run_id": r.run_id, "mode": r.mode, "scenario": r.scenario, "started_at": _iso(r.started_at),
             "stopped_at": _iso(r.stopped_at) or None}
            for r in runs
        ]
        report["fills"] = [{**row, "run_started_at": _iso(row["run_started_at"]),
                            "run_stopped_at": _iso(row["run_stopped_at"]) or None,
                            "filled_at": _iso(row["filled_at"])} for row in fills]
        if not args.json:
            print(f"Trader-IA — account baseline ({'APPLY' if args.apply else 'DRY RUN'})")
            print(f"  database: {redact(url)}   symbol: {args.symbol}   modes: {', '.join(modes)}")
            print(f"  now: {now.isoformat()}   baseline at: {at.isoformat()}")
            _print_restore("Rebuild before", before, as_json=False)
            print(f"\nSession runs ({len(runs)}) and account.* events ({events}: {moving} moving the account "
                  f"[fills/adjustments, block a baseline], {events - moving} informational [marks/plans, skipped])")
            for r in runs:
                print(f"  {r.run_id}  {r.mode:10s} {r.scenario:10s} started {_iso(r.started_at)}  "
                      f"stopped {_iso(r.stopped_at) or '— (not stopped)'}")
            print(f"\nFills in the table for {args.symbol} ({len(fills)})")
            for row in fills:
                print(f"  {row['fill_id']}  run {row['run_id']} ({row['run_mode']})  {row['side']:4s} "
                      f"{row['quantity']:.8f} @ {row['price']:.2f}  fee {row['fee']:.6f}  {row['liquidity']}  "
                      f"filled {_iso(row['filled_at'])}")

        if before.complete and not args.force_when_complete:
            report["outcome"] = "nothing to do: the rebuild is already complete"
            if not args.json:
                print(f"\nPASS  {report['outcome']}")
            else:
                print(json.dumps(report, indent=2, default=str))
            return 0

        reason = args.reason or (
            "fills written before the account journal existed (deployments up to ab68d1c); "
            "each session began at base capital and the record was never carried"
        )
        actor = args.actor or os.environ.get("USER") or "operator"
        try:
            async with db.session() as session:
                written = await AccountJournalRepository(session).open_baseline(
                    symbol=args.symbol, at=at, reason=reason, actor=actor, modes=modes,
                    allow_active_run=args.allow_active_run, now=datetime.now(UTC),
                )
                if not args.apply:
                    raise _DryRun(written)
        except _DryRun as dry:
            report["would_write"] = dry.result
            report["outcome"] = "dry run: nothing written"
            if not args.json:
                print("\nWould write (dry run — rolled back, nothing persisted):")
                print(json.dumps(dry.result, indent=2, default=str))
                print("\nDRY RUN  nothing written. Re-run with --apply --reason '...' to write this baseline.")
            else:
                print(json.dumps(report, indent=2, default=str))
            return 0
        except ValueError as refused:
            report["outcome"] = f"refused: {refused}"
            if not args.json:
                print(f"\nREFUSED  {refused}")
            else:
                print(json.dumps(report, indent=2, default=str))
            return 1

        report["written"] = written
        async with db.session() as session:
            after = await AccountJournalRepository(session).rebuild(
                now=datetime.now(UTC), initial_capital=args.capital, symbol=args.symbol, modes=modes,
            )
        report["after"] = after.as_dict()
        report["outcome"] = "complete" if after.complete else f"still incomplete: {after.error}"
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print("\nWritten:")
            print(json.dumps(written, indent=2, default=str))
            _print_restore("Rebuild after", after, as_json=False)
            print(f"\n{'PASS' if after.complete else 'FAIL'}  {report['outcome']}")
        return 0 if after.complete else 1
    finally:
        await db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", help="database URL (default: TIA_DATABASE_URL, else the SQLite demo file)")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help=f"account symbol (default {DEFAULT_SYMBOL})")
    parser.add_argument("--modes", default=DEFAULT_MODES,
                        help=f"comma-separated run modes that share the account (default {DEFAULT_MODES})")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL, help="base capital for the rebuild")
    parser.add_argument("--at", help="baseline time, ISO-8601 UTC (default: now); must follow every legacy fill")
    parser.add_argument("--reason", help="why the record is opened here (recorded in the event)")
    parser.add_argument("--actor", help="who is doing it (recorded in the event; default $USER)")
    parser.add_argument("--apply", action="store_true", help="write the baseline (default: dry run)")
    parser.add_argument("--allow-active-run", action="store_true",
                        help="proceed although a session run is not stopped (its engine may be writing)")
    parser.add_argument("--force-when-complete", action="store_true",
                        help="go through the baseline path even if the rebuild is already complete")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
