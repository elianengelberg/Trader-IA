"""Repositories — the only code that writes to the database.

One class per aggregate, each taking an `AsyncSession`. The runtime never builds a query;
the API never builds a query. Both go through here, so a change to how something is stored
is a change in one file.

Writes are idempotent wherever the thing being written can arrive twice. An event
redelivered after a restart, a fill replayed from the bus, a position updated twice in one
bar — each of those is a real occurrence, and each is handled by upserting on a natural
key rather than by hoping it does not happen.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tia.core.logging import get_logger
from tia.domain.orders import Fill, Order
from tia.domain.portfolio import PortfolioState
from tia.events.envelope import EventEnvelope
from tia.persistence.models import (
    AssessmentRow,
    BacktestRow,
    DecisionRow,
    EquityPoint,
    EventRecord,
    FillRow,
    LogRow,
    NewsRow,
    OrderRow,
    PositionRow,
    RunRecord,
)

_log = get_logger("persistence.repositories")


def _upsert(session: AsyncSession, table: Any, values: dict[str, Any], index_elements: list[str]):
    """Dialect-appropriate upsert.

    SQLite and PostgreSQL both support `ON CONFLICT`, with different import paths and
    otherwise identical semantics for what is needed here.
    """
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    statement = pg_insert(table) if dialect == "postgresql" else sqlite_insert(table)
    stmt = statement.values(**values)
    updatable = {k: v for k, v in values.items() if k not in index_elements}
    return stmt.on_conflict_do_update(index_elements=index_elements, set_=updatable)


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        run_id: str,
        mode: str,
        scenario: str,
        started_at: datetime,
        initial_capital: float,
        seed: int,
        symbols: Sequence[str],
        config_digest: str = "",
    ) -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            mode=mode,
            scenario=scenario,
            started_at=started_at,
            initial_capital=initial_capital,
            seed=seed,
            symbols=list(symbols),
            config_digest=config_digest,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def stop(self, run_id: str, stopped_at: datetime) -> None:
        run = await self._session.get(RunRecord, run_id)
        if run is not None:
            run.stopped_at = stopped_at

    async def get(self, run_id: str) -> RunRecord | None:
        return await self._session.get(RunRecord, run_id)

    async def latest(self) -> RunRecord | None:
        result = await self._session.execute(
            select(RunRecord).order_by(desc(RunRecord.started_at)).limit(1)
        )
        return result.scalars().first()

    async def list_recent(self, limit: int = 20) -> list[RunRecord]:
        result = await self._session.execute(
            select(RunRecord).order_by(desc(RunRecord.started_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def delete(self, run_id: str) -> None:
        """Cascades to every child table via the foreign keys."""
        await self._session.execute(delete(RunRecord).where(RunRecord.run_id == run_id))


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, run_id: str, envelope: EventEnvelope[Any]) -> bool:
        """Store an event. Returns ``False`` if it was a duplicate.

        Deduplication is enforced by the unique index on ``idempotency_key``, not by a
        prior SELECT: two writers racing the same redelivered event both pass a SELECT and
        only one survives the constraint.
        """
        payload = envelope.payload
        symbol = getattr(payload, "symbol", "") or ""
        values = {
            "event_id": envelope.event_id,
            "run_id": run_id,
            "sequence": envelope.sequence,
            "event_type": envelope.event_type,
            "schema_version": envelope.schema_version,
            "correlation_id": envelope.correlation_id,
            "causation_id": envelope.causation_id or "",
            "idempotency_key": envelope.idempotency_key,
            "symbol": str(symbol)[:32],
            "occurred_at": envelope.occurred_at,
            "recorded_at": envelope.recorded_at,
            "payload": envelope.payload.model_dump(mode="json"),
        }
        stmt = _upsert(self._session, EventRecord, values, ["idempotency_key"])
        await self._session.execute(stmt)
        return True

    async def by_correlation(self, correlation_id: str) -> list[EventRecord]:
        result = await self._session.execute(
            select(EventRecord)
            .where(EventRecord.correlation_id == correlation_id)
            .order_by(EventRecord.sequence)
        )
        return list(result.scalars().all())

    async def recent(
        self, run_id: str, *, limit: int = 200, event_type: str | None = None
    ) -> list[EventRecord]:
        query = select(EventRecord).where(EventRecord.run_id == run_id)
        if event_type:
            query = query.where(EventRecord.event_type == event_type)
        result = await self._session.execute(
            query.order_by(desc(EventRecord.sequence)).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self, run_id: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(EventRecord).where(EventRecord.run_id == run_id)
        )
        return int(result.scalar() or 0)


class DecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        await self._session.execute(_upsert(self._session, DecisionRow, values, ["decision_id"]))

    async def recent(
        self,
        run_id: str,
        *,
        limit: int = 100,
        symbol: str | None = None,
        actionable_only: bool = False,
    ) -> list[DecisionRow]:
        query = select(DecisionRow).where(DecisionRow.run_id == run_id)
        if symbol:
            query = query.where(DecisionRow.symbol == symbol)
        if actionable_only:
            query = query.where(DecisionRow.direction.in_(("long", "short")))
        result = await self._session.execute(
            query.order_by(desc(DecisionRow.decided_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, decision_id: str) -> DecisionRow | None:
        return await self._session.get(DecisionRow, decision_id)

    async def by_signal(self, signal_id: str) -> DecisionRow | None:
        result = await self._session.execute(
            select(DecisionRow).where(DecisionRow.signal_id == signal_id).limit(1)
        )
        return result.scalars().first()


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, run_id: str, order: Order) -> None:
        values = {
            "order_id": order.order_id,
            "run_id": run_id,
            "client_order_id": order.client_order_id,
            "correlation_id": order.correlation_id,
            "signal_id": order.signal_id,
            "risk_decision_id": order.intent_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
            "state": order.state.value,
            "filled_quantity": order.filled_quantity,
            "average_fill_price": order.average_fill_price,
            "fees_paid": order.fees_paid,
            "reject_reason": order.reject_reason or "",
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }
        await self._session.execute(_upsert(self._session, OrderRow, values, ["order_id"]))

    async def get(self, order_id: str) -> OrderRow | None:
        return await self._session.get(OrderRow, order_id)

    async def recent(
        self, run_id: str, *, limit: int = 100, open_only: bool = False
    ) -> list[OrderRow]:
        query = select(OrderRow).where(OrderRow.run_id == run_id)
        if open_only:
            query = query.where(
                OrderRow.state.in_(
                    ("submitted", "acknowledged", "partially_filled", "cancel_requested")
                )
            )
        result = await self._session.execute(
            query.order_by(desc(OrderRow.created_at)).limit(limit)
        )
        return list(result.scalars().all())


class FillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, run_id: str, fill: Fill) -> None:
        values = {
            "fill_id": fill.fill_id,
            "run_id": run_id,
            "order_id": fill.order_id,
            "sequence": fill.sequence,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "quantity": fill.quantity,
            "price": fill.price,
            "fee": fill.fee,
            "slippage_bps": fill.slippage_bps,
            "latency_ms": fill.latency_ms,
            "liquidity": fill.liquidity,
            "filled_at": fill.filled_at,
        }
        await self._session.execute(_upsert(self._session, FillRow, values, ["fill_id"]))

    async def for_order(self, order_id: str) -> list[FillRow]:
        result = await self._session.execute(
            select(FillRow).where(FillRow.order_id == order_id).order_by(FillRow.sequence)
        )
        return list(result.scalars().all())

    async def recent(self, run_id: str, *, limit: int = 100) -> list[FillRow]:
        result = await self._session.execute(
            select(FillRow)
            .where(FillRow.run_id == run_id)
            .order_by(desc(FillRow.filled_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sync_positions(
        self, run_id: str, portfolio: PortfolioState, at: datetime
    ) -> None:
        """Mirror the in-memory portfolio into the database.

        Flat positions are written too, with quantity 0, rather than deleted: a symbol
        that was traded and closed is different from one that was never traded, and the
        journal needs to tell them apart.
        """
        for symbol, position in portfolio.positions.items():
            values = {
                "run_id": run_id,
                "symbol": symbol,
                "quantity": position.quantity,
                "average_price": position.average_price,
                "realized_pnl": position.realized_pnl,
                "unrealized_pnl": position.unrealized_pnl,
                "fees_paid": position.fees_paid,
                "last_price": position.last_price,
                "opened_at": position.opened_at,
                "updated_at": at,
            }
            await self._session.execute(
                _upsert(self._session, PositionRow, values, ["run_id", "symbol"])
            )

    async def positions(self, run_id: str, *, open_only: bool = True) -> list[PositionRow]:
        query = select(PositionRow).where(PositionRow.run_id == run_id)
        if open_only:
            query = query.where(PositionRow.quantity != 0.0)
        result = await self._session.execute(query.order_by(PositionRow.symbol))
        return list(result.scalars().all())

    async def append_equity(self, run_id: str, point: dict[str, Any]) -> None:
        self._session.add(EquityPoint(run_id=run_id, **point))

    async def equity_curve(self, run_id: str, *, limit: int = 5000) -> list[EquityPoint]:
        result = await self._session.execute(
            select(EquityPoint)
            .where(EquityPoint.run_id == run_id)
            .order_by(EquityPoint.at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def latest_equity(self, run_id: str) -> EquityPoint | None:
        result = await self._session.execute(
            select(EquityPoint)
            .where(EquityPoint.run_id == run_id)
            .order_by(desc(EquityPoint.at))
            .limit(1)
        )
        return result.scalars().first()


class AssessmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        await self._session.execute(
            _upsert(self._session, AssessmentRow, values, ["assessment_id"])
        )

    async def recent(self, run_id: str, *, limit: int = 50) -> list[AssessmentRow]:
        result = await self._session.execute(
            select(AssessmentRow)
            .where(AssessmentRow.run_id == run_id)
            .order_by(desc(AssessmentRow.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def rejection_rate(self, run_id: str) -> float:
        """The number worth watching: how often the model's output is discarded."""
        total = await self._session.execute(
            select(func.count()).select_from(AssessmentRow).where(AssessmentRow.run_id == run_id)
        )
        used = await self._session.execute(
            select(func.count())
            .select_from(AssessmentRow)
            .where(AssessmentRow.run_id == run_id, AssessmentRow.used.is_(True))
        )
        count = int(total.scalar() or 0)
        return 0.0 if count == 0 else 1.0 - (int(used.scalar() or 0) / count)


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, values: dict[str, Any]) -> None:
        self._session.add(LogRow(**values))

    async def recent(
        self,
        *,
        run_id: str | None = None,
        limit: int = 200,
        level: str | None = None,
        channel: str | None = None,
    ) -> list[LogRow]:
        query = select(LogRow)
        if run_id:
            query = query.where(LogRow.run_id == run_id)
        if level:
            query = query.where(LogRow.level == level)
        if channel:
            query = query.where(LogRow.channel == channel)
        result = await self._session.execute(query.order_by(desc(LogRow.at)).limit(limit))
        return list(result.scalars().all())


class BacktestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, values: dict[str, Any]) -> None:
        await self._session.execute(_upsert(self._session, BacktestRow, values, ["run_id"]))

    async def list_recent(self, limit: int = 25) -> list[BacktestRow]:
        result = await self._session.execute(
            select(BacktestRow).order_by(desc(BacktestRow.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get(self, run_id: str) -> BacktestRow | None:
        return await self._session.get(BacktestRow, run_id)


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        await self._session.execute(_upsert(self._session, NewsRow, values, ["news_id"]))

    async def recent(self, *, limit: int = 50, run_id: str | None = None) -> list[NewsRow]:
        query = select(NewsRow)
        if run_id:
            query = query.where(NewsRow.run_id == run_id)
        result = await self._session.execute(
            query.order_by(desc(NewsRow.published_at)).limit(limit)
        )
        return list(result.scalars().all())


__all__ = [
    "AssessmentRepository",
    "BacktestRepository",
    "DecisionRepository",
    "EventRepository",
    "FillRepository",
    "LogRepository",
    "NewsRepository",
    "OrderRepository",
    "PortfolioRepository",
    "RunRepository",
]
