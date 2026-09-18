"""Metrics from the journal, and a verdict that defaults to NO EDGE DETECTED."""

from __future__ import annotations

import pytest

from tia.mm.metrics import block_bootstrap_ci, compute_metrics, edge_assessment, fills_from_journal

T0 = 1_789_754_400_000


def _fill(i: int, *, net: float, side: str = "buy", regimes: dict | None = None, markout_1s: float | None = -0.5) -> list[dict]:  # type: ignore[type-arg]
    fee = 0.001
    rows = [
        {
            "kind": "fill", "t": T0 + i * 1_000, "fill_id": f"f{i}", "side": side, "price": 100_000.0, "quantity": 0.001,
            "fee_usd": fee, "realised_usd": net + fee, "mid_at_fill": 100_000.5 if side == "buy" else 99_999.5,
            "inventory_btc": 0.001 if i % 2 == 0 else 0.0, "regimes": regimes or {"vol_regime": "low", "spread_regime": "tight", "imbalance_regime": "balanced", "flow_regime": "mixed", "side": side},
        }
    ]
    if markout_1s is not None:
        rows.append({"kind": "markout", "t": T0 + i * 1_000 + 1_000, "fill_id": f"f{i}", "markout_bps": {"1000": markout_1s}})
    return rows


def _metrics(journal: list[dict], *, fills: int, execution: dict | None = None) -> dict:  # type: ignore[type-arg]
    return compute_metrics(
        journal=journal,
        ledger={"gross_pnl_usd": 1.0, "realised_pnl_usd": 1.0, "fees_usd": 0.5, "adverse_selection_usd": 0.1, "slippage_usd": 0.0, "net_pnl_usd": 0.5, "net_pnl_conservative_usd": 0.4, "max_inventory_btc": 0.02, "inventory_duration_s": 12.0, "inventory_btc": 0.0, "drawdown_pct": 0.3},
        execution=execution or {"placed": fills * 2, "states": {"filled": fills, "cancelled": fills}, "cancelled": fills, "expired": 1, "refused_crossed": 2, "partial_orders": 3, "unresolved_fill_events": 1},
        markouts={"horizons": {"1000": {"count": fills, "mean_bps": -0.5}}},
        limits={"max_inventory_btc": 0.05},
        latency_scenario="baseline",
        fee_scenario="assumed",
    )


def test_metrics_count_quotes_fills_and_split_by_regime_and_side() -> None:
    journal = [{"kind": "decision", "t": T0, "decision": "quote"}, {"kind": "decision", "t": T0 + 1, "decision": "hold"}, {"kind": "decision", "t": T0 + 2, "decision": "no_quote", "reason": "risk controller: kill switch"}]
    for i in range(10):
        journal += _fill(i, net=0.5 if i % 2 else -0.2, side="buy" if i % 3 else "sell")
    m = _metrics(journal, fills=10)
    assert m["counts"]["total_quotes"] == 1 and m["counts"]["holds"] == 1 and m["counts"]["no_quotes_by_reason"] == {"risk controller": 1}
    assert m["counts"]["fills"] == 10 and m["counts"]["rejected_fills"] == 2 and m["counts"]["unresolved_fills"] == 1
    assert m["counts"]["unresolved_share"] == pytest.approx(1 / 11)
    assert m["ratios"]["fill_ratio"] == pytest.approx(0.5) and m["ratios"]["cancel_ratio"] == pytest.approx(0.5)
    assert m["inventory"]["inventory_utilization"] == pytest.approx(0.4)
    assert m["pnl"]["pnl_per_fill_usd"] == pytest.approx((5 * 0.5 + 5 * -0.2) / 10)
    assert m["pnl"]["pnl_per_quote_usd"] == pytest.approx(1.5)
    assert m["pnl"]["gross_spread_capture_usd"] == pytest.approx(10 * 0.5 * 0.001)  # 0.5 USD inside the mid each, 0.001 BTC
    assert m["pnl"]["ratios"]["sharpe"] is None and "not reported" in m["pnl"]["ratios"]["note"]
    assert set(m["by_regime"]["side"]) == {"buy", "sell"} and m["by_regime"]["side"]["sell"]["fills"] == 4
    assert m["by_regime"]["vol_regime"]["low"]["markout_1s_bps_mean"] == pytest.approx(-0.5)
    assert m["markouts"]["markout_1000ms"]["mean_bps"] == -0.5
    assert m["scenario"] == {"latency": "baseline", "fees": "assumed"}
    assert m["edge"]["verdict"] == "NO EDGE DETECTED" and any("< 300" in f for f in m["edge"]["failed_rules"])


def test_the_bootstrap_is_deterministic_and_the_verdict_needs_every_rule() -> None:
    fills = fills_from_journal([r for i in range(40) for r in _fill(i, net=0.3 if i % 4 else -0.1)])
    a, b = block_bootstrap_ci(fills, seed=7, rounds=200), block_bootstrap_ci(fills, seed=7, rounds=200)
    assert a == b and a["lower"] is not None and a["lower"] <= a["mean"] <= a["upper"]
    assert block_bootstrap_ci(fills, seed=8, rounds=200) != a
    assert block_bootstrap_ci(fills[:1])["lower"] is None
    # A large, positive, well-spread sample still fails on any single rule.
    journal: list[dict] = []  # type: ignore[type-arg]
    regimes = [("low", "tight"), ("mid", "normal"), ("high", "wide")]
    for i in range(330):
        vol, spread = regimes[i % 3]
        journal += _fill(i, net=0.4, regimes={"vol_regime": vol, "spread_regime": spread, "imbalance_regime": "balanced", "flow_regime": "mixed"})
    m = _metrics(journal, fills=330, execution={"placed": 400, "states": {"filled": 330}, "cancelled": 50, "refused_crossed": 0, "partial_orders": 0, "unresolved_fill_events": 0})
    assert m["pnl"]["ratios"]["sharpe"] is not None
    assert m["edge"]["verdict"] == "EDGE DETECTED", m["edge"]["failed_rules"]
    # Now the same numbers with a tenth of the fills unresolved: not determinable, not an edge.
    m2 = _metrics(journal, fills=330, execution={"placed": 400, "states": {"filled": 330}, "cancelled": 50, "refused_crossed": 0, "partial_orders": 0, "unresolved_fill_events": 60})
    assert m2["edge"]["verdict"] == "NO EDGE DETECTED" and any("unresolved" in f for f in m2["edge"]["failed_rules"])
    # And with adverse selection above the spread capture.
    m3 = dict(m)
    m3["pnl"] = {**m["pnl"], "adverse_selection_usd": 999.0}
    assert edge_assessment(m3)["verdict"] == "NO EDGE DETECTED"
    assert "never adjusted" in edge_assessment(m3)["note"]
