"""The backtest engine, the baselines and the experiment verdict.

The look-ahead properties live in ``tests/property/test_no_lookahead.py``. What is checked
here is everything else a backtest can quietly get wrong: costs that are not charged,
positions that are never closed, a result that reads as a promise, and a verdict that
flatters a sample too small to support one.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

import pytest

from tia.backtest import (
    MIN_TRADES_FOR_INFERENCE,
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    ExperimentVerdict,
    always_flat,
    buy_and_hold,
    evaluate_experiment,
    random_entry,
    run_all_baselines,
    sma_cross,
    volatility_targeted,
)
from tia.core.config import ExecutionSimConfig, RiskLimits
from tia.core.errors import BacktestError
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.enums import Direction, RiskVerdict
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
NOW = datetime(2026, 8, 13, tzinfo=UTC)
HOURLY_PERIODS = 8760.0

SERIES: list[Candle] = asyncio.run(
    CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=700)
)


@cache
def _result(liquidate: bool = True, stops: bool = True) -> BacktestResult:
    engine = BacktestEngine(
        BacktestConfig(
            dataset="fixtures",
            timeframe="1h",
            warmup_bars=120,
            execution=ExecutionSimConfig(
                reject_probability=0.0, partial_fill_probability=0.0
            ),
            liquidate_at_end=liquidate,
            use_protective_stops=stops,
        ),
        DEFAULT_UNIVERSE,
    )
    return engine.run(SERIES)


# --------------------------------------------------------------------------- the loop


def test_a_run_records_one_equity_point_per_bar() -> None:
    result = _result()
    assert len(result.equity_curve) == len(SERIES)
    assert len(result.equity_timestamps) == len(SERIES)
    assert result.equity_timestamps[-1] == SERIES[-1].close_time


def test_warmup_bars_produce_no_decisions() -> None:
    """A decision taken before the slowest feature is meaningful is noise dressed as a
    signal, and it would be counted as evidence alongside the real ones."""
    result = _result()
    first_decision = result.decision_log[0].bar_close_time
    assert first_decision >= SERIES[119].close_time
    assert result.decisions.bars_skipped_insufficient_history >= 119


def test_the_final_bar_takes_no_decision() -> None:
    """Nothing can execute a decision taken on the last bar, so taking one would only
    inflate the signal counts with proposals nothing could act on."""
    assert _result().decision_log[-1].bar_close_time < SERIES[-1].close_time


def test_declines_are_recorded_not_discarded() -> None:
    """Recording *why* the system declined is as valuable as recording why it acted."""
    counts = _result().decisions
    assert counts.signals_by_direction.get(Direction.NO_TRADE.value, 0) > 0
    assert counts.risk_verdicts.get(RiskVerdict.NO_TRADE.value, 0) > 0
    assert counts.risk_rejection_reasons, "the binding gates must be identifiable"
    # Bucketed by check name, not by free-text reason: a reason embeds the numbers, so
    # counting those produces one bucket per bar and identifies nothing.
    assert all(" " not in name for name in counts.risk_rejection_reasons)


def test_approvals_suppressed_by_an_open_position_are_counted() -> None:
    """The gap between "risk approved it" and "an order was sent" is otherwise
    invisible, and it is usually the largest number in the report."""
    counts = _result().decisions
    approved = sum(
        c for v, c in counts.risk_verdicts.items() if RiskVerdict(v).allows_execution
    )
    assert counts.intents_submitted <= approved
    assert (
        counts.intents_submitted + counts.approvals_suppressed_position_open == approved
    )


def test_a_position_open_at_the_end_is_closed_and_flagged() -> None:
    """Reporting an open position's mark as a result lets a losing trade sit unrealised
    at the sample edge and quietly improve every realised-P&L metric."""
    result = _result(liquidate=True)
    assert not result.open_positions_at_end
    forced = [t for t in result.trades if t.exit_reason.startswith("forced liquidation")]
    if forced:
        assert any("force-closed" in w for w in result.warnings)


def test_leaving_a_position_open_is_reported_as_a_caveat() -> None:
    result = _result(liquidate=False)
    if result.open_positions_at_end:
        assert any("unrealised mark" in w for w in result.warnings)


def test_every_trade_carries_the_decision_that_produced_it() -> None:
    """A trade list without provenance shows *what* happened but never *why*, which
    makes it useless for improving anything."""
    for trade in _result().trades:
        assert trade.signal_id
        assert trade.entry_at < trade.exit_at or trade.bars_held == 0
        assert trade.fees >= 0
        assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.fees)


def test_protective_stops_bound_the_loss_on_a_trade() -> None:
    """Without a stop, losses are unbounded and every drawdown figure in the report is
    an artefact of where the sample happened to end."""
    with_stops = _result(stops=True)
    assert with_stops.decisions.protective_stops_unplaced == 0
    stopped = [
        t for t in with_stops.trades if t.exit_reason.startswith("protective stop")
    ]
    assert stopped, "the fixture must exercise the stop path or this proves nothing"


# --------------------------------------------------------------------------- refusals


def test_a_run_needs_at_least_two_bars() -> None:
    engine = BacktestEngine(BacktestConfig(timeframe="1h"), DEFAULT_UNIVERSE)
    with pytest.raises(BacktestError, match="at least two bars"):
        engine.run(SERIES[:1])


def test_mixing_symbols_is_refused() -> None:
    """One symbol at a time. Silently backtesting a mixed series would produce a result
    that describes nothing."""
    other = asyncio.run(
        CsvReplayProvider(FIXTURES).get_candles("ETH-USD", "1m", limit=10)
    )
    engine = BacktestEngine(BacktestConfig(timeframe="1h"), DEFAULT_UNIVERSE)
    with pytest.raises(BacktestError, match="one symbol at a time"):
        engine.run(SERIES[:50] + other)


def test_the_config_digest_changes_when_the_experiment_changes() -> None:
    """Two results can be compared for "were these the same experiment?" without
    trusting a filename."""
    base = BacktestConfig(timeframe="1h")
    assert base.digest() == BacktestConfig(timeframe="1h").digest()
    assert base.digest() != BacktestConfig(timeframe="1h", seed=1).digest()
    assert (
        base.digest()
        != BacktestConfig(
            timeframe="1h", risk=RiskLimits(max_risk_per_trade_pct=0.25)
        ).digest()
    )


# --------------------------------------------------------------------------- honesty


def test_the_evidence_statement_never_promises_anything() -> None:
    """Rule §63. The statement describes one experiment under stated conditions."""
    statement = _result().evidence_statement()
    lowered = statement.lower()
    for forbidden in ("will make", "guarantee", "profitable strategy", "expect to earn"):
        assert forbidden not in lowered
    assert "makes no claim about future results" in lowered
    assert "seed=" in statement
    assert "bars" in statement


def test_a_small_sample_says_so() -> None:
    result = _result()
    if len(result.trades) < MIN_TRADES_FOR_INFERENCE:
        assert any("separate skill from chance" in w for w in result.warnings)


def test_the_conditions_record_everything_needed_to_reproduce_the_run() -> None:
    conditions = _result().conditions
    assert conditions.seed
    assert conditions.strategy_versions
    assert conditions.feature_version
    assert conditions.risk_limits_digest
    assert conditions.execution_config["taker_fee_bps"] > 0
    assert conditions.bars == len(SERIES)


# --------------------------------------------------------------------------- baselines


def test_always_flat_never_moves() -> None:
    baseline = always_flat(SERIES, periods_per_year=HOURLY_PERIODS)
    assert set(baseline.equity_curve) == {100_000.0}
    assert baseline.trades == 0
    assert baseline.metrics.max_drawdown_pct == 0.0


def test_buy_and_hold_tracks_the_asset_minus_costs() -> None:
    """A baseline that trades for free is not a baseline, it is a handicap applied to
    the strategy."""
    asset_return = (SERIES[-1].close / SERIES[0].close - 1.0) * 100.0
    baseline = buy_and_hold(SERIES, periods_per_year=HOURLY_PERIODS)
    assert baseline.total_return_pct < asset_return
    assert baseline.total_return_pct > asset_return - 1.0


def test_a_free_baseline_beats_a_charged_one() -> None:
    free = ExecutionSimConfig(taker_fee_bps=0.0, base_slippage_bps=0.0)
    charged = ExecutionSimConfig(taker_fee_bps=25.0, base_slippage_bps=10.0)
    assert (
        buy_and_hold(SERIES, costs=free, periods_per_year=HOURLY_PERIODS).total_return_pct
        > buy_and_hold(
            SERIES, costs=charged, periods_per_year=HOURLY_PERIODS
        ).total_return_pct
    )


def test_sma_cross_requires_a_shorter_fast_window() -> None:
    with pytest.raises(ValueError, match="shorter than slow"):
        sma_cross(SERIES, fast=50, slow=20)


def test_the_volatility_baseline_sizes_down_when_volatility_rises() -> None:
    """Much of what gets reported as alpha is this effect and nothing more, which is why
    it has to be in the comparison set."""
    calm = volatility_targeted(
        SERIES, target_annual_vol=0.05, periods_per_year=HOURLY_PERIODS
    )
    bold = volatility_targeted(
        SERIES, target_annual_vol=0.60, periods_per_year=HOURLY_PERIODS
    )
    assert abs(bold.total_return_pct) > abs(calm.total_return_pct)


def test_random_entry_is_reproducible_from_its_seed() -> None:
    """A control that changes each time it is run is not a control; it is something to
    rerun until it flatters the strategy."""
    kwargs = {
        "trade_count": 12,
        "average_bars_held": 30,
        "periods_per_year": HOURLY_PERIODS,
    }
    first = random_entry(SERIES, seed=7, **kwargs)  # type: ignore[arg-type]
    again = random_entry(SERIES, seed=7, **kwargs)  # type: ignore[arg-type]
    other = random_entry(SERIES, seed=8, **kwargs)  # type: ignore[arg-type]

    assert first.equity_curve == again.equity_curve
    assert first.equity_curve != other.equity_curve


def test_random_entry_matches_the_strategy_trade_count() -> None:
    """Unmatched, a random baseline trades a different number of times, pays different
    costs and holds for a different duration, so beating it proves nothing."""
    baseline = random_entry(
        SERIES, trade_count=10, average_bars_held=20, periods_per_year=HOURLY_PERIODS
    )
    assert 1 <= baseline.trades <= 10  # adjacent draws can merge into one exposure run


def test_random_entry_with_no_trades_stays_flat() -> None:
    baseline = random_entry(
        SERIES, trade_count=0, average_bars_held=0, periods_per_year=HOURLY_PERIODS
    )
    assert baseline.trades == 0
    assert set(baseline.equity_curve) == {100_000.0}


def test_all_five_baselines_are_produced() -> None:
    """Five, always. A report that quietly drops the one it loses to is not a report."""
    results = run_all_baselines(
        SERIES,
        strategy_trade_count=8,
        strategy_average_bars_held=25,
        periods_per_year=HOURLY_PERIODS,
    )
    assert [b.name for b in results] == [
        "buy_and_hold",
        "sma_cross",
        "volatility_targeted",
        "random_entry",
        "always_flat",
    ]
    assert all(len(b.equity_curve) == len(SERIES) for b in results)


def test_baselines_need_enough_bars() -> None:
    with pytest.raises(ValueError, match="at least three bars"):
        run_all_baselines(
            SERIES[:2], strategy_trade_count=1, strategy_average_bars_held=1
        )


# --------------------------------------------------------------------------- verdicts


def test_a_small_sample_is_inconclusive_regardless_of_the_numbers() -> None:
    """Asking "did it beat the baselines?" before "could this sample answer anything?"
    is how eleven trades become a deployment decision."""
    result = _result()
    assert len(result.trades) < MIN_TRADES_FOR_INFERENCE, "fixture assumption"

    report = evaluate_experiment(result, SERIES, at=NOW)
    assert report.verdict is ExperimentVerdict.INSUFFICIENT_EVIDENCE
    assert any("below the" in r for r in report.reasons)


def test_the_report_lists_every_baseline_it_lost_to() -> None:
    report = evaluate_experiment(_result(), SERIES, at=NOW)
    assert len(report.comparisons) == 5
    assert set(report.beaten_baselines) | set(report.losing_baselines) == {
        c.baseline for c in report.comparisons
    }


def test_a_strategy_is_not_ahead_if_it_paid_for_it_in_drawdown() -> None:
    """One point more return for twice the risk is not an edge; it is leverage, which
    requires no skill."""
    from tia.backtest.experiment import BaselineComparison

    louder = BaselineComparison(
        baseline="buy_and_hold",
        description="",
        strategy_return_pct=11.0,
        baseline_return_pct=10.0,
        strategy_sharpe=0.4,
        baseline_sharpe=1.2,
        strategy_max_drawdown_pct=40.0,
        baseline_max_drawdown_pct=10.0,
    )
    assert not louder.strategy_ahead

    genuine = BaselineComparison(
        baseline="buy_and_hold",
        description="",
        strategy_return_pct=11.0,
        baseline_return_pct=10.0,
        strategy_sharpe=1.4,
        baseline_sharpe=1.2,
        strategy_max_drawdown_pct=9.0,
        baseline_max_drawdown_pct=10.0,
    )
    assert genuine.strategy_ahead


def test_the_verdict_vocabulary_contains_nothing_that_reads_as_a_recommendation() -> None:
    """There is deliberately no ``PROFITABLE``, no ``DEPLOY``, no ``GOOD``."""
    values = {v.value for v in ExperimentVerdict}
    assert values == {
        "insufficient_evidence",
        "no_edge_demonstrated",
        "mixed",
        "beat_all_baselines",
    }


def test_the_experiment_statement_carries_the_full_disclaimer() -> None:
    statement = evaluate_experiment(_result(), SERIES, at=NOW).evidence_statement()
    assert "Not a prediction, not a recommendation" in statement
    assert "Against the mandatory baselines:" in statement
    assert statement.count("  - ") >= 5


def test_an_in_sample_run_is_told_it_measured_fit() -> None:
    """In-sample results measure fit, not edge, and a report that does not say so invites
    exactly the wrong reading."""
    from tia.backtest.experiment import _decide
    from tia.backtest.result import BacktestConditions

    result = _result()
    padded = result.model_copy(
        update={
            "trades": result.trades * 10,  # push past the sample-size gate
            "conditions": result.conditions.model_copy(
                update={"is_out_of_sample": False}
            ),
        }
    )
    assert isinstance(padded.conditions, BacktestConditions)
    _verdict, reasons = _decide(padded, evaluate_experiment(result, SERIES, at=NOW).comparisons)
    assert any("not marked out-of-sample" in r for r in reasons)


def test_a_serialized_report_round_trips_the_essentials() -> None:
    payload = evaluate_experiment(_result(), SERIES, at=NOW).to_dict()
    assert payload["verdict"] in {v.value for v in ExperimentVerdict}
    assert len(payload["baselines"]) == 5
    assert "evidence_statement" in payload["result"]
    assert payload["created_at"].endswith("+00:00")


def test_the_fixture_spans_enough_time_to_be_worth_testing() -> None:
    assert len(SERIES) == 700
    assert SERIES[-1].close_time - SERIES[0].open_time >= timedelta(days=25)
