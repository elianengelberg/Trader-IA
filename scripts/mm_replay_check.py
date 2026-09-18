"""Replay recorded tick segments and report whether the book rebuilds from them.

Phase 2 evidence: reads each segment end to end, checks the checksum against the
manifest, rebuilds the order book with the same code the live service uses, and compares
the result with the checkpoints the recording carries. Nothing here quotes or trades.

    python scripts/mm_replay_check.py --ticks-dir /app/data/runtime/ticks-check
    python scripts/mm_replay_check.py --segment /path/to/20260918-17.jsonl.gz --allow-flagged
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tia.mm.replay import replay_directory, replay_segment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks-dir", default="data/ticks-check")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--segment", help="one segment file instead of the whole directory")
    parser.add_argument("--allow-flagged", action="store_true", help="replay segments the manifest flagged too")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = (
        [replay_segment(args.segment, allow_flagged=args.allow_flagged, symbol=args.symbol)]
        if args.segment
        else replay_directory(Path(args.ticks_dir), args.symbol, allow_flagged=args.allow_flagged)
    )
    if not results:
        print(f"no segments under {args.ticks_dir}/{args.symbol}")
        return 1
    if args.json:
        print(json.dumps([r.as_dict() for r in results], indent=1, default=str))
    else:
        for r in results:
            print(f"{Path(r.path).name}: {'OK' if r.ok else 'FAIL'}")
            print(
                f"  checksum={r.checksum} lines={r.lines} events={r.events} "
                f"snapshots={r.snapshots_applied} checkpoints adopted={r.checkpoints_adopted} "
                f"compared={r.checkpoints_compared} mismatches={r.checkpoint_mismatches}"
            )
            print(
                f"  gaps replay={r.gaps_in_replay} manifest={r.gaps_in_manifest} unregistered={r.unregistered_gaps} "
                f"sequence_breaks={r.sequence_breaks} trade_id_jumps={r.trade_id_jumps} crossed={r.crossed_books}"
            )
            print(
                f"  final state={r.final_state} valid={r.final_valid} id={r.final_update_id} "
                f"matches_manifest={r.final_matches_manifest} digest_matches={r.digest_matches_manifest} "
                f"best_bid={r.best_bid} best_ask={r.best_ask} spread_bps={r.spread_bps}"
            )
            for reason in r.reasons:
                print(f"  ! {reason}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
