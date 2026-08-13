"""What a backtest produces.

A number without its conditions is not a result, so the record carries the dataset, the
period, the seed, the version of every component that participated, and the reasons the
system declined to trade as well as the reasons it acted. Rule §63: this describes what
one experiment produced under stated conditions. It is not a forecast, and nothing here
should be read as one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import Direction, MarketRegime, RiskVerdict
from tia.quant.statistics import PerformanceMetrics, TradeRecord


class ClosedTrade(BaseModel):
    """One completed round trip, with everything needed to audit it."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    symbol: str
    direction: Direction
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    entry_at: datetime
    exit_at: datetime
    gross_pnl: float
    fees: float = Field(ge=0)
    net_pnl: float
    return_pct: float
    bars_held: int = Field(ge=0)
    exit_reason: str = ""
    regime_at_entry: MarketRegime = MarketRegime.UNKNOWN
    signal_id: str = ""
    confidence: float = 0.0

    @field_validator("entry_at", "exit_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="trade time")

    @property
    def duration_seconds(self) -> float:
        return (self.exit_at - self.entry_at).total_seconds()

    def to_record(self) -> TradeRecord:
        return TradeRecord(
            symbol=self.symbol,
            pnl=self.net_pnl,
            return_pct=self.return_pct,
            duration_seconds=self.duration_seconds,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
            quantity=self.quantity,
            fees=self.fees,
        )


class DecisionRecord(BaseModel):
    """What the system decided at one bar, and what it was looking at.

    Recorded for **every** evaluated bar, including the ones that declined to trade. Two
    reasons. First, a decision log that only contains trades cannot answer "why didn't it
    act here?", which is most of the interesting questions. Second, it is what makes
    look-ahead testable: the decision at bar *t* must be a function of bars up to *t*, and
    that can only be checked against a record of the decision itself — an equity curve
    cannot distinguish a decision that changed from a price that changed.
    """

    model_config = ConfigDict(frozen=True)

    bar_close_time: datetime
    direction: Direction
    confidence: float
    verdict: RiskVerdict
    approved_quantity: float = 0.0
    regime: MarketRegime = MarketRegime.UNKNOWN
    feature_hash: str = ""
    signal_id: str = ""

    @field_validator("bar_close_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="decision time")

    def fingerprint(self) -> tuple[object, ...]:
        """Everything that must not change when future bars change."""
        return (
            self.bar_close_time,
            self.direction.value,
            round(self.confidence, 12),
            self.verdict.value,
            round(self.approved_quantity, 12),
            self.regime.value,
            self.feature_hash,
        )


class DecisionCounts(BaseModel):
    """Why the system did what it did, counted.

    The declines matter as much as the trades: a strategy that traded eleven times out of
    four thousand bars is a different object from one that traded eleven times out of
    twelve, and an equity curve alone cannot tell them apart.
    """

    model_config = ConfigDict(frozen=True)

    bars_processed: int = 0
    bars_skipped_insufficient_history: int = 0
    bars_skipped_data_quality: int = 0
    signals_generated: int = 0
    signals_by_direction: dict[str, int] = Field(default_factory=dict)
    risk_verdicts: dict[str, int] = Field(default_factory=dict)
    risk_rejection_reasons: dict[str, int] = Field(default_factory=dict)
    intents_submitted: int = 0
    orders_rejected: int = 0
    orders_expired: int = 0
    fills: int = 0
    protective_stops_unplaced: int = 0
    approvals_suppressed_position_open: int = 0

    @property
    def actionable_signal_rate(self) -> float:
        if self.signals_generated == 0:
            return 0.0
        actionable = sum(
            count
            for direction, count in self.signals_by_direction.items()
            if direction != Direction.NO_TRADE.value
        )
        return actionable / self.signals_generated

    @property
    def approval_rate(self) -> float:
        total = sum(self.risk_verdicts.values())
        if total == 0:
            return 0.0
        approved = sum(
            count
            for verdict, count in self.risk_verdicts.items()
            if RiskVerdict(verdict).allows_execution
        )
        return approved / total


class BacktestConditions(BaseModel):
    """The conditions the result is only valid under.

    Reported alongside every number, because "Sharpe 1.4" means nothing without them and
    quoting it without them is the specific dishonesty rule §63 exists to prevent.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    dataset: str
    symbols: tuple[str, ...]
    timeframe: str
    start: datetime
    end: datetime
    bars: int
    initial_capital: float
    seed: int
    strategy_versions: dict[str, str] = Field(default_factory=dict)
    feature_version: str = ""
    risk_limits_digest: str = ""
    execution_config: dict[str, float | int | bool] = Field(default_factory=dict)
    is_out_of_sample: bool = False
    notes: tuple[str, ...] = ()

    @field_validator("start", "end")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="period bound")

    def describe(self) -> str:
        return (
            f"{', '.join(self.symbols)} {self.timeframe} "
            f"{self.start.date()}..{self.end.date()} "
            f"({self.bars} bars, seed={self.seed}"
            f"{', out-of-sample' if self.is_out_of_sample else ''})"
        )


class BacktestResult(BaseModel):
    """One experiment's complete record."""

    model_config = ConfigDict(frozen=True)

    conditions: BacktestConditions
    metrics: PerformanceMetrics
    equity_curve: tuple[float, ...] = ()
    equity_timestamps: tuple[datetime, ...] = ()
    trades: tuple[ClosedTrade, ...] = ()
    decisions: DecisionCounts = Field(default_factory=DecisionCounts)
    decision_log: tuple[DecisionRecord, ...] = ()
    open_positions_at_end: dict[str, float] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1] if self.equity_curve else 0.0

    @property
    def is_reliable(self) -> bool:
        """Whether the sample supports the ratio metrics at all.

        A ``False`` here does not mean the strategy is bad. It means the experiment
        cannot support a claim in either direction, which is a different and more common
        situation than most backtest reports admit.
        """
        return self.metrics.is_reliable() and not self.warnings

    def evidence_statement(self) -> str:
        """The only sanctioned way to state a result in prose (rule §63).

        Deliberately phrased as a description of one experiment. There is no method on
        this class that will produce the sentence "this strategy wins", because there is
        no evidence that would justify it.
        """
        caveats = ""
        if self.warnings:
            caveats = f" Caveats: {'; '.join(self.warnings)}."
        if not self.metrics.is_reliable():
            caveats += (
                " The sample is too small to support the ratio metrics; they are"
                " reported for completeness, not as evidence."
            )
        return (
            f"In this experiment ({self.conditions.describe()}), the configuration"
            f" produced {self.metrics.summary_line()}."
            f" This describes past behaviour on this dataset under these costs and"
            f" makes no claim about future results.{caveats}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditions": self.conditions.model_dump(mode="json"),
            "metrics": self.metrics.model_dump(mode="json"),
            "decisions": self.decisions.model_dump(mode="json"),
            "trades": len(self.trades),
            "final_equity": self.final_equity,
            "warnings": list(self.warnings),
            "evidence_statement": self.evidence_statement(),
        }


__all__ = [
    "BacktestConditions",
    "BacktestResult",
    "ClosedTrade",
    "DecisionCounts",
    "DecisionRecord",
]
