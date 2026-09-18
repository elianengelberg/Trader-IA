"""Metrics for the market maker, and the one verdict they are allowed to reach.

Everything the acceptance list asks for, computed from the engine's journal, ledger,
execution and markout summaries: quotes, fills, partials, refusals, unresolved,
gross spread capture, gross P&L, fees, adverse selection, net, per fill and per quote,
fill and cancel ratios, inventory utilisation and duration, max inventory, drawdown,
Sharpe and Sortino only when the sample warrants them, and markouts per horizon —
split by volatility, spread, imbalance and flow regime, by inventory bucket and by
side, and stamped with the latency and fee scenarios they were computed under.

The verdict is **EDGE DETECTED** only when every rule in the audit's section 15 holds on
data that did not choose the parameters; otherwise it is **NO EDGE DETECTED** with the
rules that failed spelled out. Nothing here tunes anything.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MIN_FILLS_FOR_RATIOS = 300
EDGE_MIN_FILLS = 300
EDGE_MIN_REGIMES = 3
EDGE_MAX_UNRESOLVED_SHARE = 0.10
EDGE_MAX_REGIME_SHARE = 0.60
BOOTSTRAP_BLOCK_MS = 60_000
BOOTSTRAP_ROUNDS = 2_000


@dataclass
class FillRecord:
    t_ms: int
    side: str
    price: float
    quantity: float
    fee_usd: float
    realised_usd: float
    mid_at_fill: float | None
    inventory_btc_after: float
    regimes: dict[str, str] = field(default_factory=dict)
    markout_bps: dict[str, float | None] = field(default_factory=dict)

    @property
    def notional_usd(self) -> float:
        return self.price * self.quantity

    @property
    def spread_capture_usd(self) -> float:
        """Distance from the mid at fill time, in USD: what a maker is paid for being there."""
        if self.mid_at_fill is None:
            return 0.0
        sign = 1.0 if self.side == "buy" else -1.0
        return sign * (self.mid_at_fill - self.price) * self.quantity

    @property
    def net_usd(self) -> float:
        return self.realised_usd - self.fee_usd

    @property
    def inventory_bucket(self) -> str:
        level = abs(self.inventory_btc_after)
        if level < 1e-9:
            return "flat"
        return "long" if self.inventory_btc_after > 0 else "short"


def fills_from_journal(journal: Iterable[dict[str, Any]]) -> list[FillRecord]:
    rows = list(journal)
    markouts = {r["fill_id"]: r.get("markout_bps", {}) for r in rows if r.get("kind") == "markout" and not r.get("shadow")}
    out: list[FillRecord] = []
    for r in rows:
        if r.get("kind") != "fill":
            continue
        out.append(
            FillRecord(
                t_ms=int(r["t"]),
                side=str(r["side"]),
                price=float(r["price"]),
                quantity=float(r["quantity"]),
                fee_usd=float(r.get("fee_usd", 0.0)),
                realised_usd=float(r.get("realised_usd", 0.0)),
                mid_at_fill=r.get("mid_at_fill"),
                inventory_btc_after=float(r.get("inventory_btc", 0.0)),
                regimes=dict(r.get("regimes", {})),
                markout_bps=dict(markouts.get(r["fill_id"], {})),
            )
        )
    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _ratio_stats(values: list[float]) -> dict[str, Any]:
    """Sharpe- and Sortino-like ratios per fill, only when the sample warrants them."""
    if len(values) < MIN_FILLS_FOR_RATIOS:
        return {"sharpe": None, "sortino": None, "note": f"{len(values)} fills < {MIN_FILLS_FOR_RATIOS}: ratios not reported"}
    m, s = _mean(values), _std(values)
    downside = [v for v in values if v < 0]
    d = math.sqrt(sum(v * v for v in downside) / len(values)) if downside else 0.0
    return {
        "sharpe": (m / s) if m is not None and s else None,
        "sortino": (m / d) if m is not None and d else None,
        "standard_error": (s / math.sqrt(len(values))) if s is not None else None,
        "note": "per-fill ratios, not annualised",
    }


def block_bootstrap_ci(fills: list[FillRecord], *, seed: int = 0, rounds: int = BOOTSTRAP_ROUNDS, block_ms: int = BOOTSTRAP_BLOCK_MS) -> dict[str, Any]:
    """95% interval of the mean net per fill, resampling time blocks so autocorrelation
    within a minute is respected. Deterministic for a given seed."""
    if len(fills) < 2:
        return {"lower": None, "upper": None, "mean": _mean([f.net_usd for f in fills]), "blocks": 0, "seed": seed}
    blocks: dict[int, list[float]] = {}
    for f in fills:
        blocks.setdefault(f.t_ms // block_ms, []).append(f.net_usd)
    keys = sorted(blocks)
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(rounds):
        chosen = rng.integers(0, len(keys), size=len(keys))
        sample = [v for i in chosen for v in blocks[keys[i]]]
        means.append(sum(sample) / len(sample))
    return {
        "lower": float(np.percentile(means, 2.5)),
        "upper": float(np.percentile(means, 97.5)),
        "mean": _mean([f.net_usd for f in fills]),
        "blocks": len(keys),
        "rounds": rounds,
        "seed": seed,
    }


def _split(fills: list[FillRecord], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[FillRecord]] = {}
    for f in fills:
        label = f.inventory_bucket if key == "inventory" else (f.side if key == "side" else f.regimes.get(key, "unknown"))
        groups.setdefault(label, []).append(f)
    out = {}
    for label, rows in sorted(groups.items()):
        nets = [r.net_usd for r in rows]
        m1 = [r.markout_bps.get("1000") for r in rows if r.markout_bps.get("1000") is not None]
        out[label] = {
            "fills": len(rows),
            "net_usd": round(sum(nets), 6),
            "net_per_fill_usd": round(_mean(nets) or 0.0, 6),
            "gross_spread_capture_usd": round(sum(r.spread_capture_usd for r in rows), 6),
            "fees_usd": round(sum(r.fee_usd for r in rows), 6),
            "markout_1s_bps_mean": _mean(m1),
        }
    return out


def compute_metrics(
    *,
    journal: Iterable[dict[str, Any]],
    ledger: dict[str, Any],
    execution: dict[str, Any],
    markouts: dict[str, Any],
    limits: dict[str, Any],
    latency_scenario: str,
    fee_scenario: str,
    seed: int = 0,
) -> dict[str, Any]:
    rows = list(journal)
    fills = fills_from_journal(rows)
    decisions = [r for r in rows if r.get("kind") == "decision"]
    quotes = sum(1 for r in decisions if r.get("decision") == "quote")
    holds = sum(1 for r in decisions if r.get("decision") == "hold")
    no_quotes: dict[str, int] = {}
    for r in decisions:
        if r.get("decision") == "no_quote":
            key = str(r.get("reason", "")).split(":")[0]
            no_quotes[key] = no_quotes.get(key, 0) + 1
    nets = [f.net_usd for f in fills]
    placed = int(execution.get("placed", 0) or 0)
    states = execution.get("states", {}) or {}
    filled_orders = int(states.get("filled", 0) or 0)
    cancelled = int(execution.get("cancelled", 0) or 0)
    unresolved_events = int(execution.get("unresolved_fill_events", 0) or 0)
    candidates = len(fills) + unresolved_events
    horizons = {}
    for h, stats in (markouts.get("horizons") or {}).items():
        horizons[f"markout_{h}ms"] = stats
    max_inventory = float(ledger.get("max_inventory_btc", 0.0) or 0.0)
    inventory_limit = float(limits.get("max_inventory_btc", 0.0) or 0.0)
    metrics: dict[str, Any] = {
        "scenario": {"latency": latency_scenario, "fees": fee_scenario},
        "counts": {
            "decisions": len(decisions),
            "total_quotes": quotes,
            "holds": holds,
            "no_quotes_by_reason": no_quotes,
            "orders_placed": placed,
            "fills": len(fills),
            "partial_fills": int(execution.get("partial_orders", 0) or 0),
            "rejected_fills": int(execution.get("refused_crossed", 0) or 0),
            "unresolved_fills": unresolved_events,
            "unresolved_share": (unresolved_events / candidates) if candidates else None,
            "cancelled_orders": cancelled,
            "expired_orders": int(execution.get("expired", 0) or 0),
        },
        "pnl": {
            "gross_spread_capture_usd": round(sum(f.spread_capture_usd for f in fills), 6),
            "gross_pnl_usd": ledger.get("gross_pnl_usd"),
            "realised_pnl_usd": ledger.get("realised_pnl_usd"),
            "fees_usd": ledger.get("fees_usd"),
            "adverse_selection_usd": ledger.get("adverse_selection_usd"),
            "slippage_usd": ledger.get("slippage_usd"),
            "net_pnl_usd": ledger.get("net_pnl_usd"),
            "net_pnl_conservative_usd": ledger.get("net_pnl_conservative_usd"),
            "pnl_per_fill_usd": _mean(nets),
            "pnl_per_quote_usd": (sum(nets) / quotes) if quotes else None,
            "net_per_fill_bootstrap_95": block_bootstrap_ci(fills, seed=seed),
            "ratios": _ratio_stats(nets),
        },
        "ratios": {
            "fill_ratio": (filled_orders / placed) if placed else None,
            "cancel_ratio": (cancelled / placed) if placed else None,
        },
        "inventory": {
            "max_inventory_btc": max_inventory,
            "inventory_limit_btc": inventory_limit,
            "inventory_utilization": (max_inventory / inventory_limit) if inventory_limit else None,
            "inventory_duration_s": ledger.get("inventory_duration_s"),
            "final_inventory_btc": ledger.get("inventory_btc"),
        },
        "drawdown_pct": ledger.get("drawdown_pct"),
        "markouts": horizons,
        "by_regime": {
            "vol_regime": _split(fills, "vol_regime"),
            "spread_regime": _split(fills, "spread_regime"),
            "imbalance_regime": _split(fills, "imbalance_regime"),
            "flow_regime": _split(fills, "flow_regime"),
            "inventory": _split(fills, "inventory"),
            "side": _split(fills, "side"),
        },
    }
    metrics["edge"] = edge_assessment(metrics)
    return metrics


def edge_assessment(metrics: dict[str, Any], *, min_fills: int = EDGE_MIN_FILLS) -> dict[str, Any]:
    """The audit's section 15, applied. Never tunes; only reports which rules failed."""
    failures: list[str] = []
    counts, pnl = metrics["counts"], metrics["pnl"]
    n = counts["fills"]
    if n < min_fills:
        failures.append(f"{n} confirmed fills < {min_fills} required")
    for key in ("spread_regime", "vol_regime"):
        present = [k for k, v in metrics["by_regime"][key].items() if v["fills"] > 0 and k != "unknown"]
        if len(present) < EDGE_MIN_REGIMES:
            failures.append(f"{len(present)} {key} buckets with fills < {EDGE_MIN_REGIMES}")
    ci = pnl["net_per_fill_bootstrap_95"]
    if ci.get("lower") is None or ci["lower"] <= 0:
        failures.append(f"95% interval of net per fill not entirely positive (lower {ci.get('lower')})")
    capture = pnl.get("gross_spread_capture_usd") or 0.0
    adverse = pnl.get("adverse_selection_usd") or 0.0
    if adverse >= capture:
        failures.append(f"adverse selection {adverse:.4f} USD >= gross spread capture {capture:.4f} USD")
    share = counts.get("unresolved_share")
    if share is not None and share > EDGE_MAX_UNRESOLVED_SHARE:
        failures.append(f"unresolved fills {share:.0%} > {EDGE_MAX_UNRESOLVED_SHARE:.0%}: result not determinable")
    # Concentration is judged on the fills themselves, so the shares add up to one.
    net_total = sum(v["net_usd"] for v in metrics["by_regime"]["side"].values())
    if net_total > 0:
        for key in ("spread_regime", "vol_regime", "flow_regime"):
            populated = {label: v for label, v in metrics["by_regime"][key].items() if v["fills"] > 0}
            if len(populated) < 2:
                continue  # one bucket is coverage, not concentration; coverage has its own rule
            for label, v in populated.items():
                if v["net_usd"] / net_total > EDGE_MAX_REGIME_SHARE:
                    failures.append(f"{key}={label} contributes {v['net_usd'] / net_total:.0%} of the net > {EDGE_MAX_REGIME_SHARE:.0%}")
    verdict = "EDGE DETECTED" if not failures else "NO EDGE DETECTED"
    return {
        "verdict": verdict,
        "failed_rules": failures,
        "note": (
            "Applies only to data that did not choose the parameters (out of sample by time). "
            "A negative or undetermined result is recorded as such; parameters are never adjusted to change it."
        ),
    }


__all__ = ["FillRecord", "block_bootstrap_ci", "compute_metrics", "edge_assessment", "fills_from_journal"]
