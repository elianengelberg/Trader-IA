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

from sqlalchemy import case, delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tia.core.logging import get_logger
from tia.domain.orders import Fill, Order
from tia.domain.portfolio import PortfolioState
from tia.events.envelope import EventEnvelope
from tia.persistence.models import (
    ActivationAttemptRow,
    AssessmentRow,
    BacktestRow,
    CapitalEventRow,
    DecisionRow,
    EdgeOutcomeRow,
    EquityPoint,
    EventRecord,
    FillRow,
    IncidentRow,
    LatencySampleRow,
    LogRow,
    NewsRow,
    OrderRow,
    PositionRow,
    ReconciliationRow,
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


class EdgeStateRepository:
    """The edge estimator's memory.

    The estimator itself stays a pure in-memory structure; this repository is how it
    survives a restart. Load order at startup is: read every row, rebuild the buckets,
    and only then let the runtime trade — a runtime that starts deciding before its
    evidence is loaded is a fresh system wearing an experienced system's configuration.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, values: dict[str, Any]) -> None:
        await self._session.execute(
            _upsert(self._session, EdgeOutcomeRow, values, ["outcome_id"])
        )

    async def load_all(self, *, source: str | None = None) -> list[EdgeOutcomeRow]:
        query = select(EdgeOutcomeRow).order_by(EdgeOutcomeRow.closed_at)
        if source:
            query = query.where(EdgeOutcomeRow.source == source)
        return list((await self._session.execute(query)).scalars().all())

    async def count(self) -> int:
        return int(
            (await self._session.execute(select(func.count(EdgeOutcomeRow.outcome_id)))).scalar()
            or 0
        )

    async def journal(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        source: str | None = None,
        regime: str | None = None,
        direction: str | None = None,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        """The complete closed-trade record, newest first, with the filter's totals.

        Every round trip the system ever closed — training, demo and the 24/7 session —
        with what it expected, what it got, and what it was worth in dollars at the size
        it actually carried. The totals are computed over the *whole* filtered set, not
        the page, so "how do longs in ranging markets do?" is answered by the strip, not
        by scrolling.
        """
        conditions = []
        if source:
            conditions.append(EdgeOutcomeRow.source == source)
        if regime:
            conditions.append(EdgeOutcomeRow.regime == regime)
        if direction:
            conditions.append(EdgeOutcomeRow.direction == direction)
        if outcome == "win":
            conditions.append(EdgeOutcomeRow.net_bps > 0)
        elif outcome == "loss":
            conditions.append(EdgeOutcomeRow.net_bps <= 0)

        pnl = (
            EdgeOutcomeRow.net_bps
            * EdgeOutcomeRow.entry_price
            * EdgeOutcomeRow.quantity
            / 10_000.0
        )
        totals_query = select(
            func.count(EdgeOutcomeRow.outcome_id),
            func.sum(case((EdgeOutcomeRow.net_bps > 0, 1), else_=0)),
            func.sum(pnl),
        )
        rows_query = select(EdgeOutcomeRow).order_by(desc(EdgeOutcomeRow.closed_at))
        for condition in conditions:
            totals_query = totals_query.where(condition)
            rows_query = rows_query.where(condition)
        count, wins, total_pnl = (await self._session.execute(totals_query)).one()
        rows = list(
            (await self._session.execute(rows_query.offset(offset).limit(limit)))
            .scalars()
            .all()
        )

        def shaped(row: EdgeOutcomeRow) -> dict[str, Any]:
            notional = float(row.entry_price or 0.0) * float(row.quantity or 0.0)
            return {
                "outcome_id": row.outcome_id,
                "run_id": row.run_id,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "source": row.source,
                "symbol": row.symbol,
                "regime": row.regime,
                "direction": row.direction,
                "confidence": round(float(row.confidence), 4),
                "entry_price": float(row.entry_price),
                "exit_price": float(row.exit_price),
                "quantity": float(row.quantity),
                "notional_usd": round(notional, 2),
                "gross_bps": round(float(row.gross_bps), 4),
                "fees_bps": round(float(row.fees_bps), 4),
                "net_bps": round(float(row.net_bps), 4),
                "expected_net_bps": round(float(row.expected_net_bps), 4),
                "net_usd": round(notional * float(row.net_bps) / 10_000.0, 2),
                "expected_usd": round(notional * float(row.expected_net_bps) / 10_000.0, 2),
                "exploratory": bool(getattr(row, "exploratory", False)),
                "is_win": float(row.net_bps) > 0,
            }

        count = int(count or 0)
        return {
            "rows": [shaped(row) for row in rows],
            "total": count,
            "offset": offset,
            "limit": limit,
            "summary": {
                "trades": count,
                "wins": int(wins or 0),
                "win_rate": round(int(wins or 0) / count, 4) if count else 0.0,
                "pnl_usd": round(float(total_pnl or 0.0), 2),
                "mean_trade_usd": round(float(total_pnl or 0.0) / count, 2) if count else 0.0,
            },
        }

    async def dollar_record(self) -> dict[str, Any]:
        """Every closed trade's result in dollars, grouped by where it came from.

        Basis points are what the engine learns in; this is the question a person asks —
        "so did it make money?". Each row's dollars are its own: ``net_bps`` applied to
        the notional that row actually carried, never to an assumed one.

        Rows are returned per source rather than pooled, because pooling them would state
        something false. ``sim`` rows come from thousands of *independent* simulation
        runs, each with its own starting capital; their sum is "what these trades made",
        not the balance of an account that took them in sequence. Only ``live`` rows —
        the 24/7 session — form one continuous account, and the caller keeps them apart.
        """
        pnl = (
            EdgeOutcomeRow.net_bps
            * EdgeOutcomeRow.entry_price
            * EdgeOutcomeRow.quantity
            / 10_000.0
        )
        rows = (
            await self._session.execute(
                select(
                    EdgeOutcomeRow.source,
                    func.count(EdgeOutcomeRow.outcome_id),
                    func.sum(pnl),
                    func.sum(case((EdgeOutcomeRow.net_bps > 0, 1), else_=0)),
                    func.sum(EdgeOutcomeRow.entry_price * EdgeOutcomeRow.quantity),
                ).group_by(EdgeOutcomeRow.source)
            )
        ).all()
        return {
            str(source or "unknown"): {
                "trades": int(count or 0),
                "pnl_usd": float(total or 0.0),
                "wins": int(wins or 0),
                "notional_sum_usd": float(notional or 0.0),
            }
            for source, count, total, wins, notional in rows
        }

    async def dollar_curve(self, *, source: str, points: int = 240) -> list[float]:
        """The running dollar total of one source's trades, downsampled to ``points``.

        The shape of the record, cheap enough to poll. Reads three columns, not whole
        rows, and thins the result in Python rather than sending thousands of points to a
        browser that would draw them one pixel apart.
        """
        rows = (
            await self._session.execute(
                select(
                    EdgeOutcomeRow.net_bps,
                    EdgeOutcomeRow.entry_price,
                    EdgeOutcomeRow.quantity,
                )
                .where(EdgeOutcomeRow.source == source)
                .order_by(EdgeOutcomeRow.closed_at)
            )
        ).all()
        if not rows:
            return []
        running = 0.0
        cumulative: list[float] = []
        for net_bps, entry_price, quantity in rows:
            running += (net_bps or 0.0) * (entry_price or 0.0) * (quantity or 0.0) / 10_000.0
            cumulative.append(round(running, 2))
        if len(cumulative) <= points:
            return cumulative
        step = len(cumulative) / points
        thinned = [cumulative[min(len(cumulative) - 1, int(i * step))] for i in range(points)]
        thinned[-1] = cumulative[-1]  # the last point is the answer; never lose it
        return thinned

    async def track_record(self, *, source: str = "live") -> dict[str, Any]:
        """What the gate's paper-track-record check reads: span and volume of evidence.

        Days are measured from the first to the last *closed* trade rather than from any
        run boundary, because a run that sat idle for a week proved nothing during it.

        Counts **only** rows written by the real-time session (``source="live"`` — the tag
        the 24/7 runtime writes, paper fills included). Demo scenarios and training
        simulations feed the edge estimator, but a track record padded with synthetic
        trades would let the activation gate be satisfied by a market that never existed —
        so they are excluded here by construction, not by convention.
        """
        result = await self._session.execute(
            select(
                func.count(EdgeOutcomeRow.outcome_id),
                func.min(EdgeOutcomeRow.closed_at),
                func.max(EdgeOutcomeRow.closed_at),
                func.sum(EdgeOutcomeRow.net_bps),
            ).where(EdgeOutcomeRow.source == source)
        )
        count, first, last, net_sum = result.one()
        days = 0.0
        if first is not None and last is not None:
            days = max(0.0, (last - first).total_seconds() / 86_400.0)
        return {
            "closed_trades": int(count or 0),
            "first_closed_at": first,
            "last_closed_at": last,
            "span_days": days,
            "net_bps_sum": float(net_sum or 0.0),
        }


class ActivationRepository:
    """Arming attempts, kept forever. Failure is the common case and the useful record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        self._session.add(ActivationAttemptRow(**values))

    async def history(self, *, limit: int = 50) -> list[ActivationAttemptRow]:
        result = await self._session.execute(
            select(ActivationAttemptRow)
            .order_by(desc(ActivationAttemptRow.attempted_at))
            .limit(limit)
        )
        return list(result.scalars().all())


class ReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        self._session.add(ReconciliationRow(**values))

    async def recent(self, *, limit: int = 50, run_id: str = "") -> list[ReconciliationRow]:
        query = select(ReconciliationRow).order_by(desc(ReconciliationRow.at)).limit(limit)
        if run_id:
            query = query.where(ReconciliationRow.run_id == run_id)
        return list((await self._session.execute(query)).scalars().all())

    async def break_count(self, *, run_id: str = "") -> int:
        query = select(func.count(ReconciliationRow.reconciliation_id)).where(
            ReconciliationRow.clean.is_(False)
        )
        if run_id:
            query = query.where(ReconciliationRow.run_id == run_id)
        return int((await self._session.execute(query)).scalar() or 0)


class CapitalEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, values: dict[str, Any]) -> None:
        await self._session.execute(
            _upsert(self._session, CapitalEventRow, values, ["event_id"])
        )

    async def recent(self, *, limit: int = 100, run_id: str = "") -> list[CapitalEventRow]:
        query = select(CapitalEventRow).order_by(desc(CapitalEventRow.at)).limit(limit)
        if run_id:
            query = query.where(CapitalEventRow.run_id == run_id)
        return list((await self._session.execute(query)).scalars().all())


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, values: dict[str, Any]) -> None:
        self._session.add(IncidentRow(**values))

    async def recent(self, *, limit: int = 100, kind: str = "") -> list[IncidentRow]:
        query = select(IncidentRow).order_by(desc(IncidentRow.at)).limit(limit)
        if kind:
            query = query.where(IncidentRow.kind == kind)
        return list((await self._session.execute(query)).scalars().all())


class LatencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, values: dict[str, Any]) -> None:
        await self._session.execute(
            _upsert(self._session, LatencySampleRow, values, ["sample_id"])
        )

    async def recent(self, *, limit: int = 200, run_id: str = "") -> list[LatencySampleRow]:
        query = select(LatencySampleRow).order_by(desc(LatencySampleRow.at)).limit(limit)
        if run_id:
            query = query.where(LatencySampleRow.run_id == run_id)
        return list((await self._session.execute(query)).scalars().all())


__all__ = [
    "ActivationRepository",
    "AssessmentRepository",
    "BacktestRepository",
    "CapitalEventRepository",
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
