"""The database schema.

Everything a decision touched is stored, because the question the system exists to answer
is *"why did it do that?"* and an answer that cannot be reconstructed from storage is not
an answer.

Three design choices worth stating:

* **Append-only where it matters.** Events, decisions, fills and equity points are
  inserted, never updated. Orders and positions carry mutable state because they *are*
  state, but every transition that produced that state is in the event table.
* **Every row carries its correlation id.** One trade's entire causal chain — bar, quality
  report, features, regime, signal, assessment, risk decision, order, fills, position,
  P&L — is retrievable with a single indexed lookup. That is what makes the trade journal
  and the event trace possible rather than aspirational.
* **Money columns are floats, and that is a deliberate limitation.** This platform is
  simulation-only; nothing here settles, and a float is what NumPy and the metrics layer
  already use end to end. A system that touched real money would need `NUMERIC` and would
  need it consistently — introducing it here for one table would create silent
  float↔decimal conversions at every boundary, which is worse than being uniformly float
  and saying so.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

#: Bumped on any schema change. `ensure_schema()` refuses to run against a database
#: written by a newer version rather than silently misreading it.
SCHEMA_VERSION = 1


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


def _utc_column(**kwargs: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), **kwargs)


class SchemaInfo(Base):
    """One row. Guards against opening a database from a future version."""

    __tablename__ = "schema_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = _utc_column(nullable=False)
    application_version: Mapped[str] = mapped_column(String(32), default="")


class RunRecord(Base):
    """One session of the paper-trading runtime.

    Everything else hangs off a run, so two demo sessions cannot contaminate each other's
    P&L — the failure that makes a dashboard quietly wrong after a restart.
    """

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(24), nullable=False)
    scenario: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime] = _utc_column(nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    symbols: Mapped[list[Any]] = mapped_column(JSON, default=list)
    config_digest: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    events: Mapped[list[EventRecord]] = relationship(back_populates="run")


class EventRecord(Base):
    """The append-only event log.

    ``idempotency_key`` is unique: a redelivered event is rejected by the database itself,
    not only by the in-memory dedup store, so a restart cannot replay a fill.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_events_idempotency"),
        Index("ix_events_run_seq", "run_id", "sequence"),
        Index("ix_events_correlation", "correlation_id"),
        Index("ix_events_type_time", "event_type", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    causation_id: Mapped[str] = mapped_column(String(64), default="")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), default="", index=True)
    occurred_at: Mapped[datetime] = _utc_column(nullable=False)
    recorded_at: Mapped[datetime] = _utc_column(nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[RunRecord] = relationship(back_populates="events")


class DecisionRow(Base):
    """One evaluated bar: what the system saw, concluded, and did about it.

    Written for declines as well as trades. A journal that only records trades cannot
    answer "why didn't it act here?", which is most of the interesting questions.
    """

    __tablename__ = "decisions"
    __table_args__ = (
        Index("ix_decisions_run_time", "run_id", "decided_at"),
        Index("ix_decisions_symbol_time", "symbol", "decided_at"),
    )

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_at: Mapped[datetime] = _utc_column(nullable=False)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    base_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    approved_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    requested_quantity: Mapped[float] = mapped_column(Float, default=0.0)

    regime: Mapped[str] = mapped_column(String(24), default="unknown")
    data_quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    data_freshness_score: Mapped[float] = mapped_column(Float, default=1.0)
    feature_hash: Mapped[str] = mapped_column(String(64), default="")
    signal_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    #: The LLM's contribution, always <= 0. Stored separately from the confidence so the
    #: dashboard can show what the model cost the position rather than only the net.
    context_modifier: Mapped[float] = mapped_column(Float, default=0.0)
    context_veto: Mapped[bool] = mapped_column(Boolean, default=False)
    context_used: Mapped[bool] = mapped_column(Boolean, default=False)
    context_reason: Mapped[str] = mapped_column(Text, default="")
    thesis: Mapped[str] = mapped_column(Text, default="")

    why_enter: Mapped[list[Any]] = mapped_column(JSON, default=list)
    why_not_enter: Mapped[list[Any]] = mapped_column(JSON, default=list)
    risk_checks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class OrderRow(Base):
    """An order and its current state. Every transition is also in the event log."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_orders_client_id"),
        Index("ix_orders_run_created", "run_id", "created_at"),
        Index("ix_orders_state", "state"),
    )

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    signal_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    risk_decision_id: Mapped[str] = mapped_column(String(64), default="")

    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    average_fill_price: Mapped[float] = mapped_column(Float, default=0.0)
    fees_paid: Mapped[float] = mapped_column(Float, default=0.0)
    reject_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _utc_column(nullable=False)
    updated_at: Mapped[datetime] = _utc_column(nullable=False)

    fills: Mapped[list[FillRow]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class FillRow(Base):
    """A simulated execution. Append-only."""

    __tablename__ = "fills"
    __table_args__ = (Index("ix_fills_run_time", "run_id", "filled_at"),)

    fill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    liquidity: Mapped[str] = mapped_column(String(8), default="taker")
    filled_at: Mapped[datetime] = _utc_column(nullable=False)

    order: Mapped[OrderRow] = relationship(back_populates="fills")


class PositionRow(Base):
    """Current holding per symbol per run. Mutable, because it is state."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("run_id", "symbol", name="uq_positions_run_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    average_price: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees_paid: Mapped[float] = mapped_column(Float, default=0.0)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = _utc_column(nullable=False)


class EquityPoint(Base):
    """One point on the equity curve. Append-only, and the source of the P&L chart."""

    __tablename__ = "equity_points"
    __table_args__ = (Index("ix_equity_run_time", "run_id", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    at: Mapped[datetime] = _utc_column(nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    gross_exposure: Mapped[float] = mapped_column(Float, default=0.0)
    net_exposure: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    open_positions: Mapped[int] = mapped_column(Integer, default=0)


class AssessmentRow(Base):
    """One LLM assessment, including the ones that were rejected or never made.

    The rejections are the interesting rows: a model whose output is discarded 40% of the
    time is a fact about the system that no success-only table would ever show.
    """

    __tablename__ = "assessments"
    __table_args__ = (Index("ix_assessments_run_time", "run_id", "created_at"),)

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = _utc_column(nullable=False)
    expires_at: Mapped[datetime] = _utc_column(nullable=False)

    used: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model_id: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    context_modifier: Mapped[float] = mapped_column(Float, default=0.0)
    veto: Mapped[bool] = mapped_column(Boolean, default=False)
    leaning: Mapped[str] = mapped_column(String(16), default="no_trade")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    thesis: Mapped[str] = mapped_column(Text, default="")
    supporting: Mapped[list[Any]] = mapped_column(JSON, default=list)
    contradicting: Mapped[list[Any]] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class LogRow(Base):
    """Structured log lines, so the dashboard's log view survives a restart."""

    __tablename__ = "logs"
    __table_args__ = (
        Index("ix_logs_run_time", "run_id", "at"),
        Index("ix_logs_level", "level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    at: Mapped[datetime] = _utc_column(nullable=False)
    level: Mapped[str] = mapped_column(String(12), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), default="system")
    component: Mapped[str] = mapped_column(String(48), default="")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64), default="", index=True)


class BacktestRow(Base):
    """A stored backtest result, so the dashboard can show history without re-running."""

    __tablename__ = "backtests"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = _utc_column(nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), default="")
    symbols: Mapped[list[Any]] = mapped_column(JSON, default=list)
    timeframe: Mapped[str] = mapped_column(String(8), default="")
    bars: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(32), default="")
    total_return_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe: Mapped[float | None] = mapped_column(Float)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    equity_curve: Mapped[list[Any]] = mapped_column(JSON, default=list)
    baselines: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence_statement: Mapped[str] = mapped_column(Text, default="")
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class NewsRow(Base):
    """News items seen by the system, with whatever relevance was assigned."""

    __tablename__ = "news"
    __table_args__ = (Index("ix_news_published", "published_at"),)

    news_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    published_at: Mapped[datetime] = _utc_column(nullable=False)
    ingested_at: Mapped[datetime] = _utc_column(nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="")
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    symbols: Mapped[list[Any]] = mapped_column(JSON, default=list)
    sentiment: Mapped[str] = mapped_column(String(16), default="neutral")
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    impact: Mapped[str] = mapped_column(String(16), default="low")
    body_hash: Mapped[str] = mapped_column(String(64), default="")


ALL_TABLES = (
    SchemaInfo,
    RunRecord,
    EventRecord,
    DecisionRow,
    OrderRow,
    FillRow,
    PositionRow,
    EquityPoint,
    AssessmentRow,
    LogRow,
    BacktestRow,
    NewsRow,
)

__all__ = [
    "ALL_TABLES",
    "SCHEMA_VERSION",
    "AssessmentRow",
    "BacktestRow",
    "Base",
    "DecisionRow",
    "EquityPoint",
    "EventRecord",
    "FillRow",
    "LogRow",
    "NewsRow",
    "OrderRow",
    "PositionRow",
    "RunRecord",
    "SchemaInfo",
]
