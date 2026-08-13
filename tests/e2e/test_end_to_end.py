"""The end-to-end test the project's success criterion names.

One assertion, made of many: a user can set simulated capital, the system ingests market
data, analyses it, forms a signal, passes it through validation and the risk engine,
creates an order, fills it in the simulator, updates the position and the P&L, records the
decision, and shows the whole thing through the API — and this can be re-run automatically.

Run against the real application: a real ASGI app, a real database, the real runtime, the
real pipeline. Nothing here is mocked except the market itself, which is a seeded
generator by design.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from tia.api.app import create_app
from tia.core.config import Environment, settings_for_env

pytestmark = pytest.mark.e2e

USERNAME = "e2e-operator"
PASSWORD = "e2e-password-not-a-secret"  # noqa: S105 - a fixture credential


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The whole application, on a throwaway database."""
    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)

    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}"}
    )
    app = create_app(settings)

    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def _login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


async def _wait_for(
    check, *, max_wait_seconds: float = 90.0, interval: float = 0.25, what: str = "condition"
):
    """Poll until ``check()`` returns a truthy value, or fail saying what was awaited."""
    elapsed = 0.0
    last = None
    while elapsed < max_wait_seconds:
        last = await check()
        if last:
            return last
        await asyncio.sleep(interval)
        elapsed += interval
    pytest.fail(
        f"timed out after {max_wait_seconds}s waiting for {what} (last value: {last!r})"
    )


# --------------------------------------------------------------------------- the flow


async def test_the_complete_paper_trading_pipeline(client: httpx.AsyncClient) -> None:
    """USER → WEB → START → DATA → ANALYSIS → AI → VALIDATION → RISK → ORDER → FILL
    → POSITION → P&L → DASHBOARD → AUDIT LOG."""
    await _login(client)

    # 1. Set simulated capital and start.
    start = await client.post(
        "/api/runtime/start",
        json={
            "scenario": "mixed",
            "symbols": ["BTC-USD"],
            "initial_capital": 25_000.0,
            "seed": 20260812,
            "bar_interval_seconds": 0.0,
            "llm_enabled": True,
            "news_enabled": True,
        },
    )
    assert start.status_code == 200, start.text
    snapshot = start.json()
    assert snapshot["simulated"] is True
    assert snapshot["capital"]["starting"] == 25_000.0
    run_id = snapshot["run_id"]

    # 2. Market data is ingested and analysed into decisions.
    async def has_decisions():
        rows = (await client.get("/api/decisions?limit=50")).json()
        return rows if len(rows) >= 5 else None

    decisions = await _wait_for(has_decisions, what="decisions to be produced")
    assert all(row["feature_hash"] for row in decisions), "every decision recorded its inputs"
    assert any(row["regime"] != "unknown" for row in decisions), "the regime was classified"

    # 3. The AI layer ran, and whatever it said could only reduce risk.
    assessments = (await client.get("/api/assessments?limit=50")).json()
    assert assessments, "the context layer produced assessments"
    assert all(a["context_modifier"] <= 0.0 for a in assessments), (
        "an assessment escaped the veto/dampen channel"
    )

    # 4. Risk approved something and an order was filled.
    async def has_fills():
        fills = (await client.get("/api/fills?limit=50")).json()
        return fills or None

    fills = await _wait_for(has_fills, what="a simulated fill", max_wait_seconds=120.0)
    fill = fills[-1]
    assert fill["quantity"] > 0
    assert fill["price"] > 0
    assert fill["fee"] >= 0, "the fill was charged a fee"
    assert fill["slippage_bps"] >= 0, "slippage was modelled"

    # 5. The order exists and is traceable back to a signal.
    orders = (await client.get("/api/orders?limit=50")).json()
    assert orders
    matching = [o for o in orders if o["order_id"] == fill["order_id"]]
    assert matching, "the fill references an order the API knows about"
    assert matching[0]["signal_id"], "the order carries the signal that produced it"

    # 6. The position and P&L moved.
    portfolio = (await client.get("/api/portfolio")).json()
    capital = portfolio["capital"]
    assert capital["equity"] != 25_000.0 or capital["fees_paid"] > 0, (
        "a fill occurred but nothing moved in the portfolio"
    )
    assert len(portfolio["equity_curve"]) > 10, "the equity curve was recorded"

    # 7. The whole thing is visible through the dashboard's own endpoints.
    status = (await client.get("/api/system/status")).json()
    assert status["run"]["run_id"] == run_id
    counters = status["run"]["counters"]
    assert counters["bars"] > 100
    assert counters["signals"] > 0
    assert counters["fills"] > 0

    # 8. ...and it is in the audit log.
    logs = (await client.get("/api/logs?limit=200")).json()
    assert any("filled" in line["message"] for line in logs), "the fill was logged"

    await client.post("/api/runtime/stop")


async def test_the_run_is_reproducible(client: httpx.AsyncClient) -> None:
    """Same scenario, same seed, same result. Without this, none of the numbers mean
    anything — a demo that cannot be replayed is an anecdote."""
    await _login(client)

    async def run_once() -> list[tuple[str, float]]:
        await client.post(
            "/api/runtime/start",
            json={
                "scenario": "trend_up",
                "symbols": ["BTC-USD"],
                "initial_capital": 10_000.0,
                "seed": 4242,
                "bar_interval_seconds": 0.0,
            },
        )

        async def finished():
            state = (await client.get("/api/runtime")).json()
            return state if state["state"] in {"finished", "stopped"} else None

        await _wait_for(finished, what="the run to finish", max_wait_seconds=180.0)
        fills = (await client.get("/api/fills?limit=200")).json()
        await client.post("/api/runtime/stop")
        await client.post("/api/runtime/reset", json={"confirm": True, "initial_capital": 10_000.0})
        return [(f["symbol"], round(f["price"], 8)) for f in fills]

    first = await run_once()
    second = await run_once()
    assert first == second, "two runs of the same seed produced different fills"


async def test_a_data_failure_scenario_correctly_refuses_to_trade(
    client: httpx.AsyncClient,
) -> None:
    """The scenario whose passing outcome is *inactivity*.

    A quality gate that never actually stops anything is decoration, so this asserts the
    refusal happens rather than asserting a trade does.
    """
    await _login(client)
    await client.post(
        "/api/runtime/start",
        json={
            "scenario": "data_failure",
            "symbols": ["BTC-USD"],
            "initial_capital": 10_000.0,
            "bar_interval_seconds": 0.0,
        },
    )

    async def progressed():
        state = (await client.get("/api/runtime")).json()
        counters = state.get("counters", {})
        return state if counters.get("bars", 0) > 300 else None

    state = await _wait_for(progressed, what="the scenario to run", max_wait_seconds=180.0)
    counters = state["counters"]
    assert counters["quality_skipped"] > 0, (
        "the corrupted feed produced no quality refusals; the gate is not working"
    )
    await client.post("/api/runtime/stop")


async def test_losing_the_context_layer_does_not_stop_trading(
    client: httpx.AsyncClient,
) -> None:
    """The asymmetry rule's operational consequence: nothing depends on the model."""
    await _login(client)
    await client.post(
        "/api/runtime/start",
        json={
            "scenario": "llm_failure",
            "symbols": ["BTC-USD"],
            "initial_capital": 10_000.0,
            "bar_interval_seconds": 0.0,
        },
    )

    async def progressed():
        state = (await client.get("/api/runtime")).json()
        return state if state.get("counters", {}).get("signals", 0) > 20 else None

    state = await _wait_for(progressed, what="signals despite the outage", max_wait_seconds=180.0)
    assert state["counters"]["context_neutral"] > 0, "the outage was not exercised"
    assert state["counters"]["signals"] > 0, "the deterministic pipeline stopped with the LLM"

    assessments = (await client.get("/api/assessments?limit=30")).json()
    assert assessments, "the failures were recorded rather than dropped"
    assert all(a["context_modifier"] == 0.0 for a in assessments), (
        "a failed assessment still influenced a decision"
    )
    await client.post("/api/runtime/stop")


async def test_the_kill_switch_stops_new_risk_and_needs_a_name_to_release(
    client: httpx.AsyncClient,
) -> None:
    await _login(client)
    await client.post(
        "/api/runtime/start",
        json={"scenario": "trend_up", "initial_capital": 10_000.0, "bar_interval_seconds": 0.02},
    )

    halted = await client.post("/api/runtime/kill-switch", json={"reason": "test"})
    assert halted.status_code == 200
    assert halted.json()["risk"]["mode"] == "halted"

    # Releasing without a name is refused by the schema, not by a convention.
    refused = await client.post("/api/runtime/release-kill-switch", json={"approved_by": ""})
    assert refused.status_code == 422

    released = await client.post(
        "/api/runtime/release-kill-switch", json={"approved_by": "auditor@example.com"}
    )
    assert released.status_code == 200
    assert released.json()["risk"]["mode"] == "normal"

    logs = (await client.get("/api/logs?limit=100")).json()
    assert any("auditor@example.com" in line["message"] for line in logs), (
        "the approver's name must be in the audit log"
    )
    await client.post("/api/runtime/stop")


async def test_resetting_destroys_the_run(client: httpx.AsyncClient) -> None:
    await _login(client)
    await client.post(
        "/api/runtime/start",
        json={"scenario": "trend_up", "initial_capital": 10_000.0, "bar_interval_seconds": 0.0},
    )

    async def has_decisions():
        return (await client.get("/api/decisions?limit=10")).json() or None

    await _wait_for(has_decisions, what="decisions before the reset")

    reset = await client.post("/api/runtime/reset", json={"confirm": True, "initial_capital": 50_000.0})
    assert reset.status_code == 200
    assert (await client.get("/api/decisions")).json() == []
    assert (await client.get("/api/positions")).json() == []
    assert (await client.get("/api/runtime")).json()["state"] == "stopped"


async def test_a_reset_without_confirmation_is_refused(client: httpx.AsyncClient) -> None:
    await _login(client)
    response = await client.post(
        "/api/runtime/reset", json={"confirm": False, "initial_capital": 10_000.0}
    )
    assert response.status_code == 400


async def test_a_backtest_runs_and_reports_against_baselines(
    client: httpx.AsyncClient,
) -> None:
    await _login(client)
    response = await client.post(
        "/api/backtests",
        json={"symbol": "BTC-USD", "timeframe": "1h", "bars": 600, "seed": 20260812},
    )
    assert response.status_code == 200, response.text
    report = response.json()

    assert len(report["baselines"]) == 5, "all five mandatory baselines must be reported"
    assert report["verdict"] in {
        "insufficient_evidence",
        "no_edge_demonstrated",
        "mixed",
        "beat_all_baselines",
    }
    assert "makes no claim about future results" in report["evidence_statement"]

    listed = (await client.get("/api/backtests")).json()
    assert any(row["run_id"] == report["run_id"] for row in listed), "it was persisted"
