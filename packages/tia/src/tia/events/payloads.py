"""Event payloads and the canonical event-type catalogue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from tia.core.clock import ensure_utc
from tia.domain.enums import DataQualityFlag, Direction, MarketRegime, OrderState
from tia.domain.market import Candle, MacroEvent, NewsItem, Quote
from tia.domain.orders import Fill, OrderIntent
from tia.domain.quality import DataQualityReport
from tia.domain.risk import RiskDecision
from tia.domain.signals import ContextAssessment, SignalCandidate
from tia.events.envelope import EventPayload


class EventType:
    """Canonical event-type strings.

    A class of constants rather than an enum: event types are an open set that grows
    with the system, and a string is what actually travels on the wire.
    """

    TICK_RECEIVED = "market.tick_received"
    QUOTE_RECEIVED = "market.quote_received"
    CANDLE_CLOSED = "market.candle_closed"
    REGIME_CHANGED = "market.regime_changed"
    VOLATILITY_CHANGED = "market.volatility_changed"

    DATA_QUALITY_EVALUATED = "data.quality_evaluated"
    DATA_QUALITY_FAILURE = "data.quality_failure"
    PROVIDER_DISCONNECTED = "data.provider_disconnected"
    PROVIDER_RECONNECTED = "data.provider_reconnected"

    NEWS_RECEIVED = "news.received"
    MACRO_EVENT_DETECTED = "macro.event_detected"

    FEATURES_COMPUTED = "quant.features_computed"
    CONTEXT_ASSESSED = "ai.context_assessed"
    CONTEXT_UNAVAILABLE = "ai.context_unavailable"

    SIGNAL_CANDIDATE_CREATED = "strategy.signal_candidate_created"
    SIGNAL_EXPIRED = "strategy.signal_expired"

    RISK_DECISION_CREATED = "risk.decision_created"
    ORDER_INTENT_CREATED = "order.intent_created"
    ORDER_STATE_CHANGED = "order.state_changed"
    FILL_SIMULATED = "order.fill_simulated"
    POSITION_CHANGED = "portfolio.position_changed"
    PORTFOLIO_UPDATED = "portfolio.updated"

    RECONCILIATION_COMPLETED = "system.reconciliation_completed"
    SAFE_MODE_ENTERED = "system.safe_mode_entered"
    SAFE_MODE_EXITED = "system.safe_mode_exited"
    SYSTEM_FAILURE = "system.failure"
    HEARTBEAT = "system.heartbeat"


# --------------------------------------------------------------------------- market


class TickReceived(EventPayload):
    symbol: str
    timestamp: datetime
    price: float = Field(gt=0)
    size: float = Field(ge=0)
    provider: str

    @field_validator("timestamp")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="tick timestamp")


class QuoteReceived(EventPayload):
    quote: Quote


class CandleClosed(EventPayload):
    candle: Candle


class RegimeChanged(EventPayload):
    symbol: str
    previous: MarketRegime
    current: MarketRegime
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: dict[str, float] = Field(default_factory=dict)


class VolatilityChanged(EventPayload):
    symbol: str
    realized_volatility: float = Field(ge=0.0)
    percentile: float = Field(ge=0.0, le=1.0)
    direction: str = Field(pattern="^(rising|falling|stable)$")


# --------------------------------------------------------------------------- data quality


class DataQualityEvaluated(EventPayload):
    report: DataQualityReport


class DataQualityFailure(EventPayload):
    symbol: str
    report_id: str
    flags: tuple[DataQualityFlag, ...]
    quality_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0)
    action_taken: str = "no_trade"
    detail: str = ""


class ProviderDisconnected(EventPayload):
    provider: str
    symbol: str | None = None
    reason: str
    last_message_at: datetime | None = None
    consecutive_failures: int = 0

    @field_validator("last_message_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v, field="last_message_at") if v is not None else None


class ProviderReconnected(EventPayload):
    provider: str
    downtime_seconds: float = Field(ge=0)
    backfilled_bars: int = 0


# --------------------------------------------------------------------------- context


class NewsReceived(EventPayload):
    item: NewsItem


class MacroEventDetected(EventPayload):
    event: MacroEvent
    surprise_zscore: float | None = None


class FeaturesComputed(EventPayload):
    symbol: str
    timeframe: str
    feature_version: str
    feature_hash: str
    bar_open_time: datetime
    features: dict[str, float]

    @field_validator("bar_open_time")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="bar_open_time")


class ContextAssessed(EventPayload):
    assessment: ContextAssessment


class ContextUnavailable(EventPayload):
    symbol: str
    reason: str
    degraded_since: datetime | None = None

    @field_validator("degraded_since")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v, field="degraded_since") if v is not None else None


# --------------------------------------------------------------------------- decisions


class SignalCandidateCreated(EventPayload):
    signal: SignalCandidate


class SignalExpired(EventPayload):
    signal_id: str
    symbol: str
    created_at: datetime
    expired_at: datetime
    direction: Direction

    @field_validator("created_at", "expired_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="signal time")


class RiskDecisionCreated(EventPayload):
    decision: RiskDecision


class OrderIntentCreated(EventPayload):
    intent: OrderIntent


class OrderStateChanged(EventPayload):
    order_id: str
    client_order_id: str
    symbol: str
    previous_state: OrderState
    current_state: OrderState
    reason: str = ""
    filled_quantity: float = Field(0.0, ge=0)
    remaining_quantity: float = Field(0.0, ge=0)


class FillSimulated(EventPayload):
    fill: Fill


class PositionChanged(EventPayload):
    symbol: str
    quantity: float
    average_price: float = Field(ge=0)
    realized_pnl: float
    unrealized_pnl: float
    last_price: float = Field(ge=0)


class PortfolioUpdated(EventPayload):
    equity: float
    cash: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    net_exposure: float
    open_positions: int
    drawdown_pct: float = Field(ge=0)
    day_pnl_pct: float


# --------------------------------------------------------------------------- system


class ReconciliationCompleted(EventPayload):
    matched: int = Field(ge=0)
    discrepancies: tuple[str, ...] = ()
    resolved: tuple[str, ...] = ()
    entered_safe_mode: bool = False


class SafeModeEntered(EventPayload):
    reason: str
    discrepancies: tuple[str, ...] = ()
    triggered_by: str = ""


class SafeModeExited(EventPayload):
    reason: str
    duration_seconds: float = Field(ge=0)
    approved_by: str = "operator"


class SystemFailure(EventPayload):
    component: str
    error_code: str
    severity: str = Field("error", pattern="^(warning|error|critical)$")
    message: str
    recoverable: bool = True
    context: dict[str, Any] = Field(default_factory=dict)


class Heartbeat(EventPayload):
    component: str
    healthy: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CandleClosed",
    "ContextAssessed",
    "ContextUnavailable",
    "DataQualityEvaluated",
    "DataQualityFailure",
    "EventType",
    "FeaturesComputed",
    "FillSimulated",
    "Heartbeat",
    "MacroEventDetected",
    "NewsReceived",
    "OrderIntentCreated",
    "OrderStateChanged",
    "PortfolioUpdated",
    "PositionChanged",
    "ProviderDisconnected",
    "ProviderReconnected",
    "QuoteReceived",
    "ReconciliationCompleted",
    "RegimeChanged",
    "RiskDecisionCreated",
    "SafeModeEntered",
    "SafeModeExited",
    "SignalCandidateCreated",
    "SignalExpired",
    "SystemFailure",
    "TickReceived",
    "VolatilityChanged",
]
