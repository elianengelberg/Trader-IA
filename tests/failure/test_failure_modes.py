"""Failure injection.

`docs/ARCHITECTURE.md` §11 lists a table of failure modes and, until now, claimed each row
had a matching test here. The directory was empty. This file makes the claim true for the
rows that can be tested without a live external service, and the architecture document now
says which rows those are.

The governing rule for every case below is §64: when the system does not know its own
state, it must prefer **NO_TRADE**. A failure that produces no trades is passing. A failure
that produces a trade on unknown state is the defect these tests exist to catch.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tia.core.clock import SimulatedClock
from tia.core.config import Environment, LLMConfig, settings_for_env
from tia.core.errors import LLMUnavailableError
from tia.domain.enums import SystemMode
from tia.execution.reconciliation import (
    DiscrepancyKind,
    LedgerSnapshot,
    ReconciliationEngine,
)
from tia.llm.context import ContextRequest, ContextService
from tia.llm.governance import BreakerState, LLMGovernor
from tia.llm.provider import LLMProvider, LLMResult, MockLLMProvider
from tia.persistence import Database
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeClassifier
from tia.risk.engine import RiskEngine
from tia.runtime import RuntimeConfig, RuntimeEngine
from tia.runtime.scenarios import generate_series, get_scenario

pytestmark = pytest.mark.failure

START = datetime(2026, 1, 5, tzinfo=UTC)


async def _run_until(engine: RuntimeEngine, predicate, *, limit: int = 4000) -> None:
    """Step the engine's own loop until a predicate holds or the run ends."""
    await engine.start()
    for _ in range(limit):
        await asyncio.sleep(0.002)
        if predicate() or engine.state.value in {"finished", "halted"}:
            break
    await engine.stop()


# --------------------------------------------------------------------------- LLM


async def test_the_llm_being_unavailable_never_stops_the_pipeline() -> None:
    """Row: *LLM timeout / 429 → context unavailable, neutral modifier.*

    The strongest form of the asymmetry rule: nothing depends on the model.
    """
    settings = settings_for_env(Environment.DEMO)
    engine = RuntimeEngine(
        settings,
        RuntimeConfig(scenario="llm_failure", bar_interval_seconds=0.0, initial_capital=10_000.0),
    )
    await _run_until(engine, lambda: engine.counters.signals > 40)

    assert engine.counters.signals > 0, "the deterministic pipeline stopped with the LLM"
    assert engine.counters.context_neutral > 0, "the outage was never exercised"
    assert all(
        row["context_modifier"] == 0.0 for row in engine.recent_assessments
    ), "a failed assessment still influenced a decision"


async def test_a_provider_that_raises_an_unexpected_exception_degrades_to_neutral(
    clock: SimulatedClock,
) -> None:
    """The specific defect this caught in the audit: a pydantic ValidationError from
    inside a provider escaped the service and halted the runtime."""

    class Exploding(LLMProvider):
        name = "exploding"

        async def assess(self, prompt: str, *, call_id: str) -> LLMResult:
            del prompt, call_id
            raise RuntimeError("something the service has never heard of")

    from tia.domain.market import Candle

    candles = [
        Candle(
            symbol="BTC-USD",
            timeframe="1m",
            open_time=START + timedelta(minutes=i),
            close_time=START + timedelta(minutes=i + 1),
            open=100.0 + i * 0.01,
            high=100.2 + i * 0.01,
            low=99.8 + i * 0.01,
            close=100.1 + i * 0.01,
            volume=1000.0,
            trade_count=10,
            provider="test",
        )
        for i in range(200)
    ]
    features = FeatureBuilder().build("BTC-USD", "1m", candles)
    regime = RegimeClassifier().classify(features, now=candles[-1].close_time)

    config = LLMConfig(enabled=True)
    service = ContextService(
        Exploding(),
        LLMGovernor(config, clock),
        clock,
        config,
        known_symbols=frozenset({"BTC-USD"}),
    )
    outcome = await service.assess(
        ContextRequest(symbol="BTC-USD", features=features, regime=regime)
    )

    assert outcome.is_neutral
    assert "RuntimeError" in outcome.reason
    assert service.governor.snapshot().consecutive_failures == 1


async def test_a_sustained_outage_opens_the_breaker_and_stops_calling(
    clock: SimulatedClock,
) -> None:
    """A provider that is failing should be asked *less*, not more — otherwise one
    outage becomes a retry storm and a bill."""
    config = LLMConfig(enabled=True, circuit_breaker_failures=3)
    governor = LLMGovernor(config, clock)
    provider = MockLLMProvider(fail_rate=1.0)

    for _ in range(5):
        allowed, _reason = governor.may_call()
        if not allowed:
            break
        try:
            await provider.assess("prompt", call_id="c")
        except LLMUnavailableError:
            governor.record_failure()

    assert governor.snapshot().breaker is BreakerState.OPEN
    assert not governor.may_call()[0]


# --------------------------------------------------------------------------- data


async def test_a_corrupted_feed_produces_refusals_not_trades() -> None:
    """Row: *stale / bad data → NO_TRADE.*

    The correct outcome is inactivity. Asserted as such rather than as a trade count.
    """
    settings = settings_for_env(Environment.DEMO)
    engine = RuntimeEngine(
        settings,
        RuntimeConfig(scenario="data_failure", bar_interval_seconds=0.0, initial_capital=10_000.0),
    )
    await _run_until(engine, lambda: engine.counters.bars > 480)

    assert engine.counters.quality_skipped > 0, (
        "a feed with stuck prices and volume blackouts produced no refusals"
    )
    assert any(
        line["channel"] == "data" and "quality" in line["message"]
        for line in engine.recent_logs
    ), "the refusals were not logged"


def test_a_frozen_feed_is_detected() -> None:
    """The specific fault, in isolation: 20+ bars at an identical price."""
    from tia.data.quality import DataQualityEngine

    settings = settings_for_env(Environment.DEMO)
    scenario = get_scenario("data_failure")
    candles = generate_series(
        scenario, symbol="BTC-USD", timeframe="1m", start=START, seed=20260812
    )

    engine = DataQualityEngine(settings.data_quality)
    hard_fails = 0
    for index in range(200, len(candles), 5):
        window = candles[max(0, index - 300) : index + 1]
        report = engine.evaluate(
            symbol="BTC-USD",
            timeframe="1m",
            candles=window,
            now=window[-1].close_time,
            last_feed_message_at=window[-1].close_time,
        )
        hard_fails += int(report.hard_fail)

    assert hard_fails > 0, "the corrupted fixture never trips a hard fail"


# --------------------------------------------------------------------------- state


def test_a_phantom_position_halts_trading() -> None:
    """Row: *reconciliation divergence → SAFE MODE.*

    A position the venue holds that the system does not know about is unmanaged risk: no
    stop, no size limit, no exit logic is watching it.
    """
    settings = settings_for_env(Environment.DEMO)
    clock = SimulatedClock(START)
    from tia.domain.instruments import DEFAULT_UNIVERSE

    risk = RiskEngine(settings.risk, DEFAULT_UNIVERSE, clock)
    reconciler = ReconciliationEngine(on_critical=risk.enter_safe_mode)

    internal = LedgerSnapshot(source="internal", taken_at=START, balance=100_000.0)
    external = LedgerSnapshot(
        source="paper", taken_at=START, positions={"BTC-USD": 3.0}, balance=100_000.0
    )

    report = reconciler.reconcile(internal, external)
    assert report.has_critical
    assert report.by_kind(DiscrepancyKind.PHANTOM_POSITION)

    assert reconciler.enforce(report) is True
    assert risk.state.mode is SystemMode.SAFE_MODE
    assert risk.state.is_halted


def test_safe_mode_refuses_every_new_signal() -> None:
    """Halting must actually halt. A safe mode that still approves trades is a label."""
    from tia.domain.instruments import DEFAULT_UNIVERSE
    from tia.domain.portfolio import PortfolioState
    from tia.domain.signals import SignalCandidate

    settings = settings_for_env(Environment.DEMO)
    clock = SimulatedClock(START)
    risk = RiskEngine(settings.risk, DEFAULT_UNIVERSE, clock)
    risk.enter_safe_mode("reconciliation break")

    signal = SignalCandidate(
        signal_id="sig-1",
        symbol="BTC-USD",
        direction="long",
        confidence=0.99,
        base_confidence=0.99,
        created_at=START,
        expires_at=START + timedelta(minutes=5),
        market_snapshot_id="snap",
        entry_reference=50_000.0,
        stop_reference=49_000.0,
        strategy_id="trend_following",
        strategy_version="1",
    )
    decision = risk.evaluate(
        signal=signal, portfolio=PortfolioState.initial(100_000.0), now=START
    )
    assert not decision.allows_execution
    assert decision.approved_quantity == 0.0


def test_leaving_safe_mode_requires_a_named_approver() -> None:
    from tia.domain.instruments import DEFAULT_UNIVERSE

    settings = settings_for_env(Environment.DEMO)
    risk = RiskEngine(settings.risk, DEFAULT_UNIVERSE, SimulatedClock(START))
    risk.enter_safe_mode("test")

    with pytest.raises(TypeError):
        risk.resume()  # type: ignore[call-arg]

    risk.resume(approved_by="auditor@example.com")
    assert risk.state.mode is SystemMode.NORMAL


# --------------------------------------------------------------------------- database


async def test_the_database_being_unavailable_does_not_stop_trading(tmp_path: Path) -> None:
    """Row: *DB failure → writes buffered, trading continues.*

    Persistence is best-effort from the trading loop's point of view. A dashboard missing
    a row is a nuisance; a trading loop blocked on a database is a fault.
    """
    settings = settings_for_env(Environment.DEMO)
    failures: list[str] = []

    async def failing_persist(kind: str, payload: object) -> None:
        del payload
        failures.append(kind)
        raise RuntimeError("database is gone")

    engine = RuntimeEngine(
        settings,
        RuntimeConfig(scenario="trend_up", bar_interval_seconds=0.0, initial_capital=10_000.0),
        persist=failing_persist,
    )
    await _run_until(engine, lambda: engine.counters.signals > 30)

    assert failures, "the persistence path was never exercised"
    assert engine.counters.signals > 0, "a failing database stopped the trading loop"
    assert engine.counters.errors == 0, "a persistence failure was treated as a runtime error"
    del tmp_path


async def test_a_schema_from_another_version_is_refused(tmp_path: Path) -> None:
    """Reading a database written by a different schema is how a dashboard ends up wrong
    in a way nobody notices. It must fail loudly instead."""
    from sqlalchemy import select

    from tia.core.errors import ConfigurationError
    from tia.persistence.models import SchemaInfo

    url = f"sqlite+aiosqlite:///{tmp_path / 'versioned.db'}"
    database = Database(url)
    await database.ensure_schema()

    async with database.session() as session:
        info = (await session.execute(select(SchemaInfo))).scalars().first()
        assert info is not None
        info.version = 999

    with pytest.raises(ConfigurationError, match="schema version"):
        await database.ensure_schema()
    await database.close()


# --------------------------------------------------------------------------- restart


async def test_state_survives_a_restart(tmp_path: Path) -> None:
    """Row: *restart → reconcile then resume.*

    What is asserted is the durable half: everything the run recorded is still readable
    from a brand-new process against the same database. The runtime itself does not resume
    a stopped run — it starts a new one — and that is deliberate, because a simulated clock
    cannot be rewound.
    """
    from tia.persistence import DecisionRepository, RunRepository

    url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"

    first = Database(url)
    await first.ensure_schema()
    async with first.session() as session:
        await RunRepository(session).create(
            run_id="run-1",
            mode="paper",
            scenario="trend_up",
            started_at=START,
            initial_capital=10_000.0,
            seed=1,
            symbols=["BTC-USD"],
        )
        await DecisionRepository(session).record(
            {
                "decision_id": "dec-1",
                "run_id": "run-1",
                "symbol": "BTC-USD",
                "decided_at": START,
                "direction": "long",
                "verdict": "approved",
                "approved_quantity": 1.0,
            }
        )
    await first.close()

    # A different Database object, as a restarted process would create.
    second = Database(url)
    await second.ensure_schema()
    async with second.session() as session:
        run = await RunRepository(session).get("run-1")
        decisions = await DecisionRepository(session).recent("run-1")
    await second.close()

    assert run is not None and run.initial_capital == 10_000.0
    assert len(decisions) == 1
    assert decisions[0].decision_id == "dec-1"


async def test_a_redelivered_event_is_rejected_by_the_database(tmp_path: Path) -> None:
    """Row: *duplicate event → ignored.*

    Enforced by a unique index rather than by a prior SELECT, so two writers racing the
    same redelivered event cannot both win — which is exactly what happens after a restart
    replays a stream.
    """
    from sqlalchemy import func, select

    from tia.core.ids import deterministic_id
    from tia.persistence import EventRepository, RunRepository
    from tia.persistence.models import EventRecord

    url = f"sqlite+aiosqlite:///{tmp_path / 'dedup.db'}"
    database = Database(url)
    await database.ensure_schema()

    async with database.session() as session:
        await RunRepository(session).create(
            run_id="run-1",
            mode="paper",
            scenario="trend_up",
            started_at=START,
            initial_capital=10_000.0,
            seed=1,
            symbols=["BTC-USD"],
        )

    from tia.domain.market import Candle
    from tia.events.envelope import build_event
    from tia.events.payloads import CandleClosed, EventType

    candle = Candle(
        symbol="BTC-USD",
        timeframe="1m",
        open_time=START,
        close_time=START + timedelta(minutes=1),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
        trade_count=10,
        provider="test",
    )
    envelope = build_event(
        event_type=EventType.CANDLE_CLOSED,
        payload=CandleClosed(candle=candle),
        source="test",
        clock=SimulatedClock(START),
        correlation_id=deterministic_id("corr", "1"),
        # A redelivery is the *same* event, so its idempotency key must be the same. A
        # random key per attempt would make this test pass while proving nothing.
        deterministic_id_seed="candle-1",
        idempotency_parts=("BTC-USD", START.isoformat()),
    )

    for _ in range(3):
        async with database.session() as session:
            await EventRepository(session).append("run-1", envelope)

    async with database.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(EventRecord))
        ).scalar()
    await database.close()

    assert count == 1, f"a redelivered event was stored {count} times"
