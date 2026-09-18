"""Audit the paper market maker's journal: read-only, from the maker's own tables.

Answers the validation questions without interpreting P&L: does every fill name real
venue prints; did every fill happen after its order could have arrived (latency never
zero); was the queue ever assumed empty at arrival on a populated level; how many
UNRESOLVED cases were there and are they distributed like the confirmed fills or
concentrated in the adverse ones (shadow markouts against confirmed markouts); what
did the controller and the safety gate refuse and why. Prints a report and, with
--json, the raw figures.

    docker compose -f docker-compose.prod.yml exec backend python scripts/mm_paper_audit.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from statistics import mean, median
from typing import Any

from tia.core.config import get_settings
from tia.persistence import Database, MarketMakerRepository

NOT_MEASURED = "NOT MEASURED"


def _bucket_table(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in rows:
        counts[str((r.get("regimes") or {}).get(key, r.get(key, "unknown")))] += 1
    return dict(counts)


def _share(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {k: round(v / total, 3) for k, v in counts.items()} if total else {}


def _markout_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [r["markout_bps"].get("1000") for r in rows if isinstance(r.get("markout_bps"), dict) and r["markout_bps"].get("1000") is not None]
    if not values:
        return {"count": 0, "mean_1s_bps": None, "median_1s_bps": None, "adverse_share": None}
    return {
        "count": len(values),
        "mean_1s_bps": round(mean(values), 4),
        "median_1s_bps": round(median(values), 4),
        "adverse_share": round(sum(1 for v in values if v < 0) / len(values), 3),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None, help="defaults to mm-paper-<symbol> from the settings")
    parser.add_argument("--limit", type=int, default=200_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    run_id = args.run_id or f"mm-paper-{settings.mm.symbol}"
    database = Database(settings.database_url)
    try:
        async with database.session() as session:
            repo = MarketMakerRepository(session)
            journal = await repo.journal(run_id, limit=args.limit)
            fills_rows = await repo.fills(run_id, limit=args.limit)
            ledger_row = await repo.load_ledger(run_id)
            journal_count = await repo.journal_count(run_id)
    finally:
        await database.close()

    decisions = [r for r in journal if r.get("kind") == "decision"]
    fills = [r for r in journal if r.get("kind") == "fill"]
    unresolved = [r for r in journal if r.get("kind") == "unresolved"]
    blocks = [r for r in journal if r.get("kind") == "block"]
    markouts = [r for r in journal if r.get("kind") == "markout"]
    confirmed_markouts = [r for r in markouts if not r.get("shadow")]
    shadow_markouts = [r for r in markouts if r.get("shadow")]

    ledger_state = dict(ledger_row.state) if ledger_row is not None else {}
    scenario = ledger_row.latency_scenario if ledger_row is not None else NOT_MEASURED

    # Decision time per order, for the latency check.
    decision_t: dict[str, int] = {}
    for r in decisions:
        for oid in r.get("orders", []) or []:
            decision_t[oid] = int(r["t"])
    # Every fill must come after its decision by at least the scenario's order latency;
    # the smallest gap observed is reported and flagged if it breaks the 5 ms floor.
    gaps = [int(f["t"]) - decision_t[f["order_id"]] for f in fills if f.get("order_id") in decision_t]
    fill_audit = {
        "fills": len(fills),
        "fills_with_venue_trade_ids": sum(1 for f in fills if f.get("venue_trade_ids")),
        "fills_without_venue_trade_ids": [f.get("fill_id") for f in fills if not f.get("venue_trade_ids")],
        "fills_with_decision_known": len(gaps),
        "min_decision_to_fill_ms": min(gaps) if gaps else NOT_MEASURED,
        "median_decision_to_fill_ms": median(gaps) if gaps else NOT_MEASURED,
        "fills_before_their_decision": sum(1 for g in gaps if g < 0),
        "queue_ahead_at_arrival": {
            "zero": sum(1 for f in fills if float(f.get("queue_ahead_at_arrival", 0) or 0) <= 0),
            "positive": sum(1 for f in fills if float(f.get("queue_ahead_at_arrival", 0) or 0) > 0),
            "median": median([float(f.get("queue_ahead_at_arrival", 0) or 0) for f in fills]) if fills else NOT_MEASURED,
        },
        "resolutions": dict(Counter(str(f.get("resolution", "confirmed")) for f in fills)),
        "fill_prices_equal_order_prices": "structural: a fill is booked at the resting order's price; see tia/mm/sim.py",
        "note": "a fill exists only because a real print reached the resting simulated order past its conservative queue bound; no candle, no bookTicker, no touch rule",
    }

    unresolved_audit = {
        "events": len(unresolved),
        "quantity_btc": round(sum(float(r.get("quantity", 0) or 0) for r in unresolved), 8),
        "confirmed_fill_quantity_btc": round(sum(float(f.get("quantity", 0) or 0) for f in fills), 8),
        "share_of_candidates": round(len(unresolved) / (len(unresolved) + len(fills)), 3) if (unresolved or fills) else None,
        "by_side": {"unresolved": _share(_bucket_table(unresolved, "side")), "confirmed": _share(_bucket_table(fills, "side"))},
        "by_spread_regime": {"unresolved": _share(_bucket_table(unresolved, "spread_regime")), "confirmed": _share(_bucket_table(fills, "spread_regime"))},
        "by_vol_regime": {"unresolved": _share(_bucket_table(unresolved, "vol_regime")), "confirmed": _share(_bucket_table(fills, "vol_regime"))},
        "by_flow_regime": {"unresolved": _share(_bucket_table(unresolved, "flow_regime")), "confirmed": _share(_bucket_table(fills, "flow_regime"))},
        "shadow_markouts_1s": _markout_summary(shadow_markouts),
        "confirmed_markouts_1s": _markout_summary(confirmed_markouts),
        "reading": (
            "If the shadow (unresolved) markouts are markedly more adverse than the confirmed ones, "
            "the simulator is dropping the worst cases and the P&L is flattered: keep NO EDGE DETECTED. "
            "If they look alike, UNRESOLVED is coverage, not selection."
        ),
    }

    no_quote: Counter[str] = Counter()
    for r in decisions:
        if r.get("decision") == "no_quote":
            no_quote[str(r.get("reason", "")).split(":")[0]] += 1
    cancel_reasons: Counter[str] = Counter()
    for r in journal:
        if r.get("kind") == "block":
            cancel_reasons[f"{r.get('layer')}: {str(r.get('reason', ''))[:60]}"] += 1
        elif r.get("kind") == "decision" and r.get("decision") == "no_quote" and r.get("cancelled"):
            cancel_reasons[f"no_quote: {str(r.get('reason', '')).split(':')[0]}"] += 1
    gate_events = Counter(str(r.get("reason", ""))[:80] for r in blocks if r.get("layer") == "gate")
    controller_denials = Counter(str((r.get("allowance") or {}).get("reason", ""))[:80] for r in decisions if not (r.get("allowance") or {}).get("allowed", True))

    quoted = [r for r in decisions if r.get("decision") == "quote"]
    half_spreads = [float(r["half_spread_bps"]) for r in quoted if r.get("half_spread_bps") is not None]
    inventories = [float(r.get("inventory_btc", 0) or 0) for r in decisions]
    report: dict[str, Any] = {
        "run_id": run_id,
        "journal_rows_in_db": journal_count,
        "journal_rows_read": len(journal),
        "latency_scenario": scenario,
        "counts": {
            "decisions": len(decisions),
            "quotes": len(quoted),
            "holds": sum(1 for r in decisions if r.get("decision") == "hold"),
            "no_quotes": sum(no_quote.values()),
            "no_quote_reasons": dict(no_quote),
            "blocks": len(blocks),
            "gate_events": dict(gate_events),
            "data_blocks": sum(1 for r in blocks if r.get("layer") == "data"),
            "controller_denials": dict(controller_denials),
            "cancel_reasons": dict(cancel_reasons),
            "fills": len(fills),
            "unresolved_events": len(unresolved),
            "markouts_confirmed": len(confirmed_markouts),
            "markouts_shadow": len(shadow_markouts),
            "fills_in_mm_fills_table": len(fills_rows),
        },
        "quoting": {
            "half_spread_bps_median": round(median(half_spreads), 4) if half_spreads else NOT_MEASURED,
            "half_spread_bps_min": round(min(half_spreads), 4) if half_spreads else NOT_MEASURED,
            "half_spread_bps_max": round(max(half_spreads), 4) if half_spreads else NOT_MEASURED,
            "inventory_btc_mean": round(mean(inventories), 8) if inventories else NOT_MEASURED,
            "inventory_btc_max_abs": round(max(abs(v) for v in inventories), 8) if inventories else NOT_MEASURED,
        },
        "ledger": {k: ledger_state.get(k) for k in ("starting_equity_usd", "cash_usd", "inventory_btc", "average_cost", "realised_pnl_usd", "fees_usd", "adverse_selection_usd", "slippage_usd", "fills", "max_inventory_btc", "peak_equity_usd", "day", "day_start_equity_usd")},
        "fill_audit": fill_audit,
        "unresolved_audit": unresolved_audit,
        "flags": [],
    }
    flags = report["flags"]
    if fill_audit["fills_without_venue_trade_ids"]:
        flags.append("FILLS WITHOUT VENUE TRADE IDS: a fill not produced by a real print")
    if fill_audit["fills_before_their_decision"]:
        flags.append("FILLS BEFORE THEIR DECISION: look-ahead")
    if isinstance(fill_audit["min_decision_to_fill_ms"], int) and fill_audit["min_decision_to_fill_ms"] < 5:
        flags.append("A FILL WITHIN 5 ms OF ITS DECISION: latency floor violated")
    shadow, confirmed = unresolved_audit["shadow_markouts_1s"], unresolved_audit["confirmed_markouts_1s"]
    if shadow["count"] >= 20 and confirmed["count"] >= 20 and shadow["mean_1s_bps"] is not None and confirmed["mean_1s_bps"] is not None and shadow["mean_1s_bps"] < confirmed["mean_1s_bps"] - 0.5:
        flags.append("UNRESOLVED CASES ARE MORE ADVERSE THAN CONFIRMED FILLS: the simulator may be dropping the worst cases; P&L flattered")
    if not flags:
        flags.append("none")
    if args.json:
        print(json.dumps(report, indent=1, default=str))
    else:
        print(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
