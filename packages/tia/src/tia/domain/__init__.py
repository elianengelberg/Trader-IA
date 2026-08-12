"""Domain model: the vocabulary every other layer speaks."""

from tia.domain.enums import (
    AgentKind,
    AssetClass,
    DataQualityFlag,
    Direction,
    FindingSource,
    MarketRegime,
    OrderState,
    OrderType,
    RiskVerdict,
    Side,
    SystemMode,
    TimeInForce,
)
from tia.domain.instruments import DEFAULT_UNIVERSE, Instrument, InstrumentUniverse, Timeframe
from tia.domain.market import (
    Candle,
    MacroEvent,
    MarketSnapshot,
    NewsItem,
    OrderBook,
    Quote,
    TradePrint,
)
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioSnapshot, PortfolioState, Position
from tia.domain.quality import DataQualityReport, QualityCheck
from tia.domain.risk import PositionSizing, RiskCheck, RiskDecision
from tia.domain.signals import (
    AgentFinding,
    ContextAssessment,
    DataQualityAnnotation,
    Evidence,
    SignalCandidate,
    StrategyOpinion,
)

__all__ = [
    "DEFAULT_UNIVERSE",
    "AgentFinding",
    "AgentKind",
    "AssetClass",
    "Candle",
    "ContextAssessment",
    "DataQualityAnnotation",
    "DataQualityFlag",
    "DataQualityReport",
    "Direction",
    "Evidence",
    "Fill",
    "FindingSource",
    "Instrument",
    "InstrumentUniverse",
    "MacroEvent",
    "MarketRegime",
    "MarketSnapshot",
    "NewsItem",
    "Order",
    "OrderBook",
    "OrderIntent",
    "OrderState",
    "OrderType",
    "PortfolioSnapshot",
    "PortfolioState",
    "Position",
    "PositionSizing",
    "QualityCheck",
    "Quote",
    "RiskCheck",
    "RiskDecision",
    "RiskVerdict",
    "Side",
    "SignalCandidate",
    "StrategyOpinion",
    "SystemMode",
    "TimeInForce",
    "Timeframe",
    "TradePrint",
]
