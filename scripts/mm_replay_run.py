"""Replay the paper market maker over recorded segments, twice, with the versioned
latency profile — and print both journal hashes so determinism is a fact, not a claim.

    python scripts/mm_replay_run.py --ticks-dir /app/data/runtime/ticks --profile /app/data/runtime/mm/latency_profile.json --scenario baseline

Metrics are printed with the verdict the audit rules reach on that data, which will read
NO EDGE DETECTED until the sample and the out-of-sample rules allow otherwise. Nothing
here trades or tunes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tia.core.config import get_settings
from tia.mm.costs import MarketMakerCostConfig
from tia.mm.engine import MarketMakerConfig
from tia.mm.latency_model import LatencyProfile
from tia.mm.metrics import compute_metrics
from tia.mm.mm_replay import replay_market_maker
from tia.mm.recorder import TickRecorder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks-dir", default="data/ticks")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--profile", default=None, help="latency profile JSON; defaults to the configured path")
    parser.add_argument("--scenario", default=None, choices=["optimistic", "baseline", "conservative"])
    parser.add_argument("--segments", nargs="*", help="explicit segment files; defaults to every replayable one under the directory")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    symbol = args.symbol or settings.mm.symbol
    profile = LatencyProfile.load(args.profile or settings.mm.latency_profile_path)
    scenario = args.scenario or settings.mm.latency_scenario
    if args.segments:
        segments = [Path(s) for s in args.segments]
    else:
        folder = Path(args.ticks_dir) / symbol.replace("/", "-")
        listed = sorted(folder.glob("*.jsonl.gz"), key=TickRecorder.segment_sort_key)
        segments = []
        for path in listed:
            manifest_path = Path(str(path) + ".manifest.json")
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            if TickRecorder.replayable_from_manifest(manifest)[0]:
                segments.append(path)
    if not segments:
        print("no replayable segments found")
        return 1
    cfg = settings.mm
    config = MarketMakerConfig(
        symbol=symbol,
        starting_equity_usd=cfg.paper_capital,
        costs=MarketMakerCostConfig(maker_fee_bps=cfg.maker_fee_bps, maker_fee_status=cfg.maker_fee_status, maker_fee_verified_bps=cfg.maker_fee_verified_bps, maker_fee_adverse_bps=cfg.maker_fee_adverse_bps),
    )
    first = replay_market_maker(segments, config=config, profile=profile, scenario=scenario, keep_journal=True)
    second = replay_market_maker(segments, config=config, profile=profile, scenario=scenario)
    metrics = compute_metrics(
        journal=first.journal,
        ledger=first.snapshot["ledger"],
        execution=first.snapshot["execution"],
        markouts=first.snapshot["markouts"],
        limits=config.limits.as_dict(),
        latency_scenario=scenario,
        fee_scenario=config.fee_scenario,
    )
    report = {
        "segments": first.segments,
        "lines": first.lines,
        "events_by_kind": first.events_by_kind,
        "profile_id": first.profile_id,
        "profile_commit": profile.commit,
        "latency_scenario": scenario,
        "latency": first.snapshot["latency"],
        "config_id": first.config_id,
        "journal_hash_run_1": first.journal_hash,
        "journal_hash_run_2": second.journal_hash,
        "deterministic": first.journal_hash == second.journal_hash and first.snapshot["ledger"] == second.snapshot["ledger"],
        "ledger": first.snapshot["ledger"],
        "execution": first.snapshot["execution"],
        "counts": metrics["counts"],
        "pnl": {k: v for k, v in metrics["pnl"].items() if k != "net_per_fill_bootstrap_95"},
        "edge": metrics["edge"],
    }
    print(json.dumps(report, indent=1, default=str))
    return 0 if report["deterministic"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
