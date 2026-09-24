"""Judge recorded segments by the causal bookTicker comparison, read-only.

Reads each sealed segment of one symbol, rebuilds the book the way the replay does and
pairs every applied depth batch with the venue's last bookTicker at or below its updateId
(see tia.mm.consistency). Lets a recording made before this comparison existed be judged
by it on the very same data. Writes nothing: no manifest is touched, no verify is run.

    python scripts/mm_book_ticker_check.py --ticks-dir /app/data/runtime/ticks-validation2-...
    python scripts/mm_book_ticker_check.py --segment /path/to/20260924-00.jsonl.gz --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tia.mm.consistency import causal_comparison_from_tape
from tia.mm.recorder import TickRecorder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticks-dir", default="data/ticks-check")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--segment", help="one segment file instead of the whole directory")
    parser.add_argument("--tick-size", type=float, default=0.01, help="price tick of the symbol")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.segment:
        paths = [Path(args.segment)]
    else:
        folder = Path(args.ticks_dir) / args.symbol.replace("/", "-")
        paths = sorted(folder.glob("*.jsonl.gz"), key=TickRecorder.segment_sort_key)
    if not paths:
        print(f"no segments under {args.ticks_dir}/{args.symbol}")
        return 1
    results = [causal_comparison_from_tape(p, tick_size=args.tick_size) for p in paths]
    if args.json:
        print(json.dumps(results, indent=1, default=str))
    else:
        for r in results:
            name = Path(r["path"]).name
            c = r["comparison"]
            if c is None:
                print(f"{name}: NOT COMPARED ({r['reason']})")
                continue
            print(f"{name}: consistent={c['consistent']} lines={r['lines']}")
            print(
                f"  tickers={c['tickers']} local_states={c['local_states']} resolved={c['resolved']} "
                f"consistent={c['resolved_consistent']} exact={c['resolved_exact']} "
                f"size_mismatch={c['resolved_price_match_size_mismatch']} unresolved_at_end={c['unresolved_at_end']} "
                f"unresolvable_no_ticker={c['unresolvable_no_ticker']}"
            )
            print(
                f"  true_inconsistencies={c['true_inconsistencies']} isolated={c['isolated_true_inconsistencies']} "
                f"max_consecutive={c['max_consecutive_true_inconsistencies']} persistent={c['persistent_true_inconsistency']} "
                f"impossible_state={c['impossible_state']} {c['impossible_state_reasons']}"
            )
            instant, lag = c["instant"], c["lag"]
            print(
                f"  instant: comparisons={instant['comparisons']} disagreements={instant['disagreements']} "
                f"timing={instant['timing_disagreements']} same_id={instant['same_id_disagreements']} "
                f"venue_ahead={instant['venue_ahead_samples']} local_ahead={instant['local_ahead_samples']}"
            )
            ahead, catch = lag["id_lag_updates_when_venue_ahead"], lag["catch_up_ms"]
            print(
                f"  lag: venue ahead by updates p50={ahead['p50']} p95={ahead['p95']} p99={ahead['p99']} max={ahead['max']} | "
                f"catch-up ms p50={catch['p50']} p95={catch['p95']} p99={catch['p99']} max={catch['max']} "
                f"(n={catch['count']}, awaiting at end={lag['tickers_awaiting_catch_up_at_end']})"
            )
            for example in c["examples"]["true_inconsistency"][:3]:
                print(f"    true_inconsistency: {example}")
            for example in c["examples"]["impossible_state"][:3]:
                print(f"    impossible_state: {example}")
    return 0 if all(r["comparison"] is not None and r["comparison"]["consistent"] is True for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
