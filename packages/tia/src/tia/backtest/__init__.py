"""Backtesting — the runtime, driven by historical bars.

Nothing in this package makes a claim about future returns. A result describes what one
configuration produced on one dataset under one cost model;
:meth:`ExperimentReport.evidence_statement` is the only sanctioned way to state it in
prose, and the strongest verdict available is "beat all baselines on this dataset".
"""

from tia.backtest.baselines import (
    BaselineResult,
    always_flat,
    buy_and_hold,
    random_entry,
    run_all_baselines,
    sma_cross,
    volatility_targeted,
)
from tia.backtest.engine import MIN_TRADES_FOR_INFERENCE, BacktestConfig, BacktestEngine
from tia.backtest.experiment import (
    BaselineComparison,
    ExperimentReport,
    ExperimentVerdict,
    evaluate_experiment,
)
from tia.backtest.result import (
    BacktestConditions,
    BacktestResult,
    ClosedTrade,
    DecisionCounts,
)
from tia.backtest.walkforward import (
    Fold,
    SplitScheme,
    WalkForwardPlan,
    assert_no_leakage,
    build_plan,
)

__all__ = [
    "MIN_TRADES_FOR_INFERENCE",
    "BacktestConditions",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BaselineComparison",
    "BaselineResult",
    "ClosedTrade",
    "DecisionCounts",
    "ExperimentReport",
    "ExperimentVerdict",
    "Fold",
    "SplitScheme",
    "WalkForwardPlan",
    "always_flat",
    "assert_no_leakage",
    "build_plan",
    "buy_and_hold",
    "evaluate_experiment",
    "random_entry",
    "run_all_baselines",
    "sma_cross",
    "volatility_targeted",
]
