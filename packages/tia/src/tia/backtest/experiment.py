"""Experiments — a strategy result, its baselines, and an honest verdict.

The rule this module exists to enforce (§63): **never state that a strategy wins.** State
what one experiment produced, under which conditions, against which alternatives, and say
plainly when the evidence cannot support a conclusion — which, for most experiments, is
the correct answer.

:class:`ExperimentVerdict` has no value meaning "good". The best available outcome is
``BEAT_ALL_BASELINES``, which is a statement about a comparison on one dataset, not a
judgement about the strategy. There is deliberately no method anywhere in this package
that turns a result into a recommendation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from tia.backtest.baselines import BaselineResult, run_all_baselines
from tia.backtest.engine import MIN_TRADES_FOR_INFERENCE
from tia.backtest.result import BacktestResult
from tia.backtest.walkforward import WalkForwardPlan
from tia.core.config import ExecutionSimConfig
from tia.core.logging import get_logger
from tia.domain.instruments import Timeframe
from tia.domain.market import Candle

_log = get_logger("backtest.experiment")


class ExperimentVerdict(StrEnum):
    """What an experiment is entitled to conclude.

    Note what is missing: there is no ``PROFITABLE``, no ``DEPLOY``, no ``GOOD``. The
    strongest available verdict says the configuration beat its baselines *on this
    dataset*, which is a fact about a comparison and not a property of the strategy.
    """

    #: The sample cannot support a conclusion in either direction. The most common and
    #: most frequently ignored outcome.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    #: Beaten by at least one thing anyone could have done without the strategy.
    NO_EDGE_DEMONSTRATED = "no_edge_demonstrated"
    #: Better than some baselines, worse than others.
    MIXED = "mixed"
    #: Better than every baseline on this dataset, under these costs.
    BEAT_ALL_BASELINES = "beat_all_baselines"


@dataclass(frozen=True)
class BaselineComparison:
    """The strategy against one baseline, on the metrics that matter."""

    baseline: str
    description: str
    strategy_return_pct: float
    baseline_return_pct: float
    strategy_sharpe: float | None
    baseline_sharpe: float | None
    strategy_max_drawdown_pct: float
    baseline_max_drawdown_pct: float

    @property
    def return_difference_pct(self) -> float:
        return self.strategy_return_pct - self.baseline_return_pct

    @property
    def strategy_ahead(self) -> bool:
        """Ahead on return *and* not materially worse on drawdown.

        Both, because a strategy that earns one point more while risking twice as much
        has not beaten anything — it has taken more risk, which requires no skill.
        """
        if self.strategy_return_pct <= self.baseline_return_pct:
            return False
        allowance = max(self.baseline_max_drawdown_pct * 1.25, 1e-9)
        return self.strategy_max_drawdown_pct <= allowance

    def describe(self) -> str:
        verdict = "ahead of" if self.strategy_ahead else "not ahead of"
        return (
            f"{verdict} {self.baseline}: "
            f"{self.strategy_return_pct:+.2f}% vs {self.baseline_return_pct:+.2f}% "
            f"(maxDD {self.strategy_max_drawdown_pct:.2f}% vs "
            f"{self.baseline_max_drawdown_pct:.2f}%)"
        )


@dataclass(frozen=True)
class ExperimentReport:
    """Everything one experiment is entitled to say."""

    experiment_id: str
    created_at: datetime
    result: BacktestResult
    baselines: tuple[BaselineResult, ...]
    comparisons: tuple[BaselineComparison, ...]
    verdict: ExperimentVerdict
    reasons: tuple[str, ...]
    walk_forward: WalkForwardPlan | None = None

    @property
    def beaten_baselines(self) -> tuple[str, ...]:
        return tuple(c.baseline for c in self.comparisons if c.strategy_ahead)

    @property
    def losing_baselines(self) -> tuple[str, ...]:
        return tuple(c.baseline for c in self.comparisons if not c.strategy_ahead)

    def evidence_statement(self) -> str:
        """The full, quotable statement of what this experiment showed."""
        lines = [self.result.evidence_statement(), "", "Against the mandatory baselines:"]
        lines.extend(f"  - {c.describe()}" for c in self.comparisons)
        lines.append("")
        lines.append(f"Verdict: {self.verdict.value.replace('_', ' ')}.")
        lines.extend(f"  - {reason}" for reason in self.reasons)
        if self.walk_forward is not None:
            lines.append(f"  - {self.walk_forward.describe()}")
        lines.append("")
        lines.append(
            "Past behaviour on one dataset under one cost model. Not a prediction, not a"
            " recommendation, and not evidence that the same configuration will behave"
            " this way on data it has not seen."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "created_at": self.created_at.isoformat(),
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "result": self.result.to_dict(),
            "baselines": [
                {
                    "name": b.name,
                    "description": b.description,
                    "total_return_pct": b.total_return_pct,
                    "sharpe": b.metrics.sharpe,
                    "max_drawdown_pct": b.metrics.max_drawdown_pct,
                    "trades": b.trades,
                }
                for b in self.baselines
            ],
            "comparisons": [c.describe() for c in self.comparisons],
            "walk_forward": self.walk_forward.describe() if self.walk_forward else None,
        }


def _average_bars_held(result: BacktestResult) -> int:
    if not result.trades:
        return 0
    return max(1, round(sum(t.bars_held for t in result.trades) / len(result.trades)))


def evaluate_experiment(
    result: BacktestResult,
    candles: Sequence[Candle],
    *,
    at: datetime,
    costs: ExecutionSimConfig | None = None,
    walk_forward: WalkForwardPlan | None = None,
    baselines: Sequence[BaselineResult] | None = None,
) -> ExperimentReport:
    """Compare a result against every mandatory baseline and assign a verdict.

    The random-entry baseline is matched to this result's trade count and average holding
    period, so it pays comparable costs and carries comparable exposure. An unmatched
    random baseline is not a control.
    """
    costs = costs or ExecutionSimConfig()
    periods = Timeframe.parse(result.conditions.timeframe).bars_per_year()

    computed = list(
        baselines
        if baselines is not None
        else run_all_baselines(
            candles,
            strategy_trade_count=len(result.trades),
            strategy_average_bars_held=_average_bars_held(result),
            initial_capital=result.conditions.initial_capital,
            costs=costs,
            periods_per_year=periods,
            seed=result.conditions.seed,
        )
    )

    comparisons = tuple(
        BaselineComparison(
            baseline=b.name,
            description=b.description,
            strategy_return_pct=result.metrics.total_return_pct,
            baseline_return_pct=b.metrics.total_return_pct,
            strategy_sharpe=result.metrics.sharpe,
            baseline_sharpe=b.metrics.sharpe,
            strategy_max_drawdown_pct=result.metrics.max_drawdown_pct,
            baseline_max_drawdown_pct=b.metrics.max_drawdown_pct,
        )
        for b in computed
    )

    verdict, reasons = _decide(result, comparisons)

    _log.info(
        "experiment_evaluated",
        run_id=result.conditions.run_id,
        verdict=verdict.value,
        trades=len(result.trades),
        baselines_beaten=sum(1 for c in comparisons if c.strategy_ahead),
    )

    return ExperimentReport(
        experiment_id=f"exp-{result.conditions.run_id}",
        created_at=at,
        result=result,
        baselines=tuple(computed),
        comparisons=comparisons,
        verdict=verdict,
        reasons=reasons,
        walk_forward=walk_forward,
    )


def _decide(
    result: BacktestResult, comparisons: Sequence[BaselineComparison]
) -> tuple[ExperimentVerdict, tuple[str, ...]]:
    """Assign a verdict, sample-size question first.

    Order matters. Asking "did it beat the baselines?" before "could this sample answer
    anything?" is how eleven trades become a deployment decision.
    """
    reasons: list[str] = []

    if len(result.trades) < MIN_TRADES_FOR_INFERENCE:
        reasons.append(
            f"{len(result.trades)} closed trades is below the {MIN_TRADES_FOR_INFERENCE} "
            "needed to separate skill from chance; no comparison below is conclusive"
        )
        return (ExperimentVerdict.INSUFFICIENT_EVIDENCE, tuple(reasons))

    if not result.conditions.is_out_of_sample:
        reasons.append(
            "this run was not marked out-of-sample; in-sample results measure fit, "
            "not edge"
        )

    ahead = [c for c in comparisons if c.strategy_ahead]
    behind = [c for c in comparisons if not c.strategy_ahead]

    if not behind:
        reasons.append(
            "ahead of every baseline on return without a materially worse drawdown, "
            "on this dataset under these costs"
        )
        verdict = ExperimentVerdict.BEAT_ALL_BASELINES
    elif not ahead:
        reasons.append(
            "beaten by every baseline; nothing here is attributable to the strategy"
        )
        verdict = ExperimentVerdict.NO_EDGE_DEMONSTRATED
    else:
        reasons.append(
            f"ahead of {len(ahead)} baseline(s) and behind {len(behind)}: "
            + ", ".join(c.baseline for c in behind)
        )
        verdict = ExperimentVerdict.MIXED

    if result.warnings:
        reasons.extend(result.warnings)
    return (verdict, tuple(reasons))


__all__ = [
    "BaselineComparison",
    "ExperimentReport",
    "ExperimentVerdict",
    "evaluate_experiment",
]
