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

Usage (on the VPS, against the production database):

    docker compose -f docker-compose.prod.yml exec backend \\
        python scripts/train_sims.py --runs 25

Then restart the backend (or stop/start the 24/7 session) so the running session reloads
the enlarged evidence:

    docker compose -f docker-compose.prod.yml restart backend
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from typing import Any

#: Scenarios worth learning from. The failure-injection ones are excluded on purpose:
#: they exist to test degradation, and "how trades close during a data outage drill" is
#: not evidence about markets.
TRAINING_SCENARIOS = ("trend_up", "trend_down", "range", "high_volatility", "mixed")


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
    parser.add_argument("--seed-base", type=int, default=20260819)
    args = parser.parse_args()

    from tia.core.config import get_settings
    from tia.economics.expected_value import MIN_SAMPLES_FOR_EDGE, band_of
    from tia.persistence import Database, EdgeStateRepository

    settings = get_settings()
    database = Database(settings.database_url)
    await database.ensure_schema()

    async with database.session() as session:
        before = await EdgeStateRepository(session).count()

    total_rows = 0
    net_sum = 0.0
    wins = 0
    print(f"Running {args.runs} simulations across {len(TRAINING_SCENARIOS)} scenarios…\n")
    for index in range(args.runs):
        scenario = TRAINING_SCENARIOS[index % len(TRAINING_SCENARIOS)]
        seed = args.seed_base + index
        rows = await run_one(settings, scenario, seed, args.capital)
        async with database.session() as session:
            repo = EdgeStateRepository(session)
            for row in rows:
                await repo.append(row)
        total_rows += len(rows)
        net_sum += sum(r["net_bps"] for r in rows)
        wins += sum(1 for r in rows if r["net_bps"] > 0)
        print(f"  [{index + 1:>3}/{args.runs}] {scenario:<16} seed {seed}: {len(rows)} closed trades")

    # What the evidence now supports, bucket by bucket — the number that decides whether
    # the paper-live session will trade at all.
    async with database.session() as session:
        all_rows = await EdgeStateRepository(session).load_all()
        record = await EdgeStateRepository(session).track_record()
    buckets: dict[str, int] = defaultdict(int)
    for row in all_rows:
        low, high = band_of(row.confidence)
        buckets[f"{row.regime}|{row.direction}|{low:.2f}-{high:.2f}"] += 1
    ready = {k: v for k, v in buckets.items() if v >= MIN_SAMPLES_FOR_EDGE}

    print(f"\nThis session: {total_rows} closed trades persisted "
          f"(mean {net_sum / total_rows:+.1f} bps, {wins}/{total_rows} wins)"
          if total_rows else "\nNo trades closed — scenarios too short or too strict.")
    print(f"Evidence store: {before} rows before, {len(all_rows)} now.")
    print(f"Buckets at or above the {MIN_SAMPLES_FOR_EDGE}-trade floor: {len(ready)}")
    for key, count in sorted(ready.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {count:>4}  {key}")
    print(
        f"\nGate integrity: the activation track record still counts ONLY real-session "
        f"trades ({record['closed_trades']} so far) — these simulations teach, they do "
        "not testify.\n\nNext: restart the backend so the 24/7 session reloads the "
        "evidence:\n  docker compose -f docker-compose.prod.yml restart backend"
    )

    await database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
