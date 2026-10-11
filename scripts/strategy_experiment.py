#!/usr/bin/env python3
"""Per-strategy, per-horizon experiment with chronological partitions and sealed holdout.

Research tool. It changes no production configuration and starts no session. It answers,
for ONE dataset of closed bars:

* what each strategy does **on its own** (trend_following, mean_reversion, breakout), at
  each requested horizon (1m, and coarser bars resampled from it without look-ahead);
* with what uncertainty — a circular *block* bootstrap interval of the mean net return
  per trade (bps), because consecutive trades are not independent, at a level adjusted
  for the number of candidates judged on the same validation partition (Bonferroni);
* how sensitive the result is to costs (fee multipliers, extra slippage);
* on **chronological** partitions — research / validation / holdout, separated by purge and
  embargo gaps — where the holdout is computed only with ``--unlock-holdout``, and every
  such computation is written to an append-only ledger (``--holdout-log``).

What it will never do is call a strategy profitable. The verdict vocabulary is
``INSUFFICIENT`` / ``UNFAVOURABLE`` / ``INCONCLUSIVE`` / ``FRAGILE`` / ``PROMISING_ON_VALIDATION``,
decided by the criteria in :mod:`tia.backtest.inference` *before* any result is read, and
reported next to the number of variants tried, because a best-of-k result is not one result.
``PROMISING_ON_VALIDATION`` requires the adjusted lower bound to be strictly above zero and
means "worth a further out-of-sample evaluation", nothing more.

Data provenance is printed with every run (path, hash, span, rows, kind). The committed
fixtures are synthetic; a run on them checks the pipeline and says nothing about any market.

Usage:
    python scripts/strategy_experiment.py --fixtures data/fixtures --symbol BTC-USD
    python scripts/strategy_experiment.py --csv /path/to/BTCUSDT_1m.csv --symbol BTC-USD \\
        --timeframes 1m,5m,15m --fee-multipliers 1.0,1.5,2.0 --json out.json
    python scripts/strategy_experiment.py ... --unlock-holdout   # once, after freezing everything
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "tia" / "src"))

from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.backtest.holdout import (  # noqa: E402
    DEFAULT_LEDGER,
    HoldoutAccess,
    HoldoutLedger,
    config_hash,
    dirty_tree_digest,
    frozen_code_paths,
    git_state,
)
from tia.backtest.inference import (  # noqa: E402
    CRITERIA,
    adjusted_level,
    block_bootstrap_ci,
    block_length,
    iid_bootstrap_ci,
    verdict,
)
from tia.backtest.partitions import partitions, window_bounds  # noqa: E402
from tia.backtest.resample import resample_candles  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.data.providers.csv_replay import CsvReplayProvider  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE, Timeframe  # noqa: E402
from tia.domain.market import Candle  # noqa: E402

STRATEGIES = ("trend_following", "mean_reversion", "breakout")
#: Resampled means required beyond each bound of the adjusted interval (F13).
TAIL_MEANS = 20
#: Every source file whose change changes a result (F11): strategies, backtester,
#: execution simulator and filters, risk engine and budget, features, regimes, costs, the
#: expected-value engine and the instrument universe. ``STRATEGY_CODE`` kept as the
#: strategy-only subset for the candidate identity of the research log.
FROZEN_CODE = frozen_code_paths(ROOT / "packages" / "tia" / "src" / "tia")
STRATEGY_CODE = sorted((ROOT / "packages" / "tia" / "src" / "tia" / "strategy").glob("*.py"))
#: The backtester's parity rules as every cell runs them (defaults; recorded in the output).
PARITY = BacktestConfig()


@dataclass
class Cell:
    strategy: str
    timeframe: str
    partition: str
    bars: int
    signals: int
    actionable_rate: float
    approval_rate: float
    intents: int
    fills: int
    trades: int
    gross_pnl: float
    fees: float
    net_pnl: float
    mean_net_bps: float | None
    #: Block bootstrap at the nominal level (CRITERIA["ci_level"]); kept under its
    #: Phase 1 name so earlier records read the same.
    ci90_bps: tuple[float, float] | None
    std_net_bps: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float
    exposure_pct: float
    quantiles_bps: dict[str, float] = field(default_factory=dict)
    by_regime: dict[str, int] = field(default_factory=dict)
    by_direction: dict[str, int] = field(default_factory=dict)
    risk_rejections: dict[str, int] = field(default_factory=dict)
    reliable: bool = False
    cost_variant: str = "base"
    #: The i.i.d. interval, for comparison only — never read by a verdict.
    ci_iid_bps: tuple[float, float] | None = None
    #: The interval a verdict reads: block bootstrap at the multiplicity-adjusted level.
    ci_adjusted_bps: tuple[float, float] | None = None
    ci_level: float = CRITERIA["ci_level"]
    ci_adjusted_level: float | None = None
    block_length: int | None = None
    #: Stationarity readout (Phase 1.3): the mean net bps of the first and the second half
    #: of the cell's trades, in time order. Informational — no verdict reads it — but a
    #: candidate whose two halves disagree in sign is not one result either.
    half_split: dict[str, Any] | None = None


# ----------------------------------------------------------------------------- data


def load_csv(path: Path, *, symbol: str, timeframe: str) -> list[Candle]:
    """Closed bars from a CSV with ``open_time,open,high,low,close,volume[,trade_count]``.
    ``open_time`` may be ISO-8601 or epoch seconds/milliseconds."""
    tf = Timeframe.parse(timeframe)
    out: list[Candle] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = row["open_time"].strip()
            if raw.isdigit():
                value = int(raw)
                opened = datetime.fromtimestamp(
                    value / 1000 if value > 1_000_000_000_000 else value, tz=UTC
                )
            else:
                opened = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
            out.append(
                Candle(
                    symbol=symbol, timeframe=timeframe, open_time=opened,
                    close_time=opened + tf.delta, open=float(row["open"]),
                    high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                    volume=float(row["volume"]),
                    trade_count=int(float(row.get("trade_count") or 0)), provider="csv",
                )
            )
    out.sort(key=lambda c: c.open_time)
    return out


def provenance(path: Path, candles: list[Candle], kind: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "blake2s_16": hashlib.blake2s(path.read_bytes(), digest_size=16).hexdigest(),
        "rows": len(candles),
        "first_open": candles[0].open_time.isoformat() if candles else None,
        "last_close": candles[-1].close_time.isoformat() if candles else None,
        "kind": kind,
    }


def detect_kind(path: Path, override: str | None) -> str:
    if override:
        return override
    try:
        path.resolve().relative_to((ROOT / "data" / "fixtures").resolve())
        return "synthetic_fixture (generated; contains no real market data)"
    except ValueError:
        return "user_supplied (operator must state the source; not verified here)"


# ------------------------------------------------------------------------- statistics


def net_bps(trade: Any) -> float:
    notional = trade.quantity * trade.entry_price
    return trade.net_pnl / notional * 10_000.0 if notional > 0 else 0.0


def summarise(result: Any, *, strategy: str, timeframe: str, partition: str, bars: int,
              seed: int, cost_variant: str, partition_start: datetime,
              resamples: int) -> tuple[Cell, list[float]]:
    trades = [t for t in result.trades if t.entry_at >= partition_start]
    bps = [net_bps(t) for t in trades]
    counts = result.decisions
    wins = [b for b in bps if b > 0]
    losses = [b for b in bps if b <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (None if not wins else float("inf"))
    held = sum(t.bars_held for t in trades)
    quantiles: dict[str, float] = {}
    if len(bps) >= 4:
        qs = statistics.quantiles(bps, n=4)
        quantiles = {"p25": qs[0], "p50": qs[1], "p75": qs[2], "min": min(bps), "max": max(bps)}
    by_regime: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    for t in trades:
        by_regime[t.regime_at_entry.value] = by_regime.get(t.regime_at_entry.value, 0) + 1
        by_direction[t.direction.value] = by_direction.get(t.direction.value, 0) + 1
    level = float(CRITERIA["ci_level"])
    cell = Cell(
        strategy=strategy, timeframe=timeframe, partition=partition, bars=bars,
        signals=counts.signals_generated,
        actionable_rate=counts.actionable_signal_rate,
        approval_rate=counts.approval_rate,
        intents=counts.intents_submitted, fills=counts.fills, trades=len(trades),
        gross_pnl=sum(t.gross_pnl for t in trades), fees=sum(t.fees for t in trades),
        net_pnl=sum(t.net_pnl for t in trades),
        mean_net_bps=statistics.fmean(bps) if bps else None,
        ci90_bps=block_bootstrap_ci(bps, seed=seed, level=level, resamples=resamples),
        std_net_bps=statistics.pstdev(bps) if len(bps) >= 2 else None,
        win_rate=(len(wins) / len(bps)) if bps else None,
        profit_factor=pf,
        max_drawdown_pct=result.metrics.max_drawdown_pct,
        exposure_pct=(held / bars * 100.0) if bars else 0.0,
        quantiles_bps=quantiles, by_regime=by_regime, by_direction=by_direction,
        risk_rejections=dict(counts.risk_rejection_reasons),
        reliable=len(trades) >= int(CRITERIA["min_trades"]),
        cost_variant=cost_variant,
        ci_iid_bps=iid_bootstrap_ci(bps, seed=seed, level=level, resamples=resamples),
        block_length=block_length(len(bps)) if len(bps) >= 2 else None,
    )
    return cell, bps


# -------------------------------------------------------------------------- the runs


def run_cell(bars: list[Candle], *, start: int, end: int, lookback: int, strategy: str,
             timeframe: str, partition: str, seed: int, execution: ExecutionSimConfig,
             cost_variant: str, symbol: str, resamples: int) -> tuple[Cell, list[float]]:
    """One backtest over ``bars[start:end]`` with up to ``lookback`` earlier bars as warm-up.
    The warm-up is history, not future, and the engine takes no trade inside it."""
    window_start, warmup = window_bounds(start, end, lookback=lookback)
    window = bars[window_start:end]
    config = BacktestConfig(
        dataset=f"{symbol}:{timeframe}:{partition}",
        timeframe=timeframe,
        seed=seed,
        warmup_bars=warmup,
        lookback_bars=max(300, lookback),
        execution=execution,
        is_out_of_sample=partition != "research",
    )
    result = BacktestEngine(config, DEFAULT_UNIVERSE, strategies=[strategy]).run(window, symbol=symbol)
    return summarise(
        result, strategy=strategy, timeframe=timeframe, partition=partition,
        bars=end - start, seed=seed, cost_variant=cost_variant,
        partition_start=bars[start].open_time, resamples=resamples,
    )


def half_split(bps: list[float]) -> dict[str, Any] | None:
    """Means of the first and second half of ``bps`` (trade order is time order)."""
    if len(bps) < 4:
        return None
    mid = len(bps) // 2
    first, second = statistics.fmean(bps[:mid]), statistics.fmean(bps[mid:])
    return {
        "first_half_mean_bps": first, "second_half_mean_bps": second,
        "first_half_trades": mid, "second_half_trades": len(bps) - mid,
        "same_sign": (first > 0) == (second > 0),
    }


def research_log_path(args: argparse.Namespace) -> Path:
    """Next to the holdout ledger unless named: the two records travel together."""
    if args.research_log:
        return Path(args.research_log)
    return Path(args.holdout_log).with_name("research_runs.jsonl")


def prior_candidates(log: Path, *, partition_id: str) -> set[str]:
    """Every candidate an earlier run judged on this same validation partition.

    Multiplicity does not reset between invocations: the k in Bonferroni is the number of
    candidates that have *ever* been read against this partition, not the number in the
    run that happens to be printing (Phase 1.3). A corrupt line is skipped, not fatal.
    """
    if not log.exists():
        return set()
    out: set[str] = set()
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if isinstance(raw, dict) and raw.get("partition_id") == partition_id:
            out.update(str(c) for c in raw.get("candidates", []))
    return out


def append_research_log(log: Path, entry: dict[str, Any]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _ci(value: tuple[float, float] | None) -> str:
    return f"[{value[0]:.1f}, {value[1]:.1f}]" if value else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="closed bars CSV (open_time,open,high,low,close,volume[,trade_count])")
    source.add_argument("--fixtures", help="fixtures directory (synthetic; pipeline check only)")
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--base-timeframe", default="1m")
    parser.add_argument("--timeframes", default="1m,5m,15m")
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--split", default="0.5,0.3", help="research,validation fractions; the rest is holdout")
    parser.add_argument("--purge-bars", type=int, default=20)
    parser.add_argument("--embargo-bars", type=int, default=30)
    parser.add_argument("--lookback-bars", type=int, default=300)
    parser.add_argument("--fee-multipliers", default="1.0,1.5,2.0")
    parser.add_argument("--extra-slippage-bps", default="0,2")
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--resamples", type=int, default=int(CRITERIA["resamples"]))
    parser.add_argument("--data-kind", default=None, help="override the provenance label")
    parser.add_argument("--unlock-holdout", action="store_true", help="compute the reserved partition (once; recorded)")
    parser.add_argument("--holdout-log", default=str(DEFAULT_LEDGER), help="append-only ledger of holdout computations")
    parser.add_argument("--holdout-reopen-reason", default="", help="why a holdout already computed is being reopened under a changed configuration")
    parser.add_argument("--json", help="write the full record here")
    parser.add_argument("--research-log", default=None,
                        help="append-only log of every run's candidates per validation partition; the "
                             "Bonferroni family is cumulative over it (default: next to --holdout-log)")
    args = parser.parse_args()

    if args.fixtures:
        provider = CsvReplayProvider(args.fixtures)
        path = provider.path_for(args.symbol, args.base_timeframe)
        base = load_csv(path, symbol=args.symbol, timeframe=args.base_timeframe)
    else:
        path = Path(args.csv)
        base = load_csv(path, symbol=args.symbol, timeframe=args.base_timeframe)
    if len(base) < 600:
        print(f"only {len(base)} bars: too few for research/validation/holdout partitions", file=sys.stderr)
        return 1
    kind = detect_kind(path, args.data_kind)
    prov = provenance(path, base, kind)

    research_frac, validation_frac = (float(x) for x in args.split.split(","))
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    fee_mults = [float(x) for x in args.fee_multipliers.split(",")]
    slips = [float(x) for x in args.extra_slippage_bps.split(",")]
    # Deterministic simulator: stochastic rejects and forced partials are switched off so a
    # cost variant differs from its base by costs alone. Stated here, repeated in the output.
    base_execution = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)

    # What was frozen: the configuration and the strategy code. Hashed into the holdout
    # ledger so a later run under different rules cannot pass for the same experiment.
    frozen = {
        "criteria": CRITERIA, "strategies": strategies, "timeframes": timeframes,
        "split": args.split, "purge_bars": args.purge_bars, "embargo_bars": args.embargo_bars,
        "lookback_bars": args.lookback_bars, "fee_multipliers": fee_mults,
        "extra_slippage_bps": slips, "seed": args.seed, "resamples": args.resamples,
        "simulator": base_execution.model_dump(mode="json"), "symbol": args.symbol,
        "base_timeframe": args.base_timeframe,
    }
    frozen_hash = config_hash(frozen, code_paths=FROZEN_CODE)
    tree_digest = dirty_tree_digest(ROOT)
    ledger = HoldoutLedger(Path(args.holdout_log))
    holdout_report: dict[str, Any] = {
        "unlocked": bool(args.unlock_holdout), "ledger": str(ledger.path),
        "dataset_id": prov["blake2s_16"], "config_hash": frozen_hash,
        "prior_accesses": len(ledger.prior(prov["blake2s_16"])), "recorded": False,
    }
    opened_at = ""
    if args.unlock_holdout:
        allowed, why = ledger.check(
            dataset_id=prov["blake2s_16"], config_hash=frozen_hash,
            reopen_reason=args.holdout_reopen_reason,
        )
        holdout_report["gate"] = why
        if not allowed:
            print(f"holdout REFUSED: {why}", file=sys.stderr)
            print("nothing was computed; the validation partition remains the only out-of-sample "
                  "evidence this run may produce", file=sys.stderr)
            return 2
        # The access is on record *before* a single holdout number exists: a run that dies
        # between the check and the record would otherwise leave no trace of having read
        # the data, and the next run would count as a first access (Phase 1.3).
        head, dirty = git_state(ROOT)
        opened_at = datetime.now(UTC).isoformat()
        ledger.open_access(
            dataset_id=prov["blake2s_16"], config_hash=frozen_hash, variants_on_validation=0,
            git_head=head, git_dirty=dirty, reason=args.holdout_reopen_reason, at=opened_at,
            tree_digest=tree_digest,
        )
        holdout_report["opened_at"] = opened_at

    cells: list[Cell] = []
    returns: dict[int, list[float]] = {}
    stressed_of: dict[str, Cell | None] = {}
    base_of: dict[str, Cell] = {}
    variants_tried = 0
    for timeframe in timeframes:
        bars = resample_candles(base, timeframe)
        parts = partitions(len(bars), research=research_frac, validation=validation_frac,
                           purge=args.purge_bars, embargo=args.embargo_bars)
        for strategy in strategies:
            for name, (start, end) in parts.items():
                if name == "holdout" and not args.unlock_holdout:
                    continue
                if end - start < 150:
                    continue
                cell, bps = run_cell(bars, start=start, end=end, lookback=args.lookback_bars,
                                     strategy=strategy, timeframe=timeframe, partition=name,
                                     seed=args.seed, execution=base_execution, cost_variant="base",
                                     symbol=args.symbol, resamples=args.resamples)
                cells.append(cell)
                returns[id(cell)] = bps
                if name != "validation":
                    continue
                cell.half_split = half_split(bps)
                key = f"{strategy}@{timeframe}"
                base_of[key] = cell
                stressed: Cell | None = None
                for mult in fee_mults:
                    for slip in slips:
                        if mult == 1.0 and slip == 0.0:
                            continue
                        variants_tried += 1
                        execution = base_execution.model_copy(update={
                            "maker_fee_bps": base_execution.maker_fee_bps * mult,
                            "taker_fee_bps": base_execution.taker_fee_bps * mult,
                            "base_slippage_bps": base_execution.base_slippage_bps + slip,
                        })
                        variant, vbps = run_cell(bars, start=start, end=end, lookback=args.lookback_bars,
                                                 strategy=strategy, timeframe=timeframe, partition=name,
                                                 seed=args.seed, execution=execution,
                                                 cost_variant=f"fees x{mult:g}, +{slip:g} bps slip",
                                                 symbol=args.symbol, resamples=args.resamples)
                        cells.append(variant)
                        returns[id(variant)] = vbps
                        if mult == CRITERIA["fee_stress_multiplier"] and slip == 0.0:
                            stressed = variant
                variants_tried += 1
                stressed_of[key] = stressed

    # Multiplicity: every (strategy, horizon) candidate judged on the same validation
    # partition is one member of the family — in this run and in every earlier run on the
    # same partition (the research log). A candidate is the strategy, the horizon and the
    # strategy code it ran with: the same code judged twice is one look, changed code is
    # another. The verdict interval is recomputed at the Bonferroni-adjusted level for
    # the cumulative family from the same returns with the same seed (Phase 1.3).
    family = len(base_of)
    level = float(CRITERIA["ci_level"])
    code_hash = config_hash({}, code_paths=STRATEGY_CODE)
    partition_id = f"{prov['blake2s_16']}:{args.split}:{args.purge_bars}:{args.embargo_bars}"
    this_run = {f"{key}@{code_hash}" for key in base_of}
    log_path = research_log_path(args)
    cumulative = prior_candidates(log_path, partition_id=partition_id) | this_run
    family_cumulative = len(cumulative)
    adj = adjusted_level(level, family_cumulative) if family_cumulative else level
    # The adjusted interval reads a tail quantile that gets thinner as k grows (F13):
    # at k = 12 the 90 % family level leaves 0.4 % in each tail, eight resampled means
    # out of two thousand. The resample count scales so at least TAIL_MEANS means lie
    # beyond each adjusted bound.
    alpha_adj = (1.0 - adj) / 2.0
    resamples_adjusted = max(int(args.resamples), math.ceil(TAIL_MEANS / alpha_adj) if alpha_adj > 0 else int(args.resamples))
    for cell in cells:
        cell.ci_adjusted_level = adj
        cell.ci_adjusted_bps = block_bootstrap_ci(returns.get(id(cell), []), seed=args.seed,
                                                  level=adj, resamples=resamples_adjusted)
    verdicts: dict[str, dict[str, Any]] = {}
    for key, cell in base_of.items():
        stressed = stressed_of.get(key)
        result = verdict(
            trades=cell.trades, ci=cell.ci_adjusted_bps, profit_factor=cell.profit_factor,
            max_drawdown_pct=cell.max_drawdown_pct,
            stressed_mean_bps=stressed.mean_net_bps if stressed is not None else None,
        )
        verdicts[key] = {**result.as_dict(), "ci_adjusted_bps": cell.ci_adjusted_bps,
                         "ci_nominal_bps": cell.ci90_bps, "trades": cell.trades}

    if args.unlock_holdout:
        head, dirty = git_state(ROOT)
        ledger.record(HoldoutAccess(
            at=datetime.now(UTC).isoformat(), dataset_id=prov["blake2s_16"], config_hash=frozen_hash,
            variants_on_validation=variants_tried,
            verdicts={k: v["verdict"] for k, v in verdicts.items()},
            git_head=head, git_dirty=dirty, reason=args.holdout_reopen_reason,
            reopen=bool(args.holdout_reopen_reason), status="completed", tree_digest=tree_digest,
        ))
        holdout_report["recorded"] = True

    append_research_log(log_path, {
        "at": datetime.now(UTC).isoformat(), "partition_id": partition_id,
        "dataset_id": prov["blake2s_16"], "config_hash": frozen_hash, "code_hash": code_hash,
        "candidates": sorted(this_run), "family_this_run": family, "family_cumulative": family_cumulative,
        "adjusted_level": adj, "variants_tried_on_validation": variants_tried,
        "verdicts": {k: v["verdict"] for k, v in verdicts.items()},
        "holdout_unlocked": bool(args.unlock_holdout),
    })

    record = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance": prov,
        "criteria": CRITERIA,
        "frozen_config_hash": frozen_hash,
        "simulator": {"rejects": 0.0, "forced_partials": 0.0,
                      # The backtester's session-parity rules (Phase 1.3): what the entries,
                      # exits and gates were, read from the defaults the runs used.
                      "entries": f"{PARITY.entry_order_type} (backtester; limit entries rest "
                                 f"{PARITY.entry_limit_timeout_bars} bars)",
                      "exits": {"protective_stop": True, "target": PARITY.use_target,
                                "breakeven_after_r": PARITY.breakeven_after_r,
                                "trail_atr_multiple": PARITY.trail_atr_multiple,
                                "max_holding_bars": PARITY.max_holding_bars,
                                "exit_on_signal_reversal": PARITY.exit_on_signal_reversal},
                      "sizing": {"risk_profile": PARITY.risk_profile,
                                 "conviction_sizing": PARITY.conviction_sizing},
                      "expected_value": {"enforced": PARITY.enforce_expected_value,
                                         "threshold_bps": PARITY.ev_threshold_bps,
                                         "max_cost_ratio": PARITY.max_cost_ratio},
                      "fees_bps": [base_execution.maker_fee_bps, base_execution.taker_fee_bps],
                      "base_slippage_bps": base_execution.base_slippage_bps},
        "partitions": {"research": research_frac, "validation": validation_frac,
                       "holdout": round(1.0 - research_frac - validation_frac, 4),
                       "purge_bars": args.purge_bars, "embargo_bars": args.embargo_bars,
                       "holdout_unlocked": args.unlock_holdout},
        "inference": {"interval": CRITERIA["bootstrap"], "level": level,
                      "multiplicity": CRITERIA["multiplicity"], "family_size": family,
                      "family_cumulative": family_cumulative, "partition_id": partition_id,
                      "research_log": str(log_path), "code_hash": code_hash,
                      "adjusted_level": adj, "resamples": args.resamples,
                      "resamples_adjusted": resamples_adjusted, "tail_means": TAIL_MEANS,
                      "block_length_rule": "round(n ** (1/3))",
                      "percentile_method": "linear interpolation (Hyndman-Fan 7)",
                      "validity": "within this pre-registered run and its cumulative family; "
                                  "the holdout protection is procedural (an access ledger), not cryptographic",
                      "frozen_code_files": len(FROZEN_CODE), "tree_digest": tree_digest},
        "variants_tried_on_validation": variants_tried,
        "verdicts": verdicts,
        "holdout": holdout_report,
        "cells": [asdict(c) for c in cells],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(record, indent=2, default=str))

    print(f"# Strategy experiment — {args.symbol}")
    print(f"data: {prov['path']}  rows={prov['rows']}  span={prov['first_open']} → {prov['last_close']}")
    print(f"hash: blake2s/16 {prov['blake2s_16']}   frozen config: {frozen_hash}")
    print(f"kind: {prov['kind']}")
    print(f"simulator: deterministic (no random rejects/partials), market entries, fees "
          f"{base_execution.maker_fee_bps}/{base_execution.taker_fee_bps} bps, base slippage "
          f"{base_execution.base_slippage_bps} bps")
    print(f"partitions: research {research_frac:.0%} / validation {validation_frac:.0%} / holdout "
          f"{1 - research_frac - validation_frac:.0%} (purge {args.purge_bars}, embargo {args.embargo_bars} bars); "
          f"holdout {'UNLOCKED and recorded in ' + str(ledger.path) if args.unlock_holdout else 'SEALED — not computed'}")
    print(f"inference: circular block bootstrap (block = round(n^(1/3))), {level:.0%} two-sided nominal; "
          f"{family} candidates on validation in this run, {family_cumulative} ever on this partition "
          f"({log_path}) → Bonferroni-adjusted level {adj:.4f}; the verdict reads the "
          "adjusted lower bound and it must be strictly > 0")
    print(f"variants evaluated on validation: {variants_tried} "
          "(a best-of-k result is not one result; read every row, not the best one)\n")
    header = ("| strategy | tf | partition | costs | bars | signals | approval | trades | mean net bps "
              "| CI nominal | CI adjusted | CI iid | b | win | PF | maxDD % | exposure % | gross | fees | net |")
    print(header)
    print("|" + "---|" * 20)
    for c in cells:
        print(f"| {c.strategy} | {c.timeframe} | {c.partition} | {c.cost_variant} | {c.bars} | {c.signals} "
              f"| {c.approval_rate:.0%} | {c.trades} | {fmt(c.mean_net_bps, 1)} | {_ci(c.ci90_bps)} "
              f"| {_ci(c.ci_adjusted_bps)} | {_ci(c.ci_iid_bps)} | {c.block_length or 'n/a'} | {fmt(c.win_rate)} "
              f"| {fmt(c.profit_factor)} | {c.max_drawdown_pct:.2f} | {c.exposure_pct:.1f} "
              f"| {c.gross_pnl:.2f} | {c.fees:.2f} | {c.net_pnl:.2f} |")
    print("\nverdicts on VALIDATION (pre-registered criteria; never 'profitable'):")
    for key, value in verdicts.items():
        print(f"  {key:<28} {value['verdict']:<24} {value['reason']}")
    if "synthetic" in kind:
        print("\nNOTE: synthetic fixtures. These rows show that the pipeline runs; they are not "
              "evidence about any market.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
