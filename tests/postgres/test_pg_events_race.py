"""R24-H3 on PostgreSQL: the event upsert under two overlapping writers.

``EventRepository.append`` upserts ``ON CONFLICT (idempotency_key)``; the envelope also repeats its
primary key ``event_id``. PostgreSQL arbitrates only the conflict-target index, so a writer that
overlaps another writer of the same event used to fail on ``events_pkey``
(``test_pg_concurrency.py::test_two_writers_of_one_redelivered_event_store_it_once_without_errors``).
The append now runs in a savepoint and, when that exact conflict appears, runs once more: by then
the other writer has committed (the losing insert waited for it), and the retry meets its row
through the conflict target as a sequential redelivery would.

What must still fail: a different event that reuses an ``event_id`` under another idempotency
key is a real conflict, not a redelivery, and is not absorbed by the retry.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.postgres.test_pg_concurrency import _WIDEN_THE_WINDOW, _open_run
from tia.events.envelope import EventEnvelope
from tia.persistence import Database, EventRepository
from tia.portfolio.account_journal import EVENT_MARK, AccountMarkPayload

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def _envelope(event_id: str, key: str, price: float = 50_000.0) -> EventEnvelope[Any]:
    return EventEnvelope(
        event_id=event_id, event_type=EVENT_MARK, source="live", occurred_at=AT, ingestion_at=AT,
        recorded_at=AT, correlation_id="run_events", idempotency_key=key,
        payload=AccountMarkPayload(symbol="BTC-USD", price=price, at=AT),
    )


async def test_a_reused_event_id_under_another_key_is_still_refused(pg_db: Database) -> None:
    await _open_run(pg_db, "run_events")
    async with pg_db.session() as session:
        await EventRepository(session).append("run_events", _envelope("evt_x", "mark:a"))
    with pytest.raises(IntegrityError, match="events_pkey"):
        async with pg_db.session() as session:
            await EventRepository(session).append("run_events", _envelope("evt_x", "mark:b"))
    async with pg_db.session() as session:
        rows = (await session.execute(text("SELECT event_id, idempotency_key FROM events"))).all()
    assert [tuple(r) for r in rows] == [("evt_x", "mark:a")]


async def test_a_batch_that_overlaps_another_writer_of_one_of_its_events_keeps_all_its_events(pg_url: str) -> None:
    """The ``account_events`` case: writer B appends two events in one transaction, the first of
    them while writer A is still writing it. Before: B's first append failed on ``events_pkey`` and
    the transaction, with the event that came after it, was lost."""
    setup = Database(pg_url)
    await setup.ensure_schema()
    await _open_run(setup, "run_events")
    async with setup.session() as session:
        for statement in _WIDEN_THE_WINDOW:
            await session.execute(text(statement))
    writer_a, writer_b = Database(pg_url), Database(pg_url)
    try:
        for database in (writer_a, writer_b):
            assert await database.ping()

        async def a_writes() -> None:
            async with writer_a.session() as session:
                await EventRepository(session).append("run_events", _envelope("evt_shared", "mark:shared"))

        async def b_writes_a_batch() -> None:
            async with writer_b.session() as session:
                repository = EventRepository(session)
                await repository.append("run_events", _envelope("evt_shared", "mark:shared", price=50_001.0))
                await repository.append("run_events", _envelope("evt_own", "mark:own"))

        first = asyncio.create_task(a_writes())
        await asyncio.sleep(0.15)
        results = await asyncio.gather(first, b_writes_a_batch(), return_exceptions=True)
        errors = [f"{type(r).__name__}: {str(r).splitlines()[0][:200]}" for r in results if isinstance(r, Exception)]
        async with setup.session() as session:
            rows = dict((await session.execute(text("SELECT event_id, CAST(payload AS TEXT) FROM events"))).all())
        assert errors == [], errors
        assert set(rows) == {"evt_own", "evt_shared"}
        assert "50001" in rows["evt_shared"], "B came second: its redelivery is the row, as a sequential one would be"
    finally:
        for database in (writer_a, writer_b, setup):
            await database.close()
