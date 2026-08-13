#!/usr/bin/env python3
"""Run one backtest against the committed fixtures and print the evidence statement.

Zero configuration: no network, no credentials, no API key. It reads the CSV fixtures in
``data/fixtures``, which are committed, so the numbers this prints are reproducible by
anyone on any machine.

What it prints is deliberately not a scorecard. It is the statement of what one
experiment produced, the five mandatory baselines it is measured against, the walk-forward
schedule, and the caveats. Rule §63: no output of this script will ever say that a
strategy wins.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --symbol ETH-USD --timeframe 1m --bars 3000
    python scripts/run_backtest.py --json > experiment.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "tia" / "src"))

from tia.backtest import (  # noqa: E402
    BacktestConfig,
    BacktestEngine,
    SplitScheme,
    assert_no_leakage,
    build_plan,
    evaluate_experiment,
)
from tia.data.providers.csv_replay import CsvReplayProvider  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--bars", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--fixtures", default=str(ROOT / "data" / "fixtures"))
    parser.add_argument("--json", action="store_true", help="emit the full record as JSON")
    args = parser.parse_args()

    provider = CsvReplayProvider(args.fixtures)
    candles = asyncio.run(
        provider.get_candles(args.symbol, args.timeframe, limit=args.bars)
    )
    if len(candles) < 200:
        print(
            f"only {len(candles)} bars available for {args.symbol} {args.timeframe}; "
            "run scripts/generate_fixtures.py first",
            file=sys.stderr,
        )
        return 1

    engine = BacktestEngine(
        BacktestConfig(
            dataset=f"fixtures:{args.symbol}:{args.timeframe}",
            timeframe=args.timeframe,
            seed=args.seed,
        ),
        DEFAULT_UNIVERSE,
    )
    result = engine.run(candles)

    plan = build_plan(
        len(candles),
        train_bars=max(200, len(candles) // 4),
        test_bars=max(60, len(candles) // 10),
        scheme=SplitScheme.ANCHORED,
        purge_bars=20,
        embargo_bars=50,
    )
    assert_no_leakage(plan)

    report = evaluate_experiment(
        result,
        candles,
        at=datetime.now(UTC),
        costs=engine.config.execution,
        walk_forward=plan,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    counts = result.decisions
    print(report.evidence_statement())
    print()
    print("Decision breakdown:")
    print(f"  bars processed              {counts.bars_processed}")
    print(f"  signals generated           {counts.signals_generated}")
    print(f"  actionable signal rate      {counts.actionable_signal_rate:.1%}")
    print(f"  risk approval rate          {counts.approval_rate:.1%}")
    print(f"  approvals held (in position) {counts.approvals_suppressed_position_open}")
    print(f"  intents submitted           {counts.intents_submitted}")
    print(f"  fills                       {counts.fills}")
    print(f"  closed trades               {len(result.trades)}")
    if counts.risk_rejection_reasons:
        print("  binding risk gates:")
        for name, count in sorted(
            counts.risk_rejection_reasons.items(), key=lambda kv: -kv[1]
        ):
            print(f"    {name:<32} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
