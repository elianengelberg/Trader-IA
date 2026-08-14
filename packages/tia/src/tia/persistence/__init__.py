"""Persistence — the record of what happened and why.

SQLite by default so the demo needs no daemon; PostgreSQL by changing one URL.
"""

from tia.persistence.database import Database
from tia.persistence.models import SCHEMA_VERSION, Base
from tia.persistence.repositories import (
    ActivationRepository,
    AssessmentRepository,
    BacktestRepository,
    CapitalEventRepository,
    DecisionRepository,
    EdgeStateRepository,
    EventRepository,
    FillRepository,
    IncidentRepository,
    LatencyRepository,
    LogRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
    ReconciliationRepository,
    RunRepository,
)

__all__ = [
    "SCHEMA_VERSION",
    "ActivationRepository",
    "AssessmentRepository",
    "BacktestRepository",
    "Base",
    "CapitalEventRepository",
    "Database",
    "DecisionRepository",
    "EdgeStateRepository",
    "EventRepository",
    "FillRepository",
    "IncidentRepository",
    "LatencyRepository",
    "LogRepository",
    "NewsRepository",
    "OrderRepository",
    "PortfolioRepository",
    "ReconciliationRepository",
    "RunRepository",
]
