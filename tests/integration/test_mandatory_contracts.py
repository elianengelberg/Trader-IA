"""The contracts the hardening brief names, each under its named test.

Some of these duplicate coverage that exists elsewhere under other names. That is
deliberate: these are the claims an auditor greps for by name, and a grep that finds the
test is worth the duplication.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager

from tia.api.app import create_app
from tia.core.config import Environment, LiveConfig, settings_for_env

REPO = Path(__file__).resolve().parents[2]

USERNAME = "contract-operator"
PASSWORD = "contract-password-not-a-secret"  # noqa: S105 - fixture credential


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)


@pytest.fixture
async def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"}
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            await http.post(
                "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
            )
            yield http, app


# --------------------------------------------------------------------------- endpoints


async def test_no_withdrawal_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    """No route whose path suggests fund withdrawal exists, in any HTTP method."""
    _, app = client
    paths = [route.path.lower() for route in app.routes]
    offenders = [p for p in paths if any(w in p for w in ("withdraw", "payout", "redeem"))]
    assert not offenders, f"withdrawal-shaped routes exist: {offenders}"


async def test_no_transfer_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    _, app = client
    paths = [route.path.lower() for route in app.routes]
    offenders = [p for p in paths if any(w in p for w in ("transfer", "deposit", "/bank", "/card"))]
    assert not offenders, f"fund-movement-shaped routes exist: {offenders}"


def test_api_secret_never_frontend() -> None:
    """The frontend can neither hold, collect, nor transmit a venue secret.

    Three specific shapes are forbidden, in the source and — more importantly — in the
    built bundle, where a build step inlining an env var would leak while src stayed
    clean:

    * the signing header (``x-mbx-apikey``): its presence would mean the browser makes
      authenticated venue calls, which must never happen;
    * an input field for a secret: credentials are configured on the server, never typed
      into a page;
    * an inlined value from the live credential env vars.

    What is deliberately **allowed** is the env var *name* in instructional text — the
    Live page tells the user where on the server to configure the key, and naming the
    variable is documentation, not disclosure.
    """
    import re

    for tree in (REPO / "frontend/src", REPO / "frontend/dist"):
        if not tree.exists():
            continue
        for path in tree.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".html", ".css"}:
                continue
            lowered = path.read_text(encoding="utf-8", errors="ignore").lower()
            assert "x-mbx-apikey" not in lowered, (
                f"the signing header appears in {path} — the browser must never "
                "authenticate to the venue"
            )
            assert not re.search(
                r"<input[^>]*(secret|api[_-]?key)", lowered
            ), f"a credential input field exists in {path}"
            # An inlined value: the env var name followed by an assignment to a literal.
            assert not re.search(
                r"binance_api_secret['\"]?\s*[:=]\s*['\"][^'\"]{8,}", lowered
            ), f"a secret value looks inlined in {path}"


# --------------------------------------------------------------------------- money


def test_money_uses_decimal() -> None:
    """Settlement-critical arithmetic is Decimal; the classic float traps do not occur."""
    from decimal import Decimal

    from tia.core.money import D, format_venue_decimal, quantize_down
    from tia.portfolio.capital import CapitalLedger, CapitalPolicy

    ledger = CapitalLedger(CapitalPolicy(max_live_capital=1.0), allocated=0.3)
    ledger.allocate(0.3, at=None)
    ledger.allocate(0.3, at=None)
    # 0.3 * 3 == 0.9 exactly — float would give 0.8999999999999999.
    assert ledger.snapshot().allocated_capital == 0.9
    assert isinstance(ledger._allocated, Decimal)

    assert quantize_down("0.0000109", "0.00001") == Decimal("0.00001")
    assert format_venue_decimal(0.00001) == "0.00001"  # never "1e-05"
    assert D(0.1) + D(0.2) == Decimal("0.3")


# --------------------------------------------------------------------------- validation record


def _valid_record(**overrides: Any) -> dict[str, Any]:
    import hashlib
    import json

    facts = {
        "clock_skew_ms": 120,
        "taker_bps": 10.0,
        "duplicate_order_rejected": True,
        "user_data_stream_ok": True,
        "permissions": {"acceptable": True, "ip_restricted": True},
    }
    record = {
        "validator_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": "testnet",
        "symbol": "BTCUSDT",
        "git_commit": "abc",
        "fingerprint": hashlib.blake2s(
            json.dumps(facts, sort_keys=True, default=str).encode(), digest_size=16
        ).hexdigest(),
        "facts": facts,
    }
    record.update(overrides)
    return record


class _StateStub:
    def __init__(self) -> None:
        self.settings = settings_for_env(Environment.TESTING).model_copy(
            update={"live": LiveConfig(enabled=True, max_live_capital=100.0)}
        )


def test_binance_validation_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A record that does not match its schema, version, or fingerprint is not evidence."""
    import json

    import tia.api.gate_probes as probes

    target = tmp_path / "binance_validation.json"
    monkeypatch.setattr(probes, "BINANCE_FACTS", target)
    state = _StateStub()

    # Valid record → accepted.
    target.write_text(json.dumps(_valid_record()))
    record, problem = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is not None, problem

    # Tampered facts → fingerprint mismatch → refused.
    tampered = _valid_record()
    tampered["facts"]["taker_bps"] = 0.1  # someone "improved" their fee tier by hand
    target.write_text(json.dumps(tampered))
    record, problem = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is None
    assert "fingerprint" in problem

    # Wrong validator version → refused.
    target.write_text(json.dumps(_valid_record(validator_version=1)))
    record, problem = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is None and "v1" in problem

    # Wrong environment for this deployment → refused.
    target.write_text(json.dumps(_valid_record(environment="mainnet")))
    record, problem = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is None and "testnet" in problem

    # Garbage → refused with a schema message, not a crash.
    target.write_text('{"hello": "world"}')
    record, problem = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is None and "schema" in problem


def test_binance_validation_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale record fails the freshness check; UNKNOWN ages count as FAILED."""
    import json

    import tia.api.gate_probes as probes
    from tia.live.gate import CheckName

    target = tmp_path / "binance_validation.json"
    monkeypatch.setattr(probes, "BINANCE_FACTS", target)
    state = _StateStub()

    stale = _valid_record(
        generated_at=(datetime.now(UTC) - timedelta(hours=48)).isoformat()
    )
    target.write_text(json.dumps(stale))
    record, _ = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is not None
    check = probes._validation_fresh(record, "")
    assert not check.passed
    assert "48" in check.detail

    future = _valid_record(
        generated_at=(datetime.now(UTC) + timedelta(hours=5)).isoformat()
    )
    target.write_text(json.dumps(future))
    record, _ = probes.load_validation_record(state)  # type: ignore[arg-type]
    assert record is not None
    check = probes._validation_fresh(record, "")
    assert not check.passed and "future" in check.detail
    assert check.name is CheckName.VALIDATION_FRESH


def test_min_paper_days_gate() -> None:
    """C6 closed: the track-record probe requires days AND trades, from the DB record."""
    import tia.api.gate_probes as probes

    state = _StateStub()
    plenty_trades_no_days = {"closed_trades": 500, "span_days": 0.2}
    check = probes._track_record_probe(state, plenty_trades_no_days)  # type: ignore[arg-type]
    assert not check.passed
    assert "days" in check.detail

    enough = {"closed_trades": 500, "span_days": 30.0}
    assert probes._track_record_probe(state, enough).passed  # type: ignore[arg-type]

    unknown = probes._track_record_probe(state, None)  # type: ignore[arg-type]
    assert not unknown.passed  # unknown = failed


# --------------------------------------------------------------------------- arm flow


class _FakeLiveRuntime:
    run_id = "live_fake"

    class _State:
        value = "running"

    state = _State()
    is_running = True

    async def start(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "state": "running"}


async def _armed_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, start_ok: bool):  # type: ignore[no-untyped-def]
    """An AppState whose gate passes and whose runtime start is scripted.

    The gate itself is exercised for real elsewhere; what this fixture isolates is the
    *arm flow*: persistence of the attempt, the runtime start requirement, and the audit
    row — which need a passing gate to be reachable at all.
    """
    from tia.api.state import AppState
    from tia.live.gate import REQUIRED_CHECKS, passing

    settings = settings_for_env(Environment.TESTING).model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'arm.db'}",
            "live": LiveConfig(enabled=True, max_live_capital=100.0),
        }
    )
    state = AppState(settings)
    await state.startup()

    import tia.api.gate_probes as probes

    monkeypatch.setattr(
        probes,
        "build_probes",
        lambda *_a, **_k: {n: passing(n, "scripted green") for n in REQUIRED_CHECKS},
    )
    import tia.api.state as state_module

    monkeypatch.setattr(
        state_module.AppState,
        "_build_live_runtime",
        lambda self, token: _fake_builder(start_ok),
    )
    return state


async def _fake_builder(start_ok: bool):  # type: ignore[no-untyped-def]
    if not start_ok:
        raise ConnectionError("scripted: venue unreachable at startup")
    return _FakeLiveRuntime()


async def test_live_activation_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A REFUSED attempt is recorded with the checks that refused it. Failure is the
    common case and the useful record."""
    from tia.api.state import AppState
    from tia.core.errors import LiveActivationError
    from tia.live.gate import CONFIRMATION_PHRASE
    from tia.persistence import ActivationRepository

    settings = settings_for_env(Environment.TESTING).model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'refused.db'}",
            "live": LiveConfig(enabled=True, max_live_capital=100.0),
        }
    )
    state = AppState(settings)
    await state.startup()
    try:
        with pytest.raises(LiveActivationError):
            await state.arm_live(operator="elian", confirmation=CONFIRMATION_PHRASE)
        async with state.database.session() as session:
            rows = await ActivationRepository(session).history()
        assert len(rows) == 1
        assert rows[0].passed is False
        assert rows[0].operator == "elian"
        assert rows[0].failed_checks, "the refusal recorded nothing about why"
        assert rows[0].runtime_started is False
    finally:
        await state.shutdown()


async def test_live_activation_starts_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A passed gate STARTS the runtime, and LIVE is reported only because it reached
    RUNNING — the token is consumed, not dropped (gap A2 closed)."""
    from tia.live.gate import CONFIRMATION_PHRASE

    state = await _armed_state(tmp_path, monkeypatch, start_ok=True)
    try:
        result = await state.arm_live(operator="elian", confirmation=CONFIRMATION_PHRASE)
        assert result["live"] is True
        assert state.live_runtime is not None
        assert state.live_runtime.state.value == "running"
    finally:
        state.live_runtime = None  # the fake has no real loop to stop
        await state.shutdown()


async def test_live_activation_audit_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both halves of the audit: the passed gate AND whether the runtime started.

    The second scenario is the one that matters: gate green, venue down. The recorded
    truth must be "passed but NOT live", and the API must raise rather than celebrate.
    """
    from tia.core.errors import LiveActivationError
    from tia.live.gate import CONFIRMATION_PHRASE
    from tia.persistence import ActivationRepository

    state = await _armed_state(tmp_path, monkeypatch, start_ok=False)
    try:
        with pytest.raises(LiveActivationError, match="did not start"):
            await state.arm_live(operator="elian", confirmation=CONFIRMATION_PHRASE)
        async with state.database.session() as session:
            rows = await ActivationRepository(session).history()
        assert rows[0].passed is True
        assert rows[0].runtime_started is False
        assert rows[0].token_fingerprint, "the minted token left no fingerprint"
        assert "venue unreachable" in rows[0].detail
        assert state.live_runtime is None, "a dead runtime was left installed as live"
    finally:
        await state.shutdown()


async def test_gate_report_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full gate report rides along in the audit row, so 'what did the gate see that
    day?' is answerable without replaying that day."""
    from tia.live.gate import CONFIRMATION_PHRASE
    from tia.persistence import ActivationRepository

    state = await _armed_state(tmp_path, monkeypatch, start_ok=True)
    try:
        await state.arm_live(operator="elian", confirmation=CONFIRMATION_PHRASE)
        async with state.database.session() as session:
            rows = await ActivationRepository(session).history()
        report = rows[0].report
        assert report["passed"] is True
        assert len(report["checks"]) >= 24
    finally:
        state.live_runtime = None
        await state.shutdown()


# --------------------------------------------------------------------------- profile


async def test_risk_profile_change_audit(client) -> None:  # type: ignore[no-untyped-def]
    """Changing the profile requires confirmation, applies to the next run, and leaves
    an audit row with the actor's name on it."""
    http, _ = client

    refused = await http.post("/api/risk/profile", json={"profile": "conservative"})
    assert refused.status_code == 409  # confirm: false → refused

    changed = await http.post(
        "/api/risk/profile", json={"profile": "conservative", "confirm": True}
    )
    assert changed.status_code == 200
    body = changed.json()
    assert body["profile"] == "conservative"
    assert "next run" in body["effective"]

    history = (await http.get("/api/risk/profile/history")).json()
    assert history and history[0]["actor"] == USERNAME
    assert "conservative" in history[0]["change"]

    invalid = await http.post(
        "/api/risk/profile", json={"profile": "martingale", "confirm": True}
    )
    assert invalid.status_code == 422  # not one of the three reviewed profiles


# --------------------------------------------------------------------------- misc


async def test_economics_snapshot_matches_risk(client) -> None:  # type: ignore[no-untyped-def]
    """D2 as a named contract: the snapshot's budget inputs are the decision path's own."""
    http, app = client
    await http.post(
        "/api/runtime/start",
        json={"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 5,
              "bar_interval_seconds": 0.0},
    )
    import asyncio

    state = app.state.tia
    for _ in range(120_000):
        await asyncio.sleep(0)
        if not state.runtime.is_running:
            break

    economics = (await http.get("/api/economics")).json()
    inputs = economics["budget_inputs"]
    if inputs["inputs_from_decision"]:
        runtime = state.runtime
        assert runtime._last_budget_inputs is not None
        assert inputs["drawdown_pct"] == pytest.approx(
            runtime._last_budget_inputs.drawdown_pct
        )
        assert inputs["realised_annual_volatility"] == pytest.approx(
            runtime._last_budget_inputs.realised_annual_volatility
        )
    await http.post("/api/runtime/stop")


async def test_multi_fill_exit_vwap() -> None:
    """D1 as a named contract: a two-fill exit is scored at the exit VWAP, fees included."""
    from tia.core.config import Environment as Env
    from tia.core.config import settings_for_env as sfe
    from tia.domain.enums import Direction, MarketRegime, Side
    from tia.domain.orders import Fill
    from tia.domain.portfolio import Position
    from tia.runtime.engine import RuntimeConfig, RuntimeEngine

    engine = RuntimeEngine(
        sfe(Env.TESTING), RuntimeConfig(scenario="trend_up", bar_interval_seconds=0.0)
    )
    engine._entry_beliefs["BTC-USD"] = {
        "regime": MarketRegime.TRENDING_UP,
        "direction": Direction.LONG,
        "confidence": 0.7,
        "signal_id": "s-vwap",
        "expected_net_bps": 10.0,
    }
    now = datetime(2026, 1, 5, tzinfo=UTC)

    def fill(index: int, side: Side, quantity: float, price: float) -> Fill:
        return Fill(
            fill_id=f"f{index}", order_id=f"o{index}", sequence=0, symbol="BTC-USD",
            side=side, quantity=quantity, price=price, fee=1.0, filled_at=now,
        )

    portfolio = engine._execution.portfolio
    # Entry: 0.02 @ 50,000.
    portfolio.positions["BTC-USD"] = Position(
        symbol="BTC-USD", quantity=0.02, average_price=50_000.0
    )
    engine._track_round_trip(fill(1, Side.BUY, 0.02, 50_000.0))
    # Exit in two partial fills at different prices: VWAP = 50,500.
    portfolio.positions["BTC-USD"] = Position(
        symbol="BTC-USD", quantity=0.01, average_price=50_000.0
    )
    engine._track_round_trip(fill(2, Side.SELL, 0.01, 50_200.0))
    portfolio.positions["BTC-USD"] = Position(
        symbol="BTC-USD", quantity=0.0, average_price=50_000.0
    )
    engine._track_round_trip(fill(3, Side.SELL, 0.01, 50_800.0))

    trade = engine.closed_trades[0]
    assert trade["exit_price"] == pytest.approx(50_500.0)  # VWAP, not the last fill's 50,800
    assert trade["gross_bps"] == pytest.approx(100.0)  # (50500-50000)/50000
    # Fees: 3 fills * 1.0 over notional 1000 = 30 bps.
    assert trade["fees_bps"] == pytest.approx(30.0)
    assert trade["net_bps"] == pytest.approx(70.0)


async def test_cost_basis_recovery() -> None:
    """D3 as a named contract: no invented cost basis.

    The venue reports balances without acquisition prices; the live snapshot says the
    basis comes from the fill journal and is UNKNOWN until replayed — it never shows a
    fabricated number like 0.0-presented-as-price.
    """
    from tests.integration.test_live_runtime import build_runtime

    runtime, _, _ = build_runtime()
    snapshot = runtime.snapshot()
    assert "UNKNOWN" in snapshot["position_cost_basis"]
