"""Run the market-making market data against the real venue and report what happened.

Phase 2 evidence, from a machine with egress (the VPS). Connects the depth@100ms, trade
and bookTicker streams for one symbol, keeps the local book in sync with REST snapshots,
records ticks to disk, and after ``--minutes`` prints a report in the sections the Phase 2
acceptance asks for: Binance/WebSocket, order book, latency, recorder, host resources,
the comparison against the venue's own bookTicker, the optional stale-data test, the
replay of the segments just written, and the acceptance criteria as booleans.

Nothing here quotes, trades or touches an execution provider. Every number is a count of
what happened; a metric that could not be measured is reported as "NOT MEASURED".

    python scripts/mm_market_data_check.py --minutes 5 --ticks-dir /app/data/runtime/ticks-check
    python scripts/mm_market_data_check.py --minutes 2 --inject-stall 4 --ticks-dir /tmp/ticks-stall
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import shutil
import time
from pathlib import Path
from typing import Any

from tia.data.providers.binance_public import BinancePublicProvider
from tia.mm.consistency import TopOfBookSample, summarise
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.recorder import RecorderBusyError, TickRecorder
from tia.mm.replay import replay_segment
from tia.mm.streams import MarketDataStream

NOT_MEASURED = "NOT MEASURED"


def _rss_mb() -> float:
    try:
        with Path("/proc/self/status").open() as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _meminfo_mb() -> dict[str, Any]:
    out: dict[str, Any] = {"total_mb": NOT_MEASURED, "available_mb": NOT_MEASURED}
    try:
        with Path("/proc/meminfo").open() as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    out["total_mb"] = round(int(line.split()[1]) / 1024.0, 1)
                elif line.startswith("MemAvailable:"):
                    out["available_mb"] = round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        pass
    return out


def _loadavg() -> Any:
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except OSError:
        return NOT_MEASURED


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def _disk(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        return {"total_gb": round(usage.total / 1e9, 2), "free_gb": round(usage.free / 1e9, 2)}
    except OSError:
        return {"total_gb": NOT_MEASURED, "free_gb": NOT_MEASURED}


def _compare(book: dict[str, Any], ticker: Any, tick_size: float, t: float) -> TopOfBookSample | None:
    """One sample of the local top of book against the venue's bookTicker (see
    tia.mm.consistency for what is timing and what is an inconsistency)."""
    if not (book["valid"] and ticker is not None and book["best_bid"] and book["best_ask"]):
        return None
    return TopOfBookSample(
        t=round(t),
        local_bid=book["best_bid"][0],
        local_ask=book["best_ask"][0],
        local_update_id=book["update_id"],
        venue_bid=ticker.bid,
        venue_ask=ticker.ask,
        venue_update_id=ticker.update_id or 0,
        tick_size=tick_size,
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--minutes", type=float, default=5.0)
    parser.add_argument("--ticks-dir", default="data/ticks-check")
    parser.add_argument("--depth-speed", default="100ms")
    parser.add_argument("--snapshot-limit", type=int, default=1000)
    parser.add_argument("--tick-size", type=float, default=0.01, help="price tick of the symbol, for the bookTicker comparison")
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--inject-stall", type=float, default=0.0, help="seconds of events to ignore on purpose at 60%% of the run, to prove stale detection")
    parser.add_argument("--no-record", action="store_true")
    parser.add_argument("--json", action="store_true", help="print only the final report as JSON")
    args = parser.parse_args()

    rest = BinancePublicProvider()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        book = await rest.depth_snapshot(args.symbol, limit=args.snapshot_limit)
        return snapshot_from_levels(
            book.last_update_id or 0,
            [(lvl.price, lvl.size) for lvl in book.bids],
            [(lvl.price, lvl.size) for lvl in book.asks],
        )

    ticks_dir = Path(args.ticks_dir)
    try:
        recorder = None if args.no_record else TickRecorder(ticks_dir, args.symbol)
    except RecorderBusyError as exc:
        print(f"REFUSED: {exc}. Use another --ticks-dir or stop the other writer.")
        return 2
    service = MarketDataService(
        args.symbol,
        stream=MarketDataStream(args.symbol, depth_speed=args.depth_speed),
        fetch_snapshot=fetch_snapshot,
        recorder=recorder,
    )
    ticks_bytes_start = _dir_bytes(ticks_dir)
    cpu_start = time.process_time()
    wall_start = time.time()
    service.start()
    if not args.json:
        print(f"{started_utc} connecting to {service.stream.url}")
    deadline = wall_start + args.minutes * 60.0
    stall_at = wall_start + args.minutes * 60.0 * 0.6 if args.inject_stall > 0 else None
    samples: list[dict[str, Any]] = []
    comparisons: list[TopOfBookSample] = []
    stale_test: dict[str, Any] = {"requested_s": args.inject_stall, "exercised": False}
    synced_seen = False
    rss_max = 0.0

    def elapsed() -> float:
        return time.time() - wall_start

    async def run_stall() -> None:
        nonlocal stale_test
        service.hold(args.inject_stall, reason="mm_market_data_check --inject-stall")
        timeline: list[dict[str, Any]] = []
        t0 = elapsed()
        stale_test = {**stale_test, "exercised": True, "injected_at_s": round(t0, 1)}
        # Sample fast enough to see the freshness limit trip and the resync that follows.
        for _ in range(int((args.inject_stall + 8.0) / 0.5)):
            await asyncio.sleep(0.5)
            snap = service.snapshot(levels=1)
            timeline.append(
                {
                    "t": round(elapsed() - t0, 1),
                    "usable": snap["usable"],
                    "reason": snap["not_usable_reason"],
                    "state": snap["book"]["state"],
                    "gaps": snap["book"]["metrics"]["gaps"],
                    "resyncs": snap["sync"]["resyncs"],
                    "held_events": snap["integrity"]["held_events"],
                }
            )
        unusable = [row for row in timeline if not row["usable"]]
        stale_rows = [row for row in unusable if "old" in row["reason"]]
        gap_rows = [row for row in timeline if row["gaps"] > timeline[0]["gaps"]]
        usable_again = [row for row in timeline if row["usable"] and gap_rows and row["t"] > gap_rows[0]["t"]]
        stale_test.update(
            {
                "unusable_detected": bool(unusable),
                "stale_reason_seen": stale_rows[0]["reason"] if stale_rows else None,
                "stale_detected_after_s": stale_rows[0]["t"] if stale_rows else None,
                "gap_detected_after_s": gap_rows[0]["t"] if gap_rows else None,
                "usable_again_after_s": usable_again[0]["t"] if usable_again else None,
                "events_ignored": timeline[-1]["held_events"] if timeline else 0,
                "timeline": timeline,
            }
        )

    try:
        while time.time() < deadline:
            await asyncio.sleep(args.sample_seconds)
            if stall_at is not None and time.time() >= stall_at:
                stall_at = None
                await run_stall()
            snap = service.snapshot(levels=3)
            book, ticker = snap["book"], service.stream.last_book_ticker
            synced_seen = synced_seen or book["valid"]
            rss = _rss_mb()
            rss_max = max(rss_max, rss)
            comparison = _compare(book, ticker, args.tick_size, elapsed())
            if comparison is not None:
                comparisons.append(comparison)
            samples.append(
                {
                    "t": round(elapsed()),
                    "usable": snap["usable"],
                    "state": book["state"],
                    "update_id": book["update_id"],
                    "rss_mb": round(rss, 1),
                    "ticks_dir_mb": round(_dir_bytes(ticks_dir) / 1e6, 3),
                    "depth_events": snap["stream"]["depth_events"],
                }
            )
            if not args.json:
                lat = snap["stream"]["latency_depth_ms"]
                if comparison is None:
                    vs_venue = "n/a"
                elif comparison.exact:
                    vs_venue = "exact"
                else:
                    vs_venue = f"{comparison.bid_diff_ticks}/{comparison.ask_diff_ticks} ticks"
                print(
                    f"[{elapsed():6.0f}s] usable={snap['usable']} state={book['state']} id={book['update_id']} "
                    f"depth={snap['stream']['depth_events']} trades={snap['stream']['trade_events']} "
                    f"gaps={book['metrics']['gaps']} rebuilds={book['metrics']['rebuilds']} "
                    f"lat_p50={lat['p50_ms']} p99={lat['p99_ms']} bid={book['best_bid']} ask={book['best_ask']} "
                    f"spread_bps={book['spread_bps']} vs_venue={vs_venue} "
                    f"rss={rss:.0f}MB ticks={samples[-1]['ticks_dir_mb']:.2f}MB"
                )
    finally:
        cpu = time.process_time() - cpu_start
        wall = time.time() - wall_start
        final = service.snapshot(levels=10)
        await service.close()  # writes the closing checkpoint and closes the segment
        await rest.close()

    ticks_bytes_end = _dir_bytes(ticks_dir)
    segments = recorder.segments() if recorder is not None else []
    verifications = [TickRecorder.verify(s["path"]) for s in segments]
    replays = [replay_segment(s["path"], allow_flagged=True, symbol=args.symbol).as_dict() for s in segments]
    for row in replays:
        row.pop("events", None)
    stream, book, metrics = final["stream"], final["book"], final["book"]["metrics"]
    disconnects = stream["disconnects"]
    stalls = 1 if stale_test.get("exercised") else 0
    unexplained_gaps = max(0, metrics["gaps"] - disconnects - stalls)
    silent_loss = (final["recorder"] or {}).get("events_dropped", 0) + stream["dropped_events"]
    comparison_summary = summarise(comparisons)
    replay_ok = [r for r in replays if r["ok"]]
    clean = [s for s in segments if s["replayable"]]

    report: dict[str, Any] = {
        "run": {
            "symbol": args.symbol,
            "started_utc": started_utc,
            "duration_s": round(wall, 1),
            "config": {
                "depth_speed": args.depth_speed,
                "snapshot_limit": args.snapshot_limit,
                "max_data_age_s": final["max_data_age_s"],
                "tick_size": args.tick_size,
                "record": recorder is not None,
                "ticks_dir": str(ticks_dir),
                "inject_stall_s": args.inject_stall,
                "stream_url": stream["url"],
            },
        },
        "binance_websocket": {
            "connected_at_end": stream["connected"],
            "connections": stream["connections"],
            "disconnects": disconnects,
            "connect_failures": stream["connect_failures"],
            "reconnect_attempts": stream["reconnects"],
            "current_connection_s": stream["current_connection_s"],
            "longest_connection_s": stream["longest_connection_s"],
            "streams": stream["url"].split("streams=")[-1].split("/"),
            "messages": stream["messages"],
            "depth_updates_received": stream["depth_events"],
            "trades_received": stream["trade_events"],
            "book_ticker_received": stream["book_ticker_events"],
            "rest_snapshots_fetched": final["sync"]["snapshots_fetched"],
            "rest_snapshot_failures": final["sync"]["resync_failures"],
            "parse_errors": stream["parse_errors"],
            "events_dropped_by_subscribers": stream["dropped_events"],
            "last_error": stream["last_error"],
        },
        "order_book": {
            "final_state": book["state"],
            "valid_at_end": book["valid"],
            "usable_at_end": final["usable"],
            "not_usable_reason": final["not_usable_reason"],
            "last_snapshot_update_id": final["sync"]["last_snapshot_update_id"],
            "first_update_applied": book["first_applied_update_id"],
            "last_update_applied": book["update_id"],
            "updates_applied": metrics["updates_applied"],
            "updates_ignored_old": metrics["updates_ignored_old"],
            "updates_buffered": metrics["updates_buffered"],
            "gaps_detected": metrics["gaps"],
            "gaps_unexplained": unexplained_gaps,
            "invalidations": metrics["invalidations"],
            "rebuilds": metrics["rebuilds"],
            "snapshots_rejected_stale": metrics["snapshots_rejected_stale"],
            "crossed_books": metrics["crossed_books"],
            "stale_episodes": final["integrity"]["stale_episodes"],
            "max_silence_ms": final["integrity"]["max_silence_ms"],
            "levels_bid": book["levels_bid"],
            "levels_ask": book["levels_ask"],
            "best_bid": book["best_bid"],
            "best_ask": book["best_ask"],
            "spread": book["spread"],
            "spread_bps": book["spread_bps"],
            "microprice_1": book["microprice_1"],
            "imbalance": book["imbalance"],
            "top10_bids": book["bids"],
            "top10_asks": book["asks"],
        },
        "latency": {
            "exchange_to_local_depth_ms": stream["latency_depth_ms"],
            "exchange_to_local_trade_ms": stream["latency_trade_ms"],
            "venue_internal_trade_to_event_ms": stream["venue_trade_to_event_ms"],
            "local_processing_us": final["processing_us"],
            "book_ticker": "no exchange timestamp on Spot bookTicker: not measured, not invented",
            "note": "exchange->local = local receive clock minus event time E; includes clock offset between host and venue",
        },
        "recorder": (
            {
                **{k: final["recorder"][k] for k in ("events_written", "events_dropped", "bytes_written", "flushes", "segments", "segments_replayable", "total_bytes_on_disk", "last_error")},
                "segments_detail": [
                    {
                        "file": Path(s["path"]).name,
                        "bytes_compressed": s["bytes"],
                        "bytes_raw": s["manifest"].get("raw_bytes"),
                        "compression_ratio": round(s["manifest"]["raw_bytes"] / s["bytes"], 2) if s["manifest"].get("raw_bytes") and s["bytes"] else None,
                        "lines": s["manifest"].get("lines"),
                        "duration_s": round((s["manifest"]["last_received_at_ms"] - s["manifest"]["first_received_at_ms"]) / 1000.0, 1) if s["manifest"].get("first_received_at_ms") and s["manifest"].get("last_received_at_ms") else None,
                        "depth_events": s["manifest"].get("depth_events"),
                        "trade_events": s["manifest"].get("trade_events"),
                        "book_ticker_events": s["manifest"].get("book_events"),
                        "snapshots": s["manifest"].get("snapshot_events"),
                        "checkpoints": s["manifest"].get("checkpoint_events"),
                        "sha256": s["manifest"].get("sha256"),
                        "dropped_events": s["manifest"].get("dropped_events"),
                        "disconnects": s["manifest"].get("disconnects"),
                        "book_gaps": s["manifest"].get("book_gaps"),
                        "faults_injected": s["manifest"].get("faults_injected"),
                        "corrupt": s["manifest"].get("corrupt"),
                        "sealed": s["sealed"],
                        "part": s["manifest"].get("part", 0),
                        "first_state": s["manifest"].get("first_state_kind"),
                        "closing_checkpoint": s["manifest"].get("closing_checkpoint"),
                        "replayable": s["replayable"],
                        "not_replayable": s["not_replayable"],
                        "verify": v,
                    }
                    for s, v in zip(segments, verifications, strict=True)
                ],
            }
            if recorder is not None
            else NOT_MEASURED
        ),
        "resources": {
            "cpu_seconds_this_process": round(cpu, 2),
            "cpu_pct_of_one_core": round(cpu / wall * 100.0, 1) if wall else NOT_MEASURED,
            "rss_mb_end": round(_rss_mb(), 1),
            "rss_mb_max_sampled": round(rss_max, 1),
            "host_memory": _meminfo_mb(),
            "host_loadavg_1_5_15": _loadavg(),
            "disk": _disk(ticks_dir),
            "ticks_dir_bytes_start": ticks_bytes_start,
            "ticks_dir_bytes_end": ticks_bytes_end,
            "ticks_dir_growth_mb_per_hour": round((ticks_bytes_end - ticks_bytes_start) / 1e6 / (wall / 3600.0), 2) if wall else NOT_MEASURED,
            "samples": samples,
        },
        "book_ticker_comparison": comparison_summary,
        "stale_test": stale_test,
        "replay": replays,
        "criteria": {
            "1_binance_reachable": stream["connections"] >= 1,
            "2_snapshot_received": final["sync"]["snapshots_fetched"] >= 1,
            "3_depth_updates_received": stream["depth_events"] > 0,
            "4_book_reached_synced": synced_seen,
            "5_no_unexplained_gaps": unexplained_gaps == 0,
            "6_no_silent_loss": silent_loss == 0,
            "7_segments_intact": bool(verifications) and all(v["ok"] for v in verifications),
            "8_replay_ok": bool(replay_ok) if replays else "no segment written",
            "8b_clean_segment_replayed": any(r["ok"] and r["manifest_replayable"] for r in replays) if clean else "no clean segment (see flags)",
            "9_stale_detected": stale_test.get("stale_detected_after_s") is not None if stale_test.get("exercised") else "not exercised (--inject-stall 0)",
            "10_real_execution_enabled": False,
            "11_invented_data": False,
            "12_book_ticker_consistent": not comparison_summary["persistent_inconsistency"] and not comparison_summary["impossible_state"],
        },
        "execution": "none — no execution provider was constructed",
    }
    print("\n=== PHASE 2 LIVE REPORT ===" if not args.json else "")
    print(json.dumps(report, indent=1, default=str))
    hard = ("1_binance_reachable", "2_snapshot_received", "3_depth_updates_received", "4_book_reached_synced", "5_no_unexplained_gaps", "6_no_silent_loss")
    return 0 if all(report["criteria"][k] is True for k in hard) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
