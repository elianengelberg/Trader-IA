"""Constraints, cascades and idempotent upserts on PostgreSQL.

``_upsert`` (persistence/repositories.py) builds ``pg_insert(...).on_conflict_do_update``
here and ``sqlite_insert`` everywhere else: every repository that writes by upsert is
exercised once on the PostgreSQL branch below, replayed, and read back as one row. The
foreign keys and unique constraints the schema relies on are enforced by the server
itself (SQLite needs ``PRAGMA foreign_keys=ON`` for that; PostgreSQL always does).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order
from tia.domain.portfolio import PortfolioState, Position
from tia.events.envelope import EventEnvelope
from tia.persistence import (
    AssessmentRepository,
    BacktestRepository,
    CapitalEventRepository,
    Database,
    DecisionRepository,
    EdgeStateRepository,
    EventRepository,
    FillRepository,
    LatencyRepository,
    MarketMakerRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
    RunRepository,
)
from tia.persistence.models import (
    DecisionRow,
    EdgeOutcomeRow,
    EquityPoint,
    EventRecord,
    FillRow,
    OrderRow,
    PositionRow,
)
from tia.portfolio.account_journal import EVENT_MARK, AccountMarkPayload

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


async def _run(database: Database, run_id: str = "run_c") -> None:
    async with database.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime", started_at=AT,
            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
        )


def _order(order_id: str = "ord_1", *, state: OrderState = OrderState.ACKNOWLEDGED, filled: float = 0.0,
           client_order_id: str | None = None) -> Order:
    return Order(
        order_id=order_id, client_order_id=client_order_id or f"coid_{order_id}", intent_id="int",
        signal_id="sig", symbol="BTC-USD", side=Side.BUY, order_type=OrderType.MARKET, quantity=0.02,
        state=state, filled_quantity=filled, average_fill_price=50_000.0 if filled else 0.0,
        fees_paid=0.0, created_at=AT, updated_at=AT + timedelta(seconds=filled * 100),
    )


def _fill(fill_id: str = "fill_1", order_id: str = "ord_1") -> Fill:
    return Fill(fill_id=fill_id, order_id=order_id, sequence=0, symbol="BTC-USD", side=Side.BUY,
                quantity=0.02, price=50_000.0, fee=1.0, filled_at=AT)


async def _count(database: Database, model: Any) -> int:
    async with database.session() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# ----------------------------------------------------------------------- foreign keys


async def test_a_fill_for_an_order_the_store_does_not_know_is_refused(pg_db: Database) -> None:
    await _run(pg_db)
    with pytest.raises(IntegrityError, match="fills_order_id_fkey"):
        async with pg_db.session() as session:
            await FillRepository(session).append("run_c", _fill(order_id="ord_never_written"))
    assert await _count(pg_db, FillRow) == 0


async def test_an_order_for_a_run_the_store_does_not_know_is_refused(pg_db: Database) -> None:
    with pytest.raises(IntegrityError, match="orders_run_id_fkey"):
        async with pg_db.session() as session:
            await OrderRepository(session).upsert("run_never_written", _order())


async def test_deleting_a_run_cascades_to_its_rows_and_only_its_rows(pg_db: Database) -> None:
    for run_id in ("run_gone", "run_kept"):
        await _run(pg_db, run_id)
        async with pg_db.session() as session:
            await OrderRepository(session).upsert(run_id, _order(f"ord_{run_id}", state=OrderState.FILLED, filled=0.02))
            await FillRepository(session).append(run_id, _fill(f"fill_{run_id}", f"ord_{run_id}"))
            await DecisionRepository(session).record({
                "decision_id": f"dec_{run_id}", "run_id": run_id, "symbol": "BTC-USD", "decided_at": AT,
                "direction": "long", "verdict": "approved",
            })
            await PortfolioRepository(session).append_equity(run_id, {"at": AT, "equity": 1.0, "cash": 1.0})
            await EventRepository(session).append(run_id, _mark(run_id, f"evt_{run_id}"))
    async with pg_db.session() as session:
        await RunRepository(session).delete("run_gone")
    for model in (OrderRow, FillRow, DecisionRow, EquityPoint, EventRecord):
        async with pg_db.session() as session:
            runs = (await session.execute(select(model.run_id))).scalars().all()
        assert runs == ["run_kept"], (model.__tablename__, runs)


# ------------------------------------------------------------------ unique constraints


async def test_a_client_order_id_belongs_to_one_order(pg_db: Database) -> None:
    await _run(pg_db)
    async with pg_db.session() as session:
        await OrderRepository(session).upsert("run_c", _order("ord_1", client_order_id="coid_shared"))
    with pytest.raises(IntegrityError, match="uq_orders_client_id"):
        async with pg_db.session() as session:
            await OrderRepository(session).upsert("run_c", _order("ord_2", client_order_id="coid_shared"))


def _mark(run_id: str, event_id: str, key: str | None = None, price: float = 50_000.0) -> EventEnvelope[Any]:
    return EventEnvelope(
        event_id=event_id, event_type=EVENT_MARK, source="live", occurred_at=AT, ingestion_at=AT,
        recorded_at=AT, correlation_id=run_id, idempotency_key=key or f"mark:{event_id}",
        payload=AccountMarkPayload(symbol="BTC-USD", price=price, at=AT),
    )


async def test_a_redelivered_event_is_one_row_with_the_latest_payload(pg_db: Database) -> None:
    """The unique idempotency key is the upsert target: a redelivery under a new event id
    replaces the row instead of adding one."""
    await _run(pg_db)
    async with pg_db.session() as session:
        await EventRepository(session).append("run_c", _mark("run_c", "evt_first", "mark:k", price=1.0))
    async with pg_db.session() as session:
        await EventRepository(session).append("run_c", _mark("run_c", "evt_again", "mark:k", price=2.0))
    async with pg_db.session() as session:
        rows = (await session.execute(select(EventRecord))).scalars().all()
    assert len(rows) == 1 and rows[0].payload["price"] == 2.0 and rows[0].event_id == "evt_again"


# ----------------------------------------------------------------- idempotent upserts


async def test_order_and_fill_replays_are_one_row_each_and_the_order_advances(pg_db: Database) -> None:
    await _run(pg_db)
    for _ in range(3):
        async with pg_db.session() as session:
            await OrderRepository(session).upsert("run_c", _order(state=OrderState.ACKNOWLEDGED))
    async with pg_db.session() as session:
        await OrderRepository(session).upsert("run_c", _order(state=OrderState.FILLED, filled=0.02))
        for _ in range(3):
            await FillRepository(session).append("run_c", _fill())
    async with pg_db.session() as session:
        order = await OrderRepository(session).get("ord_1")
        fills = await FillRepository(session).for_order("ord_1")
    assert order is not None and order.state == "filled" and order.filled_quantity == 0.02
    assert order.updated_at > order.created_at
    assert [f.fill_id for f in fills] == ["fill_1"]


async def test_positions_upsert_on_run_and_symbol(pg_db: Database) -> None:
    await _run(pg_db)
    for quantity in (0.01, 0.03, 0.0):
        portfolio = PortfolioState(
            cash=10_000.0, initial_capital=10_000.0,
            positions={"BTC-USD": Position(symbol="BTC-USD", quantity=quantity, average_price=50_000.0)},
        )
        async with pg_db.session() as session:
            await PortfolioRepository(session).sync_positions("run_c", portfolio, AT)
    async with pg_db.session() as session:
        rows = (await session.execute(select(PositionRow))).scalars().all()
        still_open = await PortfolioRepository(session).positions("run_c")
    assert [(r.run_id, r.symbol, r.quantity) for r in rows] == [("run_c", "BTC-USD", 0.0)]
    assert still_open == [], "a flat position is kept but is not open"


async def test_a_replayed_outcome_keeps_its_first_ingestion_stamp(pg_db: Database) -> None:
    """``ingested_at`` is the server's write clock and the refresher's watermark. The
    upsert does not touch it, so a replay neither moves the row forward nor duplicates it."""
    row = {
        "outcome_id": "o-1", "run_id": "run_a", "signal_id": "s-1", "symbol": "BTC-USD",
        "regime": "trending_up", "direction": "long", "confidence": 0.7, "entry_price": 50_000.0,
        "exit_price": 50_100.0, "quantity": 0.01, "gross_bps": 20.0, "fees_bps": 10.0,
        "net_bps": 10.0, "closed_at": AT, "source": "live",
    }
    async with pg_db.session() as session:
        await EdgeStateRepository(session).append(row)
    async with pg_db.session() as session:
        first = (await session.execute(select(EdgeOutcomeRow.ingested_at))).scalar_one()
        await session.execute(text("SELECT pg_sleep(0.01)"))
    async with pg_db.session() as session:
        await EdgeStateRepository(session).append({**row, "net_bps": 11.0})
    async with pg_db.session() as session:
        rows = (await session.execute(select(EdgeOutcomeRow))).scalars().all()
    assert len(rows) == 1 and rows[0].net_bps == 11.0 and rows[0].ingested_at == first


async def test_every_upserting_repository_takes_the_postgresql_branch_and_is_idempotent(
    pg_db: Database,
) -> None:
    """Each remaining ``_upsert`` caller, written twice under its deterministic id."""
    await _run(pg_db)
    writes = {
        "decisions": lambda s: DecisionRepository(s).record({
            "decision_id": "dec_1", "run_id": "run_c", "symbol": "BTC-USD", "decided_at": AT,
            "direction": "long", "verdict": "approved", "features": {"rsi": 51.5}}),
        "assessments": lambda s: AssessmentRepository(s).record({
            "assessment_id": "as_1", "run_id": "run_c", "symbol": "BTC-USD", "created_at": AT,
            "expires_at": AT + timedelta(minutes=5)}),
        "news": lambda s: NewsRepository(s).record({
            "news_id": "news_1", "published_at": AT, "ingested_at": AT, "headline": "h"}),
        "backtests": lambda s: BacktestRepository(s).save({
            "run_id": "bt_1", "created_at": AT, "equity_curve": [1.0, 1.5], "conditions": {"seed": 1}}),
        "capital_events": lambda s: CapitalEventRepository(s).append({
            "event_id": "cap_1", "run_id": "run_c", "at": AT, "kind": "deposit", "amount": 100.0}),
        "latency_samples": lambda s: LatencyRepository(s).append({
            "sample_id": "lat_1", "run_id": "run_c", "at": AT, "segments_ms": {"a": 1.5}, "total_ms": 1.5}),
        "mm_journal": lambda s: MarketMakerRepository(s).append_journal("run_c", 7, {"t": 1_760_000_000_000, "kind": "hold"}),
        "mm_fills": lambda s: MarketMakerRepository(s).upsert_fill("run_c", {
            "fill_id": "mmf_1", "t_ms": 1_760_000_000_000, "price": 50_000.0, "quantity": 0.001,
            "venue_trade_ids": [1, 2], "regimes": {"vol": "low"}}),
        "mm_ledger": lambda s: MarketMakerRepository(s).save_ledger(
            "run_c", state={"cash": 100.0}, config_id="c", profile_id="p", latency_scenario="l", at=AT),
    }
    for _ in range(2):
        for write in writes.values():
            async with pg_db.session() as session:
                assert session.bind.dialect.name == "postgresql"
                await write(session)
    async with pg_db.session() as session:
        counts = {
            table: (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()  # noqa: S608
            for table in writes
        }
        journal = await MarketMakerRepository(session).journal("run_c")
    assert counts == dict.fromkeys(writes, 1), counts
    assert journal == [{"t": 1_760_000_000_000, "kind": "hold"}]
