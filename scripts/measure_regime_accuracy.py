#!/usr/bin/env python3
"""Measure regime-classifier accuracy against the only trusted labels that exist here.

    python scripts/measure_regime_accuracy.py
    python scripts/measure_regime_accuracy.py --seeds 10 --json

**What the ground truth is, and is not.** The scenario generator writes each series as a
sequence of parameterised segments (drift, volatility, mean reversion, jumps). Those
parameters ARE the label: a segment generated with positive drift *is* an uptrend by
construction. That makes this a fair test of "does the classifier recover the process
that generated the data" — and nothing more.

**Caveats, before any number:**

* Synthetic series. Real markets are not piecewise GBM; accuracy here is an upper bound
  on nothing and a lower bound on nothing. Regime accuracy on real markets remains
  UNVALIDATED and is labelled that way in the audit.
* Labels are ambiguous at boundaries: after a segment switch, indicators carry the old
  segment for tens of bars, and the classifier's hysteresis is *designed* to lag. Both a
  strict score (every bar) and a settled score (excluding the first SETTLE bars of each
  segment) are reported; the honest headline is the settled one, with the lag visible in
  the gap between the two.
* Some calm segments are legitimately two things at once (a flat, quiet market is both
  "ranging" and "low_volatility"), so each segment maps to a primary label plus an
  acceptable set. Both scores are reported; the confusion matrix uses the primary label.

Writes ``data/runtime/regime_accuracy.json``. Exit 0 always — this measures, it does not
gate; the number's job is to be known, not to be green.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "tia" / "src"))

from tia.domain.enums import MarketRegime
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeClassifier
from tia.runtime.scenarios import Segment, generate_series, get_scenario

START = datetime(2026, 1, 1, tzinfo=UTC)
SYMBOL = "BTC-USD"
TIMEFRAME = "1m"
#: Bars ignored at the start of each segment for the settled score: indicator windows
#: (ADX 14, slope 20, vol percentile 100) plus deliberate hysteresis need time to turn.
SETTLE = 60
SCENARIOS = ("trend_up", "trend_down", "range", "high_volatility", "mixed")


def segment_truth(segment: Segment) -> tuple[str, frozenset[str]]:
    """Primary expected regime and the set that counts as correct, from the parameters
    the generator used. Thresholds mirror the scenario catalogue: labelled trends use
    |drift| >= 5e-5, labelled turbulence uses volatility >= 1e-3 or jumps."""
    if segment.volatility >= 1.0e-3 or segment.jump_probability > 0:
        return (
            MarketRegime.HIGH_VOLATILITY.value,
            frozenset(
                {
                    MarketRegime.HIGH_VOLATILITY.value,
                    MarketRegime.ANOMALOUS.value,
                    MarketRegime.CRISIS.value,
                }
            ),
        )
    if segment.drift >= 5.0e-5:
        return MarketRegime.TRENDING_UP.value, frozenset({MarketRegime.TRENDING_UP.value})
    if segment.drift <= -5.0e-5:
        return (
            MarketRegime.TRENDING_DOWN.value,
            frozenset({MarketRegime.TRENDING_DOWN.value}),
        )
    return (
        MarketRegime.RANGING.value,
        frozenset({MarketRegime.RANGING.value, MarketRegime.LOW_VOLATILITY.value}),
    )


def bar_labels(scenario_id: str) -> list[tuple[str, frozenset[str], bool]]:
    """(primary, acceptable, settled) per bar index."""
    scenario = get_scenario(scenario_id)
    labels: list[tuple[str, frozenset[str], bool]] = []
    for segment in scenario.segments:
        primary, acceptable = segment_truth(segment)
        for k in range(segment.bars):
            labels.append((primary, acceptable, k >= SETTLE))
    return labels


def measure(scenario_id: str, seeds: list[int]) -> dict[str, object]:
    labels = bar_labels(scenario_id)
    builder = FeatureBuilder()
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    strict = Counter()
    settled = Counter()

    for seed in seeds:
        candles = generate_series(
            get_scenario(scenario_id), symbol=SYMBOL, timeframe=TIMEFRAME, start=START, seed=seed
        )
        classifier = RegimeClassifier()  # fresh hysteresis per series
        first = builder.min_bars - 1
        features = builder.build_series(SYMBOL, TIMEFRAME, candles)
        for offset, feature_set in enumerate(features):
            index = first + offset
            if index >= len(labels):
                break
            primary, acceptable, is_settled = labels[index]
            observed = classifier.classify(
                feature_set, now=candles[index].close_time
            ).regime.value
            confusion[primary][observed] += 1
            strict["total"] += 1
            strict["primary"] += observed == primary
            strict["acceptable"] += observed in acceptable
            if is_settled:
                settled["total"] += 1
                settled["primary"] += observed == primary
                settled["acceptable"] += observed in acceptable

    def ratio(counter: Counter, key: str) -> float | None:
        return round(counter[key] / counter["total"], 4) if counter["total"] else None

    return {
        "scenario": scenario_id,
        "bars_scored": strict["total"],
        "strict": {
            "primary_accuracy": ratio(strict, "primary"),
            "acceptable_accuracy": ratio(strict, "acceptable"),
        },
        "settled": {
            "bars": settled["total"],
            "primary_accuracy": ratio(settled, "primary"),
            "acceptable_accuracy": ratio(settled, "acceptable"),
        },
        "confusion": {truth: dict(row) for truth, row in confusion.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=5, help="series per scenario (default 5)")
    parser.add_argument("--json", action="store_true", help="emit the full JSON to stdout")
    args = parser.parse_args()
    seeds = [101 + i for i in range(args.seeds)]

    results = [measure(s, seeds) for s in SCENARIOS]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": (
            "generator segment parameters as ground truth; strict = every classified "
            f"bar, settled = excluding the first {SETTLE} bars of each segment"
        ),
        "seeds": seeds,
        "caveats": [
            "synthetic series only — real-market accuracy remains UNVALIDATED",
            "boundary bars are ambiguous by construction; hysteresis lag is designed",
            "acceptable-set scoring treats calm segments as ranging OR low_volatility",
        ],
        "scenarios": results,
    }

    out = Path("data/runtime/regime_accuracy.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("Regime-classifier accuracy vs generator ground truth")
    print(f"  ({args.seeds} seeds per scenario; settled = after {SETTLE} bars in-segment)")
    print()
    print(f"  {'scenario':<18} {'bars':>6}  {'strict':>7}  {'settled':>8}  {'acceptable':>11}")
    for r in results:
        print(
            f"  {r['scenario']:<18} {r['bars_scored']:>6}"
            f"  {r['strict']['primary_accuracy']!s:>7}"
            f"  {r['settled']['primary_accuracy']!s:>8}"
            f"  {r['settled']['acceptable_accuracy']!s:>11}"
        )
    print()
    for line in report["caveats"]:
        print(f"  caveat: {line}")
    print(f"\n  full confusion matrices: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
