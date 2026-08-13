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
    AssessmentRepository,
    BacktestRepository,
    Database,
    DecisionRepository,
    FillRepository,
    LogRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
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

    async def shutdown(self) -> None:
        if self.runtime is not None and self.runtime.is_running:
            await self.runtime.stop()
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
        # would either rewind time or resume where the last run ended.
        engine = RuntimeEngine(
            self.settings,
            config,
            on_event=self.broadcast,
            persist=self._persist,
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
        if self.runtime is None:
            return []
        stream = self.runtime._streams.get(symbol)
        if stream is None:
            return []
        return [
            {
                "time": candle.open_time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in list(stream.buffer)[-limit:]
        ]

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

    def settings_view(self) -> dict[str, Any]:
        """Configuration, with every secret withheld.

        Risk limits are included but marked read-only: they are enforced by an immutable
        object, and the API has no route that changes them. That is by design — §48.
        """
        return {
            "environment": self.settings.env.value,
            "mode": self.settings.mode.value,
            "simulated_only": True,
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

        components = {
            "database": "online" if database_ok else "offline",
            "market_data": "online" if runtime and runtime.is_running else "unknown",
            "paper_execution": "online" if runtime else "unknown",
            "risk_engine": (
                "degraded"
                if runtime and runtime.risk.state.is_halted
                else ("online" if runtime else "unknown")
            ),
            "llm": llm_state,
            "backtest_engine": "online",
            "event_stream": "online" if self._subscribers else "unknown",
            "news": "online" if runtime and runtime.config.news_enabled else "unknown",
        }
        degraded = [k for k, v in components.items() if v in {"offline", "degraded"}]
        return {
            "status": "degraded" if degraded else "ok",
            "components": components,
            "degraded": degraded,
            "uptime_seconds": (datetime.now(UTC) - self.started_at).total_seconds(),
            "version": "0.1.0",
            "simulated_only": True,
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
