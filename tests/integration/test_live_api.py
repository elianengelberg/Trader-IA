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

from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from pydantic import SecretStr

from tia.api.app import create_app
from tia.core.config import Environment, LiveConfig, settings_for_env
from tia.live.gate import CONFIRMATION_PHRASE, REQUIRED_CHECKS

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
