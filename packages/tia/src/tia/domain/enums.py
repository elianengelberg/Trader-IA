"""Domain vocabulary.

String enums throughout: they serialize to readable JSON, survive a database round-trip
without a mapping table, and make log lines legible without a decoder ring.
"""

from __future__ import annotations

from enum import StrEnum


class AssetClass(StrEnum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    INDEX = "index"
    FX = "fx"
    COMMODITY = "commodity"
    RATE = "rate"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Direction(StrEnum):
    """What the decision layer may output.

    ``NO_TRADE`` is a first-class, always-valid answer — distinct from ``HOLD``:
    ``HOLD`` means "a position thesis exists but now is not the entry"; ``NO_TRADE``
    means "we decline to act", typically because data, risk or context is insufficient.
    """

    LONG = "long"
    SHORT = "short"
    HOLD = "hold"
    NO_TRADE = "no_trade"

    @property
    def is_actionable(self) -> bool:
        return self in {Direction.LONG, Direction.SHORT}

    def to_side(self) -> Side:
        if self is Direction.LONG:
            return Side.BUY
        if self is Direction.SHORT:
            return Side.SELL
        raise ValueError(f"{self} is not an actionable direction")


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class TimeInForce(StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"


class OrderState(StrEnum):
    CREATED = "created"
    VALIDATED = "validated"
    RISK_APPROVED = "risk_approved"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_ORDER_STATES

    @property
    def is_open(self) -> bool:
        return self in OPEN_ORDER_STATES


TERMINAL_ORDER_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
        OrderState.FAILED,
    }
)

OPEN_ORDER_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.SUBMITTED,
        OrderState.ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED,
        OrderState.CANCEL_REQUESTED,
    }
)


class MarketRegime(StrEnum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    ANOMALOUS = "anomalous"
    CRISIS = "crisis"
    UNKNOWN = "unknown"

    @property
    def is_hostile(self) -> bool:
        """Regimes in which the platform declines new risk by default."""
        return self in {MarketRegime.ANOMALOUS, MarketRegime.CRISIS}


class RiskVerdict(StrEnum):
    APPROVED = "approved"
    REDUCED_SIZE = "reduced_size"
    REJECTED = "rejected"
    NO_TRADE = "no_trade"

    @property
    def allows_execution(self) -> bool:
        return self in {RiskVerdict.APPROVED, RiskVerdict.REDUCED_SIZE}


class DataQualityFlag(StrEnum):
    STALE = "stale"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    IMPOSSIBLE_VALUE = "impossible_value"
    INVALID_OHLC = "invalid_ohlc"
    INVALID_VOLUME = "invalid_volume"
    SPREAD_ANOMALY = "spread_anomaly"
    FEED_DISCONNECTED = "feed_disconnected"
    INSUFFICIENT_HISTORY = "insufficient_history"
    FUTURE_TIMESTAMP = "future_timestamp"


class AgentKind(StrEnum):
    MARKET_DATA = "market_data"
    TECHNICAL = "technical"
    QUANT = "quant"
    MACRO = "macro"
    NEWS = "news"
    INTERNATIONAL = "international"
    REGIME = "regime"
    STRATEGY_CONTEXT = "strategy_context"


class FindingSource(StrEnum):
    """Provenance of a finding. Governs what it is allowed to influence."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"


class SystemMode(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    SAFE_MODE = "safe_mode"
    HALTED = "halted"


__all__ = [
    "OPEN_ORDER_STATES",
    "TERMINAL_ORDER_STATES",
    "AgentKind",
    "AssetClass",
    "DataQualityFlag",
    "Direction",
    "FindingSource",
    "MarketRegime",
    "OrderState",
    "OrderType",
    "RiskVerdict",
    "Side",
    "SystemMode",
    "TimeInForce",
]
