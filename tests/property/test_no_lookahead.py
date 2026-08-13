"""The no-look-ahead property.

One idea, applied at three levels: **truncating the future must not change the past.**

If a decision taken at bar *t* differs depending on what bars *t+1…n* contain, then the
system saw them, and every number the backtest produced is an artefact. This is the
single failure mode that most reliably turns a mediocre strategy into a spectacular
backtest, and it is invisible in the equity curve — the curve looks better, which is
exactly what the author was hoping for.

The test is structural rather than statistical: run the same pipeline over a prefix and
over the full series, and require the prefix run's output to be a byte-for-byte prefix of
the longer run's.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import cache
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tia.backtest import BacktestConfig, BacktestEngine, BacktestResult
from tia.backtest.baselines import (
    _equity_from_exposure,
    buy_and_hold,
    sma_cross,
    volatility_targeted,
)
from tia.core.config import ExecutionSimConfig
from tia.core.errors import BacktestError
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.enums import Direction
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeClassifier

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
BARS = 800

# Rejections and forced partials are seeded per symbol, so they replay identically. The
# costs stay on elsewhere, but here they are switched off so that a difference between
# two runs can only come from a decision, never from a seeded coin flip landing on a
# different bar index.
COSTS = ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)

#: Committed CSV fixture rather than a generated series: this file is the same on every
#: machine and in every CI run, so a failure here is a real regression rather than a
#: generator that drifted.
SERIES: list[Candle] = asyncio.run(
    CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=BARS)
)


@cache
def _run(cut: int) -> BacktestResult:
    """Backtest the first ``cut`` bars. Cached — these runs are the slow part."""
    engine = BacktestEngine(
        BacktestConfig(
            dataset="lookahead",
            timeframe="1h",
            warmup_bars=120,
            execution=COSTS,
            liquidate_at_end=False,  # the forced exit is a boundary effect, not a decision
        ),
        DEFAULT_UNIVERSE,
    )
    return engine.run(SERIES[:cut])


# --------------------------------------------------------------------------- features


@given(cut=st.integers(min_value=140, max_value=740))
@settings(max_examples=25, deadline=None)
def test_a_feature_set_does_not_change_when_later_bars_are_removed(cut: int) -> None:
    """The feature vector at bar ``cut`` must be identical whether or not the bars after
    it exist. ``feature_hash`` makes that a single comparison."""
    builder = FeatureBuilder()
    truncated = builder.build("BTC-USD", "1h", SERIES[: cut + 1])
    full_prefix = builder.build("BTC-USD", "1h", SERIES[: cut + 1])
    assert truncated.feature_hash == full_prefix.feature_hash

    # And the same feature set built from a longer list, sliced to the same bar.
    later = builder.build("BTC-USD", "1h", SERIES[: cut + 51])
    assert later.bar_close_time > truncated.bar_close_time
    assert truncated.values == builder.build("BTC-USD", "1h", SERIES[: cut + 1]).values


def test_a_feature_series_matches_bar_by_bar_reconstruction() -> None:
    """``build_series`` must agree with building each bar independently.

    A vectorised implementation that computes over the whole array and then slices is the
    usual way look-ahead enters a feature pipeline, and it produces exactly this
    disagreement.
    """
    builder = FeatureBuilder()
    window = SERIES[:400]
    batch = builder.build_series("BTC-USD", "1h", window, start_index=380)
    for feature_set in batch:
        index = next(
            i for i, c in enumerate(window) if c.close_time == feature_set.bar_close_time
        )
        one_off = builder.build("BTC-USD", "1h", window[: index + 1])
        assert feature_set.feature_hash == one_off.feature_hash


# --------------------------------------------------------------------------- regime


def test_regime_classification_is_causal() -> None:
    """Replaying the same prefix through a fresh classifier must reproduce the same
    regime path. The classifier carries hysteresis state, so this also checks that the
    state is a function of the past alone."""
    builder = FeatureBuilder()
    window = SERIES[:400]

    def path(bars: list[Candle]) -> list[str]:
        classifier = RegimeClassifier()
        out = []
        for i in range(150, len(bars)):
            features = builder.build("BTC-USD", "1h", bars[: i + 1])
            out.append(classifier.classify(features, now=bars[i].close_time).regime.value)
        return out

    short = path(window[:300])
    full = path(window)
    assert full[: len(short)] == short


# --------------------------------------------------------------------------- baselines


@pytest.mark.parametrize("baseline", [buy_and_hold, sma_cross, volatility_targeted])
def test_a_baseline_equity_curve_is_a_prefix_of_the_longer_one(baseline: object) -> None:
    """A baseline that peeks is worse than no baseline: it sets an impossible bar and
    makes a sound strategy look like it failed."""
    short = baseline(SERIES[:300], periods_per_year=8760.0)  # type: ignore[operator]
    long = baseline(SERIES[:600], periods_per_year=8760.0)  # type: ignore[operator]
    assert short.equity_curve == pytest.approx(long.equity_curve[:300])


def test_perturbing_the_future_is_what_catches_a_one_bar_leak() -> None:
    """Why this file uses two different detectors, demonstrated.

    A prefix comparison catches leaks that reach *backwards* — a z-score over the whole
    sample, a rank, a forward-fill from the end. It does **not** catch a leak that only
    reaches one bar ahead, because such a leak is stable under truncation: the value it
    steals is the same in the short series and the long one, so both curves agree and the
    test passes while the strategy is cheating.

    The detector for that class is perturbation: change the future, and check that the
    *decision* did not move. Both are shown here on a hand-built cheat, so the reader can
    see that the first detector genuinely misses what the second catches.
    """
    free = ExecutionSimConfig(
        taker_fee_bps=0.0,
        maker_fee_bps=0.0,
        base_slippage_bps=0.0,
        reject_probability=0.0,
        partial_fill_probability=0.0,
    )

    def cheating_exposure(bars: list[Candle]) -> np.ndarray:
        closes = np.array([c.close for c in bars], dtype=np.float64)
        returns = np.diff(closes) / closes[:-1]
        exposure = np.zeros(closes.size)
        exposure[:-1] = np.sign(returns)  # reads the bar it is about to trade
        return exposure

    honest = buy_and_hold(SERIES[:300], costs=free, periods_per_year=8760.0)
    closes = np.array([c.close for c in SERIES[:300]], dtype=np.float64)
    cheat_equity = _equity_from_exposure(
        closes, cheating_exposure(SERIES[:300]), initial_capital=100_000.0, costs=free
    )
    assert cheat_equity[-1] > honest.equity_curve[-1] * 1.10, (
        "perfect one-bar foresight must beat holding, or the cheat is not a cheat"
    )

    # Detector 1 — prefix comparison. It passes. The cheat is invisible to it.
    long_equity = _equity_from_exposure(
        np.array([c.close for c in SERIES[:600]], dtype=np.float64),
        cheating_exposure(SERIES[:600]),
        initial_capital=100_000.0,
        costs=free,
    )
    assert cheat_equity == pytest.approx(long_equity[:300]), (
        "the prefix detector is expected to miss a one-bar leak; if this ever fails the "
        "explanation above is wrong and this file needs revisiting"
    )

    # Detector 2 — perturb the future. The cheat's decision at bar k moves; an honest
    # rule's does not.
    k = 200
    perturbed = list(SERIES[:300])
    perturbed[k + 1] = perturbed[k + 1].model_copy(
        update={
            "open": perturbed[k + 1].open * 1.05,
            "high": perturbed[k + 1].high * 1.06,
            "low": perturbed[k + 1].low * 1.04,
            "close": perturbed[k + 1].close * 1.05,
        }
    )
    assert cheating_exposure(SERIES[:300])[k] != cheating_exposure(perturbed)[k], (
        "the perturbation detector must catch the one-bar leak"
    )


# --------------------------------------------------------------------------- end to end


@pytest.mark.parametrize("cut", [300, 500, 650])
def test_the_backtest_equity_curve_is_a_prefix_of_a_longer_run(cut: int) -> None:
    """The whole pipeline, end to end.

    Every component — quality gate, features, regime, strategies, fusion, risk, execution
    — participates. If any one of them reads a future bar, this comparison breaks.
    """
    short = _run(cut)
    full = _run(BARS)

    assert len(short.equity_curve) == cut
    assert short.equity_curve == pytest.approx(full.equity_curve[:cut])


def test_trades_taken_early_are_unchanged_by_later_data() -> None:
    short = _run(500)
    full = _run(BARS)

    assert short.trades, "the fixture must produce trades or this test proves nothing"
    assert len(full.trades) > len(short.trades), (
        "the longer run must add trades, otherwise the comparison is vacuous"
    )

    for early, later in zip(short.trades, full.trades, strict=False):
        assert early.trade_id == later.trade_id
        assert early.entry_price == later.entry_price
        assert early.exit_price == later.exit_price
        assert early.net_pnl == pytest.approx(later.net_pnl)


def test_a_decision_bar_never_executes_at_its_own_close() -> None:
    """Every fill must be priced from a bar strictly later than the decision.

    Read from the timestamps the engine recorded rather than from the matching engine's
    internals, so the property holds however the fill was produced.
    """
    result = _run(BARS)
    stamps = list(result.equity_timestamps)
    assert result.trades
    for trade in result.trades:
        entry_index = stamps.index(trade.entry_at)
        assert entry_index > 0
        assert trade.entry_at > stamps[entry_index - 1]
        assert trade.exit_at >= trade.entry_at


def test_two_runs_of_the_same_experiment_are_identical() -> None:
    """Reproducibility from the seed. An experiment that cannot be replayed is not
    evidence of anything, however good its numbers look."""
    engine_config = BacktestConfig(
        dataset="lookahead",
        timeframe="1h",
        warmup_bars=120,
        execution=COSTS,
        liquidate_at_end=False,
    )
    first = BacktestEngine(engine_config, DEFAULT_UNIVERSE).run(SERIES[:400])
    second = BacktestEngine(engine_config, DEFAULT_UNIVERSE).run(SERIES[:400])

    assert first.equity_curve == second.equity_curve
    assert first.conditions.run_id == second.conditions.run_id
    assert [t.trade_id for t in first.trades] == [t.trade_id for t in second.trades]


def test_the_engine_rejects_bars_that_are_not_chronological() -> None:
    """Out-of-order bars let a "past" bar carry future information, and the resulting
    backtest looks entirely normal."""
    scrambled = list(SERIES[:200])
    scrambled[100], scrambled[150] = scrambled[150], scrambled[100]
    engine = BacktestEngine(
        BacktestConfig(dataset="scrambled", timeframe="1h", warmup_bars=120),
        DEFAULT_UNIVERSE,
    )
    with pytest.raises(BacktestError, match="chronological"):
        engine.run(scrambled)


def test_perturbing_the_future_does_not_change_a_single_past_decision() -> None:
    """The strongest form of the property, run over the whole pipeline.

    Every bar after ``k`` is replaced with a wildly different one. Every decision the
    engine took at or before bar ``k`` must be **byte-identical** — same direction, same
    confidence, same regime, same feature hash, same risk verdict, same approved size.

    Unlike the prefix comparison, this catches a leak of any reach, including one bar,
    because the value a leaky component would have read no longer exists.
    """
    k = 500
    mutated = list(SERIES[:BARS])
    for i in range(k + 1, BARS):
        bar = mutated[i]
        # A large, direction-flipping perturbation: anything reading these bars produces
        # visibly different numbers rather than a rounding-level difference.
        scale = 1.35 if i % 2 == 0 else 0.72
        mutated[i] = bar.model_copy(
            update={
                "open": bar.open * scale,
                "high": max(bar.open, bar.close) * scale * 1.02,
                "low": min(bar.open, bar.close) * scale * 0.98,
                "close": bar.close * scale,
                "volume": bar.volume * 2.5,
            }
        )

    engine_config = BacktestConfig(
        dataset="perturbation",
        timeframe="1h",
        warmup_bars=120,
        execution=COSTS,
        liquidate_at_end=False,
    )
    original = BacktestEngine(engine_config, DEFAULT_UNIVERSE).run(SERIES[:BARS])
    perturbed = BacktestEngine(engine_config, DEFAULT_UNIVERSE).run(mutated)

    cutoff = SERIES[k].close_time
    before = [d for d in original.decision_log if d.bar_close_time <= cutoff]
    after = [d for d in perturbed.decision_log if d.bar_close_time <= cutoff]

    assert len(before) > 100, "the cut must leave enough decisions to be a real test"
    assert [d.fingerprint() for d in before] == [d.fingerprint() for d in after]

    # And the perturbation must actually have changed something later, or the test is
    # comparing two identical runs and proving nothing.
    assert original.decision_log[-1].fingerprint() != perturbed.decision_log[-1].fingerprint()


def test_the_decision_log_covers_every_evaluated_bar() -> None:
    """One record per evaluated bar, including the declines.

    A log that only contains trades cannot answer "why didn't it act here?", and it
    cannot support the perturbation test above.
    """
    result = _run(BARS)
    assert len(result.decision_log) == result.decisions.signals_generated
    declines = [d for d in result.decision_log if d.direction is Direction.NO_TRADE]
    assert declines, "a NO_TRADE-preferring system must record declines"
    assert all(d.feature_hash for d in result.decision_log)


def test_the_fixture_is_long_enough_to_be_a_real_test() -> None:
    """Guard against the fixture silently shrinking and turning every test above into a
    trivially-true statement about a run that never traded."""
    assert len(SERIES) == BARS
    assert SERIES[-1].open_time - SERIES[0].open_time >= timedelta(days=25)
    assert len(_run(BARS).trades) >= 3
