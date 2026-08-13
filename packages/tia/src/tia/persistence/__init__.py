"""Persistence — the record of what happened and why.

SQLite by default so the demo needs no daemon; PostgreSQL by changing one URL.
"""

from tia.persistence.database import Database
from tia.persistence.models import SCHEMA_VERSION, Base
from tia.persistence.repositories import (
    AssessmentRepository,
    BacktestRepository,
    DecisionRepository,
    EventRepository,
    FillRepository,
    LogRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
    RunRepository,
)

__all__ = [
    "SCHEMA_VERSION",
    "AssessmentRepository",
    "BacktestRepository",
    "Base",
    "Database",
    "DecisionRepository",
    "EventRepository",
    "FillRepository",
    "LogRepository",
    "NewsRepository",
    "OrderRepository",
    "PortfolioRepository",
    "RunRepository",
]
