"""The learning layer: what the system takes forward from its own closed trades.

The Expected Value Engine (:mod:`tia.economics.expected_value`) is where learning *acts* —
it estimates edge from realised outcomes and refuses buckets it has no evidence for. This
package is where learning becomes *legible*: the retrospective engine turns each closed
trade into a categorised, readable lesson, accumulates per-pattern memory, and derives
guardrails that make the system warier of exactly the patterns that have disappointed
before. It only ever tightens; it never invents an edge.
"""

from tia.learning.retrospective import (
    Guardrail,
    LessonCategory,
    PatternMemory,
    RetrospectiveEngine,
    TradeReview,
)

__all__ = [
    "Guardrail",
    "LessonCategory",
    "PatternMemory",
    "RetrospectiveEngine",
    "TradeReview",
]
