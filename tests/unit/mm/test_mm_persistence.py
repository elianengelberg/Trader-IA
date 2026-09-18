"""The market maker's own tables: written once, read back, and nowhere near the
session's fills, edge outcomes or capital ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from tia.mm.ledger import MarketMakerLedger
from tia.mm.sim import SimulatedFill
from tia.persistence.database import Database
from tia.persistence.models import (
    ALL_TABLES,
    SCHEMA_VERSION,
    FillRow,
    MarketMakerFillRow,
    MarketMakerJournalRow,
    MarketMakerLedgerRow,
)
from tia.persistence.repositories import EdgeStateRepository, MarketMakerRepository

T0 = 1_789_754_400_000


async def test_journal_fills_and_ledger_round_trip_and_stay_apart(tmp_path: Path) -> None:
    assert SCHEMA_VERSION == 6 and {MarketMakerJournalRow, MarketMakerFillRow, MarketMakerLedgerRow} <= set(ALL_TABLES)
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'mm.db'}")
    await db.create_schema()
    ledger = MarketMakerLedger(10_000.0)
    ledger.apply_fill(SimulatedFill("f1", "o1", "buy", 100_000.0, 0.001, T0, (11, 12), 0.5, 100_000.5))
    ledger.mark(T0 + 1, bid=100_000.0, ask=100_000.2)
    async with db.session() as session:
        repo = MarketMakerRepository(session)
        await repo.append_journal("run-a", 1, {"t": T0, "kind": "decision", "decision": "quote", "bid": 99_999.0})
        await repo.append_journal("run-a", 2, {"t": T0 + 1, "kind": "fill", "fill_id": "f1"})
        await repo.append_journal("run-a", 2, {"t": T0 + 1, "kind": "fill", "fill_id": "f1"})  # idempotent on (run, seq)
        await repo.upsert_fill("run-a", {"fill_id": "f1", "order_id": "o1", "t_ms": T0, "side": "buy", "price": 100_000.0, "quantity": 0.001, "fee_usd": 0.1, "realised_usd": 0.0, "mid_at_fill": 100_000.5, "venue_trade_ids": [11, 12], "regimes": {"vol_regime": "low"}})
        await repo.set_markout("f1", {"1000": -0.4})
        await repo.save_ledger("run-a", state=ledger.export(), config_id="cfg", profile_id="prof", latency_scenario="baseline", at=datetime.now(UTC))
    async with db.session() as session:
        repo = MarketMakerRepository(session)
        rows = await repo.journal("run-a")
        assert [r["kind"] for r in rows] == ["decision", "fill"] and await repo.journal_count("run-a") == 2
        assert await repo.journal("run-a", kind="fill") == [{"t": T0 + 1, "kind": "fill", "fill_id": "f1"}]
        fills = await repo.fills("run-a")
        assert len(fills) == 1 and fills[0].venue_trade_ids == [11, 12] and fills[0].markout_bps == {"1000": -0.4} and fills[0].regimes == {"vol_regime": "low"}
        assert await repo.fill_count("run-a") == 1 and await repo.fill_count("run-b") == 0
        saved = await repo.load_ledger("run-a")
        assert saved is not None and saved.config_id == "cfg" and saved.profile_id == "prof"
        restored = MarketMakerLedger.restore(saved.state)
        assert restored.state.inventory_btc == ledger.state.inventory_btc and restored.state.fees_usd == ledger.state.fees_usd
        assert await repo.load_ledger("run-b") is None
        # The session's own tables saw nothing of it.
        assert await EdgeStateRepository(session).count() == 0
        assert int((await session.execute(select(func.count()).select_from(FillRow))).scalar_one()) == 0
    await db.close()
