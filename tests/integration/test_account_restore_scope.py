"""The paper account folds paper-live events only (Phase 1.3, G11).

A live run writes the same ``account.*`` events as a paper run; its fills belong to the
venue's account. Before 1.3 the paper rebuild read both modes and a live fill would have
moved the paper account.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.integration.test_account_restore import _db, persister, register_run
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order
from tia.events.envelope import EventEnvelope
from tia.persistence import AccountJournalRepository, RunRepository
from tia.portfolio.account_journal import EVENT_FILL, AccountFillPayload

SYMBOL = "BTC-USD"
CAPITAL = 10_000.0


async def _session_with_one_fill(db, *, run_id: str, mode: str, fill_id: str, at: datetime) -> None:  # type: ignore[no-untyped-def]
    if mode == "paper-live":
        await register_run(db, run_id, started_at=at)
    else:
        async with db.session() as session:
            await RunRepository(session).create(
                run_id=run_id, mode=mode, scenario=mode, started_at=at, initial_capital=CAPITAL, seed=1, symbols=(SYMBOL,),
            )
    persist = persister(db)
    fill = Fill(fill_id=fill_id, order_id=f"ord_{fill_id}", sequence=1, symbol=SYMBOL, side=Side.BUY,
                quantity=0.01, price=50_000.0, fee=0.5, filled_at=at)
    order = Order(order_id=f"ord_{fill_id}", client_order_id=f"coid_{fill_id}", intent_id="i", signal_id="sig",
                  symbol=SYMBOL, side=Side.BUY, order_type=OrderType.MARKET, quantity=0.01, state=OrderState.FILLED,
                  filled_quantity=0.01, average_fill_price=50_000.0, fees_paid=0.5, created_at=at, updated_at=at, fills=[fill])
    await persist("order", {"run_id": run_id, "order": order})
    await persist("fill", {"run_id": run_id, "fill": fill})
    envelope = EventEnvelope(
        event_id=f"evt_{fill_id}", event_type=EVENT_FILL, source="live", occurred_at=at, ingestion_at=at,
        recorded_at=at, correlation_id=run_id, idempotency_key=f"{EVENT_FILL}:{fill_id}",
        payload=AccountFillPayload(symbol=SYMBOL, fill_id=fill_id, order_id=f"ord_{fill_id}", side="buy",
                                   quantity=0.01, price=50_000.0, fee=0.5, filled_at=at),
    )
    await persist("account_event", {"run_id": run_id, "envelope": envelope})


async def test_a_live_runs_fills_do_not_move_the_paper_account(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        t0 = datetime.now(UTC) - timedelta(hours=2)
        await _session_with_one_fill(db, run_id="run_paper", mode="paper-live", fill_id="paper_fill", at=t0)
        await _session_with_one_fill(db, run_id="run_live", mode="live", fill_id="live_fill", at=t0 + timedelta(minutes=1))
        now = datetime.now(UTC)
        async with db.session() as session:
            paper_only = await AccountJournalRepository(session).rebuild(
                now=now, initial_capital=CAPITAL, symbol=SYMBOL, modes=("paper-live",),
            )
            both = await AccountJournalRepository(session).rebuild(now=now, initial_capital=CAPITAL, symbol=SYMBOL)
        assert paper_only.complete, paper_only.error
        assert paper_only.fills_seen == 1 and paper_only.position_quantity == 0.01
        assert paper_only.checks["fills_in_table"] == 1, "the cross-check is scoped the same way"
        # The default (both modes) still folds both: the application passes the paper scope.
        assert both.fills_seen == 2 and both.position_quantity == 0.02
    finally:
        await db.close()


async def test_the_application_rebuilds_the_paper_account_from_paper_live_runs_only(tmp_path: Path) -> None:
    from tests.integration.test_live_api import _settings
    from tia.api.state import AppState

    state = AppState(_settings(tmp_path))
    await state.database.ensure_schema()
    try:
        t0 = datetime.now(UTC) - timedelta(hours=2)
        await _session_with_one_fill(state.database, run_id="run_paper", mode="paper-live", fill_id="paper_fill", at=t0)
        await _session_with_one_fill(state.database, run_id="run_live", mode="live", fill_id="live_fill", at=t0 + timedelta(minutes=1))
        restore = await state._load_account_restore(symbol=SYMBOL, initial_capital=CAPITAL)
        assert restore.complete, restore.error
        assert restore.fills_seen == 1 and restore.position_quantity == 0.01
    finally:
        await state.database.close()
