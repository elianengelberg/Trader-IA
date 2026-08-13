"""Deterministic quantitative computation.

Every number describing markets or performance originates here, in tested code. The
language model never produces one.
"""

from tia.quant.features import FEATURE_VERSION, FeatureBuilder, FeatureSet
from tia.quant.statistics import (
    MIN_OBSERVATIONS_FOR_RATIOS,
    PerformanceMetrics,
    TradeRecord,
    compute_metrics,
    correlation_matrix,
    drawdown_series,
    max_drawdown,
    returns_from_equity,
    sharpe_ratio,
    sortino_ratio,
)

__all__ = [
    "FEATURE_VERSION",
    "MIN_OBSERVATIONS_FOR_RATIOS",
    "FeatureBuilder",
    "FeatureSet",
    "PerformanceMetrics",
    "TradeRecord",
    "compute_metrics",
    "correlation_matrix",
    "drawdown_series",
    "max_drawdown",
    "returns_from_equity",
    "sharpe_ratio",
    "sortino_ratio",
]
