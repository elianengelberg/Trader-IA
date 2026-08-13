"""Performance statistics.

The behaviour under test is as much about *refusing to answer* as about computing: a
Sharpe ratio from nine observations is noise wearing a decimal point, and reporting it
would be worse than reporting nothing.
"""

from __future__ import annotations

import numpy as np
import pytest

from tia.quant.statistics import (
    MIN_OBSERVATIONS_FOR_RATIOS,
    TradeRecord,
    compute_metrics,
    conditional_var,
    correlation_matrix,
    drawdown_series,
    expectancy,
    max_drawdown,
    profit_factor,
    returns_from_equity,
    sharpe_ratio,
    sortino_ratio,
    stability_of_returns,
    value_at_risk,
)

BARS_PER_YEAR = 252.0


def trade(pnl: float, ret: float = 1.0, fees: float = 0.0) -> TradeRecord:
    return TradeRecord(
        symbol="BTC-USD",
        pnl=pnl,
        return_pct=ret,
        duration_seconds=3600,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        quantity=1.0,
        fees=fees,
    )


class TestBasics:
    def test_returns_from_equity(self) -> None:
        out = returns_from_equity([100.0, 110.0, 99.0])
        assert out[0] == pytest.approx(0.10)
        assert out[1] == pytest.approx(-0.10)

    def test_drawdown_is_zero_on_a_monotonic_curve(self) -> None:
        assert np.all(drawdown_series([100.0, 110.0, 120.0]) == 0.0)

    def test_max_drawdown_and_duration(self) -> None:
        equity = [100.0, 120.0, 90.0, 95.0, 130.0]
        dd, duration = max_drawdown(equity)
        assert dd == pytest.approx(25.0)  # 120 -> 90
        assert duration == 2  # two bars below the peak

    def test_profit_factor(self) -> None:
        assert profit_factor([10.0, -5.0, 20.0, -5.0]) == pytest.approx(3.0)

    def test_profit_factor_without_losses_is_infinite(self) -> None:
        assert profit_factor([10.0, 20.0]) == float("inf")

    def test_expectancy_is_the_mean(self) -> None:
        assert expectancy([10.0, -5.0, 25.0]) == pytest.approx(10.0)

    def test_empty_inputs_return_none(self) -> None:
        assert profit_factor([]) is None
        assert expectancy([]) is None


class TestRefusalToOverclaim:
    def test_sharpe_is_withheld_below_the_minimum_sample(self) -> None:
        short = [0.01] * (MIN_OBSERVATIONS_FOR_RATIOS - 1)
        assert sharpe_ratio(short, periods_per_year=BARS_PER_YEAR) is None

    def test_sharpe_is_computed_once_the_sample_suffices(self) -> None:
        rng = np.random.default_rng(1)
        rets = rng.normal(0.001, 0.01, 500)
        assert sharpe_ratio(rets, periods_per_year=BARS_PER_YEAR) is not None

    def test_zero_variance_returns_none_not_infinity(self) -> None:
        assert sharpe_ratio([0.01] * 100, periods_per_year=BARS_PER_YEAR) is None

    def test_sortino_without_a_losing_period_returns_none(self) -> None:
        """No downside in the sample means an unrepresentative sample, not perfection."""
        assert sortino_ratio([0.01] * 100, periods_per_year=BARS_PER_YEAR) is None

    def test_short_period_is_not_annualized(self) -> None:
        metrics = compute_metrics(
            equity_curve=[100.0, 101.0, 102.0], periods_per_year=BARS_PER_YEAR
        )
        assert metrics.annualized_return_pct is None
        assert any("annualize" in w for w in metrics.warnings)

    def test_small_trade_count_is_warned_about(self) -> None:
        metrics = compute_metrics(
            equity_curve=list(np.linspace(100, 110, 100)),
            trades=[trade(5.0), trade(-2.0)],
            periods_per_year=BARS_PER_YEAR,
        )
        assert any("only 2 trades" in w for w in metrics.warnings)
        assert metrics.is_reliable() is False

    def test_var_needs_a_sample(self) -> None:
        assert value_at_risk([0.01] * 5) is None
        assert conditional_var([0.01] * 5) is None


class TestFullMetrics:
    @pytest.fixture
    def rising_equity(self) -> list[float]:
        rng = np.random.default_rng(7)
        rets = rng.normal(0.0008, 0.01, 600)
        return list(100_000 * np.cumprod(1 + rets))

    def test_computes_a_coherent_summary(self, rising_equity: list[float]) -> None:
        trades = [trade(120.0), trade(-60.0), trade(200.0), trade(-40.0)] * 6
        metrics = compute_metrics(
            equity_curve=rising_equity,
            trades=trades,
            periods_per_year=BARS_PER_YEAR,
            bars_in_market=300,
        )
        assert metrics.observations == len(rising_equity) - 1
        assert metrics.trades == 24
        assert metrics.sharpe is not None
        assert metrics.win_rate == pytest.approx(0.5)
        assert metrics.max_drawdown_pct >= 0
        assert metrics.exposure_pct == pytest.approx(50.0, abs=0.5)
        assert metrics.is_reliable() is True

    def test_losing_curve_reports_negative_return(self) -> None:
        equity = list(np.linspace(100_000, 80_000, 400))
        metrics = compute_metrics(equity_curve=equity, periods_per_year=BARS_PER_YEAR)
        assert metrics.total_return_pct < 0
        assert metrics.max_drawdown_pct == pytest.approx(20.0, abs=0.1)

    def test_calmar_relates_return_to_drawdown(self) -> None:
        rng = np.random.default_rng(9)
        equity = list(100_000 * np.cumprod(1 + rng.normal(0.001, 0.01, 400)))
        metrics = compute_metrics(equity_curve=equity, periods_per_year=BARS_PER_YEAR)
        if metrics.calmar is not None and metrics.annualized_return_pct is not None:
            assert metrics.calmar == pytest.approx(
                metrics.annualized_return_pct / metrics.max_drawdown_pct, rel=1e-6
            )

    def test_stability_distinguishes_steady_from_lucky(self) -> None:
        """Same total return, very different quality of return."""
        steady = list(np.linspace(100.0, 200.0, 300))
        lucky = [100.0] * 299 + [200.0]
        assert stability_of_returns(steady) > 0.98
        assert stability_of_returns(lucky) < 0.5

    def test_fees_are_totalled(self) -> None:
        metrics = compute_metrics(
            equity_curve=list(np.linspace(100, 110, 100)),
            trades=[trade(5.0, fees=1.5), trade(-2.0, fees=1.5)],
            periods_per_year=BARS_PER_YEAR,
        )
        assert metrics.total_fees == pytest.approx(3.0)

    def test_too_short_curve_returns_an_empty_summary(self) -> None:
        metrics = compute_metrics(equity_curve=[100.0], periods_per_year=BARS_PER_YEAR)
        assert metrics.observations == 1
        assert metrics.sharpe is None
        assert "too short" in metrics.warnings[0]

    def test_summary_line_is_readable(self, rising_equity: list[float]) -> None:
        metrics = compute_metrics(equity_curve=rising_equity, periods_per_year=BARS_PER_YEAR)
        line = metrics.summary_line()
        assert "return=" in line and "maxDD=" in line


class TestCorrelation:
    def test_identical_series_correlate_at_one(self) -> None:
        rng = np.random.default_rng(2)
        a = rng.normal(0, 1, 100)
        result = correlation_matrix({"A": a, "B": a})
        assert result[("A", "B")] == pytest.approx(1.0)

    def test_inverted_series_correlate_at_minus_one(self) -> None:
        rng = np.random.default_rng(3)
        a = rng.normal(0, 1, 100)
        result = correlation_matrix({"A": a, "B": -a})
        assert result[("A", "B")] == pytest.approx(-1.0)

    def test_matrix_is_symmetric(self) -> None:
        rng = np.random.default_rng(4)
        result = correlation_matrix({"A": rng.normal(0, 1, 80), "B": rng.normal(0, 1, 80)})
        assert result[("A", "B")] == result[("B", "A")]

    def test_unequal_lengths_are_aligned_to_the_common_tail(self) -> None:
        """Correlating a 500-bar series against a 50-bar one by index is a silent bug."""
        rng = np.random.default_rng(5)
        long = rng.normal(0, 1, 500)
        short = long[-50:]
        assert correlation_matrix({"A": long, "B": short})[("A", "B")] == pytest.approx(1.0)

    def test_constant_series_correlates_at_zero_not_nan(self) -> None:
        result = correlation_matrix({"A": [1.0] * 50, "B": list(range(50))})
        assert result[("A", "B")] == 0.0
