"""Application state — the one object the API routes talk to.

Holds the database, the current runtime (at most one), and the set of SSE subscribers.
Every route reads or mutates this and nothing else, which keeps the routing layer free of
logic and makes the interesting behaviour testable without HTTP.

Two things it deliberately does *not* do:

* It does not queue an unbounded amount of data for a slow browser. Each subscriber has a
  bounded queue and a subscriber that cannot keep up loses events rather than growing the
  server's memory until it dies.
* It does not let a persistence failure stop trading. Writes are fire-and-forget from the
  runtime's point of view, logged on failure. A dashboard missing a row is a nuisance; a
  trading loop blocked on a database is a fault.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tia.core.config import Settings
from tia.core.logging import get_logger
from tia.persistence import (
    ActivationRepository,
    AssessmentRepository,
    BacktestRepository,
    Database,
    DecisionRepository,
    EdgeStateRepository,
    FillRepository,
    IncidentRepository,
    LogRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
    ReconciliationRepository,
    RunRepository,
)
from tia.runtime.engine import RuntimeConfig, RuntimeEngine, RuntimeState

_log = get_logger("api.state")

#: Per-subscriber buffer. Large enough for a browser that blinks, small enough that a
#: subscriber which has gone away cannot consume meaningful memory.
SUBSCRIBER_QUEUE_SIZE = 512


class AppState:
    """Everything the API needs, in one place."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = Database(settings.database_url)
        self.runtime: RuntimeEngine | None = None
        #: The live session, if one was armed and started. At most one, and its state
        #: machine — not this reference's existence — is what the API reports.
        self.live_runtime: Any | None = None
        self.started_at = datetime.now(UTC)

        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dropped_events = 0
        self._request_errors = 0
        self._recent_backtests: deque[dict[str, Any]] = deque(maxlen=25)

    # ------------------------------------------------------------------ lifecycle

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self.database.ensure_schema()
        await self._maybe_resume_paper_realtime()

    async def shutdown(self) -> None:
        if self.runtime is not None and self.runtime.is_running:
            await self.runtime.stop()
        if self.live_runtime is not None and self.live_runtime.is_running:
            await self.live_runtime.stop(reason="application shutdown")
        await self.database.close()

    # ------------------------------------------------------------------ streaming

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def broadcast(self, event: dict[str, Any]) -> None:
        """Fan out to every subscriber, dropping rather than blocking.

        Called from the runtime's loop, so it must never await and must never raise: a
        browser that stopped reading cannot be allowed to stall the trading loop.
        """
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._dropped_events += 1
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()  # drop the oldest and keep the newest
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    # ------------------------------------------------------------------ run control

    async def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.runtime is not None and self.runtime.is_running:
            raise ValueError("a run is already active; stop it before starting another")

        config = RuntimeConfig(
            scenario=payload.get("scenario", "trend_up"),
            symbols=tuple(payload.get("symbols") or ["BTC-USD"]),
            initial_capital=float(payload.get("initial_capital", 100_000.0)),
            seed=int(payload.get("seed", 20260812)),
            bar_interval_seconds=float(payload.get("bar_interval_seconds", 0.35)),
            enabled_strategies=tuple(
                payload.get("strategies")
                or ["trend_following", "mean_reversion", "breakout"]
            ),
            llm_enabled=bool(payload.get("llm_enabled", True)),
            news_enabled=bool(payload.get("news_enabled", True)),
        )

        # A fresh engine per run: the simulated clock only moves forward, so reusing one
        # would either rewind time or resume where the last run ended. The edge evidence
        # is *not* fresh — it is reloaded from every previous run, because a restart that
        # forgot its closed trades would reset the paper track record the activation gate
        # requires, and would let the same lesson be paid for twice.
        engine = RuntimeEngine(
            self.settings,
            config,
            on_event=self.broadcast,
            persist=self._persist,
            prior_outcomes=await self._load_prior_outcomes(),
        )
        self.runtime = engine

        async with self.database.session() as session:
            await RunRepository(session).create(
                run_id=engine.run_id,
                mode="paper",
                scenario=config.scenario,
                started_at=datetime.now(UTC),
                initial_capital=config.initial_capital,
                seed=config.seed,
                symbols=config.symbols,
            )

        await engine.start()
        return engine.snapshot()

    def _dispatch_alert(self, incident: dict[str, Any]) -> None:
        """Push an incident to the configured webhook. Fire-and-forget, never raises.

        The webhook URL comes from configuration and the payload carries no secret —
        it is the same incident row the database keeps. Email/Telegram/Discord are all
        webhook consumers in practice; this is the architecture seam they plug into.
        """
        url = getattr(self.settings.observability, "alert_webhook_url", "")
        if not url:
            return

        async def _post() -> None:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        url,
                        json={
                            "source": "trader-ia",
                            "kind": incident.get("kind"),
                            "reason": incident.get("reason"),
                            "actor": incident.get("actor"),
                            "run_id": incident.get("run_id"),
                            "at": str(incident.get("at")),
                        },
                    )
            except Exception as exc:
                _log.warning("alert_dispatch_failed", error=str(exc)[:200])

        with contextlib.suppress(Exception):
            asyncio.ensure_future(_post())  # noqa: RUF006 - fire and forget by design
        self.broadcast({"type": "alert", "payload": incident})

    async def _load_prior_outcomes(self):  # type: ignore[no-untyped-def]
        """Rebuild the edge estimator's input from every persisted round trip.

        Failure here degrades to an empty list **with a loud log**, never to a crash: a
        corrupted evidence store should stop live activation (the gate's edge check will
        fail on the missing evidence), not stop paper trading — paper is how the evidence
        gets rebuilt.
        """
        from tia.domain.enums import Direction, MarketRegime
        from tia.economics.expected_value import Outcome

        try:
            async with self.database.session() as session:
                rows = await EdgeStateRepository(session).load_all()
            return [
                Outcome(
                    regime=MarketRegime(row.regime),
                    direction=Direction(row.direction),
                    confidence=row.confidence,
                    net_return_bps=row.net_bps,
                )
                for row in rows
            ]
        except Exception as exc:
            _log.warning("edge_state_load_failed", error=str(exc)[:300])
            return []

    async def _load_prior_reviews(self) -> list[dict[str, Any]]:
        """Rebuild the retrospective's input from the persisted trade record.

        The same rows the estimator learns from, but kept whole — the retrospective needs
        the expectation and the fees each trade carried, which the lossy ``Outcome`` drops.
        Degrades to an empty list on any failure, never a crash: a session that cannot read
        its past lessons still trades, it just starts its guardrails from a clean slate.
        """
        try:
            async with self.database.session() as session:
                rows = await EdgeStateRepository(session).load_all()
            return [
                {
                    "regime": row.regime,
                    "direction": row.direction,
                    "confidence": row.confidence,
                    "expected_net_bps": row.expected_net_bps,
                    "net_bps": row.net_bps,
                    "fees_bps": row.fees_bps,
                    "closed_at": row.closed_at,
                    "signal_id": row.signal_id,
                    "symbol": row.symbol,
                }
                for row in rows
            ]
        except Exception as exc:
            _log.warning("edge_review_load_failed", error=str(exc)[:300])
            return []

    async def stop_run(self) -> dict[str, Any]:
        if self.runtime is None:
            return {"state": "stopped", "detail": "no run was active"}
        await self.runtime.stop()
        async with self.database.session() as session:
            await RunRepository(session).stop(self.runtime.run_id, datetime.now(UTC))
        return self.runtime.snapshot()

    def pause_run(self) -> dict[str, Any]:
        self._require_runtime().pause()
        return self.runtime_snapshot()

    def resume_run(self) -> dict[str, Any]:
        self._require_runtime().resume()
        return self.runtime_snapshot()

    def stop_new_trades(self) -> dict[str, Any]:
        self._require_runtime().stop_new_trades()
        return self.runtime_snapshot()

    def kill_switch(self, reason: str) -> dict[str, Any]:
        self._require_runtime().kill_switch(reason)
        return self.runtime_snapshot()

    def release_kill_switch(self, approved_by: str) -> dict[str, Any]:
        self._require_runtime().release_kill_switch(approved_by)
        return self.runtime_snapshot()

    async def reset_account(self, initial_capital: float, *, by: str) -> dict[str, Any]:
        """Destroy the current run's record and forget it.

        Deletes rather than archives, because the alternative — leaving orphaned runs in
        the database — makes "what is my P&L?" ambiguous, and an ambiguous P&L is worse
        than a deleted one in a simulation whose data is disposable by design.
        """
        if self.runtime is not None:
            run_id = self.runtime.run_id
            if self.runtime.is_running:
                await self.runtime.stop()
            async with self.database.session() as session:
                await RunRepository(session).delete(run_id)
            self.runtime = None

        _log.warning("paper_account_reset", by=by, initial_capital=initial_capital)
        self.broadcast(
            {
                "type": "runtime.reset",
                "data": {"by": by, "initial_capital": initial_capital},
            }
        )
        return {
            "state": "stopped",
            "initial_capital": initial_capital,
            "detail": "simulated account reset; start a run to begin again",
        }

    def _require_runtime(self) -> RuntimeEngine:
        if self.runtime is None:
            raise ValueError("no run is active")
        return self.runtime

    # ------------------------------------------------------------------ persistence

    async def _persist(self, kind: str, payload: Any) -> None:
        """Write one runtime artefact. Failures are logged, never raised."""
        try:
            async with self.database.session() as session:
                if kind == "decision":
                    await DecisionRepository(session).record(payload)
                elif kind == "order":
                    await OrderRepository(session).upsert(payload["run_id"], payload["order"])
                elif kind == "fill":
                    await FillRepository(session).append(payload["run_id"], payload["fill"])
                elif kind == "assessment":
                    await AssessmentRepository(session).record(payload)
                elif kind == "news":
                    await NewsRepository(session).record(payload)
                elif kind == "log":
                    await LogRepository(session).append(payload)
                elif kind == "edge_outcome":
                    await EdgeStateRepository(session).append(payload)
                elif kind == "reconciliation":
                    await ReconciliationRepository(session).record(payload)
                elif kind == "incident":
                    await IncidentRepository(session).record(payload)
                    self._dispatch_alert(payload)
                elif kind == "latency":
                    from tia.persistence import LatencyRepository

                    await LatencyRepository(session).append(payload)
                elif kind == "equity" and self.runtime is not None:
                    await PortfolioRepository(session).append_equity(
                        self.runtime.run_id, payload
                    )
                    await PortfolioRepository(session).sync_positions(
                        self.runtime.run_id,
                        self.runtime.execution.portfolio,
                        payload["at"],
                    )
        except Exception as exc:
            _log.warning("persist_failed", kind=kind, error=str(exc)[:300])

    # ------------------------------------------------------------------ views

    def runtime_snapshot(self) -> dict[str, Any]:
        if self.runtime is None:
            return {
                "state": RuntimeState.STOPPED.value,
                "mode": "paper",
                "simulated": True,
                "run_id": None,
                "capital": {
                    "starting": 0.0,
                    "equity": 0.0,
                    "cash": 0.0,
                    "invested": 0.0,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0,
                    "total_pnl": 0.0,
                    "return_pct": 0.0,
                    "max_drawdown_pct": 0.0,
                },
                "counters": {},
                "detail": "no run active",
            }
        return self.runtime.snapshot()

    def portfolio(self) -> dict[str, Any]:
        snapshot = self.runtime_snapshot()
        curve = (
            [
                {
                    "at": p["at"].isoformat() if hasattr(p["at"], "isoformat") else p["at"],
                    "equity": p["equity"],
                    "drawdown_pct": p["drawdown_pct"],
                }
                for p in list(self.runtime.equity_curve)[-600:]
            ]
            if self.runtime
            else []
        )
        return {**snapshot, "equity_curve": curve, "positions": self.positions()}

    def positions(self) -> list[dict[str, Any]]:
        if self.runtime is None:
            return []
        portfolio = self.runtime.execution.portfolio
        out = []
        for symbol, position in portfolio.positions.items():
            if position.is_flat:
                continue
            market = self.runtime.market_state.get(symbol, {})
            out.append(
                {
                    "symbol": symbol,
                    "quantity": position.quantity,
                    "direction": "long" if position.quantity > 0 else "short",
                    "average_price": position.average_price,
                    "last_price": position.last_price or market.get("price", 0.0),
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                    "fees_paid": position.fees_paid,
                    "notional": abs(position.quantity) * (position.last_price or 0.0),
                    "opened_at": (
                        position.opened_at.isoformat() if position.opened_at else None
                    ),
                }
            )
        return out

    def orders(self, limit: int) -> list[dict[str, Any]]:
        return list(self.runtime.recent_orders)[:limit] if self.runtime else []

    def fills(self, limit: int) -> list[dict[str, Any]]:
        return list(self.runtime.recent_fills)[:limit] if self.runtime else []

    def decisions(self, limit: int, actionable_only: bool) -> list[dict[str, Any]]:
        if self.runtime is None:
            return []
        rows = list(self.runtime.recent_decisions)
        if actionable_only:
            rows = [r for r in rows if r.get("direction") in {"long", "short"}]
        return rows[:limit]

    def decision(self, decision_id: str) -> dict[str, Any] | None:
        if self.runtime is None:
            return None
        return next(
            (r for r in self.runtime.recent_decisions if r.get("decision_id") == decision_id),
            None,
        )

    def assessments(self, limit: int) -> list[dict[str, Any]]:
        return list(self.runtime.recent_assessments)[:limit] if self.runtime else []

    def news(self, limit: int) -> list[dict[str, Any]]:
        return list(self.runtime.recent_news)[:limit] if self.runtime else []

    def logs(self, limit: int, level: str | None, channel: str | None) -> list[dict[str, Any]]:
        if self.runtime is None:
            return []
        rows = list(self.runtime.recent_logs)
        if level:
            rows = [r for r in rows if r.get("level") == level.upper()]
        if channel:
            rows = [r for r in rows if r.get("channel") == channel]
        return rows[:limit]

    def markets(self) -> list[dict[str, Any]]:
        # A running paper-live session is the real thing: show ITS real Binance data,
        # not the synthetic demo runtime that may also be running. The operator asked to
        # see the real BTC price here, and this is where it comes from.
        live = self.live_runtime
        if live is not None and live.is_running:
            row = live.market_state()
            if row is not None:
                return [row]
        if self.runtime is None:
            return []
        out = []
        for symbol, state in self.runtime.market_state.items():
            stream = self.runtime._streams.get(symbol)
            regime = "unknown"
            if stream is not None and stream.buffer:
                regime = self.runtime._regimes.current_regime(symbol).value
            out.append({**state, "regime": regime})
        return out

    def candles(self, symbol: str, limit: int) -> list[dict[str, Any]]:
        def shape(candle: Any) -> dict[str, Any]:
            return {
                "time": candle.open_time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }

        # Real venue candles from the paper-live session take precedence over the demo.
        live = self.live_runtime
        if live is not None and live.is_running:
            real = live.real_candles(limit)
            if real:
                return [shape(c) for c in real]
        if self.runtime is None:
            return []
        stream = self.runtime._streams.get(symbol)
        if stream is None:
            return []
        return [shape(c) for c in list(stream.buffer)[-limit:]]

    async def market_history(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[dict[str, Any]]:
        """Historical candles straight from Binance public klines (e.g. a year of daily
        bars). Independent of any running session — it opens a short-lived read-only
        client, fetches, and closes. Never touches credentials; public endpoints only.
        """
        from tia.core.clock import SystemClock
        from tia.data.providers.binance_public import BinancePublicProvider

        provider = BinancePublicProvider(
            base_url=self.settings.live.public_data_url, clock=SystemClock()
        )
        try:
            candles = await provider.get_candles(symbol, timeframe, limit=limit)
        finally:
            with contextlib.suppress(Exception):
                await provider.close()
        return [
            {
                "time": c.open_time.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

    async def order_book(self, symbol: str, limit: int) -> dict[str, Any]:
        """Live order book (bids/asks) from Binance public depth. Keyless, read-only."""
        from tia.core.clock import SystemClock
        from tia.data.providers.binance_public import BinancePublicProvider

        provider = BinancePublicProvider(
            base_url=self.settings.live.public_data_url, clock=SystemClock()
        )
        try:
            return await provider.order_book(symbol, limit=limit)
        finally:
            with contextlib.suppress(Exception):
                await provider.close()

    def risk(self) -> dict[str, Any]:
        snapshot = self.runtime_snapshot()
        risk = snapshot.get("risk", {})
        counters = snapshot.get("counters", {})
        blocked: dict[str, int] = {}
        if self.runtime is not None:
            for row in self.runtime.recent_decisions:
                for check in row.get("risk_checks", []):
                    if not check.get("passed"):
                        blocked[check["name"]] = blocked.get(check["name"], 0) + 1
        return {
            **risk,
            "blocked_by_check": blocked,
            "rejected_total": counters.get("risk_rejected", 0),
            "approved_total": counters.get("approved", 0),
            "reconciliations": counters.get("reconciliations", 0),
            "reconciliation_breaks": counters.get("reconciliation_breaks", 0),
        }

    def strategies(self) -> list[dict[str, Any]]:
        from tia.strategy.library import STRATEGY_REGISTRY

        enabled = set(self.runtime.config.enabled_strategies) if self.runtime else set()
        by_strategy: dict[str, dict[str, Any]] = {}
        if self.runtime is not None:
            for row in self.runtime.recent_decisions:
                key = row.get("signal_id", "")
                del key
        out = []
        for name, factory in STRATEGY_REGISTRY.items():
            instance = factory()
            out.append(
                {
                    "id": name,
                    "version": instance.version,
                    "enabled": name in enabled,
                    "applicable_regimes": [
                        r.value for r in getattr(instance, "regimes", ()) or ()
                    ],
                    "description": (instance.__doc__ or "").strip().split("\n")[0],
                    **by_strategy.get(name, {}),
                }
            )
        return out

    # ------------------------------------------------------------------ economics

    def economics(self) -> dict[str, Any]:
        """The trade-or-not machinery: costs, expected value, risk budget, evidence."""
        if self.runtime is None:
            return {
                "available": False,
                "reason": "no run is active; start one to see how signals are priced",
            }
        return {"available": True, **self.runtime.economics_snapshot()}

    def learning_report(self) -> dict[str, Any]:
        """What the system has learned from its own closed trades.

        Prefers the 24/7 paper-live session, because that is the one whose guardrails
        actually tighten risk; falls back to the demo run, which reads the same lessons but
        only to show them. Returns a refusal, never a crash, when nothing is running.
        """
        session = self.live_runtime
        if session is not None and session.is_running:
            return {"available": True, **session.learning_report()}
        if self.runtime is not None:
            return {"available": True, **self.runtime.learning_report()}
        return {
            "available": False,
            "reason": (
                "no session is running. The system learns from closed trades — start the "
                "24/7 paper session (or a demo run) and lessons appear here as trades close."
            ),
        }

    def analytics(self) -> dict[str, Any]:
        """Ruin probability and safe sizing, computed from this run's closed trades.

        Returns a refusal rather than a number when there are too few trades. A ruin
        probability derived from four round trips is a precise-looking figure in front of
        someone deciding how much to risk, which is worse than no figure at all.
        """
        from tia.risk.ruin import max_safe_risk_fraction, monte_carlo_ruin

        if self.runtime is None:
            return {"available": False, "reason": "no run is active"}

        trades = list(self.runtime.closed_trades)
        # Per-trade returns as fractions of the equity at risk. bps -> fraction.
        returns = [row["net_bps"] / 10_000.0 for row in trades]

        if len(returns) < 2:
            return {
                "available": False,
                "reason": (
                    f"{len(returns)} closed round trips. A ruin estimate needs at least "
                    "two, and is not worth much below thirty. Let the paper run continue."
                ),
                "closed_trades": len(returns),
            }

        estimate = monte_carlo_ruin(returns, horizon_trades=250, paths=5_000)
        safe = max_safe_risk_fraction(returns, horizon_trades=250)

        return {
            "available": True,
            "closed_trades": len(returns),
            "ruin": estimate.as_dict(),
            "explanation": estimate.explain(),
            "max_safe_risk_fraction": None if safe is None else round(safe[0] * 100.0, 4),
            "max_safe_risk_note": (
                "Even the smallest tested bet size ruins too often — this distribution "
                "should not be traded."
                if safe is None
                else "The largest per-trade risk whose simulated ruin probability stays "
                "under 1%, searched over a fixed ladder rather than optimised, because the "
                "input distribution does not support finer precision."
            ),
            "sample_warning": (
                "Fewer than 30 closed trades. Treat every number here as an illustration "
                "of the method, not as a measurement."
                if len(returns) < 30
                else ""
            ),
            "profile": self.runtime.economics_snapshot()["profile"],
        }

    def capital(self) -> dict[str, Any]:
        """The capital panel: what was contributed, what the strategy did with it.

        Deposits and withdrawals are reported separately from trading P&L and are never
        counted as return — see :mod:`tia.portfolio.capital` for why that direction of
        error is the one that matters.
        """
        snapshot = self.runtime_snapshot()
        capital = snapshot.get("capital", {})
        starting = capital.get("starting", 0.0) or 0.0
        realized = capital.get("realized_pnl", 0.0)
        unrealized = capital.get("unrealized_pnl", 0.0)

        return {
            "simulated": True,
            "currency": self.settings.base_currency,
            "contributed": starting,
            "deposits": starting,
            "withdrawals": 0.0,
            "net_contributed": starting,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "fees_paid": capital.get("fees_paid", 0.0),
            "equity": capital.get("equity", starting),
            "cash": capital.get("cash", starting),
            "invested": capital.get("invested", 0.0),
            "trading_pnl": realized + unrealized,
            "return_pct": (
                (realized + unrealized) / starting * 100.0 if starting > 0 else 0.0
            ),
            "max_drawdown_pct": capital.get("max_drawdown_pct", 0.0),
            "peak_equity": capital.get("peak_equity", starting),
            "live": {
                "enabled": self.settings.live.enabled,
                "max_live_capital": self.settings.live.max_live_capital,
                "allocated": 0.0,
                "note": (
                    "No real capital is allocated. Money would stay at the venue in every "
                    "case: this platform has no wallet, takes no custody, and its API key "
                    "must not be able to withdraw."
                ),
            },
            "explanation": (
                "Return is measured against contributed capital, not against the account "
                "balance. A deposit raises the balance and the denominator together and is "
                "never counted as profit."
            ),
        }

    # ------------------------------------------------------------------ live gate

    async def _gate_inputs(self) -> dict[str, Any]:
        """The async-derived facts the probes need, gathered in one place."""
        from tia.persistence.models import SCHEMA_VERSION, SchemaInfo

        database_ok = await self.database.ping()
        schema_version_ok: bool | None = None
        edge_persisted: int | None = None
        track_record: dict[str, Any] | None = None
        if database_ok:
            try:
                from sqlalchemy import select

                async with self.database.session() as session:
                    info = (await session.execute(select(SchemaInfo))).scalars().first()
                    schema_version_ok = info is not None and info.version == SCHEMA_VERSION
                    repo = EdgeStateRepository(session)
                    edge_persisted = await repo.count()
                    track_record = await repo.track_record()
            except Exception as exc:
                _log.warning("gate_inputs_failed", error=str(exc)[:200])
        return {
            "database_ok": database_ok,
            "schema_version_ok": schema_version_ok,
            "edge_persisted": edge_persisted,
            "track_record": track_record,
        }

    async def live_gate(self) -> dict[str, Any]:
        """Run every activation check and report. **Never arms anything.**"""
        from tia.api.gate_probes import build_probes, validation_facts
        from tia.core.clock import SystemClock
        from tia.live.gate import CONFIRMATION_PHRASE, LiveActivationGate

        gate = LiveActivationGate(
            SystemClock(),
            environment=self.settings.env.value,
            ttl_seconds=self.settings.live.activation_ttl_seconds,
        )
        probes = build_probes(self, **await self._gate_inputs())
        report = gate.evaluate(probes)

        return {
            **report.as_dict(),
            "live_enabled_in_config": self.settings.live.enabled,
            "max_live_capital": self.settings.live.max_live_capital,
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "ttl_seconds": gate.ttl_seconds,
            "venue_validation": validation_facts(),
            "live_runtime": (
                self.live_runtime.snapshot() if self.live_runtime is not None else None
            ),
            "custody_note": (
                "Arming lets this system place and cancel spot orders on your behalf. It "
                "never lets it move funds: there is no withdrawal or transfer code path, "
                "and the API key must not have the permission either."
            ),
        }

    async def arm_live(self, *, operator: str, confirmation: str) -> dict[str, Any]:
        """Arm, then actually start the live runtime — and report only what happened.

        Every attempt is persisted, pass or fail, with the report that decided it. On a
        passed gate the runtime is constructed and started; LIVE is reported active only
        if the state machine reached RUNNING. A minted token whose runtime failed to
        start is recorded as exactly that and discarded.
        """
        from tia.api.gate_probes import build_probes
        from tia.core.clock import SystemClock
        from tia.core.errors import LiveActivationError
        from tia.core.ids import new_ulid
        from tia.live.gate import LiveActivationGate, configuration_fingerprint

        if not self.settings.live.enabled:
            raise PermissionError(
                "the live path is disabled in configuration. Enable it deliberately with "
                "TIA_LIVE__ENABLED=true after every activation check passes."
            )
        if self.live_runtime is not None and self.live_runtime.is_running:
            raise LiveActivationError(
                "a live session is already active; stop it before arming another"
            )

        clock = SystemClock()
        gate = LiveActivationGate(
            clock,
            environment=self.settings.env.value,
            ttl_seconds=self.settings.live.activation_ttl_seconds,
        )
        probes = build_probes(self, **await self._gate_inputs())
        fingerprint = configuration_fingerprint(self.settings.risk, self.settings.live)
        attempt_id = f"arm_{new_ulid(clock)}"

        try:
            token = gate.arm(
                probes,
                operator=operator,
                confirmation=confirmation,
                max_live_capital=self.settings.live.max_live_capital,
                fingerprint=fingerprint,
            )
        except LiveActivationError as exc:
            report = gate.last_report
            await self._record_activation(
                attempt_id=attempt_id,
                operator=operator,
                passed=False,
                report=report.as_dict() if report else {},
                failed_checks=(
                    [c.name.value for c in report.failures] if report else ["unknown"]
                ),
                fingerprint=fingerprint,
                token_fingerprint="",
                runtime_started=False,
                runtime_state="",
                detail=str(exc)[:1000],
            )
            raise

        # The gate passed. Now the runtime has to actually start — and if it does not,
        # the honest answer is "armed but NOT live", recorded as such.
        runtime_started = False
        runtime_state = ""
        detail = ""
        try:
            runtime = await self._build_live_runtime(token)
            await runtime.start()
            self.live_runtime = runtime
            runtime_started = runtime.state.value == "running"
            runtime_state = runtime.state.value
            async with self.database.session() as session:
                await RunRepository(session).create(
                    run_id=runtime.run_id,
                    mode="live",
                    scenario="live",
                    started_at=datetime.now(UTC),
                    initial_capital=self.settings.live.max_live_capital,
                    seed=0,
                    symbols=(self.settings.live.symbol,),
                )
        except Exception as exc:
            detail = f"gate passed but the runtime did not start: {exc}"[:1000]
            runtime_state = "error"
        finally:
            await self._record_activation(
                attempt_id=attempt_id,
                operator=operator,
                passed=True,
                report=token.report.as_dict(),
                failed_checks=[],
                fingerprint=fingerprint,
                token_fingerprint=_hash_token(token),
                runtime_started=runtime_started,
                runtime_state=runtime_state,
                detail=detail,
            )

        if not runtime_started:
            raise LiveActivationError(
                detail or "the live runtime did not reach RUNNING; LIVE is not active"
            )
        return {
            "armed": True,
            "live": True,
            "runtime": self.live_runtime.snapshot(),
            "activation": token.as_dict(),
        }

    async def _build_live_runtime(self, token: Any) -> Any:
        """Construct the live runtime with the real adapters.

        REQUIRES VALIDATION end to end: nothing here has ever reached a Binance host from
        this environment. The construction is still real — credentials from the process
        environment, the signed execution adapter, the public data client, the venue's
        own time endpoint for the skew monitor.
        """
        from tia.core.clock import SystemClock
        from tia.data.providers.binance_live import BinanceExecutionProvider
        from tia.data.providers.binance_public import BinancePublicProvider
        from tia.data.providers.binance_signing import signer_from_live_config
        from tia.runtime.live import LiveRuntime

        live = self.settings.live
        clock = SystemClock()
        market = BinancePublicProvider(base_url=live.base_url, clock=clock)
        try:
            signer = signer_from_live_config(live, clock)
        except ValueError as exc:
            raise PermissionError(str(exc)) from exc
        execution = BinanceExecutionProvider(
            signer=signer,
            clock=clock,
            activation=None if live.use_testnet else token,
            base_url=live.base_url,
            simulated=live.use_testnet,
        )
        return LiveRuntime(
            self.settings,
            activation=token,
            market_data=market,
            execution=execution,
            clock=clock,
            venue_time_ms=market.server_time_ms,
            persist=self._persist,
            on_event=self.broadcast,
            prior_outcomes=await self._load_prior_outcomes(),
            prior_reviews=await self._load_prior_reviews(),
        )

    async def _record_activation(self, **values: Any) -> None:
        try:
            async with self.database.session() as session:
                await ActivationRepository(session).record(
                    {
                        "attempt_id": values["attempt_id"],
                        "attempted_at": datetime.now(UTC),
                        "operator": values["operator"],
                        "environment": self.settings.env.value,
                        "passed": values["passed"],
                        "failed_checks": values["failed_checks"],
                        "report": values["report"],
                        "configuration_fingerprint": values["fingerprint"],
                        "token_fingerprint": values["token_fingerprint"],
                        "max_live_capital": self.settings.live.max_live_capital,
                        "runtime_started": values["runtime_started"],
                        "runtime_state": values["runtime_state"],
                        "detail": values["detail"],
                    }
                )
        except Exception as exc:
            _log.warning("activation_record_failed", error=str(exc)[:300])

    async def start_paper_realtime(self, *, actor: str) -> dict[str, Any]:
        """Start a 24/7 paper-realtime session: real market data, simulated fills.

        No activation token — nothing here can spend real money, and the provider layer
        guarantees it independently. This is the session the 7-day paper track record
        runs on; its closed round trips persist as source="paper" evidence.
        """
        from tia.core.clock import SystemClock
        from tia.core.errors import LiveActivationError
        from tia.core.rng import RngRegistry
        from tia.data.providers.binance_public import BinancePublicProvider
        from tia.domain.instruments import DEFAULT_UNIVERSE
        from tia.execution.paper import PaperExecutionProvider
        from tia.runtime.live import LiveRuntime

        if self.live_runtime is not None and self.live_runtime.is_running:
            raise LiveActivationError(
                "a realtime session is already active; stop it before starting another"
            )

        clock = SystemClock()
        # Mainnet public data on purpose, whatever use_testnet says: paper's execution
        # is simulated, and a track record needs real spreads, not testnet's thin market.
        market = BinancePublicProvider(
            base_url=self.settings.live.public_data_url, clock=clock
        )
        execution = PaperExecutionProvider(
            self.settings.execution,
            DEFAULT_UNIVERSE,
            clock,
            RngRegistry(self.settings.seed),
            initial_capital=min(
                self.settings.initial_capital,
                self.settings.live.max_live_capital or self.settings.initial_capital,
            ),
        )
        runtime = LiveRuntime(
            self.settings,
            activation=None,
            market_data=market,
            execution=execution,
            clock=clock,
            venue_time_ms=market.server_time_ms,
            persist=self._persist,
            on_event=self.broadcast,
            prior_outcomes=await self._load_prior_outcomes(),
            prior_reviews=await self._load_prior_reviews(),
            poll_interval_seconds=10.0,
        )
        await runtime.start()
        self.live_runtime = runtime
        async with self.database.session() as session:
            await RunRepository(session).create(
                run_id=runtime.run_id,
                mode="paper-live",
                scenario="realtime",
                started_at=datetime.now(UTC),
                initial_capital=self.settings.initial_capital,
                seed=self.settings.seed,
                symbols=(self.settings.live.symbol,),
            )
        _log.info("paper_realtime_started", run_id=runtime.run_id, actor=actor)
        return runtime.snapshot()

    async def stop_realtime_session(self, *, reason: str) -> dict[str, Any]:
        """Stop the live/paper-realtime session AND stamp its run row.

        The stamp is what makes operator intent survive a restart: startup resumes only
        runs with no ``stopped_at``, so a session stopped through this method stays
        stopped, while one interrupted by a crash or redeploy comes back on its own.
        """
        live = self.live_runtime
        if live is None:
            return {"active": False, "state": "disarmed"}
        await live.stop(reason=reason)
        with contextlib.suppress(Exception):  # the stop itself must not fail on a stamp
            async with self.database.session() as session:
                await RunRepository(session).stop(live.run_id, datetime.now(UTC))
        return live.snapshot()

    async def _maybe_resume_paper_realtime(self) -> None:
        """Resume a 24/7 paper session that a restart interrupted — and only that.

        Three rules, in tension and resolved deliberately:

        * A run row with ``stopped_at`` NULL means the process died mid-session — every
          intentional stop goes through :meth:`stop_realtime_session`, which stamps it.
        * Operator-level halts outlive the process: a run that saw a kill switch,
          emergency flatten or safe-mode incident is NOT resumed. Sticky means sticky.
        * Only ``paper-live`` runs resume. A live session re-arms through the gate and a
          human, never through a reboot.

        The resumed session is a *new* run over the same evidence store — closed trades,
        the edge estimator and the paper track record all reload from the database, so a
        restart costs continuity of process, not continuity of evidence. Failure to
        resume (say, the data host is unreachable at boot) is logged and alerted, never
        fatal: the API must come up so the operator can see what happened.
        """
        from sqlalchemy import text

        try:
            async with self.database.session() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT run_id FROM runs WHERE mode = 'paper-live' "
                            "AND stopped_at IS NULL ORDER BY started_at DESC LIMIT 1"
                        )
                    )
                ).first()
                if row is None:
                    return
                interrupted = str(row[0])
                halts = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM incidents WHERE run_id = :run AND "
                            "kind IN ('kill_switch', 'emergency_flatten', 'safe_mode')"
                        ),
                        {"run": interrupted},
                    )
                ).scalar()
                # Either way this run is over; the question is only whether a new one
                # starts unattended.
                await RunRepository(session).stop(interrupted, datetime.now(UTC))
        except Exception as exc:
            _log.warning("paper_realtime_resume_check_failed", error=str(exc)[:300])
            return

        if halts:
            _log.warning(
                "paper_realtime_not_resumed",
                run_id=interrupted,
                reason="an operator-level halt was engaged; restart it deliberately",
            )
            return

        try:
            await self.start_paper_realtime(actor="startup-recovery")
            _log.info("paper_realtime_resumed", interrupted_run=interrupted)
        except Exception as exc:
            _log.warning(
                "paper_realtime_resume_failed", run_id=interrupted, error=str(exc)[:300]
            )
            self._dispatch_alert(
                {
                    "kind": "paper_resume_failed",
                    "reason": str(exc)[:300],
                    "actor": "startup-recovery",
                    "run_id": interrupted,
                    "at": datetime.now(UTC).isoformat(),
                }
            )

    async def change_risk_profile(
        self, *, profile: str, actor: str, confirmed: bool
    ) -> dict[str, Any]:
        """Change the risk profile — audited, confirmed, and never mid-session.

        The change applies to the *next* run, not the current one: a session's budget
        engine is constructed once at start, and swapping its parameters mid-flight would
        be exactly the runtime limit mutation the whole design forbids. A live session
        must be paused or stopped first, which is the PAUSE + CONFIRM + REVALIDATE path —
        the revalidation happening naturally because arming again re-runs the gate against
        the new configuration fingerprint.
        """
        from tia.risk.budget import RiskProfileName

        if profile not in {p.value for p in RiskProfileName}:
            raise ValueError(f"unknown profile {profile!r}")
        if not confirmed:
            raise ValueError("a risk profile change must be explicitly confirmed")
        if self.live_runtime is not None and self.live_runtime.is_running:
            raise ValueError(
                "a live session is active; pause or stop it before changing the risk "
                "profile. The change would apply to the next session either way."
            )

        previous = self.settings.live.risk_profile
        self.settings = self.settings.model_copy(
            update={"live": self.settings.live.model_copy(update={"risk_profile": profile})}
        )
        try:
            from tia.core.ids import deterministic_id

            async with self.database.session() as session:
                await IncidentRepository(session).record(
                    {
                        "incident_id": deterministic_id(
                            "inc", "profile", actor, datetime.now(UTC)
                        ),
                        "at": datetime.now(UTC),
                        "kind": "risk_profile_change",
                        "actor": actor,
                        "reason": f"{previous} -> {profile}",
                        "run_id": "",
                        "detail": {"from": previous, "to": profile},
                    }
                )
        except Exception as exc:
            _log.warning("profile_change_audit_failed", error=str(exc)[:200])
        return {
            "profile": profile,
            "previous": previous,
            "effective": "next run — an active session keeps the parameters it started with",
            "changed_by": actor,
        }

    async def profile_change_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        async with self.database.session() as session:
            rows = await IncidentRepository(session).recent(
                limit=limit, kind="risk_profile_change"
            )
        return [
            {
                "at": row.at.isoformat(),
                "actor": row.actor,
                "change": row.reason,
                "detail": row.detail,
            }
            for row in rows
        ]

    async def activation_history(self, *, limit: int = 50) -> list[dict[str, Any]]:
        async with self.database.session() as session:
            rows = await ActivationRepository(session).history(limit=limit)
        return [
            {
                "attempt_id": row.attempt_id,
                "attempted_at": row.attempted_at.isoformat(),
                "operator": row.operator,
                "environment": row.environment,
                "passed": row.passed,
                "failed_checks": row.failed_checks,
                "configuration_fingerprint": row.configuration_fingerprint,
                "runtime_started": row.runtime_started,
                "runtime_state": row.runtime_state,
                "detail": row.detail,
            }
            for row in rows
        ]

    def settings_view(self) -> dict[str, Any]:
        """Configuration, with every secret withheld.

        Risk limits are included but marked read-only: they are enforced by an immutable
        object, and the API has no route that changes them. That is by design — §48.
        """
        return {
            "environment": self.settings.env.value,
            "mode": self.settings.mode.value,
            "simulated_only": self.settings.is_simulation_only,
            "live": {
                "enabled": self.settings.live.enabled,
                "venue": self.settings.live.venue,
                "use_testnet": self.settings.live.use_testnet,
                "max_live_capital": self.settings.live.max_live_capital,
                "risk_profile": self.settings.live.risk_profile,
                "ev_threshold_bps": self.settings.live.ev_threshold_bps,
                # Whether a key is configured, never the key. The frontend needs to know
                # if it should tell the user to set one; it must never learn what it is.
                "credentials_configured": self.settings.live.has_credentials,
            },
            "database": self.database.url,
            "llm": {
                "provider": self.settings.llm.provider,
                "model": self.settings.llm.model,
                "enabled": self.settings.llm.enabled,
                "api_key_configured": self.settings.anthropic_api_key is not None,
                "max_calls_per_day": self.settings.llm.max_calls_per_day,
                "max_cost_usd_per_day": self.settings.llm.max_cost_usd_per_day,
            },
            "market_data": {
                "provider": self.settings.market_data.provider,
                "symbols": list(self.settings.market_data.symbols),
                "timeframe": self.settings.market_data.timeframe,
            },
            "execution": self.settings.execution.model_dump(mode="json"),
            "risk_limits": {
                "values": self.settings.risk.model_dump(mode="json"),
                "editable_from_ui": False,
                "reason": (
                    "Risk limits are immutable at runtime and have no API route that "
                    "changes them. Altering them is a code change that goes through "
                    "review and backtesting."
                ),
            },
        }

    # ------------------------------------------------------------------ health

    async def health(self) -> dict[str, Any]:
        database_ok = await self.database.ping()
        runtime = self.runtime
        llm_state = "unknown"
        if runtime is not None:
            breaker = runtime.context_service.governor.snapshot().breaker.value
            llm_state = {
                "closed": "online",
                "half_open": "degraded",
                "open": "offline",
            }.get(breaker, "unknown")

        # A running paper-live session is the active engine; prefer its state over the
        # demo run's for the components the operator watches on the banner.
        live_active = self.live_runtime is not None and self.live_runtime.is_running
        if live_active:
            risk_engine_state = "degraded" if self.live_runtime.risk_is_halted else "online"
            market_data_state = "online"
        else:
            risk_engine_state = (
                "degraded"
                if runtime and runtime.risk.state.is_halted
                else ("online" if runtime else "unknown")
            )
            market_data_state = "online" if runtime and runtime.is_running else "unknown"

        components = {
            "database": "online" if database_ok else "offline",
            "market_data": market_data_state,
            "paper_execution": "online" if (runtime or live_active) else "unknown",
            "risk_engine": risk_engine_state,
            "llm": llm_state,
            "backtest_engine": "online",
            "event_stream": "online" if self._subscribers else "unknown",
            "news": "online" if runtime and runtime.config.news_enabled else "unknown",
        }
        live = self.live_runtime
        live_view: dict[str, Any] | None = None
        simulated_only = True
        if live is not None:
            snapshot = live.snapshot()
            heartbeat_age = snapshot.get("heartbeat_age_seconds")
            # "The HTTP server answers" is not "the trading engine is alive": the engine
            # proves life by moving its own heartbeat, and a stalled loop reports as
            # degraded here even while this endpoint keeps returning 200.
            components["trading_engine"] = (
                "degraded"
                if heartbeat_age is not None and heartbeat_age > 120
                else snapshot.get("state", "unknown")
            )
            components["market_data_feed"] = (
                "degraded"
                if (snapshot.get("market_data_age_seconds") or 0) > live.market_data_ttl_seconds
                else "online"
            )
            simulated_only = bool(snapshot.get("simulated", True))
            live_view = {
                "mode": snapshot.get("mode"),
                "state": snapshot.get("state"),
                "heartbeat_age_seconds": heartbeat_age,
                "market_data_age_seconds": snapshot.get("market_data_age_seconds"),
            }
        degraded = [
            k
            for k, v in components.items()
            if v in {"offline", "degraded", "safe_mode", "error"}
        ]
        return {
            "status": "degraded" if degraded else "ok",
            "live_runtime": live_view,
            "components": components,
            "degraded": degraded,
            "uptime_seconds": (datetime.now(UTC) - self.started_at).total_seconds(),
            "version": "0.1.0",
            "simulated_only": simulated_only,
        }

    async def system_status(self) -> dict[str, Any]:
        health = await self.health()
        runtime = self.runtime
        return {
            **health,
            "subscribers": len(self._subscribers),
            "dropped_events": self._dropped_events,
            "run": self.runtime_snapshot(),
            "scenario": (
                {
                    "id": runtime.scenario.id.value,
                    "title": runtime.scenario.title,
                    "demonstrates": runtime.scenario.demonstrates,
                }
                if runtime
                else None
            ),
        }

    def prometheus_metrics(self) -> str:
        """A minimal exposition. Hand-rolled rather than pulling in a client library for
        eight gauges, which would add a dependency to produce the same eight lines."""
        snapshot = self.runtime_snapshot()
        counters = snapshot.get("counters", {})
        capital = snapshot.get("capital", {})
        lines = [
            "# HELP tia_up 1 when the API is serving",
            "# TYPE tia_up gauge",
            "tia_up 1",
            "# HELP tia_sse_subscribers Active event-stream subscribers",
            "# TYPE tia_sse_subscribers gauge",
            f"tia_sse_subscribers {len(self._subscribers)}",
            "# HELP tia_events_dropped_total Events dropped for slow subscribers",
            "# TYPE tia_events_dropped_total counter",
            f"tia_events_dropped_total {self._dropped_events}",
        ]
        for name, value in counters.items():
            lines.append(f"# TYPE tia_runtime_{name} counter")
            lines.append(f"tia_runtime_{name} {value}")
        for name in ("equity", "realized_pnl", "unrealized_pnl", "max_drawdown_pct"):
            if name in capital:
                lines.append(f"# TYPE tia_portfolio_{name} gauge")
                lines.append(f"tia_portfolio_{name} {capital[name]}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ backtests

    async def event_trace(self, correlation_id: str) -> list[dict[str, Any]]:
        """Reconstruct one decision's causal chain from stored events."""
        from tia.persistence.repositories import EventRepository

        async with self.database.session() as session:
            rows = await EventRepository(session).by_correlation(correlation_id)
            return [
                {
                    "event_id": row.event_id,
                    "type": row.event_type,
                    "sequence": row.sequence,
                    "occurred_at": row.occurred_at.isoformat(),
                    "payload": row.payload,
                }
                for row in rows
            ]

    async def list_backtests(self) -> list[dict[str, Any]]:
        async with self.database.session() as session:
            rows = await BacktestRepository(session).list_recent()
            return [
                {
                    "run_id": row.run_id,
                    "created_at": row.created_at.isoformat(),
                    "dataset": row.dataset,
                    "symbols": row.symbols,
                    "timeframe": row.timeframe,
                    "bars": row.bars,
                    "verdict": row.verdict,
                    "total_return_pct": row.total_return_pct,
                    "max_drawdown_pct": row.max_drawdown_pct,
                    "sharpe": row.sharpe,
                    "trades": row.trades,
                    "baselines": row.baselines,
                    "equity_curve": row.equity_curve,
                    "evidence_statement": row.evidence_statement,
                    "warnings": row.warnings,
                }
                for row in rows
            ]

    async def run_backtest(
        self, *, symbol: str, timeframe: str, bars: int, seed: int
    ) -> dict[str, Any]:
        """Run a backtest against the committed fixtures and store the result.

        Executed in a worker thread: the engine is CPU-bound and synchronous, and running
        it on the event loop would freeze the SSE stream for every connected browser.
        """
        from tia.backtest import BacktestConfig, BacktestEngine, evaluate_experiment
        from tia.data.providers.csv_replay import CsvReplayProvider
        from tia.domain.instruments import DEFAULT_UNIVERSE

        fixtures = Path(self.settings.market_data.fixtures_dir)
        provider = CsvReplayProvider(fixtures)
        candles = await provider.get_candles(symbol, timeframe, limit=bars)
        if len(candles) < 200:
            raise ValueError(
                f"only {len(candles)} bars available for {symbol} {timeframe}; "
                "run scripts/generate_fixtures.py"
            )

        def _run() -> Any:
            engine = BacktestEngine(
                BacktestConfig(
                    dataset=f"fixtures:{symbol}:{timeframe}", timeframe=timeframe, seed=seed
                ),
                DEFAULT_UNIVERSE,
            )
            result = engine.run(candles)
            report = evaluate_experiment(
                result, candles, at=datetime.now(UTC), costs=engine.config.execution
            )
            return (result, report)

        result, report = await asyncio.to_thread(_run)

        stored = {
            "run_id": result.conditions.run_id,
            "created_at": datetime.now(UTC),
            "dataset": result.conditions.dataset,
            "symbols": list(result.conditions.symbols),
            "timeframe": result.conditions.timeframe,
            "bars": result.conditions.bars,
            "seed": result.conditions.seed,
            "verdict": report.verdict.value,
            "total_return_pct": result.metrics.total_return_pct,
            "max_drawdown_pct": result.metrics.max_drawdown_pct,
            "sharpe": result.metrics.sharpe,
            "trades": len(result.trades),
            "equity_curve": [round(v, 4) for v in result.equity_curve[::5]],
            "baselines": [
                {
                    "name": b.name,
                    "description": b.description,
                    "total_return_pct": b.metrics.total_return_pct,
                    "max_drawdown_pct": b.metrics.max_drawdown_pct,
                    "sharpe": b.metrics.sharpe,
                    "trades": b.trades,
                }
                for b in report.baselines
            ],
            "evidence_statement": report.evidence_statement(),
            "warnings": list(result.warnings),
            "conditions": result.conditions.model_dump(mode="json"),
        }
        async with self.database.session() as session:
            await BacktestRepository(session).save(stored)

        stored["created_at"] = stored["created_at"].isoformat()
        self.broadcast({"type": "backtest.completed", "data": {"run_id": stored["run_id"]}})
        return stored


__all__ = ["SUBSCRIBER_QUEUE_SIZE", "AppState"]


def _hash_token(token: Any) -> str:
    """A one-way fingerprint of an activation token, for the audit row.

    The token itself is a capability and is never stored; what the audit needs is only
    "was the token used later the one minted here?", which a digest answers.
    """
    import hashlib

    payload = f"{token.issued_at.isoformat()}|{token.expires_at.isoformat()}|{token.issued_by}"
    return hashlib.blake2s(payload.encode("utf-8"), digest_size=16).hexdigest()
