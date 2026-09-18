"""Run the market-making market data against the real venue and report what happened.

Phase 2 evidence, from a machine with egress (the VPS). Connects the depth@100ms, trade
and bookTicker streams for one symbol, keeps the local book in sync with REST snapshots,
records ticks to disk, and after ``--minutes`` prints: updates processed, gaps, rebuilds,
events dropped, latency percentiles, CPU/RAM/disk, the files written and their sizes, and
a reconstruction example (the book's top levels against the venue's own bookTicker).

Nothing here quotes, trades or touches an execution provider.

    python scripts/mm_market_data_check.py --minutes 5 --symbol BTC-USD --ticks-dir /tmp/ticks
"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
import time
from pathlib import Path

from tia.data.providers.binance_public import BinancePublicProvider
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.recorder import TickRecorder
from tia.mm.streams import MarketDataStream


def _rss_mb() -> float:
    try:
        with Path("/proc/self/status").open() as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--minutes", type=float, default=5.0)
    parser.add_argument("--ticks-dir", default="data/ticks-check")
    parser.add_argument("--depth-speed", default="100ms")
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument("--json", action="store_true", help="print the final report as JSON")
    args = parser.parse_args()

    rest = BinancePublicProvider()

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        book = await rest.depth_snapshot(args.symbol, limit=1000)
        return snapshot_from_levels(
            book.last_update_id or 0,
            [(lvl.price, lvl.size) for lvl in book.bids],
            [(lvl.price, lvl.size) for lvl in book.asks],
        )

    recorder = None if args.no_record else TickRecorder(Path(args.ticks_dir), args.symbol)
    service = MarketDataService(
        args.symbol,
        stream=MarketDataStream(args.symbol, depth_speed=args.depth_speed),
        fetch_snapshot=fetch_snapshot,
        recorder=recorder,
    )
    cpu_start = time.process_time()
    wall_start = time.time()
    service.start()
    print(f"connecting to {service.stream.url}")
    deadline = wall_start + args.minutes * 60.0
    checks: list[dict] = []  # type: ignore[type-arg]
    mismatches = 0
    samples = 0
    try:
        while time.time() < deadline:
            await asyncio.sleep(10.0)
            snap = service.snapshot(levels=3)
            book, ticker = snap["book"], service.stream.last_book_ticker
            # Reconstruction check: our best bid/ask against the venue's own bookTicker.
            agree = None
            if book["valid"] and ticker is not None and book["best_bid"] and book["best_ask"]:
                samples += 1
                agree = (
                    abs(book["best_bid"][0] - ticker.bid) <= 0.01 * max(1.0, ticker.bid / 1000.0)
                    and abs(book["best_ask"][0] - ticker.ask) <= 0.01 * max(1.0, ticker.ask / 1000.0)
                )
                if not agree:
                    mismatches += 1
            checks.append({"t": round(time.time() - wall_start), "usable": snap["usable"], "agree": agree})
            print(
                f"[{time.time() - wall_start:6.0f}s] usable={snap['usable']} state={book['state']} "
                f"id={book['update_id']} depth={snap['stream']['depth_events']} trades={snap['stream']['trade_events']} "
                f"gaps={book['metrics']['gaps']} rebuilds={book['metrics']['rebuilds']} "
                f"lat_p50={snap['stream']['latency_depth_ms']['p50_ms']} p99={snap['stream']['latency_depth_ms']['p99_ms']} "
                f"bid={book['best_bid']} ask={book['best_ask']} spread_bps={book['spread_bps']} agree={agree}"
            )
    finally:
        cpu = time.process_time() - cpu_start
        wall = time.time() - wall_start
        final = service.snapshot(levels=5)
        await service.close()
        await rest.close()

    files = recorder.segments() if recorder is not None else []
    report = {
        "symbol": args.symbol,
        "duration_s": round(wall, 1),
        "usable_at_end": final["usable"],
        "book": {k: final["book"][k] for k in ("state", "update_id", "levels_bid", "levels_ask", "spread_bps", "best_bid", "best_ask", "microprice_1", "imbalance", "bids", "asks")},
        "book_metrics": final["book"]["metrics"],
        "stream": {k: final["stream"][k] for k in ("connected", "reconnects", "messages", "depth_events", "trade_events", "book_ticker_events", "parse_errors", "dropped_events", "last_error")},
        "latency_depth_ms": final["stream"]["latency_depth_ms"],
        "latency_trade_ms": final["stream"]["latency_trade_ms"],
        "venue_trade_to_event_ms": final["stream"]["venue_trade_to_event_ms"],
        "sync": final["sync"],
        "reconstruction_check": {"samples": samples, "mismatches": mismatches, "checks": checks[-6:]},
        "resources": {"cpu_seconds": round(cpu, 2), "cpu_pct_of_one_core": round(cpu / wall * 100.0, 1) if wall else None, "rss_mb": round(_rss_mb(), 1)},
        "recorder": final["recorder"],
        "files": [{"path": f["path"], "bytes": f["bytes"], "replayable": f["replayable"]} for f in files],
        "invented_data": False,
        "execution": "none — no execution provider was constructed",
    }
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print("\n=== REPORT ===")
        print(json.dumps(report, indent=1, default=str))
    return 0 if final["usable"] or samples > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
