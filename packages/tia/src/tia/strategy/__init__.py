"""Strategies, fusion and the signal engine."""

from tia.strategy.base import Strategy
from tia.strategy.engine import StrategyEngine
from tia.strategy.fusion import (
    FusionResult,
    FusionWeights,
    context_factor,
    data_quality_factor,
    fuse,
)
from tia.strategy.library import (
    STRATEGY_REGISTRY,
    BreakoutStrategy,
    MeanReversionStrategy,
    TrendFollowingStrategy,
    build_strategies,
)

__all__ = [
    "STRATEGY_REGISTRY",
    "BreakoutStrategy",
    "FusionResult",
    "FusionWeights",
    "MeanReversionStrategy",
    "Strategy",
    "StrategyEngine",
    "TrendFollowingStrategy",
    "build_strategies",
    "context_factor",
    "data_quality_factor",
    "fuse",
]
