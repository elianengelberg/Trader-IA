"""The HTTP API and the application that serves the dashboard.

One process serves both: the JSON API under `/api`, a Server-Sent Events stream at
`/api/stream`, and the built frontend as static files. That is a deliberate simplification
— it removes CORS, removes a second deployable, and makes `docker compose up` produce one
URL that works.

**Push, not poll.** Prices, P&L, positions, orders, decisions and logs all arrive over the
SSE stream as the runtime produces them. The frontend polls nothing on a timer; the only
periodic request is a health check.

**Nothing here can touch real money.** There is no deposit endpoint, no withdrawal
endpoint, no broker credential field, and no route that reaches an execution provider that
is not a simulator. `POST /api/runtime/capital` sets a number in a simulation.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tia.api.security import (
    SECURITY_HEADERS,
    SESSION_COOKIE,
    SESSION_HOURS,
    AuthService,
    RateLimiter,
    User,
    current_user,
    default_credentials,
    require_operator,
)
from tia.api.state import AppState
from tia.core.config import Environment, Settings, settings_for_env
from tia.core.errors import LiveActivationError, ProviderUnavailableError
from tia.core.logging import get_logger

_log = get_logger("api.app")

FRONTEND_DIR = Path(__file__).resolve().parents[5] / "frontend" / "dist"


# --------------------------------------------------------------------------- schemas


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class StartRequest(BaseModel):
    """Everything a run needs. All of it is simulated."""

    scenario: str = "trend_up"
    symbols: list[str] = Field(default_factory=lambda: ["BTC-USD"], max_length=5)
    #: **Simulated** capital. There is no path from this number to a real account.
    initial_capital: float = Field(default=100_000.0, gt=0, le=100_000_000)
    seed: int = Field(default=20260812, ge=0)
    bar_interval_seconds: float = Field(default=0.35, ge=0.0, le=10.0)
    strategies: list[str] = Field(
        default_factory=lambda: ["trend_following", "mean_reversion", "breakout"]
    )
    llm_enabled: bool = True
    news_enabled: bool = True


class ResetRequest(BaseModel):
    confirm: bool = Field(description="must be true; a reset destroys the run's history")
    initial_capital: float = Field(default=100_000.0, gt=0, le=100_000_000)


class KillRequest(BaseModel):
    reason: str = Field(default="operator", max_length=200)


class ReleaseRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=120)


class BacktestRequest(BaseModel):
    symbol: str = "BTC-USD"
    timeframe: str = "1h"
    bars: int = Field(default=1200, ge=200, le=5000)
    seed: int = Field(default=20260812, ge=0)


class ArmLiveRequest(BaseModel):
    """Note what is *not* here: no API key, no secret, no capital amount.

    Credentials come from the process environment and the ceiling comes from
    configuration. Accepting either over HTTP would mean a secret travelling through a
    request log, a proxy and a browser's memory, and would let the amount at risk be set
    by whoever can reach the endpoint.
    """

    confirmation: str = Field(min_length=1, max_length=200)


class ProfileChangeRequest(BaseModel):
    profile: str = Field(pattern="^(conservative|balanced|aggressive)$")
    confirm: bool = False


# --------------------------------------------------------------------------- app


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or settings_for_env(Environment.DEMO)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state: AppState = app.state.tia
        await state.startup()
        _log.info(
            "api_ready",
            environment=settings.env.value,
            database=state.database.url,
            frontend_built=FRONTEND_DIR.is_dir(),
        )
        try:
            yield
        finally:
            await state.shutdown()

    app = FastAPI(
        title="Trader-IA",
        version="0.1.0",
        description=(
            "Simulation-only quantitative research and paper-trading platform. "
            "No real money, no broker connection, no custody. Nothing served by this API "
            "is a prediction or a recommendation."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.tia = AppState(settings)
    app.state.auth = AuthService()
    app.state.login_limiter = RateLimiter(limit=8, window_seconds=300)
    app.state.api_limiter = RateLimiter(limit=600, window_seconds=60)

    username, password, generated = default_credentials()
    app.state.auth.add_user(username, password, role="operator")
    if generated:
        # Printed once, to the server's own log. Never returned by an endpoint.
        _log.warning(
            "demo_credentials_generated",
            username=username,
            password=password,
            hint="set TIA_DEMO_USER / TIA_DEMO_PASSWORD to choose your own",
        )

    _register_middleware(app)
    _register_routes(app, settings)
    _register_frontend(app)
    return app


def _register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def harden(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()

        # A blunt but effective body cap. FastAPI would otherwise buffer whatever it is
        # sent, and none of this API's endpoints has a legitimate large body.
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > 256_000:
            return JSONResponse({"detail": "request body too large"}, status_code=413)

        client = request.client.host if request.client else "unknown"
        if request.url.path.startswith("/api/") and not app.state.api_limiter.check(
            client, now=time.time()
        ):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)

        try:
            response = await call_next(request)
        except HTTPException:
            raise
        except Exception as exc:
            # Never leak a traceback or an internal path to a client.
            _log.exception("unhandled_request_error", path=request.url.path)
            response = JSONResponse(
                {"detail": "internal error", "error_id": str(int(time.time() * 1000))},
                status_code=500,
            )
            del exc

        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response


def _register_routes(app: FastAPI, settings: Settings) -> None:
    def tia(request: Request) -> AppState:
        return request.app.state.tia  # type: ignore[no-any-return]

    # ------------------------------------------------------------------ auth

    @app.post("/api/auth/login")
    async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        client = request.client.host if request.client else "unknown"
        if not request.app.state.login_limiter.check(client, now=time.time()):
            raise HTTPException(429, "too many login attempts; wait five minutes")

        user = request.app.state.auth.authenticate(body.username, body.password)
        if user is None:
            # One message for both failure modes, so the endpoint is not a username oracle.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

        request.app.state.login_limiter.reset(client)
        token = request.app.state.auth.issue_token(user)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=SESSION_HOURS * 3600,
            path="/",
        )
        return {"username": user.username, "role": user.role}

    @app.post("/api/auth/logout")
    async def logout(response: Response) -> dict[str, str]:
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"status": "logged out"}

    @app.get("/api/auth/me")
    async def me(user: User = Depends(current_user)) -> dict[str, Any]:
        return {"username": user.username, "role": user.role}

    # ------------------------------------------------------------------ health

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        """Unauthenticated on purpose: a health probe should not need a session.

        Returns component states only — no data, no counts, nothing that would help an
        unauthenticated caller learn anything about the account.
        """
        return await tia(request).health()

    @app.get("/api/system/status")
    async def system_status(
        request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        return await tia(request).system_status()

    # ------------------------------------------------------------------ runtime control

    @app.get("/api/runtime")
    async def runtime_state(
        request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        return tia(request).runtime_snapshot()

    @app.post("/api/runtime/start")
    async def start_runtime(
        body: StartRequest, request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        try:
            return await tia(request).start_run(body.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/runtime/stop")
    async def stop_runtime(
        request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        return await tia(request).stop_run()

    @app.post("/api/runtime/pause")
    async def pause_runtime(
        request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        return tia(request).pause_run()

    @app.post("/api/runtime/resume")
    async def resume_runtime(
        request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        return tia(request).resume_run()

    @app.post("/api/runtime/stop-new-trades")
    async def stop_new_trades(
        request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        return tia(request).stop_new_trades()

    @app.post("/api/runtime/kill-switch")
    async def kill_switch(
        body: KillRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        return tia(request).kill_switch(f"{body.reason} (by {user.username})")

    @app.post("/api/runtime/release-kill-switch")
    async def release_kill_switch(
        body: ReleaseRequest, request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Leaving safe mode requires naming who approved it. That name is recorded."""
        return tia(request).release_kill_switch(body.approved_by)

    @app.post("/api/runtime/reset")
    async def reset_account(
        body: ResetRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        if not body.confirm:
            raise HTTPException(400, "reset requires confirm=true")
        return await tia(request).reset_account(body.initial_capital, by=user.username)

    # ------------------------------------------------------------------ data

    @app.get("/api/portfolio")
    async def portfolio(
        request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        return tia(request).portfolio()

    @app.get("/api/positions")
    async def positions(request: Request, _user: User = Depends(current_user)) -> list[Any]:
        return tia(request).positions()

    @app.get("/api/orders")
    async def orders(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(100, ge=1, le=500),
    ) -> list[Any]:
        return tia(request).orders(limit)

    @app.get("/api/fills")
    async def fills(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(100, ge=1, le=500),
    ) -> list[Any]:
        return tia(request).fills(limit)

    @app.get("/api/decisions")
    async def decisions(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(50, ge=1, le=300),
        actionable_only: bool = False,
    ) -> list[Any]:
        return tia(request).decisions(limit, actionable_only)

    @app.get("/api/decisions/{decision_id}")
    async def decision_detail(
        decision_id: str, request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        found = tia(request).decision(decision_id)
        if found is None:
            raise HTTPException(404, "decision not found")
        return found

    @app.get("/api/assessments")
    async def assessments(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(50, ge=1, le=200),
    ) -> list[Any]:
        return tia(request).assessments(limit)

    @app.get("/api/markets")
    async def markets(request: Request, _user: User = Depends(current_user)) -> list[Any]:
        return tia(request).markets()

    @app.get("/api/markets/{symbol}/candles")
    async def candles(
        symbol: str,
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(200, ge=10, le=1000),
    ) -> list[Any]:
        return tia(request).candles(symbol, limit)

    @app.get("/api/news")
    async def news(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(40, ge=1, le=200),
    ) -> list[Any]:
        return tia(request).news(limit)

    @app.get("/api/logs")
    async def logs(
        request: Request,
        _user: User = Depends(current_user),
        limit: int = Query(200, ge=1, le=1000),
        level: str | None = None,
        channel: str | None = None,
    ) -> list[Any]:
        return tia(request).logs(limit, level, channel)

    @app.get("/api/risk")
    async def risk(request: Request, _user: User = Depends(current_user)) -> dict[str, Any]:
        return tia(request).risk()

    @app.get("/api/strategies")
    async def strategies(request: Request, _user: User = Depends(current_user)) -> list[Any]:
        return tia(request).strategies()

    # ------------------------------------------------------------------ economics

    @app.get("/api/economics")
    async def economics(request: Request, _user: User = Depends(current_user)) -> dict[str, Any]:
        """Costs, expected value and the risk budget for the most recent signals."""
        return tia(request).economics()

    @app.get("/api/analytics")
    async def analytics(request: Request, _user: User = Depends(current_user)) -> dict[str, Any]:
        """Probability of ruin and safe sizing, from this run's closed trades."""
        return tia(request).analytics()

    @app.get("/api/capital")
    async def capital(request: Request, _user: User = Depends(current_user)) -> dict[str, Any]:
        """Contributed capital, trading P&L, and the two kept strictly apart."""
        return tia(request).capital()

    # ------------------------------------------------------------------ live gate

    @app.get("/api/live/gate")
    async def live_gate(request: Request, _user: User = Depends(current_user)) -> dict[str, Any]:
        """Every activation check, with its verdict and what to do about it.

        Read-only. Nothing here arms anything, so it is safe for any authenticated user
        to look at — and looking is the point: the checks are meant to be visible before
        anyone tries to pass them.
        """
        return await tia(request).live_gate()

    @app.post("/api/live/arm")
    async def arm_live(
        body: ArmLiveRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Attempt to arm live trading.

        Requires an operator, the exact confirmation phrase, and every activation check
        passing. Refuses with the full report otherwise — which is what it will do in any
        deployment where the venue adapter has not been validated against the real venue.
        """
        try:
            return await tia(request).arm_live(
                operator=user.username, confirmation=body.confirmation
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except LiveActivationError as exc:
            # 409, not 400: the request was well-formed and the *system* is not in a state
            # where it can be granted. A 400 would suggest the caller should fix the body.
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/live/paper-start")
    async def paper_realtime_start(
        request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Start the 24/7 paper-realtime session: real market data, simulated fills.

        No activation token, no confirmation phrase, no body at all — because nothing this
        route starts can spend real money. The provider layer enforces that independently:
        a non-simulated execution provider cannot be constructed without a token, and this
        session is built over the paper simulator. Stopping goes through the same
        `POST /api/live/stop` as a live session.
        """
        try:
            return await tia(request).start_paper_realtime(actor=user.username)
        except LiveActivationError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ProviderUnavailableError as exc:
            # The venue's public data host could not be reached. Nothing was started.
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/live")
    async def live_snapshot(
        request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        """The live session's real state — the state machine's word, not a wish."""
        live = tia(request).live_runtime
        if live is None:
            return {"active": False, "state": "disarmed"}
        return {"active": live.is_running, **live.snapshot()}

    @app.post("/api/risk/profile")
    async def change_risk_profile(
        body: ProfileChangeRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Change the risk profile for the NEXT run. Audited; refused mid-live-session.

        Note what this route cannot do: it cannot touch `RiskLimits` (immutable, no route
        exists), cannot raise `max_live_capital`, and cannot affect a session already
        running. It selects among the three reviewed profiles, nothing more.
        """
        try:
            return await tia(request).change_risk_profile(
                profile=body.profile, actor=user.username, confirmed=body.confirm
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/risk/profile/history")
    async def profile_history(
        request: Request, _user: User = Depends(current_user)
    ) -> list[dict[str, Any]]:
        return await tia(request).profile_change_history()

    @app.get("/api/live/history")
    async def live_history(
        request: Request, _user: User = Depends(current_user)
    ) -> list[dict[str, Any]]:
        """Every arming attempt ever made, pass or fail, with what decided it."""
        return await tia(request).activation_history()

    @app.post("/api/live/stop")
    async def live_stop(
        request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Stops the session and stamps its run row — which is what keeps an operator
        stop stopped across restarts, while a crash-interrupted paper session resumes."""
        return await tia(request).stop_realtime_session(
            reason=f"operator stop by {user.username}"
        )

    @app.post("/api/live/kill-switch")
    async def live_kill_switch(
        body: KillRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """The emergency stop. Cancels resting orders and lands in SAFE_MODE.

        Reachable by an operator only, never by a model — there is no code path from the
        LLM layer to this endpoint, and the runtime method requires a named actor.
        """
        live = tia(request).live_runtime
        if live is None:
            raise HTTPException(409, "no live session to stop")
        return await live.kill_switch(reason=body.reason, actor=user.username)

    @app.post("/api/live/flatten")
    async def live_flatten(
        body: KillRequest, request: Request, user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        """Emergency flatten: cancel everything, close every position, verify, record."""
        live = tia(request).live_runtime
        if live is None:
            raise HTTPException(409, "no live session to flatten")
        return await live.emergency_flatten(reason=body.reason, actor=user.username)

    @app.get("/api/scenarios")
    async def scenarios(_user: User = Depends(current_user)) -> list[Any]:
        from tia.runtime.scenarios import scenario_catalogue

        return scenario_catalogue()

    @app.get("/api/events/{correlation_id}")
    async def event_trace(
        correlation_id: str, request: Request, _user: User = Depends(current_user)
    ) -> list[Any]:
        return await tia(request).event_trace(correlation_id)

    # ------------------------------------------------------------------ backtests

    @app.get("/api/backtests")
    async def list_backtests(
        request: Request, _user: User = Depends(current_user)
    ) -> list[Any]:
        return await tia(request).list_backtests()

    @app.post("/api/backtests")
    async def run_backtest(
        body: BacktestRequest, request: Request, _user: User = Depends(require_operator)
    ) -> dict[str, Any]:
        try:
            return await tia(request).run_backtest(
                symbol=body.symbol, timeframe=body.timeframe, bars=body.bars, seed=body.seed
            )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(400, str(exc)) from exc

    # ------------------------------------------------------------------ settings

    @app.get("/api/settings")
    async def get_settings(
        request: Request, _user: User = Depends(current_user)
    ) -> dict[str, Any]:
        return tia(request).settings_view()

    # ------------------------------------------------------------------ stream

    @app.get("/api/stream")
    async def stream(request: Request, _user: User = Depends(current_user)) -> StreamingResponse:
        """Server-Sent Events.

        Chosen over WebSockets because the traffic is one-directional: the server pushes,
        the browser never sends anything back on this channel. SSE reconnects on its own,
        works through any proxy that handles HTTP, and needs no protocol upgrade.
        """
        state: AppState = request.app.state.tia
        queue = state.subscribe()

        async def generator() -> AsyncIterator[bytes]:
            try:
                yield b": connected\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        # A comment frame keeps intermediaries from closing an idle
                        # connection, and costs nothing.
                        yield b": keepalive\n\n"
                        continue
                    payload = json.dumps(event.get("data", {}), default=str)
                    yield f"event: {event.get('type', 'message')}\ndata: {payload}\n\n".encode()
            finally:
                state.unsubscribe(queue)

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/metrics")
    async def metrics(request: Request, _user: User = Depends(current_user)) -> Response:
        return Response(
            content=tia(request).prometheus_metrics(), media_type="text/plain; version=0.0.4"
        )

    del settings


def _register_frontend(app: FastAPI) -> None:
    """Serve the built dashboard, if it has been built.

    When it has not, `/` returns a short instruction rather than a 404 — the most common
    reason to hit this is a fresh clone where `npm run build` has not run yet, and a 404
    does not say that.
    """
    if FRONTEND_DIR.is_dir():
        assets = FRONTEND_DIR / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> Response:
            # Anything that is not an API route falls through to index.html so the
            # single-page app can own its own routing.
            if full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            candidate = FRONTEND_DIR / full_path
            if full_path and candidate.is_file() and candidate.resolve().is_relative_to(
                FRONTEND_DIR.resolve()
            ):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIR / "index.html")

    else:

        @app.get("/", include_in_schema=False)
        async def not_built() -> JSONResponse:
            return JSONResponse(
                {
                    "status": "frontend not built",
                    "fix": "cd frontend && npm install && npm run build",
                    "api_docs": "/api/docs",
                },
                status_code=503,
            )


def get_app() -> FastAPI:  # pragma: no cover - uvicorn factory entry point
    return create_app()


__all__ = ["FRONTEND_DIR", "create_app", "get_app"]
