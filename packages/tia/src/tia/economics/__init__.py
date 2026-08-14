"""Cost and expected-value engines.

The question these answer is the one that separates a signal generator from a trading
system: **does this edge survive its own costs?**
"""

from tia.economics.costs import BPS, CostModel, FeeSchedule, MarketConditions, TradeCosts
from tia.economics.expected_value import (
    CONFIDENCE_BANDS,
    MIN_SAMPLES_FOR_EDGE,
    EdgeEstimate,
    EdgeEstimator,
    ExpectedValue,
    ExpectedValueEngine,
    Outcome,
    band_of,
)

__all__ = [
    "BPS",
    "CONFIDENCE_BANDS",
    "MIN_SAMPLES_FOR_EDGE",
    "CostModel",
    "EdgeEstimate",
    "EdgeEstimator",
    "ExpectedValue",
    "ExpectedValueEngine",
    "FeeSchedule",
    "MarketConditions",
    "Outcome",
    "TradeCosts",
    "band_of",
]
