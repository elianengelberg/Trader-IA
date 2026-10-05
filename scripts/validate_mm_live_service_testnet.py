#!/usr/bin/env python
"""Run the live market-making **service** against Binance Spot Testnet for a few minutes.

``scripts/validate_mm_testnet.py`` proves the building blocks one at a time: REST, the signed
account stream, one post-only order, its cancel, the reconciliation. This script proves the
assembly the operator would actually start: ``LiveMarketMakerService.start_live()`` — the
initial reconciliation, the ledger seeded from the venue's balances, the engine quoting on
Testnet market data, cancel/replace through the real adapter, the account stream feeding
execution reports, periodic reconciliation, the kill switch, and ``stop()`` with its final
reconciliation. It is the path ``POST /api/mm/live/start`` takes, without the API, without the
database and without the production configuration.

Rails, every one checked before anything connects:

* Testnet only: REST, account stream and market data stream must all be ``testnet.binance.vision``
  hosts; a mainnet host in any of the three is a refusal;
* the provider is simulated by construction (``is_live`` False) and no activation token exists
  or can be minted here; ``TIA_MM__REAL_MONEY`` is read by nothing;
* the market maker's own rules apply unchanged: LIMIT_MAKER only, the maker-only validation
  against the local book, the risk and economics authorizers, the kill switch, the strict
  cancel/replace. This script configures sizes and caps; it relaxes nothing;
* on exit, success or failure, the service is stopped (cancel everything, wait for the venue,
  reconcile) and the venue is asked again, with a fresh client, whether any order of this
  maker is still open.

What a run can and cannot show. Testnet's book is thin and its prices are its own, so the
economics authorizer may deny every quote and the engine may cancel more than it rests; both
are recorded as what happened, not as failures of the plumbing. A fill is welcome and is
checked, never provoked. Nothing here is evidence about profitability.

Usage (from the VPS, in the same one-off container as the block validation):

    python scripts/validate_mm_live_service_testnet.py --minutes 3 \\
        --profile /app/data/runtime/mm/latency_profile.json --json-out /out/mm_service_testnet.json

The latency profile is the one measured on that host (``mm_market_data_check.py
--write-latency-profile``); the engine refuses to run without a measured one, by design.
For a Testnet run, measure it against Testnet (``--rest-url https://testnet.binance.vision
--stream-url wss://stream.testnet.binance.vision/stream``) into a directory of its own and
bind-mount that directory at ``/app/data/runtime`` read-only; the production data volume
holds the profile the paper maker measured against Mainnet public data and is not the
place for it. ``scripts/run_mm_service_testnet_validation.sh`` does the whole sequence.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_mm_testnet import REST_URL, TESTNET_HOST, WS_URL, Evidence, Rails, _env_live_config

from tia.core.clock import SystemClock
from tia.data.providers.binance_live import BinanceExecutionProvider
from tia.data.providers.binance_public import BinancePublicProvider
from tia.data.providers.binance_signing import signer_from_live_config
from tia.data.providers.binance_user_stream import BinanceUserDataStream
from tia.mm.adverse_selection import HORIZON_RULE, HORIZONS_MS
from tia.mm.authorization import EconomicsConfig
from tia.mm.costs import MarketMakerCostConfig
from tia.mm.engine import MarketMakerConfig
from tia.mm.execution import CLIENT_ID_PREFIX, SymbolFilters
from tia.mm.latency_model import LatencyProfile, LatencyProfileError
from tia.mm.live_service import LiveMarketMakerService
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.quoting import QuotingConfig
from tia.mm.streams import MarketDataStream

STREAM_URL = "wss://stream.testnet.binance.vision/stream"
MAINNET_MARKERS = ("api.binance.com", "stream.binance.com", "ws-api.binance.com", "data-stream.binance.vision")


async def _wait_until(predicate: Any, seconds: float, step: float = 0.1) -> bool:
    """Poll ``predicate`` for up to ``seconds``; True as soon as it holds."""
    deadline = time.monotonic() + seconds
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(step)


def _check_stream_rail(stream_url: str) -> None:
    if TESTNET_HOST not in stream_url:
        raise SystemExit(f"REFUSED: the market data stream URL {stream_url!r} is not a Testnet host")
    if any(marker in stream_url for marker in MAINNET_MARKERS):
        raise SystemExit("REFUSED: a mainnet market data host was configured")


# ---------------------------------------------------------------- the S8 experiment (harness overrides)
#
# EXPERIMENTAL. These three overrides exist so that a Testnet run can show the service's own
# quotes being filled: engine -> adapter -> account stream -> correlation -> ledger ->
# reconciliation. With the production defaults the engine's quotes rest about 10 bps away
# from the mid (the cost floor assumes 10 bps of maker fee), live one second and are replaced
# on a 0.5 bps move, so on Testnet none of them is ever reached (sections 10.12 to 10.14 of
# the Phase 4 document). The overrides change quoting parameters only, in this harness only,
# and only when asked for on the command line; they are recorded in the evidence. They are
# not a strategy, not a fee assumption for Mainnet and not a statement about profitability.
# Nothing here touches the stale-data threshold, the kill switch, the risk or economics
# authorizers, the maker-only validation, the capital cap or the Testnet-only rails.

DEFAULT_FEE_SCENARIO = MarketMakerConfig().fee_scenario  # "assumed"
DEFAULT_QUOTE_TTL_MS = QuotingConfig().quote_ttl_ms  # 1000
DEFAULT_REQUOTE_THRESHOLD_BPS = MarketMakerConfig().requote_threshold_bps  # 0.5
FEE_SCENARIO_CHOICES = (DEFAULT_FEE_SCENARIO, "testnet_zero")
QUOTE_TTL_RANGE_MS = (100, 300_000)
REQUOTE_THRESHOLD_RANGE_BPS = (0.1, 100.0)
TESTNET_ZERO_FEE_STATUS = "EXPERIMENT_TESTNET_ZERO: Binance Spot Testnet charges no commission (n=0.0 on the real fills observed); an experiment on Testnet, not a Mainnet assumption, not a strategy"


def _quote_ttl_ms(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid quote TTL {text!r}: an integer number of milliseconds") from exc
    lo, hi = QUOTE_TTL_RANGE_MS
    if not lo <= value <= hi:
        raise argparse.ArgumentTypeError(f"invalid quote TTL {value} ms: must be between {lo} and {hi}")
    return value


def _requote_threshold_bps(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid requote threshold {text!r}: a number of bps") from exc
    lo, hi = REQUOTE_THRESHOLD_RANGE_BPS
    if not lo <= value <= hi:
        raise argparse.ArgumentTypeError(f"invalid requote threshold {value} bps: must be between {lo} and {hi}")
    return value


def _fee_scenario(text: str) -> str:
    if text not in FEE_SCENARIO_CHOICES:
        raise argparse.ArgumentTypeError(f"invalid fee scenario {text!r}: one of {list(FEE_SCENARIO_CHOICES)} (the production scenarios 'verified' and 'adverse' are not offered by this harness)")
    return text


@dataclass(frozen=True)
class ExperimentOverrides:
    """What the command line changed, if anything. Defaults are the production defaults."""

    fee_scenario: str = DEFAULT_FEE_SCENARIO
    quote_ttl_ms: int = DEFAULT_QUOTE_TTL_MS
    requote_threshold_bps: float = DEFAULT_REQUOTE_THRESHOLD_BPS

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> ExperimentOverrides:
        return cls(
            fee_scenario=_fee_scenario(str(getattr(args, "fee_scenario", DEFAULT_FEE_SCENARIO))),
            quote_ttl_ms=_quote_ttl_ms(str(getattr(args, "quote_ttl_ms", DEFAULT_QUOTE_TTL_MS))),
            requote_threshold_bps=_requote_threshold_bps(str(getattr(args, "requote_threshold_bps", DEFAULT_REQUOTE_THRESHOLD_BPS))),
        )

    @property
    def defaults(self) -> dict[str, Any]:
        return {"fee_scenario": DEFAULT_FEE_SCENARIO, "quote_ttl_ms": DEFAULT_QUOTE_TTL_MS, "requote_threshold_bps": DEFAULT_REQUOTE_THRESHOLD_BPS}

    @property
    def active(self) -> dict[str, Any]:
        mine = {"fee_scenario": self.fee_scenario, "quote_ttl_ms": self.quote_ttl_ms, "requote_threshold_bps": self.requote_threshold_bps}
        return {k: v for k, v in mine.items() if v != self.defaults[k]}

    @property
    def experimental(self) -> bool:
        return bool(self.active)

    def as_dict(self) -> dict[str, Any]:
        return {
            "experimental": self.experimental,
            "overrides": self.active,
            "defaults": self.defaults,
            "note": "EXPERIMENTAL harness overrides for the S8 experiment on Testnet; quoting parameters only; not a strategy, not a fee assumption for Mainnet, not a statement about profitability; the stale-data threshold, kill switch, authorizers, maker-only validation, capital cap and Testnet-only rails are untouched" if self.experimental else "production defaults; no override",
        }


def build_maker_config(*, symbol: str, filters: SymbolFilters, quote_size: float, overrides: ExperimentOverrides) -> MarketMakerConfig:
    """The maker's configuration for the run. With no overrides it is exactly what this
    harness always built: production defaults plus the venue's grid and the quote size."""
    quoting = QuotingConfig(base_quote_size_btc=quote_size, tick_size=filters.tick_size, size_step=filters.step_size, min_size_btc=max(0.0001, filters.min_qty), quote_ttl_ms=overrides.quote_ttl_ms)
    kwargs: dict[str, Any] = {"symbol": symbol, "quoting": quoting, "requote_threshold_bps": overrides.requote_threshold_bps}
    if overrides.fee_scenario == "testnet_zero":
        # The engine's cost floor, the ledger's assumed fee and the economics authorizer all
        # read the cost config's maker fee; a zero-fee cost config is the override. The
        # scenario name the engine looks up stays "assumed": nothing in production learns a
        # new scenario, and the status string says what this is.
        kwargs["costs"] = MarketMakerCostConfig(maker_fee_bps=0.0, maker_fee_adverse_bps=0.0, taker_fee_bps=0.0, maker_fee_status=TESTNET_ZERO_FEE_STATUS)
    return MarketMakerConfig(**kwargs)


# ---------------------------------------------------------------- what happened to every order

CANCEL_CLASSES = ("ttl", "requote", "stale_data", "kill_switch", "shutdown", "pacing", "gate_other", "no_quote_size", "no_quote_confidence", "no_quote_risk", "no_quote_implausible", "other", "none")


def _classify_cancel_reason(reason: str) -> str:
    """The adapter records why a cancel was asked for; the classes the evidence reports."""
    r = (reason or "").strip().lower()
    if not r:
        return "none"
    if r.startswith("ttl expired"):
        return "ttl"
    if r.startswith("requote"):
        return "requote"
    if "data_invalid" in r or "market data not usable" in r or "last event" in r or "kill switch (data)" in r:
        return "stale_data"
    if r.startswith("shutdown") or "shut down" in r:
        return "shutdown"
    if "pacing" in r:
        return "pacing"
    if "kill switch" in r:
        return "kill_switch"
    if r.startswith("gate"):
        return "gate_other"
    # The engine withdrew its quotes because it had none to make: the quoting layer's own
    # no_quote reasons, passed verbatim as the cancel reason (engine.py, cancel_all on a
    # decision without a quote). Told apart from each other because they are different
    # findings: a size scaled below the venue's minimum, a fair value it does not trust, the
    # risk controller, or a price it refused as implausible.
    if r.startswith("both sides sized to zero"):
        return "no_quote_size"
    if r.startswith("fair value confidence"):
        return "no_quote_confidence"
    if r.startswith("risk controller"):
        return "no_quote_risk"
    if "refused as implausible" in r:
        return "no_quote_implausible"
    return "other"


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return float(ordered[idx])


def _order_lifecycle(orders: Iterable[Any]) -> dict[str, Any]:
    """Per order: was it sent, acknowledged, how long did it rest, how did it end and why.
    Read from the adapter's own records (its closed deque and open orders), so a quote the
    engine decided but never sent, an order the venue never acknowledged, a TTL expiry, a
    requote, a stale-data cancel, a shutdown cancel, a withdrawal because the engine had no
    quote to make (size, confidence, risk, implausible price) and a fill are told apart."""
    rows: list[dict[str, Any]] = []
    for o in orders:
        fills = list(getattr(o, "fills", []) or [])
        t_ack = getattr(o, "t_ack_ms", None)
        end: int | None = None
        if o.state == "filled" and fills:
            end = max(int(getattr(f, "t_ms", 0) or 0) for f in fills) or None
        if end is None:
            end = getattr(o, "t_cancel_requested_ms", None) or getattr(o, "t_cancel_effective_ms", None)
        resting_ms = (max(0, int(end) - int(t_ack)) if (t_ack is not None and end is not None) else None)
        cancel_class = _classify_cancel_reason(getattr(o, "cancel_reason", "")) if o.state == "cancelled" else None
        terminal = "filled" if o.state == "filled" else (f"cancelled:{cancel_class}" if o.state == "cancelled" else str(o.state))
        rows.append({
            "order_id": o.order_id, "side": o.side, "price": o.price, "quantity": o.quantity,
            "sent": getattr(o, "t_submitted_ms", None) is not None, "acked": t_ack is not None, "ack_source": getattr(o, "ack_source", ""),
            "t_enqueued_ms": getattr(o, "t_enqueued_ms", None), "t_ack_ms": t_ack, "t_end_ms": end, "resting_ms": resting_ms,
            "terminal": terminal, "cancel_reason": (getattr(o, "cancel_reason", "") or "")[:160], "fills": len(fills), "filled_qty": sum(float(getattr(f, "quantity", 0.0)) for f in fills),
            "venue_order_id": getattr(o, "venue_order_id", ""),
        })
    resting = [r["resting_ms"] for r in rows if r["resting_ms"] is not None]
    terminal = Counter(r["terminal"] for r in rows)
    return {
        "orders": len(rows),
        "sent_to_venue": sum(1 for r in rows if r["sent"]),
        "acknowledged": sum(1 for r in rows if r["acked"]),
        "never_acknowledged": sum(1 for r in rows if not r["acked"]),
        "terminal": dict(terminal),
        "cancel_reasons": dict(Counter(r["terminal"].split(":", 1)[1] for r in rows if r["terminal"].startswith("cancelled:"))),
        "filled_orders": [r for r in rows if r["terminal"] == "filled"],
        "resting_ms": {"count": len(resting), "p50": _percentile(resting, 0.5), "p90": _percentile(resting, 0.9), "max": max(resting) if resting else None, "min": min(resting) if resting else None},
        "rows": rows,
    }


def _fill_rows(execution: Any) -> list[dict[str, Any]]:
    """Every fill the adapter booked, with what correlates it: the venue's trade id, our
    client id, the venue's orderId, the source that said it first, and the fee as reported."""
    known = {o.order_id: o for o in list(getattr(execution, "closed", [])) + list(getattr(execution, "orders", {}).values())}
    rows = []
    for f in list(getattr(execution, "recent_fills", [])):
        order = known.get(f.order_id)
        rows.append({
            "fill_id": f.fill_id, "order_id": f.order_id, "venue_order_id": getattr(f, "venue_order_id", ""), "side": f.side, "price": f.price, "quantity": f.quantity,
            "liquidity": getattr(f, "liquidity", ""), "attribution_source": getattr(f, "attribution_source", ""), "fee": getattr(f, "fee", 0.0), "fee_asset": getattr(f, "fee_asset", ""), "fee_status": getattr(f, "fee_status", ""),
            "t_ms": f.t_ms, "received_at_ms": getattr(f, "received_at_ms", None),
            "order_known": order is not None,
            "order_venue_order_id": getattr(order, "venue_order_id", None) if order is not None else None,
            "correlated": order is not None and str(getattr(order, "venue_order_id", "")) == str(getattr(f, "venue_order_id", "")) and any(getattr(x, "fill_id", None) == f.fill_id for x in getattr(order, "fills", [])),
        })
    return rows


# ---------------------------------------------------------------- markouts and fill context, raw

FILL_EVIDENCE_FIELDS = (
    "trade_id", "venue_order_id", "client_order_id", "t_fill_ms", "side", "price", "quantity", "notional_usd",
    "inventory_before_btc", "inventory_after_btc", "bid_quote", "ask_quote", "mid_at_fill", "fair_value_at_quote",
    "fair_value_at_fill", "capture_bps_vs_fair_value_at_quote", "capture_bps_vs_mid_at_fill", "confidence_at_quote",
    "toxicity_at_quote", "toxicity_at_fill", "data_age_at_quote_ms", "data_age_at_fill_ms", "resting_ms", "t_registered_ms",
    "registration_lag_ms", "markouts",
)


def _stats(values: list[float], weights: list[float] | None = None) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p25": None, "p75": None, "min": None, "max": None, "weighted_mean": None}
    ordered = sorted(values)
    out: dict[str, Any] = {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": _percentile(values, 0.5),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
        "min": ordered[0],
        "max": ordered[-1],
        "weighted_mean": None,
    }
    if weights and sum(weights) > 0:
        out["weighted_mean"] = sum(v * w for v, w in zip(values, weights, strict=True)) / sum(weights)
    return out


def _markout_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per horizon, from the raw rows: the signed markout (mean, median, p25/p75, min/max,
    mean weighted by notional), the same split BUY/SELL, and the cost side apart: the mean
    of max(0, -markout) (clipped adverse, what toxicity sees), the mean of max(0, markout)
    and the share of fills whose markout was negative. Shadow rows and unmeasured horizons
    are left out, and said so in the counts."""
    out: dict[str, Any] = {}
    real = [r for r in rows if not r.get("shadow")]
    for h in HORIZONS_MS:
        measured = [(r, hz) for r in real for hz in r["horizons"] if hz["horizon_ms"] == h and hz["measured"]]
        late = [(r, hz) for r, hz in measured if hz.get("measured_late")]
        on_time = [(r, hz) for r, hz in measured if not hz.get("measured_late")]
        vals = [hz["markout_bps"] for _, hz in measured]
        weights = [r["notional_usd"] for r, _ in measured]
        by_side = {}
        for side in ("buy", "sell"):
            sv = [hz["markout_bps"] for r, hz in measured if r["side"] == side]
            sw = [r["notional_usd"] for r, _ in measured if r["side"] == side]
            by_side[side] = _stats(sv, sw)
        out[str(h)] = {
            "fills": len(real),
            "measured": len(vals),
            "unmeasured": len(real) - len(vals),
            # nominal: every measured mark, late or not (what the tracker holds)
            "markout_bps": _stats(vals, weights),
            # the nominal horizon was still ahead when the fill was registered: the mark is at the horizon
            "measured_on_time": len(on_time),
            "markout_bps_on_time": _stats([hz["markout_bps"] for _, hz in on_time], [r["notional_usd"] for r, _ in on_time]),
            # the nominal horizon had passed at registration: the mark is the first mid after registration
            "measured_late": len(late),
            "markout_bps_late": _stats([hz["markout_bps"] for _, hz in late], [r["notional_usd"] for r, _ in late]),
            "late_by_ms": _stats([float(hz["late_by_ms"]) for _, hz in late if hz.get("late_by_ms") is not None]),
            "effective_horizon_ms": _stats([float(hz["effective_horizon_ms"]) for _, hz in measured if hz.get("effective_horizon_ms") is not None]),
            "markout_usd_sum": sum(hz["markout_usd"] for _, hz in measured) if measured else None,
            "by_side": by_side,
            "adverse_share": (sum(1 for v in vals if v < 0) / len(vals)) if vals else None,
            "clipped_adverse_bps_mean": (sum(max(0.0, -v) for v in vals) / len(vals)) if vals else None,
            "clipped_favourable_bps_mean": (sum(max(0.0, v) for v in vals) / len(vals)) if vals else None,
            "delay_ms": _stats([float(hz["delay_ms"]) for _, hz in measured]),
        }
    return out


def _mid_series_inversions(samples: list[Any]) -> list[dict[str, Any]]:
    """Samples whose timestamp is older than one already processed, in processing order.
    Each is reported with its index, its stamp, the running maximum before it and how far
    back it went. A series fed with correct times has none."""
    out: list[dict[str, Any]] = []
    run_max: int | None = None
    for i, sample in enumerate(samples):
        t = int(sample[0])
        if run_max is not None and t < run_max:
            out.append({"index": i, "t_ms": t, "previous_max_ms": run_max, "backwards_ms": run_max - t})
        run_max = t if run_max is None else max(run_max, t)
    return out


def _first_mid_seen(samples: list[Any], *, after_ms: int | None, at_or_after_ms: int) -> tuple[int, float] | None:
    """The tracker's own rule, replayed on the series in PROCESSING order: the first sample
    processed after the fill was registered (``after_ms``) whose stamp is at or after the
    target. A sample's processing instant is never earlier than the largest stamp processed
    before it, so a stamp that went backwards (a stale timestamp) is placed by that envelope,
    not by its own value. Without ``after_ms`` (registration unknown) only the target rule
    applies."""
    run_max: int | None = None
    for sample in samples:
        t = int(sample[0])
        processed = t if run_max is None else max(run_max, t)
        run_max = processed
        if after_ms is not None and processed < after_ms:
            continue
        if t >= at_or_after_ms:
            return t, float(sample[1])
    return None


def _markout_consistency(rows: list[dict[str, Any]], mids: list[Any] | None = None, *, bps_tolerance: float = 1e-6) -> list[str]:
    """Checks the raw rows against their own rule: target = t_fill + horizon; the mark is at
    or after the target and within tolerance; late_by_ms, measured_late and the effective
    horizon follow from t_registered; the bps and usd values match the mid and the price;
    and, when the mid series is given (in processing order), the mid at mark is the first
    mid observed after registration whose stamp is at or after the target. Returns the
    problems found (empty means consistent). Timestamp inversions in the series are a
    separate finding: see ``_mid_series_inversions``."""
    problems: list[str] = []
    series = list(mids) if mids else None
    for r in rows:
        if r.get("shadow"):
            continue
        sign = 1.0 if r["side"] == "buy" else -1.0
        notional = r["price"] * r["quantity"]
        registered = r.get("t_registered_ms")
        if registered is not None and r.get("registration_lag_ms") is not None and r["registration_lag_ms"] != registered - r["t_fill_ms"]:
            problems.append(f"{r['fill_id']}: registration_lag_ms inconsistent with t_registered - t_fill")
        for hz in r["horizons"]:
            tag = f"{r['fill_id']}@{hz['horizon_ms']}"
            if hz["target_t_ms"] != r["t_fill_ms"] + hz["horizon_ms"]:
                problems.append(f"{tag}: target {hz['target_t_ms']} != t_fill + horizon")
            if registered is not None and "late_by_ms" in hz and hz["late_by_ms"] != max(0, registered - hz["target_t_ms"]):
                problems.append(f"{tag}: late_by_ms {hz['late_by_ms']} != max(0, t_registered - target)")
            if "measured_late" in hz and hz["measured_late"] != bool(hz["measured"] and (hz.get("late_by_ms") or 0) > 0):
                problems.append(f"{tag}: measured_late flag inconsistent")
            if not hz["measured"]:
                if hz["markout_bps"] is not None or hz["mark_t_ms"] is not None:
                    problems.append(f"{tag}: unmeasured but carries values")
                continue
            if hz.get("effective_horizon_ms") is not None and hz["effective_horizon_ms"] != hz["mark_t_ms"] - r["t_fill_ms"]:
                problems.append(f"{tag}: effective_horizon_ms inconsistent")
            if hz["mark_t_ms"] is None or hz["mark_t_ms"] < hz["target_t_ms"]:
                problems.append(f"{tag}: mark {hz['mark_t_ms']} before target {hz['target_t_ms']}")
            elif hz["mark_t_ms"] - hz["target_t_ms"] > r["tolerance_ms"]:
                problems.append(f"{tag}: delay {hz['mark_t_ms'] - hz['target_t_ms']} ms over tolerance {r['tolerance_ms']}")
            if hz["delay_ms"] != hz["mark_t_ms"] - hz["target_t_ms"]:
                problems.append(f"{tag}: delay_ms inconsistent")
            expected_bps = sign * (hz["mid_at_mark"] - r["price"]) / r["price"] * 10_000.0
            if abs(expected_bps - hz["markout_bps"]) > bps_tolerance:
                problems.append(f"{tag}: markout_bps {hz['markout_bps']} != {expected_bps} from mid {hz['mid_at_mark']}")
            if abs(hz["markout_bps"] / 10_000.0 * notional - hz["markout_usd"]) > 1e-9:
                problems.append(f"{tag}: markout_usd inconsistent")
            if series:
                first = _first_mid_seen(series, after_ms=registered, at_or_after_ms=hz["target_t_ms"])
                if first is None or first[0] != hz["mark_t_ms"] or abs(first[1] - hz["mid_at_mark"]) > 1e-9:
                    rule = "first mid seen after registration with stamp >= target" if registered is not None else "first mid >= target (registration time unknown)"
                    problems.append(f"{tag}: mid series says the {rule} is {first}, row says ({hz['mark_t_ms']}, {hz['mid_at_mark']})")
    return problems


def _fill_evidence(fill_rows: list[dict[str, Any]], records: list[dict[str, Any]], markout_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per fill, joined by the venue's trade id: the adapter's correlation row, the
    engine's record (inventory, quote context, estimators, timings) and the raw markouts.
    Fields the run could not know are None, never guessed."""
    by_record = {str(r.get("fill_id")): r for r in records}
    by_markout = {str(r.get("fill_id")): r for r in markout_rows}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for f in fill_rows:
        fid = str(f["fill_id"])
        seen.add(fid)
        rec = by_record.get(fid) or {}
        quote = rec.get("quote") or {}
        mo = by_markout.get(fid)
        out.append({
            **f,
            "trade_id": fid,
            "client_order_id": f.get("order_id"),
            "t_fill_ms": f.get("t_ms"),
            "notional_usd": rec.get("notional_usd", (f.get("price") or 0.0) * (f.get("quantity") or 0.0)),
            "inventory_before_btc": rec.get("inventory_before_btc"),
            "inventory_after_btc": rec.get("inventory_after_btc"),
            "bid_quote": quote.get("bid"),
            "ask_quote": quote.get("ask"),
            "bid_size": quote.get("bid_size"),
            "ask_size": quote.get("ask_size"),
            "mid_at_quote": quote.get("mid"),
            "mid_at_fill": rec.get("mid_at_fill"),
            "mid_used_by_tracker": rec.get("mid_used_by_tracker"),
            "fair_value_at_quote": rec.get("fair_value_at_quote"),
            "fair_value_at_fill": rec.get("fair_value_at_fill"),
            "half_spread_bps_at_quote": quote.get("half_spread_bps"),
            "spread_binding_at_quote": quote.get("spread_binding"),
            "capture_bps_vs_fair_value_at_quote": rec.get("capture_bps_vs_fair_value_at_quote"),
            "capture_bps_vs_mid_at_fill": rec.get("capture_bps_vs_mid_at_fill"),
            "confidence_at_quote": quote.get("fair_value_confidence"),
            "toxicity_at_quote": quote.get("toxicity"),
            "toxicity_at_fill": rec.get("toxicity_at_fill"),
            "data_age_at_quote_ms": quote.get("data_age_ms"),
            "data_age_at_fill_ms": rec.get("data_age_at_fill_ms"),
            "vol_5s_bps_at_quote": quote.get("vol_5s_bps"),
            "inventory_adjustment_bps_at_quote": quote.get("inventory_adjustment_bps"),
            "t_decision_ms": rec.get("t_decision_ms"),
            "t_enqueued_ms": rec.get("t_enqueued_ms"),
            "t_ack_ms": rec.get("t_ack_ms"),
            "ack_source": rec.get("ack_source"),
            "resting_ms": rec.get("resting_ms"),
            "t_booked_ms": rec.get("t_booked_ms"),
            "t_registered_ms": mo.get("t_registered_ms") if mo else None,
            "registration_lag_ms": mo.get("registration_lag_ms") if mo else None,
            "realised_usd": rec.get("realised_usd"),
            "regimes": rec.get("regimes"),
            "record_error": rec.get("error"),
            "markouts": mo["horizons"] if mo else None,
            "markouts_resolved": mo["resolved"] if mo else None,
            "markouts_expired": mo["expired"] if mo else None,
            "markouts_pending": mo["pending"] if mo else None,
        })
    for fid, rec in by_record.items():  # a record without an adapter row: say so rather than drop it
        if fid not in seen:
            out.append({**rec, "trade_id": fid, "client_order_id": rec.get("order_id"), "correlated": False, "note": "engine record without an adapter fill row", "markouts": (by_markout.get(fid) or {}).get("horizons")})
    return out


# ---------------------------------------------------------------- the event loop, watched from the harness

def _lag_summary(samples: list[float], stalls: list[dict[str, Any]], stall_ms: float) -> dict[str, Any]:
    return {
        "samples": len(samples),
        "p50_ms": _percentile(samples, 0.5), "p99_ms": _percentile(samples, 0.99), "max_ms": max(samples) if samples else None,
        "stall_threshold_ms": stall_ms, "stall_count": len(stalls), "stalls": stalls[-50:],
        "note": "lag of this process's event loop measured by a 100 ms sleeper: the service, the adapter worker and the streams share it; a stall here delays every one of them",
    }


class LoopLagSampler:
    """A 100 ms sleeper that notes how late it wakes up. Harness only."""

    def __init__(self, *, interval_s: float = 0.1, stall_ms: float = 200.0, now_ms: Any = None) -> None:
        self.interval_s, self.stall_ms = interval_s, stall_ms
        self.samples: list[float] = []
        self.stalls: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._run(), name="harness-loop-lag")

    async def _run(self) -> None:
        while True:
            t0 = time.perf_counter()
            await asyncio.sleep(self.interval_s)
            lag_ms = max(0.0, (time.perf_counter() - t0 - self.interval_s) * 1000.0)
            self.samples.append(round(lag_ms, 1))
            if lag_ms >= self.stall_ms and len(self.stalls) < 500:
                self.stalls.append({"t_ms": self._now_ms(), "lag_ms": round(lag_ms, 1)})

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    def summary(self) -> dict[str, Any]:
        return _lag_summary(self.samples, self.stalls, self.stall_ms)


def _left_resting(open_orders: list[Any]) -> tuple[list[str], list[str]]:
    """What a dying run leaves at the venue, read from its local picture at the instant it
    dies: the orders resting with NO cancel in flight are what the venue will still hold;
    an order whose cancel was already requested is on its way out and the venue may well
    have closed it by the time anyone asks, so it is listed apart and never counted as
    'left'. Seen on Testnet (R1, 2026-10-04): the one resting order at death carried a
    cancel the data gate had just requested; the venue completed it, and a harness that
    counted it as left reported a discrepancy that was not one."""
    left = sorted(o.order_id for o in open_orders if o.state == "resting" and getattr(o, "t_cancel_requested_ms", None) is None)
    in_flight = sorted(o.order_id for o in open_orders if o.state == "resting" and getattr(o, "t_cancel_requested_ms", None) is not None)
    return left, in_flight


class ServiceValidation:
    def __init__(self, args: argparse.Namespace, live: Any) -> None:
        self.args = args
        self.live = live
        self.ev = Evidence()
        self.clock = SystemClock()
        self.samples: list[dict[str, Any]] = []
        self.service: LiveMarketMakerService | None = None
        self.market: MarketDataService | None = None
        self.provider: BinanceExecutionProvider | None = None
        self.public: BinancePublicProvider | None = None
        self.filters: SymbolFilters | None = None
        self.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.final_status: dict[str, Any] | None = None
        self.stop_result: dict[str, Any] | None = None
        self.open_after_stop: list[str] | None = None
        self.config: MarketMakerConfig | None = None
        self.profile: LatencyProfile | None = None
        self.first_run_status: dict[str, Any] | None = None  # the recovery drill's dead run, as it was when it died
        self.overrides = ExperimentOverrides.from_args(args)
        self.lag = LoopLagSampler(now_ms=self.now_ms)
        self.lifecycle: dict[str, Any] | None = None
        self.fills: list[dict[str, Any]] = []
        self.fill_records: list[dict[str, Any]] = []
        self.markout_rows: list[dict[str, Any]] = []
        self.markout_tracker: dict[str, Any] | None = None
        self.toxicity_final: dict[str, Any] | None = None
        self.mid_series: list[tuple[int, float]] = []

    def now_ms(self) -> int:
        return self.clock.timestamp_ms()

    # ------------------------------------------------------------------ assembly

    async def build(self) -> None:
        ev = self.ev
        args = self.args
        signer = signer_from_live_config(self.live, self.clock)
        self.provider = BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=args.rest_url, simulated=True)
        self.public = BinancePublicProvider(base_url=args.rest_url, clock=self.clock)
        ev.mark("S0.provider_is_simulated_without_token", "PASS" if not self.provider.is_live and self.provider.activation is None else "FAIL", f"is_live={self.provider.is_live} activation={self.provider.activation}")

        try:
            profile = LatencyProfile.load(args.profile)
        except LatencyProfileError as exc:
            ev.mark("S0.latency_profile_measured_on_this_host", "NOT TESTED", str(exc)[:200])
            raise SystemExit(f"NOT TESTED: {exc}") from exc
        ev.mark("S0.latency_profile_measured_on_this_host", "PASS", f"profile {profile.profile_id} commit {profile.commit} measured {profile.measured_at_utc} source {profile.source or 'not recorded'}")

        ev.command(f"provider.get_exchange_info({args.symbol})  [GET /api/v3/exchangeInfo]")
        info = await self.provider.get_exchange_info(args.symbol)
        venue_symbol = BinanceExecutionProvider.to_venue_symbol(args.symbol)
        self.filters = SymbolFilters.from_exchange_info(info, symbol=args.symbol, venue_symbol=venue_symbol)
        f = self.filters
        ev.responses["filters"] = f.as_dict()
        ev.mark("S0.exchange_filters_read", "PASS", f"tick {f.tick_size} step {f.step_size} minQty {f.min_qty} minNotional {f.min_notional}")

        quote_size = args.quote_size
        config = build_maker_config(symbol=args.symbol, filters=f, quote_size=quote_size, overrides=self.overrides)
        quoting = config.quoting
        ev.responses["quoting"] = {"base_quote_size_btc": quote_size, "tick_size": f.tick_size, "size_step": f.step_size, "min_size_btc": quoting.min_size_btc, "quote_ttl_ms": quoting.quote_ttl_ms, "requote_threshold_bps": config.requote_threshold_bps, "fee_scenario": config.fee_scenario, "costs": config.costs.__dict__, "limits": config.limits.as_dict()}
        ev.responses["experiment"] = self.overrides.as_dict()
        ev.mark("S0.experimental_overrides_recorded", "PASS", f"EXPERIMENTAL overrides {self.overrides.active} (defaults {self.overrides.defaults})" if self.overrides.experimental else "none: production defaults")

        public = self.public

        async def fetch_snapshot():  # type: ignore[no-untyped-def]
            book = await public.depth_snapshot(args.symbol, limit=args.depth_limit)
            return snapshot_from_levels(book.last_update_id or 0, [(lvl.price, lvl.size) for lvl in book.bids], [(lvl.price, lvl.size) for lvl in book.asks])

        stream = MarketDataStream(args.symbol, stream_url=args.stream_url, depth_speed="100ms")
        self.market = MarketDataService(args.symbol, stream=stream, fetch_snapshot=fetch_snapshot, recorder=None)
        self.config, self.profile = config, profile
        self.service = self._assemble_service(run_id="mm-testnet-service")
        ev.mark("S0.service_assembled_like_the_api_would", "PASS", "LiveMarketMakerService + BinanceUserDataStream + MarketDataService on Testnet URLs; capital cap " + (f"{args.capital_cap_usd} USD" if args.capital_cap_usd > 0 else "none"))

    def _new_provider(self) -> BinanceExecutionProvider:
        signer = signer_from_live_config(self.live, self.clock)
        return BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=self.args.rest_url, simulated=True)

    def _assemble_service(self, *, run_id: str) -> LiveMarketMakerService:
        """The service exactly as ``POST /api/mm/live/start`` would build it, on the current
        provider: the maker, its account stream, the market data already running."""
        assert self.market is not None and self.provider is not None and self.filters is not None and self.config is not None and self.profile is not None
        args = self.args
        service = LiveMarketMakerService(
            market=self.market,
            config=self.config,
            profile=self.profile,
            scenario=args.scenario,
            run_id=run_id,
            risk_state=lambda: None,  # no directional session here: the gate reads data validity and the kill switch
            provider=self.provider,
            clock=self.clock,
            filters=self.filters,
            activation=None,
            capital_cap_usd=args.capital_cap_usd if args.capital_cap_usd > 0 else None,
            economics=EconomicsConfig(min_net_edge_bps=args.min_net_edge_bps),
            reconcile_interval_s=args.reconcile_interval,
            trades_poll_interval_s=3.0,
            open_sync_interval_s=10.0,
            venue_label="binance-spot-testnet",
        )
        user_stream = BinanceUserDataStream(
            self.provider,
            now_ms=self.now_ms,
            on_report=service.execution.absorb_execution_report,
            on_balances=service.execution.absorb_balances,
            on_status=service.execution.absorb_stream_status,
            base_url=args.ws_url,
        )
        service.attach_user_stream(user_stream)
        return service

    async def _own_open_at_venue(self) -> list[str]:
        """The venue's open orders of this maker's prefix, asked with a fresh client so the
        answer does not depend on any adapter's mirror."""
        fresh = self._new_provider()
        try:
            open_orders = await fresh.get_orders(open_only=True, symbol=self.args.symbol)
            return sorted(o.client_order_id for o in open_orders if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX))
        finally:
            await fresh.close()

    # ------------------------------------------------------------------ the run

    async def run(self) -> int:
        ev = self.ev
        args = self.args
        failed = False
        try:
            await self.build()
            assert self.market is not None and self.service is not None
            self.lag.start()
            ev.command(f"MarketDataService.start()  [{args.stream_url}; snapshot GET {args.rest_url}/api/v3/depth]")
            self.market.start()
            await _wait_until(lambda: bool(self.market and self.market.usable), 60.0)
            snap = self.market.snapshot(levels=1)
            ev.responses["market_at_start"] = {k: snap.get(k) for k in ("usable", "not_usable_reason", "freshness")}
            ev.mark("S1.testnet_market_data_usable", "PASS" if self.market.usable else "FAIL", f"usable={self.market.usable} {snap.get('not_usable_reason') or ''}".strip())
            if not self.market.usable:
                raise RuntimeError("Testnet market data never became usable; the engine would not quote")

            ev.command("service.start_live()  [check_grid, worker, account stream, initial reconciliation, ledger seed, subscribe]")
            report = await self.service.start_live()
            ev.responses["initial_reconciliation"] = report.as_dict()
            ev.mark("S2.initial_reconciliation_completed", "PASS" if not report.critical else "FAIL", report.summary)
            ledger = self.service.live_ledger.snapshot()
            ev.responses["ledger_after_seed"] = ledger
            ev.mark("S2.ledger_seeded_from_venue_balances", "PASS" if self.service.live_ledger.seeded else "FAIL", f"seeded={self.service.live_ledger.seeded}")
            up = await _wait_until(lambda: self.service is not None and self.service.user_stream is not None and bool(self.service.user_stream.connected), 20.0)
            ev.mark("S3.account_stream_subscribed_through_the_service", "PASS" if up else "FAIL", f"connected={up} subscriptionId={getattr(self.service.user_stream, 'subscription_id', None)} last_error={getattr(self.service.user_stream, 'last_error', '')!r}")

            await self._observe(args.minutes * 60.0)
            if args.recovery_drill:
                await self.recovery_drill()
        except SystemExit:
            raise
        except Exception as exc:
            failed = True
            print(f"\nSTOPPED: {type(exc).__name__}: {str(exc)[:300]}")
            ev.notes["stopped"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            await self.shutdown()
        self.judge()
        return 1 if failed or any(v == "FAIL" for v in ev.results.values()) else 0

    async def recovery_drill(self) -> None:
        """RECOVERY — the running service dies with quotes resting: no stop(), no cancel (the
        engine stops hearing the market, the loops are cancelled, the account stream and the
        worker are cut). A second service starts on the same account with a fresh client, as a
        restarted process would: it must find the dead run's orders under its own prefix and
        cancel them before placing anything, reconcile clean, quote with its own ids, and never
        resubmit a client id. The venue is asked with a fresh client at every step; the
        S-items that follow judge the second run, and stop() runs on it."""
        ev = self.ev
        first = self.service
        assert first is not None and self.provider is not None
        print("\nRECOVERY DRILL — the first run dies with orders resting; a second run starts on the same account")
        # Die at an instant when something rests with no cancel in flight: a quote the engine
        # is already taking off the book is not 'left', the venue is about to close it.
        await _wait_until(lambda: bool(_left_resting(first.execution.open_orders())[0]), 90.0)
        # From here nothing new may be asked of the venue by the dying run: the engine stops
        # hearing the market and the loops end, synchronously, before the picture is read.
        ev.command("first run dies: market subscription dropped, loops cancelled, account stream and worker cut — no stop(), no cancel")
        if first._unsubscribe is not None:
            first._unsubscribe()
            first._unsubscribe = None
        for task in (first._reconcile_task, first._heartbeat_task):
            if task is not None:
                task.cancel()
        left, in_flight = _left_resting(first.execution.open_orders())
        drill: dict[str, Any] = {"left_by_first_run": left, "cancel_in_flight_at_death": in_flight}
        ev.responses["recovery_drill"] = drill
        with contextlib.suppress(Exception):
            if first.user_stream is not None:
                await first.user_stream.close()
        worker = getattr(first.execution, "_worker", None)
        if worker is not None:
            worker.cancel()  # a crash does not drain its queue
        await asyncio.sleep(0.2)
        self.first_run_status = first.status()
        drill["first_run_order_lifecycle"] = _order_lifecycle(list(first.execution.closed) + list(first.execution.orders.values()))
        still = await self._own_open_at_venue()
        drill["open_at_venue_after_death"] = still
        ev.command(f"GET /api/v3/openOrders  [fresh client]  — the venue still holds the dead run's orders: {still}")
        if not left:
            ev.mark("R1.first_run_died_with_orders_resting", "NOT TESTED", f"nothing rested without a cancel in flight when the run died (in flight: {in_flight}); the venue lists {still}; last block {first.engine.last_block_reason!r}")
        else:
            ev.mark("R1.first_run_died_with_orders_resting", "PASS" if set(left) <= set(still) else "FAIL", f"left resting, no cancel in flight: {left}; cancel in flight (not counted): {in_flight}; open at the venue: {still}")
        nothing_to_sweep = not still

        # The second run: a fresh provider, a fresh account stream, the same market data.
        with contextlib.suppress(Exception):
            await self.provider.close()
        self.provider = self._new_provider()
        second = self._assemble_service(run_id="mm-testnet-service-restarted")
        self.service = second
        ev.command("second run: service.start_live()  [orphan sweep by id, initial reconciliation, ledger seed]")
        report = await second.start_live()
        sweep = second.orphan_sweep or {}
        drill["sweep"] = sweep
        drill["initial_reconciliation_second_run"] = report.as_dict()
        cancelled = sorted(c["order_id"] for c in sweep.get("cancelled", []))
        if nothing_to_sweep:
            # A sweep of nothing proves nothing: the items that judge it are not passed in a vacuum.
            ev.mark("R2.orphans_found_and_cancelled_before_quoting", "NOT TESTED", f"the venue held nothing of the dead run when the second run started; the sweep found {sweep.get('found')}")
        else:
            ev.mark("R2.orphans_found_and_cancelled_before_quoting", "PASS" if sorted(sweep.get("found", [])) == still and cancelled == still and not sweep.get("failed") else "FAIL", f"found {sweep.get('found')} cancelled {cancelled} failed {sweep.get('failed')}")
        ev.mark("R3.initial_reconciliation_clean_after_the_sweep", "PASS" if not report.critical else "FAIL", report.summary)
        after = await self._own_open_at_venue()
        drill["open_at_venue_after_sweep"] = after
        if nothing_to_sweep:
            ev.mark("R4.no_order_of_the_dead_run_open_at_the_venue", "NOT TESTED", "nothing of the dead run was open to begin with")
        else:
            ev.mark("R4.no_order_of_the_dead_run_open_at_the_venue", "PASS" if not (set(after) & set(still)) else "FAIL", f"open at the venue after the sweep {after}")
        up = await _wait_until(lambda: bool(second.user_stream is not None and second.user_stream.connected), 20.0)
        ev.mark("R5.second_run_account_stream_subscribed", "PASS" if up else "FAIL", f"connected={up} subscriptionId={getattr(second.user_stream, 'subscription_id', None)}")
        await self._observe(min(60.0, max(20.0, self.args.minutes * 60.0 / 3)))
        placed = second.execution.counters["placed"]
        own = f"{CLIENT_ID_PREFIX}{second.execution.run_tag[:8]}"
        open_now = await self._own_open_at_venue()
        drill["open_at_venue_while_second_run_quotes"] = open_now
        not_ours = [cid for cid in open_now if not cid.startswith(own)]
        ev.mark("R6.second_run_quotes_with_its_own_ids_only", "PASS" if placed > 0 and not not_ours else ("NOT TESTED" if placed == 0 and not not_ours else "FAIL"), f"placed {placed}; open at the venue {open_now}; not this run's {not_ours}")
        known = {o.order_id for o in list(second.execution.closed) + list(second.execution.orders.values())}
        dead_ids = set(still) | set(left) | set(in_flight)
        if nothing_to_sweep:
            ev.mark("R7.no_client_id_of_the_dead_run_adopted_or_resubmitted", "NOT TESTED", "nothing of the dead run was at the venue for the second run to meet")
        else:
            ev.mark("R7.no_client_id_of_the_dead_run_adopted_or_resubmitted", "PASS" if not (known & dead_ids) and second.execution.counters["venue_orders_unknown_locally"] == 0 else "FAIL", f"dead run's ids known to the second run {sorted(known & dead_ids)}; venue_orders_unknown_locally {second.execution.counters['venue_orders_unknown_locally']}")

    async def _observe(self, seconds: float) -> None:
        assert self.service is not None
        print(f"\nOBSERVING for {seconds:g} s — the engine quotes (or says why not), the adapter cancels and replaces, the stream reports")
        start = time.monotonic()
        next_sample = start
        while time.monotonic() - start < seconds:
            if time.monotonic() >= next_sample:
                self.samples.append(self._sample())
                s = self.samples[-1]
                print(f"  t+{s['t_s']:>5.0f}s quotes {s['counts']['quotes']:>4} placed {s['placed']:>4} acked {s['acked']:>4} cancelled {s['cancelled']:>4} would_cross {s['rejected_would_cross']:>3} fills {s['fills']:>2} unknown {s['unknown_open']} open {s['open_orders']} kill={s['kill_engaged']} gate={s['gate_state']} block={s['last_block_reason'][:60]!r}")
                next_sample += self.args.sample_seconds
            await asyncio.sleep(0.2)

    def _sample(self) -> dict[str, Any]:
        assert self.service is not None
        st = self.service.status()
        c = st["execution"]  # the adapter's counters are flattened into its stats
        kill = st["kill_switch"]
        return {
            "t_s": round(time.monotonic() - self._t0(), 1),
            "counts": st["counts"],
            "placed": c["placed"], "acked": c["acked"], "cancelled": c["cancelled"], "rejected": c["rejected"], "rejected_would_cross": c["rejected_would_cross"],
            "fills": c["fills"], "unknown": c["unknown"], "unknown_open": len(st["unknown_orders"]), "open_orders": len(st["open_orders"]),
            "refused_validation": c["refused_validation"], "refused_blocked": c["refused_blocked"], "deferred_cancel_pending": c["deferred_cancel_pending"],
            "kill_engaged": kill.get("engaged"), "kill": kill,
            "gate_state": (st["gate"] or {}).get("state"), "last_block_reason": st["last_block_reason"] or "",
            "authorization_blocks": st["authorization_blocks"], "authorization_side_removals": st["authorization_side_removals"],
            "authorizations": st["authorizations"],
            "reconciliations": st["reconciliation"]["count"], "reconciliation_failures": st["reconciliation"]["failures"],
            "stream_connected": st["user_stream"].get("connected"), "stream_reports": st["user_stream"].get("reports"),
            "heartbeats": st["heartbeats"], "data_usable": st["data"]["usable"], "engine_errors": st["engine_errors"],
            "ledger": {k: st["ledger"].get(k) for k in ("cash_usd", "inventory_btc", "fills", "realised_pnl_usd", "fees_usd") if k in st["ledger"]},
        }

    def _t0(self) -> float:
        if not hasattr(self, "_t0_value"):
            self._t0_value = time.monotonic()
        return self._t0_value

    # ------------------------------------------------------------------ shutdown and verdicts

    async def shutdown(self) -> None:
        ev = self.ev
        print("\nSHUTDOWN — stop (cancel, wait for the venue, reconcile), then ask the venue again with a fresh client")
        if self.service is not None and (self.service.is_running or self.service.execution.open_orders()):
            try:
                ev.command("service.stop()  [cancel_all, drain until quiet, final reconciliation, close]")
                self.stop_result = await self.service.stop(reason="validation window elapsed", actor="validate_mm_live_service_testnet")
                self.final_status = self.stop_result
            except Exception as exc:
                ev.mark("S12.stop_completed", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
        await self.lag.stop()
        ev.responses["event_loop"] = self.lag.summary()
        if self.service is not None:
            with contextlib.suppress(Exception):
                self.lifecycle = _order_lifecycle(list(self.service.execution.closed) + list(self.service.execution.orders.values()))
                self.fills = _fill_rows(self.service.execution)
            with contextlib.suppress(Exception):
                engine = self.service.engine
                self.fill_records = list(engine.fill_records)
                self.markout_rows = engine.markouts.raw_rows()
                self.markout_tracker = engine.markouts.summary()
                self.toxicity_final = engine.toxicity.as_dict()
                self.mid_series = list(engine.mid_samples)
        elif self.service is not None:
            self.final_status = self.service.status()
        if self.service is not None:
            with contextlib.suppress(Exception):
                await self.service.close()
        if self.market is not None:
            with contextlib.suppress(Exception):
                await self.market.close()
        if self.public is not None:
            with contextlib.suppress(Exception):
                await self.public.close()
        # A fresh client, so the question does not depend on what stop() closed.
        try:
            signer = signer_from_live_config(self.live, self.clock)
            fresh = BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=self.args.rest_url, simulated=True)
            try:
                ev.command(f"GET /api/v3/openOrders?symbol={BinanceExecutionProvider.to_venue_symbol(self.args.symbol)}  [fresh client]")
                open_orders = await fresh.get_orders(open_only=True, symbol=self.args.symbol)
                self.open_after_stop = [o.client_order_id for o in open_orders if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX)]
                for cid in list(self.open_after_stop):
                    # Should never happen after stop(); if it does, cancel and say so.
                    with contextlib.suppress(Exception):
                        await fresh.resolve_unknown_order(symbol=self.args.symbol, client_order_id=cid)
                        await fresh.cancel_order(cid)
            finally:
                await fresh.close()
        except Exception as exc:
            ev.notes["open_orders_check"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    def judge(self) -> None:
        ev = self.ev
        st = self.final_status
        if st is None:
            ev.mark("S12.stop_completed", "FAIL", "no final status: the service never reached stop()")
            return
        c = st["execution"]  # the adapter's counters are flattened into its stats
        counts = st["counts"]
        last = self.samples[-1] if self.samples else None
        ev.responses["final_status"] = st
        ev.responses["samples"] = self.samples
        ev.mark("S4.engine_processed_market_events", "PASS" if counts["events"] > 0 and counts["decisions"] > 0 else "FAIL", f"events {counts['events']} decisions {counts['decisions']} heartbeats {st['heartbeats']} engine_errors {st['engine_errors']} {st['last_engine_error']!r}")
        blocks = {"gate_blocks": counts["gate_blocks"], "data_blocks": counts["data_blocks"], "authorization_blocks": st["authorization_blocks"], "authorization_side_removals": st["authorization_side_removals"], "refused_validation": c["refused_validation"], "refused_blocked": c["refused_blocked"], "deferred_cancel_pending": c["deferred_cancel_pending"], "last_block_reason": st["last_block_reason"], "last_authorizations": st["authorizations"]}
        ev.responses["why_not_quoting"] = blocks
        if c["placed"] > 0:
            ev.mark("S5.quotes_placed_through_the_real_adapter", "PASS", f"placed {c['placed']} (engine quotes {counts['quotes']}, requotes {counts['requotes']})")
        else:
            ev.mark("S5.quotes_placed_through_the_real_adapter", "NOT TESTED", f"the engine sent nothing: {json.dumps(blocks, default=str)[:400]}")
        if c["placed"] > 0:
            ev.mark("S6.orders_acknowledged_by_the_venue", "PASS" if c["acked"] > 0 else "FAIL", f"acked {c['acked']} rejected {c['rejected']} (would cross: {c['rejected_would_cross']}, the post-only rail) unknown {c['unknown']}")
            ev.mark("S7.cancel_replace_through_the_venue", "PASS" if c["cancelled"] > 0 and c["unknown"] == 0 else ("NOT TESTED" if c["cancelled"] == 0 and c["unknown"] == 0 else "FAIL"), f"cancel requests {c['cancel_requests']} cancelled {c['cancelled']} expired {c['expired']} unknown {c['unknown']} cancel_rejected_after_close {c['cancel_rejected_after_close']}")
        else:
            ev.mark("S6.orders_acknowledged_by_the_venue", "NOT TESTED", "nothing was placed")
            ev.mark("S7.cancel_replace_through_the_venue", "NOT TESTED", "nothing was placed")
        ledger = st["ledger"]
        lifecycle: dict[str, Any] | None = getattr(self, "lifecycle", None)
        fills: list[dict[str, Any]] = getattr(self, "fills", [])
        records: list[dict[str, Any]] = getattr(self, "fill_records", [])
        markout_rows: list[dict[str, Any]] = getattr(self, "markout_rows", [])
        mid_series: list[tuple[int, float]] = getattr(self, "mid_series", [])
        fills = _fill_evidence(fills, records, markout_rows) if (records or markout_rows) else fills
        ev.responses["order_lifecycle"] = lifecycle
        ev.responses["fills"] = fills
        ev.responses["markouts"] = {
            "convention": HORIZON_RULE,
            "horizons_ms": list(HORIZONS_MS),
            "tracker": getattr(self, "markout_tracker", None),
            "toxicity_final": getattr(self, "toxicity_final", None),
            "summary": _markout_summary(markout_rows),
            "rows": markout_rows,
            "note": "raw per fill and per horizon; the summary leaves out shadow rows and unmeasured horizons; clipped adverse is what toxicity sees, the signed markout is the economics",
        }
        inversions = _mid_series_inversions(mid_series)
        ev.responses["mid_series"] = {
            "count": len(mid_series),
            "t_first_ms": mid_series[0][0] if mid_series else None,
            "t_last_ms": mid_series[-1][0] if mid_series else None,
            "samples": [[t, m] for t, m in mid_series],
            "order": "processing order (the order the tracker saw them), not sorted by stamp",
            "inversions": {"count": len(inversions), "max_backwards_ms": max((i["backwards_ms"] for i in inversions), default=0), "examples": inversions[:10]},
            "note": "every mid the markout tracker was shown (local book, same instants); recompute a markout as the first sample processed after the fill's t_registered_ms whose stamp is at or after t_fill + horizon, within the tolerance; an inversion is a sample stamped earlier than one already processed and means a caller fed the engine a stale timestamp",
        }
        if lifecycle is not None:
            lc = lifecycle
            ev.mark("S5b.order_lifecycle_recorded", "PASS", f"orders {lc['orders']} sent {lc['sent_to_venue']} acked {lc['acknowledged']} never_acked {lc['never_acknowledged']} terminal {lc['terminal']} resting_ms p50 {lc['resting_ms']['p50']} p90 {lc['resting_ms']['p90']} max {lc['resting_ms']['max']}")
        if c["fills"] > 0:
            ev.mark("S8.fills_booked_once_into_the_ledger", "PASS" if ledger.get("fills") == c["fills"] and c["duplicate_trades"] >= 0 else "FAIL", f"real_testnet_fill: execution fills {c['fills']} (reports {c['report_fills']}, trade poll {c['trade_poll_fills']}, duplicates recognised {c['duplicate_trades']}) ledger fills {ledger.get('fills')} inventory {ledger.get('inventory_btc')}")
            correlated = [f for f in fills if f["correlated"]]
            ev.mark("S8b.fills_correlated_by_clientOrderId_and_orderId", "PASS" if fills and len(correlated) == len(fills) else "FAIL", f"{len(correlated)} of {len(fills)} fills correlate (venue trade id, our client id, the venue's orderId, booked once on the order): {[(f['fill_id'], f['order_id'], f['venue_order_id'], f['attribution_source'], f['liquidity']) for f in fills][:6]}")
            last = (st.get("reconciliation") or {}).get("last") or {}
            last_fill_t = max((f["t_ms"] for f in fills), default=0)
            ev.mark("S8c.reconciliation_after_the_fill_clean", "PASS" if last.get("ok") and not last.get("critical") and int(last.get("t_ms") or 0) >= last_fill_t else "FAIL", f"last reconciliation ok={last.get('ok')} critical={last.get('critical')} at {last.get('t_ms')} vs last fill {last_fill_t}; balances {json.dumps({k: (last.get('balances') or {}).get(k) for k in ('expected_quote_usd', 'venue_quote_usd', 'expected_base_btc', 'venue_base_btc')}, default=str)}")
            f2l = (st.get("latency") or {}).get("fill_to_ledger_ms") or {}
            ev.mark("S8d.fill_to_ledger_latency_measured", "PASS" if (f2l.get("count") or 0) == c["fills"] else "FAIL", f"fill_to_ledger_ms count {f2l.get('count')} p50 {f2l.get('p50_ms')} max {f2l.get('max_ms')} for {c['fills']} fill(s)")
            # Raw markouts: judged for completeness and internal consistency only, never for
            # their value. Every real fill must have a raw row, every row must obey the rule it
            # states, and the mid series must reproduce each mark.
            real_rows = [r for r in markout_rows if not r.get("shadow")]
            fill_ids = {str(f["fill_id"]) for f in fills}
            missing = sorted(fill_ids - {str(r["fill_id"]) for r in real_rows})
            problems = _markout_consistency(real_rows, mid_series)
            inversions = _mid_series_inversions(mid_series)
            measured = {h: sum(1 for r in real_rows for hz in r["horizons"] if hz["horizon_ms"] == h and hz["measured"]) for h in HORIZONS_MS}
            late = {h: sum(1 for r in real_rows for hz in r["horizons"] if hz["horizon_ms"] == h and hz.get("measured_late")) for h in HORIZONS_MS}
            lags = [r["registration_lag_ms"] for r in real_rows if r.get("registration_lag_ms") is not None]
            with_context = sum(1 for f in fills if f.get("inventory_before_btc") is not None and f.get("fair_value_at_quote") is not None)
            ok = not missing and not problems and not inversions and bool(mid_series) and with_context == len(fills)
            ev.mark("S8e.markouts_raw_exported_and_consistent", "PASS" if ok else "FAIL", f"raw rows {len(real_rows)} for {len(fills)} fills (missing {missing[:5]}), measured per horizon {measured}, of which measured_late (nominal horizon already past at registration) {late}, registration lag ms min {min(lags) if lags else None} max {max(lags) if lags else None}, pending {sum(1 for r in real_rows if r['pending'])} expired {sum(1 for r in real_rows if r['expired'])}, fills with quote context {with_context}/{len(fills)}, mid samples {len(mid_series)} with {len(inversions)} timestamp inversion(s){(' (max ' + str(max(i['backwards_ms'] for i in inversions)) + ' ms backwards; e.g. ' + str(inversions[:2]) + ')') if inversions else ''}, reconstruction problems {len(problems)}: {problems[:3]}")
        else:
            ev.mark("S8.fills_booked_once_into_the_ledger", "NOT TESTED", "no fill occurred (not provoked); the fill paths are SYNTHETIC ONLY here (tests/unit/mm, tests/adversarial), which is not evidence about Binance")
            for item in ("S8b.fills_correlated_by_clientOrderId_and_orderId", "S8c.reconciliation_after_the_fill_clean", "S8d.fill_to_ledger_latency_measured", "S8e.markouts_raw_exported_and_consistent"):
                ev.mark(item, "NOT TESTED", "no fill occurred")
        loop = ev.responses.get("event_loop") or {}
        ev.mark("S4b.event_loop_stalls_observed", "PASS", f"{loop.get('stall_count')} stall(s) over {loop.get('stall_threshold_ms')} ms in {loop.get('samples')} samples; lag p50 {loop.get('p50_ms')} p99 {loop.get('p99_ms')} max {loop.get('max_ms')} ms (recorded, not judged)")
        rec = st["reconciliation"]
        ev.mark("S9.periodic_reconciliation_ran", "PASS" if rec["count"] >= 2 and rec["failures"] == 0 else ("FAIL" if rec["failures"] else "NOT TESTED"), f"reconciliations {rec['count']} failures {rec['failures']} interval {rec['interval_s']} s last ok={((rec.get('last') or {}).get('ok'))} critical={((rec.get('last') or {}).get('critical'))}")
        # The kill switch, in two readings. Before stop(): a sticky engagement means a critical
        # finding stopped the maker for good during the run — that is what the item judges;
        # transient engagements (stale market data, a stream drop) are the rails working and
        # are recorded, not failed. After stop(): a deliberate shutdown is its own state, not
        # a safety engagement — it must be recorded as such, no sticky safety engagement may
        # remain (one would mean a critical finding preceded the stop), and no transient
        # condition may survive a service that can no longer observe it.
        kill_before = (last or {}).get("kill") or {}
        history = (st["kill_switch"].get("history") or [])
        engagements = [(h.get("trigger"), h.get("sticky"), h.get("action")) for h in history if h.get("action") == "engage"]
        ev.responses["kill_switch_engagements"] = history
        if kill_before.get("sticky"):
            ev.mark("S10.no_sticky_kill_during_the_run", "FAIL", f"sticky before stop: trigger={kill_before.get('trigger')!r} reason={kill_before.get('reason')!r}; engagements {engagements}")
        else:
            # The history the status carries is bounded (the last 20 events); the switch's own
            # counter is the number of engagements over the whole run.
            total = st["kill_switch"].get("engagements")
            total = len(engagements) if total is None else total
            ev.mark("S10.no_sticky_kill_during_the_run", "PASS", f"transient engagements during the run: {total} by the kill switch's counter; the last {len(history)} events kept show {[t for t, sticky, _ in engagements if not sticky]}; none sticky")
        kill = st["kill_switch"]
        shutdown_ok = bool(kill.get("shutdown")) and not kill.get("sticky") and not kill.get("transient") and not kill.get("engaged")
        ev.mark("S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left", "PASS" if shutdown_ok else "FAIL", json.dumps({k: kill.get(k) for k in ("engaged", "sticky", "trigger", "reason", "severity", "transient", "shutdown", "blocks_quoting")}, default=str)[:400])
        ev.mark("S11.no_unknown_orders", "PASS" if not st["unknown_orders"] and c["unknown"] == 0 else "FAIL", f"unknown counter {c['unknown']} open unknown {len(st['unknown_orders'])}")
        stream = st["user_stream"]
        ev.mark("S3b.account_stream_reports_received", "PASS" if (stream.get("reports") or 0) > 0 else ("NOT TESTED" if c["placed"] == 0 else "FAIL"), f"reports {stream.get('reports')} balance_updates {stream.get('balance_updates')} disconnects {stream.get('disconnects')} reconnects {stream.get('reconnects')}")
        if self.stop_result is not None:
            ev.mark("S12.stop_completed", "PASS" if not st["running"] and not st["open_orders"] else "FAIL", f"running={st['running']} open locally {len(st['open_orders'])} stop_reason={st['stop_reason']!r}")
        if self.open_after_stop is not None:
            ev.mark("S12b.no_open_orders_at_the_venue_after_stop", "PASS" if not self.open_after_stop else "FAIL", f"{len(self.open_after_stop)} open {CLIENT_ID_PREFIX} order(s) found and cancelled: {self.open_after_stop}" if self.open_after_stop else "none")
        else:
            ev.mark("S12b.no_open_orders_at_the_venue_after_stop", "FAIL", ev.notes.get("open_orders_check", "the venue could not be asked"))
        ev.mark("S13.testnet_only_no_token_no_real_money", "PASS" if st["is_live"] is False and st["activation"] is None and all(TESTNET_HOST in u for u in (self.args.rest_url, self.args.ws_url, self.args.stream_url)) else "FAIL", f"is_live={st['is_live']} activation={st['activation']} venue={st['venue']}")
        if last is not None:
            ev.latency_ms["service"] = st["latency"]

    def report(self) -> dict[str, Any]:
        groups: dict[str, list[str]] = {"PASS": [], "FAIL": [], "NOT TESTED": []}
        for item, verdict in self.ev.results.items():
            groups.setdefault(verdict, []).append(item)
        print("\n" + "=" * 72)
        for verdict in ("PASS", "FAIL", "NOT TESTED"):
            print(f"{verdict}:")
            for item in groups[verdict]:
                note = self.ev.notes.get(item, "")
                print(f"  - {item}" + (f": {note}" if note else ""))
        return {
            "script": "validate_mm_live_service_testnet.py",
            "started_utc": self.started_utc,
            "args": dict(vars(self.args)),
            "results": self.ev.results,
            "notes": self.ev.notes,
            "commands": self.ev.commands,
            "responses": self.ev.responses,
            "latency_ms": self.ev.latency_ms,
            "journal_tail": self.service.journal(limit=300) if self.service is not None else [],
            "first_run_status_before_death": self.first_run_status,
            "fill_evidence_kind": "real_testnet_fill" if (self.final_status or {}).get("execution", {}).get("fills", 0) > 0 else None,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--minutes", type=float, default=3.0, help="how long the service runs before stop()")
    parser.add_argument("--profile", default="data/runtime/mm/latency_profile.json", help="the latency profile measured on this host (mm_market_data_check.py --write-latency-profile)")
    parser.add_argument("--scenario", default="baseline", choices=("optimistic", "baseline", "conservative"))
    parser.add_argument("--quote-size", type=float, default=0.0002, help="base quote size in BTC (Testnet assets; above the venue minimum)")
    parser.add_argument("--capital-cap-usd", type=float, default=200.0, help="the maker's capital cap, as the activation token would impose it (0 = none)")
    parser.add_argument("--min-net-edge-bps", type=float, default=0.0)
    parser.add_argument("--reconcile-interval", type=float, default=15.0)
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--depth-limit", type=int, default=1000)
    parser.add_argument("--rest-url", default=REST_URL)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--stream-url", default=STREAM_URL)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--recovery-drill", action="store_true", help="after the window: the service dies with quotes resting (no stop, no cancel) and a second service starts on the same account, which must sweep the dead run's orders before quoting (items R1-R7); stop() then runs on the second run")
    experiment = parser.add_argument_group("S8 experiment (EXPERIMENTAL harness overrides; quoting parameters only; recorded in the evidence; not a strategy, not a Mainnet fee assumption)")
    experiment.add_argument("--fee-scenario", type=_fee_scenario, default=DEFAULT_FEE_SCENARIO, help=f"'{DEFAULT_FEE_SCENARIO}' (production default, 10 bps assumed maker fee) or 'testnet_zero' (a zero-fee cost config: Testnet charges none, so the cost floor stops pushing the quotes 10 bps off the mid)")
    experiment.add_argument("--quote-ttl-ms", type=_quote_ttl_ms, default=DEFAULT_QUOTE_TTL_MS, help=f"how long a quote may rest before the TTL cancels it (default {DEFAULT_QUOTE_TTL_MS}; {QUOTE_TTL_RANGE_MS[0]}..{QUOTE_TTL_RANGE_MS[1]})")
    experiment.add_argument("--requote-threshold-bps", type=_requote_threshold_bps, default=DEFAULT_REQUOTE_THRESHOLD_BPS, help=f"how far the desired quotes must move before the resting ones are replaced (default {DEFAULT_REQUOTE_THRESHOLD_BPS}; {REQUOTE_THRESHOLD_RANGE_BPS[0]}..{REQUOTE_THRESHOLD_RANGE_BPS[1]})")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    live = _env_live_config(args)
    if live is None:
        print("NOT TESTED: TIA_LIVE__BINANCE_API_KEY / TIA_LIVE__BINANCE_API_SECRET (Testnet keys) are not in the process environment; nothing was attempted")
        return 2
    Rails.check(live, args.rest_url, args.ws_url)
    _check_stream_rail(args.stream_url)
    validation = ServiceValidation(args, live)
    try:
        code = asyncio.run(validation.run())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("interrupted; the shutdown ran in the finally block if the service had started")
        return 130
    payload = validation.report()
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=1, default=str))
        print(f"evidence written to {out}")
    return code


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(main())
