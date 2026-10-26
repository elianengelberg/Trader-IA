"""Types and numeric precision on PostgreSQL.

* ``DateTime(timezone=True)`` is ``timestamptz``: an instant, stored in UTC, read back
  timezone-aware whatever the server's ``TimeZone`` (the disposable cluster runs on
  America/Argentina/Buenos_Aires on purpose). SQLite stores the wall-clock text and
  reads it back naive; the restore paths normalise both (``as_utc``), and this pins that
  the aware form round-trips the same instant to the microsecond.
* ``Float`` is ``double precision``: prices and quantities round-trip bit for bit,
  including the float artefacts the account code is written around
  (0.001932 + 0.002064 == 0.0039959999999999996).
* Where PostgreSQL is stricter than SQLite — ``VARCHAR(n)`` lengths, JSON without
  NaN/Infinity, text without NUL — the difference is pinned as such: a value SQLite
  accepts silently and PostgreSQL refuses is a write that only production loses.
"""

from __future__ import annotations

import math
import struct
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order
from tia.persistence import (
    Database,
    DecisionRepository,
    EdgeStateRepository,
    FillRepository,
    IncidentRepository,
    OrderRepository,
    RiskStateRepository,
    RunRepository,
)
from tia.persistence.models import (
    FillRow,
    MarketMakerFillRow,
    MarketMakerJournalRow,
    OrderRow,
    RunRecord,
)

INSTANTS = [
    datetime(2026, 10, 22, 21, 59, 59, 999_999, tzinfo=UTC),
    datetime(2026, 10, 22, 18, 59, 59, 999_999, tzinfo=timezone(timedelta(hours=-3))),
    datetime(2026, 3, 29, 1, 30, 0, 1, tzinfo=timezone(timedelta(hours=5, minutes=45))),
    datetime(1970, 1, 1, 0, 0, 0, 1, tzinfo=UTC),
    datetime(2099, 12, 31, 23, 59, 59, 999_999, tzinfo=UTC),
]

#: Prices, quantities and fees as the account produces them, plus IEEE edge values.
FLOATS = [
    0.1, 0.2, 0.1 + 0.2, 0.001932, 0.002064, 0.001932 + 0.002064, 1e-8, 0.00000001 * 3,
    50_000.12345678, 123_456_789.123_456_78, 2.0**53 + 2.0, 5e-324, 1.7976931348623157e308,
    -0.0, -2.5e-7,
]


def _bits(value: float) -> bytes:
    return struct.pack(">d", value)


async def _run(database: Database, run_id: str = "run_types", *, started_at: datetime | None = None) -> None:
    async with database.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime",
            started_at=started_at or datetime(2026, 10, 22, tzinfo=UTC), initial_capital=10_000.0,
            seed=1, symbols=("BTC-USD",),
        )


async def test_timestamptz_round_trips_the_same_instant_to_the_microsecond(pg_db: Database) -> None:
    for index, instant in enumerate(INSTANTS):
        await _run(pg_db, f"run_{index}", started_at=instant)
    async with pg_db.session() as session:
        server_tz = (await session.execute(text("SHOW timezone"))).scalar_one()
        rows = {r.run_id: r.started_at for r in (await session.execute(select(RunRecord))).scalars()}
    for index, instant in enumerate(INSTANTS):
        got = rows[f"run_{index}"]
        assert got.tzinfo is not None and got.utcoffset() == timedelta(0), (server_tz, got)
        assert got == instant and got.microsecond == instant.astimezone(UTC).microsecond


async def test_a_naive_datetime_is_stored_as_utc(pg_db: Database) -> None:
    """asyncpg reads a naive value as UTC — the same convention ``_as_utc`` applies to
    SQLite's naive reads, so both dialects agree on what a naive stamp meant."""
    await _run(pg_db, started_at=datetime(2026, 10, 22, 12, 0))
    async with pg_db.session() as session:
        row = await session.get(RunRecord, "run_types")
    assert row is not None and row.started_at == datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


async def test_the_risk_rebuild_draws_the_utc_day_line_at_the_microsecond(pg_db: Database) -> None:
    """Two entries a microsecond either side of 00:00 UTC — on a server whose own
    TimeZone is not UTC. Only the one after midnight is today's."""
    midnight = datetime(2026, 10, 22, 0, 0, tzinfo=UTC)
    await _run(pg_db, started_at=midnight - timedelta(hours=1))
    async with pg_db.session() as session:
        for name, at in (("before", midnight - timedelta(microseconds=1)), ("after", midnight)):
            order = Order(
                order_id=f"ord_{name}", client_order_id=f"coid_{name}", intent_id="int",
                signal_id=f"sig_{name}", symbol="BTC-USD", side=Side.BUY, order_type=OrderType.MARKET,
                quantity=0.01, state=OrderState.FILLED, filled_quantity=0.01,
                average_fill_price=50_000.0, fees_paid=0.5, created_at=at, updated_at=at,
            )
            await OrderRepository(session).upsert("run_types", order)
            await FillRepository(session).append("run_types", Fill(
                fill_id=f"fill_{name}", order_id=f"ord_{name}", sequence=0, symbol="BTC-USD",
                side=Side.BUY, quantity=0.01, price=50_000.0, fee=0.5, filled_at=at,
            ))
    async with pg_db.session() as session:
        restore = await RiskStateRepository(session).rebuild(now=midnight + timedelta(minutes=5))
    assert restore.complete, restore
    assert restore.entries_today == 1 and restore.entries_today_by_symbol == {"BTC-USD": 1}
    assert restore.last_entry_at["BTC-USD"] == midnight


async def test_float_columns_round_trip_ieee_doubles_bit_for_bit(pg_db: Database) -> None:
    await _run(pg_db)
    async with pg_db.session() as session:
        for index, value in enumerate(FLOATS):
            order = Order(
                order_id=f"ord_{index}", client_order_id=f"coid_{index}", intent_id="int",
                signal_id="sig", symbol="BTC-USD", side=Side.BUY, order_type=OrderType.MARKET,
                quantity=abs(value) or 1.0, state=OrderState.FILLED, filled_quantity=abs(value) or 1.0,
                average_fill_price=50_000.0, fees_paid=0.0, created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await OrderRepository(session).upsert("run_types", order)
            # Fill is a validated domain model; the row is written as the repository does.
            session.add(FillRow(
                fill_id=f"fill_{index}", run_id="run_types", order_id=f"ord_{index}", sequence=index,
                symbol="BTC-USD", side="buy", quantity=value, price=value, fee=value,
                filled_at=datetime.now(UTC),
            ))
    async with pg_db.session() as session:
        rows = {r.fill_id: r for r in (await session.execute(select(FillRow))).scalars()}
        orders = {r.order_id: r for r in (await session.execute(select(OrderRow))).scalars()}
        column_type = (await session.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'fills' AND column_name = 'quantity'"
        ))).scalar_one()
        two_partials = (await session.execute(
            select(func.sum(FillRow.quantity)).where(FillRow.fill_id.in_(["fill_3", "fill_4"]))
        )).scalar_one()
    assert column_type == "double precision"
    for index, value in enumerate(FLOATS):
        row = rows[f"fill_{index}"]
        for got in (row.quantity, row.price, row.fee):
            assert _bits(got) == _bits(value), (index, value, got)
        assert _bits(orders[f"ord_{index}"].quantity) == _bits(abs(value) or 1.0)
    # The sum the database computes is the sum Python computes: the account cross-check
    # compares the two.
    assert two_partials == 0.001932 + 0.002064 == 0.0039959999999999996


async def test_money_aggregates_agree_with_python_over_the_journal(pg_db: Database) -> None:
    """The journal's dollar figures are computed in SQL; the same rows summed in Python
    give the same numbers (``pytest.approx`` only for summation order)."""
    async with pg_db.session() as session:
        repo = EdgeStateRepository(session)
        for index in range(60):
            await repo.append({
                "outcome_id": f"o-{index:03d}", "run_id": "run_a", "signal_id": f"s-{index}",
                "symbol": "BTC-USD", "regime": "trending_up" if index % 3 else "ranging",
                "direction": "long" if index % 2 else "short", "confidence": 0.6 + index / 1000,
                "entry_price": 50_000.0 + index * 1.37, "exit_price": 50_100.0,
                "quantity": 0.001 * (1 + index % 7), "gross_bps": 20.0 - index * 0.75,
                "fees_bps": 10.0, "net_bps": 10.0 - index * 0.75,
                "exploratory": index % 10 == 0, "closed_at": datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=index),
                "source": "live" if index % 4 else "sim", "exit_reason": None if index % 5 else "time stop",
            })
    async with pg_db.session() as session:
        repo = EdgeStateRepository(session)
        rows = await repo.load_all()
        journal = await repo.journal(limit=500)
        record = await repo.dollar_record()
        curve = await repo.dollar_curve(source="live", points=10)
        track = await repo.track_record()
        exits = await repo.exits()
    pnl = {r.outcome_id: r.net_bps * r.entry_price * r.quantity / 10_000.0 for r in rows}
    assert journal["total"] == 60
    assert journal["summary"]["pnl_usd"] == pytest.approx(round(sum(pnl.values()), 2), abs=0.005)
    live = [r for r in rows if r.source == "live"]
    assert record["live"]["trades"] == len(live)
    assert record["live"]["pnl_usd"] == pytest.approx(sum(pnl[r.outcome_id] for r in live), rel=1e-12)
    ordered = sorted(live, key=lambda r: (r.closed_at, r.outcome_id))
    running = 0.0
    totals = []
    for row in ordered:
        running += pnl[row.outcome_id]
        totals.append(round(running, 2))
    assert curve[-1] == pytest.approx(totals[-1], abs=0.011)
    claims = [r for r in live if not r.exploratory]
    assert track["closed_trades"] == len(claims)
    assert track["first_closed_at"] == min(r.closed_at for r in claims)
    assert track["first_closed_at"].tzinfo is not None
    assert {e["exit_reason"] for e in exits} == {"time stop", "unrecorded"}


# ---------------------------------------------------- where PostgreSQL is stricter than SQLite


async def test_varchar_lengths_are_enforced(pg_db: Database) -> None:
    """SQLite ignores ``VARCHAR(n)``; PostgreSQL refuses the 65th character."""
    await _run(pg_db)
    with pytest.raises(DBAPIError, match="value too long for type character varying"):
        async with pg_db.session() as session:
            await DecisionRepository(session).record({
                "decision_id": "d1", "run_id": "run_types", "symbol": "BTC-USD",
                "decided_at": datetime.now(UTC), "direction": "long", "verdict": "approved",
                "signal_id": "s" * 65,
            })


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
async def test_json_columns_refuse_nan_and_infinity(pg_db: Database, value: float) -> None:
    """``json.dumps`` writes ``NaN``/``Infinity``; SQLite stores the text, PostgreSQL's
    ``json`` type refuses it. The decision path filters features to finite values
    (``finite_values()``); a raw dict that reached a JSON column would not be."""
    await _run(pg_db)
    with pytest.raises(DBAPIError, match="invalid input syntax for type json"):
        async with pg_db.session() as session:
            await DecisionRepository(session).record({
                "decision_id": "d1", "run_id": "run_types", "symbol": "BTC-USD",
                "decided_at": datetime.now(UTC), "direction": "long", "verdict": "approved",
                "features": {"x": value},
            })


async def test_float_columns_keep_nan_and_infinity(pg_db: Database) -> None:
    """The other way round: ``double precision`` stores NaN and ±Infinity (SQLite turns
    NaN into NULL)."""
    async with pg_db.session() as session:
        session.add(MarketMakerJournalRow(row_id="j", run_id="r", seq=0, t_ms=2**62, kind="k", payload={}))
        for name, value in (("nan", math.nan), ("inf", math.inf), ("ninf", -math.inf)):
            session.add(MarketMakerFillRow(
                fill_id=name, run_id="r", order_id="", t_ms=2**62, side="buy", price=value,
                quantity=1.0, fee_usd=0.0, realised_usd=0.0, mid_at_fill=None,
                resolution="confirmed", venue_trade_ids=[], regimes={}, markout_bps=None,
            ))
    async with pg_db.session() as session:
        prices = dict((await session.execute(text("SELECT fill_id, price FROM mm_fills"))).all())
        t_ms = (await session.execute(text("SELECT MAX(t_ms) FROM mm_journal"))).scalar_one()
    assert math.isnan(prices["nan"]) and prices["inf"] == math.inf and prices["ninf"] == -math.inf
    assert t_ms == 2**62, "t_ms is BIGINT: epoch milliseconds do not overflow"


async def test_text_refuses_a_nul_character(pg_db: Database) -> None:
    with pytest.raises((DBAPIError, ValueError)):
        async with pg_db.session() as session:
            await IncidentRepository(session).record({
                "incident_id": "inc_nul", "at": datetime.now(UTC), "kind": "halt_new_orders",
                "actor": "operator", "reason": "copied from a log\x00", "run_id": "", "detail": {},
            })
