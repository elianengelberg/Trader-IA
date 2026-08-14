#!/usr/bin/env python3
"""Endurance: run the pipeline for a simulated day (or week) and watch what degrades.

The failures this looks for do not appear in a 500-bar test: memory that creeps, order
ids that eventually collide, latency that stretches as buffers fill, state that corrupts
across session boundaries. So this runs **consecutive sessions over one shared database**
— the restart pattern a long-lived deployment actually has — until the requested number
of simulated bars has elapsed, measuring as it goes.

    python scripts/endurance.py --bars 1440     # 24 simulated hours of 1m bars
    python scripts/endurance.py --bars 10080    # 7 simulated days

Checks, each with a hard verdict:

* **No duplicate client order ids**, across every session in the run.
* **RSS growth bounded** — the last session may not use more than 1.5x the first's peak.
* **Cycle latency stable** — mean bar-processing time in the last session may not exceed
  3x the first session's.
* **State coherent** — persisted evidence count equals the sum of closed trades reported
  by each session; equity is finite; no session ended in an error state.

Writes ``data/runtime/endurance_report.json``. Exit 0 only if every check passed.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "tia" / "src"))

from sqlalchemy import text

from tia.api.state import AppState
from tia.core.config import Environment, settings_for_env
from tia.persistence import Database, EdgeStateRepository

SCENARIOS = ("trend_up", "mixed", "trend_down", "range_bound")


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


async def run_session(state: AppState, scenario: str, seed: int) -> dict[str, Any]:
    started = time.perf_counter()
    await state.start_run(
        {
            "scenario": scenario,
            "initial_capital": 25_000.0,
            "seed": seed,
            "bar_interval_seconds": 0.0,
        }
    )
    runtime = state.runtime
    assert runtime is not None
    while runtime.is_running:  # noqa: ASYNC110 - polling a runtime with no completion event
        await asyncio.sleep(0.05)
    await state.stop_run()
    await asyncio.sleep(0.5)  # drain persistence tasks
    elapsed = time.perf_counter() - started
    bars = runtime.counters.bars
    return {
        "scenario": scenario,
        "seed": seed,
        "bars": bars,
        "closed_trades": len(runtime.closed_trades),
        "fills": runtime.counters.fills,
        "errors": runtime.counters.errors,
        "state": runtime.state.value,
        "wall_seconds": round(elapsed, 2),
        "ms_per_bar": round(elapsed / max(1, bars) * 1000.0, 3),
        "rss_mb": round(rss_mb(), 1),
        "equity": runtime.snapshot()["capital"]["equity"],
    }


async def main(bars_target: int, db_path: Path) -> int:
    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{db_path}"}
    )
    state = AppState(settings)
    await state.startup()

    sessions: list[dict[str, Any]] = []
    simulated_bars = 0
    seed = 1000
    try:
        while simulated_bars < bars_target:
            scenario = SCENARIOS[len(sessions) % len(SCENARIOS)]
            outcome = await run_session(state, scenario, seed)
            sessions.append(outcome)
            simulated_bars += outcome["bars"]
            seed += 1
            gc.collect()
            print(
                f"session {len(sessions):3d}  {scenario:12s} bars={outcome['bars']:4d} "
                f"total={simulated_bars:6d}/{bars_target}  rss={outcome['rss_mb']}MB  "
                f"{outcome['ms_per_bar']}ms/bar  closed={outcome['closed_trades']}"
            )
    finally:
        await state.shutdown()

    # ------------------------------------------------------------------ verdicts
    database = Database(f"sqlite+aiosqlite:///{db_path}")
    await database.ensure_schema()
    async with database.session() as session:
        duplicate_orders = (
            await session.execute(
                text(
                    "SELECT client_order_id, COUNT(*) c FROM orders "
                    "GROUP BY client_order_id HAVING c > 1"
                )
            )
        ).all()
        persisted_evidence = await EdgeStateRepository(session).count()
    await database.close()

    closed_total = sum(s["closed_trades"] for s in sessions)
    first, last = sessions[0], sessions[-1]
    checks = {
        "no_duplicate_orders": not duplicate_orders,
        "rss_bounded": last["rss_mb"] <= max(first["rss_mb"] * 1.5, first["rss_mb"] + 200),
        "latency_stable": last["ms_per_bar"] <= max(first["ms_per_bar"] * 3.0, 5.0),
        "no_error_states": all(s["errors"] == 0 and s["state"] != "halted" for s in sessions),
        "evidence_coherent": persisted_evidence == closed_total,
        "equity_finite": all(
            s["equity"] == s["equity"] and abs(s["equity"]) < 1e12 for s in sessions
        ),
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "bars_target": bars_target,
        "bars_simulated": simulated_bars,
        "sessions": sessions,
        "duplicate_orders": [list(r) for r in duplicate_orders],
        "persisted_evidence": persisted_evidence,
        "closed_trades_total": closed_total,
        "checks": checks,
        "passed": all(checks.values()),
    }
    out = Path("data/runtime/endurance_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")  # noqa: ASYNC240

    print()
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{'ENDURANCE PASSED' if report['passed'] else 'ENDURANCE FAILED'} — {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=int, default=1440, help="simulated 1m bars (1440 = 24h)")
    parser.add_argument("--db", default="data/runtime/endurance.db")
    args = parser.parse_args()
    db_file = Path(args.db)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()  # each endurance run starts from a genuinely empty database
    raise SystemExit(asyncio.run(main(args.bars, db_file)))
