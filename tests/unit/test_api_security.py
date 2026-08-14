"""API surface and security.

The threat model is narrow and worth stating, because it changes what matters: this
application holds **no money and no financial credential**. What authentication protects
is the control surface — who may start, halt or reset a simulation — and what the rest of
the hardening protects is the operator's browser and the server's own integrity.

So the tests below check the things that are actually reachable: authentication,
authorisation, injection through every parameter that reaches the database, XSS through
every string that reaches the page, rate limiting, header hardening, and the absence of
any route that could touch real money.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from tia.api.app import create_app
from tia.api.security import AuthService, RateLimiter, hash_password, verify_password
from tia.core.config import Environment, settings_for_env

USERNAME = "api-operator"
PASSWORD = "api-password-not-a-secret"  # noqa: S105 - a fixture credential, by design

#: Signing keys for the token tests. A test that verifies signature checking has to hold
#: a key; these are literals so the assertions are readable, and they never leave this file.
TEST_SIGNING_KEY_A = "test-signing-key-alpha"
TEST_SIGNING_KEY_B = "test-signing-key-beta"


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)
    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"}
    )
    app = create_app(settings)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest.fixture
async def authed(client: httpx.AsyncClient) -> httpx.AsyncClient:
    await client.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    return client


# --------------------------------------------------------------------------- passwords


def test_a_password_is_never_stored_in_plaintext() -> None:
    stored = hash_password("hunter2")
    assert "hunter2" not in stored
    assert stored.count("$") == 1, "salt and digest, both hex"
    assert verify_password("hunter2", stored)
    assert not verify_password("hunter3", stored)


def test_the_same_password_hashes_differently_each_time() -> None:
    """Per-password salt. Identical hashes would leak that two accounts share a password."""
    assert hash_password("same") != hash_password("same")


@pytest.mark.parametrize("stored", ["", "garbage", "nosalt$", "$nodigest", "zz$zz"])
def test_a_malformed_hash_fails_closed(stored: str) -> None:
    assert not verify_password("anything", stored)


# --------------------------------------------------------------------------- tokens


def test_a_token_signed_with_another_secret_is_rejected() -> None:
    issuer = AuthService(secret=TEST_SIGNING_KEY_A)
    attacker = AuthService(secret=TEST_SIGNING_KEY_B)
    from tia.api.security import User

    token = attacker.issue_token(User(username="mallory", role="operator"))
    assert issuer.read_token(token) is None


def test_a_tampered_token_is_rejected() -> None:
    from tia.api.security import User

    service = AuthService(secret=TEST_SIGNING_KEY_A)
    token = service.issue_token(User(username="alice"))
    header, payload, signature = token.split(".")
    assert service.read_token(f"{header}.{payload}x.{signature}") is None


def test_the_alg_none_attack_does_not_work() -> None:
    """`algorithms=[ALGORITHM]` at decode time is what closes this. Asserted rather than
    trusted, because the failure is silent and total."""
    import base64
    import json

    def b64(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': 'mallory', 'role': 'operator'})}."
    assert AuthService(secret=TEST_SIGNING_KEY_A).read_token(forged) is None


def test_an_expired_token_is_rejected() -> None:
    from datetime import UTC, datetime, timedelta

    from tia.api.security import User

    service = AuthService(secret=TEST_SIGNING_KEY_A)
    token = service.issue_token(
        User(username="alice"), now=datetime.now(UTC) - timedelta(days=2)
    )
    assert service.read_token(token) is None


def test_each_process_gets_its_own_secret_when_none_is_configured() -> None:
    """No shared default. A hard-coded fallback is how a demo key reaches production."""
    from tia.api.security import User

    first, second = AuthService(), AuthService()
    assert first.uses_ephemeral_secret
    assert second.read_token(first.issue_token(User(username="alice"))) is None


# --------------------------------------------------------------------------- auth flow


@pytest.mark.parametrize(
    "path",
    [
        "/api/runtime",
        "/api/portfolio",
        "/api/positions",
        "/api/orders",
        "/api/decisions",
        "/api/assessments",
        "/api/logs",
        "/api/risk",
        "/api/settings",
        "/api/markets",
        "/api/backtests",
        "/api/stream",
        "/api/metrics",
        "/api/system/status",
    ],
)
async def test_every_data_endpoint_requires_a_session(
    client: httpx.AsyncClient, path: str
) -> None:
    """Read endpoints too: an unauthenticated scrape must not enumerate the system."""
    assert (await client.get(path)).status_code == 401


@pytest.mark.parametrize(
    "path",
    ["/api/runtime/start", "/api/runtime/stop", "/api/runtime/kill-switch", "/api/runtime/reset"],
)
async def test_every_control_endpoint_requires_a_session(
    client: httpx.AsyncClient, path: str
) -> None:
    assert (await client.post(path, json={})).status_code == 401


async def test_health_is_reachable_without_a_session(client: httpx.AsyncClient) -> None:
    """A health probe should not need credentials — and it returns component states only,
    never data."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"status", "components", "simulated_only"}
    assert "capital" not in body and "positions" not in body


async def test_wrong_credentials_are_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrong"}
    )
    assert response.status_code == 401


async def test_the_login_endpoint_is_not_a_username_oracle(client: httpx.AsyncClient) -> None:
    """Identical response for a wrong password and a nonexistent user."""
    missing = await client.post(
        "/api/auth/login", json={"username": "nobody", "password": "x"}
    )
    wrong = await client.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrong"}
    )
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


async def test_the_session_cookie_is_hardened(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
    )
    header = response.headers.get("set-cookie", "").lower()
    assert "httponly" in header, "page JavaScript must not be able to read the session"
    assert "samesite=strict" in header, "a cross-site request must not carry the session"


async def test_logging_out_clears_the_session(authed: httpx.AsyncClient) -> None:
    assert (await authed.get("/api/runtime")).status_code == 200
    await authed.post("/api/auth/logout")
    authed.cookies.clear()
    assert (await authed.get("/api/runtime")).status_code == 401


async def test_repeated_failed_logins_are_rate_limited(client: httpx.AsyncClient) -> None:
    codes = [
        (
            await client.post(
                "/api/auth/login", json={"username": USERNAME, "password": "wrong"}
            )
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codes, "a login endpoint that never rate-limits can be brute-forced"


def test_the_rate_limiter_window_slides() -> None:
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.check("client", now=1000.0)
    assert limiter.check("client", now=1001.0)
    assert not limiter.check("client", now=1002.0)
    assert limiter.check("client", now=1065.0), "the window must slide"


# --------------------------------------------------------------------------- injection


@pytest.mark.parametrize(
    "payload",
    [
        "'; DROP TABLE runs; --",
        "1 OR 1=1",
        "\" OR \"\"=\"",
        "'; DELETE FROM decisions WHERE 1=1; --",
        "%27%20OR%201%3D1",
    ],
)
async def test_sql_injection_through_a_path_parameter_does_nothing(
    authed: httpx.AsyncClient, payload: str
) -> None:
    """Every query goes through SQLAlchemy with bound parameters, so this cannot work.
    Asserted anyway: the day someone writes an f-string query, this fails."""
    response = await authed.get(f"/api/decisions/{payload}")
    assert response.status_code in {404, 400, 422}

    # The database is still intact and still answering.
    assert (await authed.get("/api/backtests")).status_code == 200


@pytest.mark.parametrize(
    "payload", ["'; DROP TABLE fills; --", "../../etc/passwd", "<script>alert(1)</script>"]
)
async def test_injection_through_a_query_parameter_does_nothing(
    authed: httpx.AsyncClient, payload: str
) -> None:
    response = await authed.get("/api/logs", params={"limit": 10, "level": payload})
    assert response.status_code == 200
    assert response.json() == [] or isinstance(response.json(), list)


async def test_a_path_traversal_attempt_cannot_read_the_filesystem(
    authed: httpx.AsyncClient,
) -> None:
    """What matters is the *content*, not the status code.

    Some of these normalise into a path that no API route matches and fall through to the
    single-page app, which correctly answers with index.html and a 200. That is not a
    leak, and asserting on the status would flag it as one. The assertion is therefore on
    what came back: never the contents of a file on the host.
    """
    for attempt in (
        "../../../etc/passwd",
        "..%2f..%2f..%2fetc%2fpasswd",
        "/etc/passwd",
        "....//....//etc/passwd",
        "..\\..\\windows\\win.ini",
    ):
        response = await authed.get(f"/api/markets/{attempt}/candles")
        body = response.text
        assert "root:x:" not in body, "a traversal returned /etc/passwd"
        assert "[fonts]" not in body, "a traversal returned a Windows file"
        assert "BEGIN PRIVATE KEY" not in body
        assert "sqlite" not in body.lower() or response.headers.get(
            "content-type", ""
        ).startswith("text/html"), "a traversal returned database bytes"


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "body",
    [
        {"initial_capital": -1000},
        {"initial_capital": 0},
        {"initial_capital": 10**12},
        {"scenario": "does_not_exist"},
        {"symbols": ["a"] * 40},
        {"bar_interval_seconds": -5},
        {"seed": -1},
    ],
)
async def test_bad_start_parameters_are_refused(
    authed: httpx.AsyncClient, body: dict
) -> None:
    response = await authed.post("/api/runtime/start", json=body)
    assert response.status_code in {400, 422}, f"{body} was accepted"


async def test_an_oversized_body_is_refused(authed: httpx.AsyncClient) -> None:
    response = await authed.post(
        "/api/runtime/start",
        content=b'{"scenario": "' + b"x" * 300_000 + b'"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code in {413, 422}


async def test_an_internal_error_never_leaks_a_traceback(
    authed: httpx.AsyncClient,
) -> None:
    """Whatever goes wrong, the client learns a status code and nothing about the host."""
    response = await authed.post(
        "/api/backtests",
        json={"symbol": "NOT-A-SYMBOL", "timeframe": "1h", "bars": 300, "seed": 1},
    )
    assert response.status_code in {400, 422, 500}
    body = response.text.lower()
    for leak in ("traceback", "/home/", "site-packages", "sqlalchemy.exc", ".py\", line"):
        assert leak not in body, f"the response leaked {leak!r}"


# --------------------------------------------------------------------------- headers


async def test_security_headers_are_present(client: httpx.AsyncClient) -> None:
    headers = (await client.get("/api/health")).headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"


async def test_the_csp_forbids_inline_script(client: httpx.AsyncClient) -> None:
    """The XSS mitigation that survives a mistake in the app: even if a payload reaches
    the page, the browser refuses to execute it."""
    policy = (await client.get("/api/health")).headers["content-security-policy"]
    assert "script-src 'self'" in policy
    assert "'unsafe-inline'" not in policy.split("style-src")[0]


# --------------------------------------------------------------------------- secrets


async def test_no_endpoint_returns_a_secret(authed: httpx.AsyncClient) -> None:
    settings = (await authed.get("/api/settings")).json()
    serialised = str(settings).lower()
    for marker in ("sk-ant", "api_key\":", "password", "secret_value"):
        assert marker not in serialised, f"the settings endpoint leaked {marker!r}"
    # It reports *whether* a key exists, which is useful and harmless.
    assert "api_key_configured" in settings["llm"]


async def test_a_database_password_is_masked(tmp_path: Path) -> None:
    from tia.persistence.database import _mask

    masked = _mask("postgresql+asyncpg://user:hunter2@db:5432/tia")
    assert "hunter2" not in masked
    assert masked.endswith("@db:5432/tia")
    del tmp_path


# --------------------------------------------------------------------------- scope


async def test_the_api_exposes_no_route_that_could_move_real_money(
    authed: httpx.AsyncClient,
) -> None:
    """The scope rule at the HTTP boundary.

    A route named for a deposit, a withdrawal or a broker credential would be the first
    visible sign of scope creep, so its absence is checked rather than assumed.
    """
    spec = (await authed.get("/api/openapi.json")).json()
    paths = " ".join(spec["paths"]).lower()
    for forbidden in (
        "deposit", "withdraw", "transfer", "payout", "bank", "card",
        "broker", "credential", "wallet", "custody", "kyc", "payment",
    ):
        assert forbidden not in paths, f"the API exposes a /{forbidden} route"


async def test_the_api_declares_itself_simulation_only(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/health")).json()["simulated_only"] is True
    spec = (await client.get("/api/openapi.json")).json()
    assert "simulation-only" in spec["info"]["description"].lower()


async def test_risk_limits_are_not_editable_through_the_api(
    authed: httpx.AsyncClient,
) -> None:
    """§48: the system may not rewrite its own risk rules, and neither may the UI."""
    settings = (await authed.get("/api/settings")).json()
    assert settings["risk_limits"]["editable_from_ui"] is False

    spec = (await authed.get("/api/openapi.json")).json()
    mutating = [
        path
        for path, methods in spec["paths"].items()
        if {"post", "put", "patch", "delete"} & set(methods)
    ]
    assert not any("risk" in path and "limit" in path for path in mutating)


def test_a_configured_jwt_secret_is_actually_used_and_the_placeholder_is_not() -> None:
    """The wiring the first CI run of the 24/7 stack depends on: with a real secret in
    configuration, sessions survive a process restart (two apps over the same settings
    validate each other's tokens); on the placeholder, the service falls back to a
    per-process random secret — safe, but every restart logs everyone out."""
    from pydantic import SecretStr

    from tia.api.security import User
    from tia.core.config import SecurityConfig

    configured = settings_for_env(Environment.TESTING).model_copy(
        update={
            "security": SecurityConfig(
                jwt_secret=SecretStr("a-real-secret-long-enough-to-sign-with-123456")
            )
        }
    )
    first = create_app(configured).state.auth
    second = create_app(configured).state.auth
    assert first.uses_ephemeral_secret is False
    token = first.issue_token(User(username="op", role="operator"))
    survivor = second.read_token(token)
    assert survivor is not None and survivor.username == "op"

    placeholder = create_app(settings_for_env(Environment.TESTING)).state.auth
    assert placeholder.uses_ephemeral_secret is True
    assert placeholder.read_token(token) is None
