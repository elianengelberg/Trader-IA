"""The live-trading surface of the API, against the real application.

The endpoints under test are the ones that would put money at risk, so the tests are
written as an adversary would approach them: what does the API leak, and what will it let
me turn on?

Two properties matter more than the rest:

* **No secret leaves.** Not through settings, not through the gate report, not through an
  error message. Checked by scanning entire response bodies for the configured value
  rather than by asserting on the fields someone remembered to redact.
* **Nothing arms by accident.** The arm endpoint refuses without operator role, without
  the exact phrase, and — decisively — while any activation check is failing, which in
  this environment is most of them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from pydantic import SecretStr

from tia.api.app import create_app
from tia.core.config import Environment, LiveConfig, settings_for_env
from tia.core.errors import ProviderUnavailableError
from tia.data.providers.base import MarketDataProvider, ProviderCapabilities
from tia.live.gate import CONFIRMATION_PHRASE, REQUIRED_CHECKS
from tia.runtime.scenarios import generate_series, get_scenario

USERNAME = "live-operator"
PASSWORD = "live-password-not-a-secret"  # noqa: S105 - a fixture credential
API_KEY = "public-key-material-for-a-test"
API_SECRET = "SECRET-VALUE-THAT-MUST-NEVER-APPEAR"  # noqa: S105 - the canary


def _settings(tmp_path: Path, *, live: LiveConfig | None = None):  # type: ignore[no-untyped-def]
    return settings_for_env(Environment.TESTING).model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'live.db'}",
            "live": live or LiveConfig(),
        }
    )


async def _client(app):  # type: ignore[no-untyped-def]
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            await http.post(
                "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
            )
            yield http


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)


@pytest.fixture
async def client(tmp_path: Path):  # type: ignore[no-untyped-def]
    async for http in _client(create_app(_settings(tmp_path))):
        yield http


@pytest.fixture
async def armed_client(tmp_path: Path):  # type: ignore[no-untyped-def]
    """The application configured as far toward live as configuration alone can take it.

    Which is not very far, and that is the point of the fixture.
    """
    live = LiveConfig(
        enabled=True,
        max_live_capital=500.0,
        binance_api_key=SecretStr(API_KEY),
        binance_api_secret=SecretStr(API_SECRET),
    )
    async for http in _client(create_app(_settings(tmp_path, live=live))):
        yield http


# --------------------------------------------------------------------------- the gate


async def test_the_gate_reports_every_check_with_a_remedy(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/live/gate")
    assert response.status_code == 200

    report = response.json()
    assert report["passed"] is False
    assert report["total"] == len(REQUIRED_CHECKS)
    assert {check["name"] for check in report["checks"]} == {
        check.value for check in REQUIRED_CHECKS
    }
    for check in report["checks"]:
        assert check["rationale"], f"{check['name']} has no rationale"
        if not check["passed"]:
            assert check["remedy"], f"{check['name']} failed without saying what to do"


async def test_the_gate_is_readable_without_arming_anything(client: httpx.AsyncClient) -> None:
    """Reading the checks is how someone finds out what they would have to fix. It must
    not require the permission that arming requires, and it must not have side effects."""
    first = (await client.get("/api/live/gate")).json()
    second = (await client.get("/api/live/gate")).json()

    assert first["failed"] == second["failed"]
    assert first["passed"] is second["passed"] is False


async def test_the_gate_states_that_funds_never_leave_the_venue(
    client: httpx.AsyncClient,
) -> None:
    """The page a user reads before connecting an exchange account. What the system cannot
    do belongs where they will see it, not in a footnote."""
    report = (await client.get("/api/live/gate")).json()

    assert "never lets it move funds" in report["custody_note"]
    assert "withdrawal" in report["custody_note"]


# --------------------------------------------------------------------------- arming


async def test_arming_is_refused_while_the_live_path_is_disabled(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/live/arm", json={"confirmation": CONFIRMATION_PHRASE}
    )
    assert response.status_code == 403
    assert "disabled in configuration" in response.json()["detail"]


async def test_arming_is_refused_while_any_check_fails(
    armed_client: httpx.AsyncClient,
) -> None:
    """The decisive one. Configuration is as permissive as it can be — live enabled, a
    ceiling set, credentials present — and the gate still refuses, because the machinery
    has not been verified. A 409, not a 400: the request was fine, the system is not."""
    response = await armed_client.post(
        "/api/live/arm", json={"confirmation": CONFIRMATION_PHRASE}
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "LIVE REFUSED" in detail
    assert "fees_verified_at_source" in detail


async def test_arming_is_refused_without_the_exact_phrase(
    armed_client: httpx.AsyncClient,
) -> None:
    for attempt in ("yes", "si", CONFIRMATION_PHRASE.lower(), CONFIRMATION_PHRASE[:-2]):
        response = await armed_client.post("/api/live/arm", json={"confirmation": attempt})
        assert response.status_code == 409


async def test_the_arm_request_has_no_field_for_a_secret_or_a_capital_amount(
    armed_client: httpx.AsyncClient,
) -> None:
    """Accepting either over HTTP would mean a secret travelling through a request log and
    a proxy, and would let whoever can reach the endpoint choose the amount at risk.

    Extra fields are ignored rather than honoured — asserted by sending them and checking
    the ceiling did not move.
    """
    await armed_client.post(
        "/api/live/arm",
        json={
            "confirmation": CONFIRMATION_PHRASE,
            "max_live_capital": 10_000_000.0,
            "binance_api_secret": "injected",
        },
    )
    report = (await armed_client.get("/api/live/gate")).json()
    assert report["max_live_capital"] == 500.0


# --------------------------------------------------------------------------- secrets


@pytest.mark.parametrize(
    "path", ["/api/live/gate", "/api/settings", "/api/health", "/api/system/status"]
)
async def test_no_endpoint_leaks_the_venue_secret(
    armed_client: httpx.AsyncClient, path: str
) -> None:
    """Scans the whole body rather than named fields. A redaction that covers the fields
    someone remembered is a redaction that misses the one they added last week."""
    body = (await armed_client.get(path)).text

    assert API_SECRET not in body
    assert API_KEY not in body


async def test_settings_reports_whether_a_key_is_configured_but_never_which(
    armed_client: httpx.AsyncClient,
) -> None:
    settings = (await armed_client.get("/api/settings")).json()

    assert settings["live"]["credentials_configured"] is True
    assert settings["live"]["max_live_capital"] == 500.0
    assert "binance_api_key" not in settings["live"]
    assert "binance_api_secret" not in settings["live"]


async def test_an_arm_failure_message_does_not_leak_a_secret(
    armed_client: httpx.AsyncClient,
) -> None:
    """Error paths are where redaction is usually forgotten, because nobody reads them
    until something is already going wrong."""
    response = await armed_client.post(
        "/api/live/arm", json={"confirmation": CONFIRMATION_PHRASE}
    )

    assert API_SECRET not in response.text
    assert API_KEY not in response.text


# --------------------------------------------------------------------------- panels


async def test_the_capital_panel_separates_contributions_from_trading_pnl(
    client: httpx.AsyncClient,
) -> None:
    capital = (await client.get("/api/capital")).json()

    assert set(capital) >= {
        "deposits", "withdrawals", "net_contributed", "realized_pnl",
        "unrealized_pnl", "trading_pnl", "return_pct",
    }
    assert "never counted as profit" in capital["explanation"]
    assert capital["live"]["allocated"] == 0.0
    assert "no wallet" in capital["live"]["note"]


async def test_economics_and_analytics_refuse_rather_than_inventing_numbers(
    client: httpx.AsyncClient,
) -> None:
    """With no run active there is nothing to report, and saying so beats returning zeros
    that read as measurements."""
    economics = (await client.get("/api/economics")).json()
    analytics = (await client.get("/api/analytics")).json()

    assert economics["available"] is False
    assert economics["reason"]
    assert analytics["available"] is False
    assert analytics["reason"]


async def test_every_new_endpoint_requires_a_session(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            for path in ("/api/economics", "/api/analytics", "/api/capital", "/api/live/gate"):
                assert (await http.get(path)).status_code == 401
            assert (
                await http.post("/api/live/arm", json={"confirmation": CONFIRMATION_PHRASE})
            ).status_code == 401
            assert (await http.post("/api/live/paper-start")).status_code == 401


# --------------------------------------------------------------------------- paper 24/7


class _FakePublicFeed(MarketDataProvider):
    """Stands in for ``BinancePublicProvider``: same constructor shape, synthetic bars.

    Substituted by monkeypatch because every Binance host is blocked in this environment.
    What these tests exercise is the route, the session lifecycle and the honesty of the
    snapshot — not the venue client, which has its own tests against a mock transport and
    an external validation script for the real thing.
    """

    def __init__(self, *, base_url: str = "", clock: Any = None, **_: Any) -> None:
        super().__init__(ProviderCapabilities(name="fake-binance-public"))
        scenario = get_scenario("trend_up")
        # Anchored so the last closed bar ends at wall-now: the runtime uses a
        # SystemClock, and both the quality gate and the staleness watchdog measure
        # freshness against it.
        start = datetime.now(UTC) - timedelta(minutes=scenario.total_bars)
        self._candles = generate_series(
            scenario, symbol="BTC-USD", timeframe="1m", start=start, seed=11
        )

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        return self._candles[-limit:]

    async def server_time_ms(self) -> int:
        return int(datetime.now(UTC).timestamp() * 1000)


class _UnreachableFeed(MarketDataProvider):
    """A venue whose host cannot be resolved. Every call fails the way httpx would."""

    def __init__(self, *, base_url: str = "", clock: Any = None, **_: Any) -> None:
        super().__init__(ProviderCapabilities(name="unreachable-binance-public"))

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        raise ProviderUnavailableError("binance: host unreachable (egress blocked)")

    async def server_time_ms(self) -> int:
        raise ProviderUnavailableError("binance: host unreachable (egress blocked)")


async def test_paper_realtime_starts_without_credentials_and_says_it_is_simulated(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 24/7 session: real-data-shaped feed, simulated fills, no token, no secret.

    The snapshot must say what it is — ``paper-live`` and ``simulated: true`` — because a
    session that could be mistaken for live is how a track record gets misread later.
    """
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)

    started = await client.post("/api/live/paper-start")
    assert started.status_code == 200, started.text
    body = started.json()
    try:
        assert body["mode"] == "paper-live"
        assert body["simulated"] is True
        assert body["activation"] is None
        assert body["state"] == "running"

        snapshot = (await client.get("/api/live")).json()
        assert snapshot["active"] is True
        assert snapshot["mode"] == "paper-live"

        # Health distinguishes "the HTTP server answers" from "the engine is alive":
        # the trading_engine component reads the loop's own heartbeat.
        health = (await client.get("/api/health")).json()
        assert health["components"]["trading_engine"] == "running"
        assert health["components"]["market_data_feed"] == "online"
        assert health["live_runtime"]["mode"] == "paper-live"
        assert health["live_runtime"]["heartbeat_age_seconds"] is not None
        assert health["simulated_only"] is True

        # A second session on top of the first is refused, not stacked.
        second = await client.post("/api/live/paper-start")
        assert second.status_code == 409
        assert "already active" in second.json()["detail"]
    finally:
        stopped = await client.post("/api/live/stop")
        assert stopped.status_code == 200

    assert (await client.get("/api/live")).json()["active"] is False


async def test_paper_start_refuses_cleanly_when_the_data_host_is_unreachable(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly what happens in this build environment: egress blocked. The route must
    answer 503 with the reason, and must not leave a half-started session behind."""
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _UnreachableFeed)

    response = await client.post("/api/live/paper-start")
    assert response.status_code == 503
    assert "unreachable" in response.json()["detail"]

    assert (await client.get("/api/live")).json()["active"] is False


async def test_paper_session_resumes_after_a_crash_but_not_after_an_operator_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 24/7 contract across restarts, both halves.

    A redeploy or crash interrupts the session mid-flight and leaves its run row
    unstamped — the next boot resumes a fresh session over the same evidence store. An
    operator stop goes through the stamping path, and stamped intent survives reboots.
    """
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)

    # Boot 1: start the paper session, then "crash" — the lifespan exit stops the loop
    # (SIGTERM does the same) but nothing stamps the run row.
    async for http in _client(create_app(_settings(tmp_path))):
        started = await http.post("/api/live/paper-start")
        assert started.status_code == 200, started.text

    # Boot 2: the session is back without anyone asking.
    async for http in _client(create_app(_settings(tmp_path))):
        snapshot = (await http.get("/api/live")).json()
        assert snapshot["active"] is True
        assert snapshot["mode"] == "paper-live"
        # Now stop it properly: this stamps the run row.
        assert (await http.post("/api/live/stop")).status_code == 200

    # Boot 3: stopped means stopped.
    async for http in _client(create_app(_settings(tmp_path))):
        assert (await http.get("/api/live")).json()["active"] is False


async def test_a_kill_switched_paper_session_stays_down_across_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sticky means sticky: SAFE_MODE engaged by an operator is not something a reboot
    may undo. The next boot sees the halt incident and leaves the session down."""
    import asyncio

    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)

    async for http in _client(create_app(_settings(tmp_path))):
        assert (await http.post("/api/live/paper-start")).status_code == 200
        killed = await http.post("/api/live/kill-switch", json={"reason": "drill"})
        assert killed.status_code == 200
        assert killed.json()["state"] == "safe_mode"
        await asyncio.sleep(0.1)  # let the fire-and-forget incident row land

    async for http in _client(create_app(_settings(tmp_path))):
        assert (await http.get("/api/live")).json()["active"] is False


async def test_incident_alerts_reach_the_webhook_and_carry_no_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alert seam: an incident goes out to the configured webhook with the incident's
    facts and nothing else. Scanned for the canary secret like every other egress path."""
    import asyncio
    import json as jsonlib

    import httpx as httpx_module

    from tia.api.state import AppState

    sent: list[tuple[str, dict[str, Any]]] = []

    class _Recorder:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        async def __aenter__(self) -> _Recorder:
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def post(self, url: str, json: dict[str, Any] | None = None) -> None:
            sent.append((url, json or {}))

    monkeypatch.setattr(httpx_module, "AsyncClient", _Recorder)

    live = LiveConfig(
        enabled=True,
        max_live_capital=500.0,
        binance_api_key=SecretStr(API_KEY),
        binance_api_secret=SecretStr(API_SECRET),
    )
    settings = _settings(tmp_path, live=live)
    settings = settings.model_copy(
        update={
            "observability": settings.observability.model_copy(
                update={"alert_webhook_url": "https://alerts.example/hook"}
            )
        }
    )
    state = AppState(settings)
    await state.startup()
    try:
        state._dispatch_alert(
            {
                "kind": "safe_mode",
                "reason": "kill switch engaged",
                "actor": "operator",
                "run_id": "run-1",
                "at": "2026-08-14T12:00:00+00:00",
            }
        )
        for _ in range(5):  # let the fire-and-forget task run
            await asyncio.sleep(0)

        assert sent, "the configured webhook was never called"
        url, payload = sent[0]
        assert url == "https://alerts.example/hook"
        assert payload["kind"] == "safe_mode"
        assert payload["source"] == "trader-ia"
        body = jsonlib.dumps(payload)
        assert API_SECRET not in body
        assert API_KEY not in body
    finally:
        await state.shutdown()


async def test_no_webhook_configured_means_no_outbound_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    import httpx as httpx_module

    from tia.api.state import AppState

    calls: list[Any] = []

    class _Recorder:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            calls.append(self)

        async def __aenter__(self) -> _Recorder:
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        async def post(self, url: str, json: dict[str, Any] | None = None) -> None:
            calls.append((url, json))

    monkeypatch.setattr(httpx_module, "AsyncClient", _Recorder)

    state = AppState(_settings(tmp_path))  # default: alert_webhook_url == ""
    await state.startup()
    try:
        state._dispatch_alert({"kind": "safe_mode", "reason": "x", "actor": "y"})
        for _ in range(5):
            await asyncio.sleep(0)
        assert calls == []
    finally:
        await state.shutdown()


async def test_paper_start_requires_the_operator_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A viewer can watch a session; only an operator can start one."""
    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)
    app = create_app(_settings(tmp_path))
    app.state.auth.add_user("viewer", "viewer-password-not-a-secret", role="viewer")
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            await http.post(
                "/api/auth/login",
                json={"username": "viewer", "password": "viewer-password-not-a-secret"},
            )
            assert (await http.post("/api/live/paper-start")).status_code == 403
