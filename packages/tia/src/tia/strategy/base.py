"""Strategy interface.

A strategy produces an *opinion*, never an order. It sees features and a regime, and
returns a direction with a strength in ``[0, 1]`` plus the evidence for it. It does not
know about position size, capital, or risk limits — those belong to the Risk Engine, and
keeping the boundary sharp is what stops sizing logic from being reinvented three times
with three different answers.

Every strategy must:

* be **deterministic** — same features in, same opinion out, always;
* provide a **stop reference** on any actionable opinion, because a position without a
  predefined invalidation level cannot be sized by the risk engine and has undefined risk;
* declare **invalidation conditions** in plain language, so a human reviewing the decision
  later can tell whether the thesis was wrong or merely unlucky.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from tia.domain.enums import Direction, MarketRegime
from tia.domain.signals import Evidence, StrategyOpinion
from tia.quant.features import FeatureSet
from tia.regime.classifier import RegimeAssessment


class Strategy(ABC):
    """Base class for all deterministic strategies."""

    #: Stable identifier, referenced by persisted signals and config weights.
    strategy_id: str = "base"
    #: Bumped whenever the logic changes in a way that alters output.
    version: str = "1.0.0"
    #: Regimes in which this strategy is allowed to express an opinion.
    preferred_regimes: frozenset[MarketRegime] = frozenset()
    #: Minimum bars of history the strategy needs.
    min_bars: int = 120

    @abstractmethod
    def evaluate(self, features: FeatureSet, regime: RegimeAssessment) -> StrategyOpinion:
        """Return this strategy's view of the current bar."""

    def applies_in(self, regime: MarketRegime) -> bool:
        """Whether this strategy should be consulted at all in ``regime``.

        A strategy that stays silent in a regime it was not designed for is more useful
        than one that contributes a weak, meaningless vote to the fusion.
        """
        if regime.is_hostile:
            return False
        return not self.preferred_regimes or regime in self.preferred_regimes

    def _no_trade(
        self, features: FeatureSet, reason: str, *, metrics: dict[str, float] | None = None
    ) -> StrategyOpinion:
        """Helper for the common "nothing to do here" outcome."""
        return StrategyOpinion(
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            symbol=features.symbol,
            direction=Direction.NO_TRADE,
            strength=0.0,
            entry_reference=features.get("close", 1.0),
            evidence=(Evidence(claim=reason, weight=0.0),),
            metrics=metrics or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} id={self.strategy_id} v{self.version}>"


__all__ = ["Strategy"]
