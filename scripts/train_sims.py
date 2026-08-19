#!/usr/bin/env python3
"""Seed the learning evidence with simulated trading runs.

The 24/7 paper-live session enforces the expected-value gate: it will not enter a
(regime, direction, confidence) bucket until that bucket holds enough closed trades to
prove an edge after costs. A fresh database therefore produces a session that refuses
everything — which is correct, and also means nothing ever gets learned. This script is
the designed way out of that loop: it runs seeded scenario simulations through the full
pipeline (features → regimes → strategies → risk → costs → paper fills) and persists
every closed round trip as evidence the estimator, the retrospective and the Mentor all
learn from.

Honesty rules, enforced elsewhere and restated here:

* Simulated outcomes are stored with ``source="sim"``. They TEACH — the estimator loads
  every source — but they can never satisfy the activation gate's track-record check,
  which counts only rows the real-time session wrote (``source="live"``). A track record
  padded with synthetic trades would describe a market that never existed.
* Nothing here touches the live path, the gate, or any risk limit. It writes evidence
  rows and stops.

Operational contract (this is what the dashboard's training panel reads):

* A **PID lock** at ``data/train.lock`` guarantees a single trainer. A stale lock (its
  process is gone) is reclaimed automatically, so a crash never wedges training forever.
* **Progress** is written to ``data/training_status.json`` after every run — state, run
  counter, trades so far, mean — so the web UI can show a live progress bar without
  touching the process.
* ``--seed-base 0`` (the default) derives the base from the clock, which makes every
  launch use fresh seeds. Re-running identical seeds would duplicate identical trades —
  copies, not evidence. Pass an explicit base only when reproducing a specific batch.

Usage (on the VPS, against the production database):

    docker compose -f docker-compose.prod.yml exec -d backend \\
        python scripts/train_sims.py --runs 100

Evidence loads into the 24/7 session when the backend restarts (the dashboard's
training panel has a button for that, or: ``docker compose ... up -d backend``).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import signal
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

LOCK_FILE = Path("data/train.lock")
STATUS_FILE = Path("data/training_status.json")

#: Scenarios worth learning from. The failure-injection ones are excluded on purpose:
#: they exist to test degradation, and "how trades close during a data outage drill" is
#: not evidence about markets.
TRAINING_SCENARIOS = ("trend_up", "trend_down", "range", "high_volatility", "mixed")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


def acquire_lock() -> bool:
    """Take the PID lock, reclaiming it if its owner died. False if a live trainer holds it."""
    if LOCK_FILE.exists():
        try:
            owner = int(LOCK_FILE.read_text().strip() or 0)
        except ValueError:
            owner = 0
        if owner and owner != os.getpid() and _pid_alive(owner):
            return False
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    with contextlib.suppress(Exception):
        if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == str(os.getpid()):
            LOCK_FILE.unlink()


def write_status(**fields: Any) -> None:
    """Best-effort progress file for the dashboard. Never allowed to break training."""
    with contextlib.suppress(Exception):
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        current: dict[str, Any] = {}
        if STATUS_FILE.exists():
            with contextlib.suppress(Exception):
                current = json.loads(STATUS_FILE.read_text())
        current.update(fields, updated_at=time.time())
        STATUS_FILE.write_text(json.dumps(current))


async def run_one(settings: Any, scenario: str, seed: int, capital: float) -> list[dict[str, Any]]:
    """Run one full simulation and return its closed-trade evidence rows."""
    from tia.runtime.engine import RuntimeConfig, RuntimeEngine

    rows: list[dict[str, Any]] = []

    def collect(kind: str, payload: dict[str, Any]) -> None:
        if kind == "edge_outcome":
            rows.append({**payload, "source": "sim"})

    engine = RuntimeEngine(
        settings,
        RuntimeConfig(
            scenario=scenario,
            seed=seed,
            initial_capital=capital,
            bar_interval_seconds=0.0,
            llm_enabled=False,  # the mock context layer adds nothing to evidence
        ),
        persist=collect,
    )
    await engine.start()
    for _ in range(200_000):
        await asyncio.sleep(0)
        if not engine.is_running:
            break
    await engine.stop()
    return rows


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=25, help="simulations to run")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument(
        "--seed-base", type=int, default=0,
        help="0 (default) derives fresh seeds from the clock; set explicitly to reproduce",
    )
    args = parser.parse_args()

    from tia.core.config import get_settings
    from tia.economics.expected_value import MIN_SAMPLES_FOR_EDGE, band_of
    from tia.persistence import Database, EdgeStateRepository

    if not acquire_lock():
        print("Another trainer is already running (live PID in data/train.lock); refusing.")
        return 1

    # SIGTERM (the dashboard's stop button, docker stop) unwinds like Ctrl-C so the
    # finally block below still records an honest final state and frees the lock.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    seed_base = args.seed_base or int(time.time())
    settings = get_settings()
    database = Database(settings.database_url)
    await database.ensure_schema()

    async with database.session() as session:
        before = await EdgeStateRepository(session).count()

    total_rows = 0
    net_sum = 0.0
    wins = 0
    completed = 0
    state = "failed"
    write_status(
        state="running", pid=os.getpid(), run=0, total=args.runs, scenario="",
        seed_base=seed_base, closed_trades=0, mean_bps=None, wins=0,
        started_at=time.time(), finished_at=None, error=None, buckets_ready=None,
    )
    print(f"Running {args.runs} simulations across {len(TRAINING_SCENARIOS)} scenarios…\n")
    try:
        for index in range(args.runs):
            scenario = TRAINING_SCENARIOS[index % len(TRAINING_SCENARIOS)]
            seed = seed_base + index
            rows = await run_one(settings, scenario, seed, args.capital)
            async with database.session() as session:
                repo = EdgeStateRepository(session)
                for row in rows:
                    await repo.append(row)
            completed = index + 1
            total_rows += len(rows)
            net_sum += sum(r["net_bps"] for r in rows)
            wins += sum(1 for r in rows if r["net_bps"] > 0)
            print(f"  [{completed:>4}/{args.runs}] {scenario:<16} seed {seed}: {len(rows)} closed trades")
            write_status(
                state="running", run=completed, scenario=scenario,
                closed_trades=total_rows,
                mean_bps=round(net_sum / total_rows, 2) if total_rows else None,
                wins=wins,
            )
        state = "finished"
    except KeyboardInterrupt:
        state = "stopped"
        print(f"\nStopped by operator after {completed} of {args.runs} runs — "
              "every completed run's evidence is already persisted.")
    except Exception as exc:  # the status file must tell the truth
        state = "failed"
        write_status(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        raise
    finally:
        # What the evidence now supports, bucket by bucket — the number that decides
        # whether the paper-live session will trade at all.
        buckets_ready = None
        with contextlib.suppress(Exception):
            async with database.session() as session:
                all_rows = await EdgeStateRepository(session).load_all()
                record = await EdgeStateRepository(session).track_record()
            buckets: dict[str, int] = defaultdict(int)
            for row in all_rows:
                low, high = band_of(row.confidence)
                buckets[f"{row.regime}|{row.direction}|{low:.2f}-{high:.2f}"] += 1
            ready = {k: v for k, v in buckets.items() if v >= MIN_SAMPLES_FOR_EDGE}
            buckets_ready = len(ready)

            if total_rows:
                print(f"\nThis session: {total_rows} closed trades persisted "
                      f"(mean {net_sum / total_rows:+.1f} bps, {wins}/{total_rows} wins)")
            print(f"Evidence store: {before} rows before, {len(all_rows)} now.")
            print(f"Buckets at or above the {MIN_SAMPLES_FOR_EDGE}-trade floor: {len(ready)}")
            for key, count in sorted(ready.items(), key=lambda kv: -kv[1])[:12]:
                print(f"  {count:>4}  {key}")
            print(
                f"\nGate integrity: the activation track record still counts ONLY "
                f"real-session trades ({record['closed_trades']} so far) — these "
                "simulations teach, they do not testify.\n\nNext: restart the backend so "
                "the 24/7 session reloads the evidence (the dashboard's training panel "
                "has a button, or: docker compose -f docker-compose.prod.yml up -d backend)"
            )
        write_status(state=state, finished_at=time.time(), buckets_ready=buckets_ready)
        with contextlib.suppress(Exception):
            await database.close()
        release_lock()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
