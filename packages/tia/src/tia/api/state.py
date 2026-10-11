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
import json
import os
import signal
import sys
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tia.core.config import Settings
from tia.core.logging import get_logger
from tia.learning.antipatterns import AntiPatternMonitor
from tia.learning.mentor import MentorEngine
from tia.persistence import (
    AccountJournalRepository,
    ActivationRepository,
    AssessmentRepository,
    BacktestRepository,
    Database,
    DecisionRepository,
    EdgeStateRepository,
    EventRepository,
    FillRepository,
    IncidentRepository,
    LogRepository,
    MarketMakerRepository,
    NewsRepository,
    OrderRepository,
    PortfolioRepository,
    ReconciliationRepository,
    RiskStateRepository,
    RunRepository,
)
from tia.runtime.engine import RuntimeConfig, RuntimeEngine, RuntimeState

_log = get_logger("api.state")

#: Per-subscriber buffer. Large enough for a browser that blinks, small enough that a
#: subscriber which has gone away cannot consume meaningful memory.
SUBSCRIBER_QUEUE_SIZE = 512

#: The trainer's PID lock and progress file — the contract shared with
#: ``scripts/train_sims.py``, which owns writing them. Relative to the process CWD
#: (``/app`` in the container, the repo root locally), same as the runtime data dir.
#: How often the running 24/7 session checks the evidence store for trades it has not
#: seen. A minute is far below the pace at which a training batch produces them and far
#: above the cost of a row count, which is all a quiet check does.
EVIDENCE_REFRESH_SECONDS = 60.0
#: How long a boot that found a fresh heartbeat on the interrupted run waits before
#: reading it again (Phase 1.3, G9): longer than the runtime's heartbeat interval, so a
#: live writer has stamped at least once more; a dead one has not.
LEASE_PROBE_SECONDS = 45.0

#: How long the money-record answer is reused. It reads every closed trade, and the
#: number moves on the timescale of trades closing, not of a browser polling.
MONEY_RECORD_CACHE_SECONDS = 30.0

TRAINING_LOCK = Path("data/train.lock")
TRAINING_STATUS = Path("data/training_status.json")


class AppState:
    """Everything the API needs, in one place."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = Database(settings.database_url)
        self.runtime: RuntimeEngine | None = None
        #: The live session, if one was armed and started. At most one, and its state
        #: machine — not this reference's existence — is what the API reports.
        self.live_runtime: Any | None = None
        #: Serialises every start and arm of a session: two concurrent requests cannot
        #: both pass the "already active" check and build two runtimes over one account.
        #: Process-local by nature — see docs/PHASE_1_2_REPAIR_REPORT.md for the limit.
        self._session_lock = asyncio.Lock()
        self.started_at = datetime.now(UTC)

        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._live_activity: deque[dict[str, Any]] = deque(maxlen=150)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dropped_events = 0
        #: Persistence accounting (Phase 1.4). Every write the engines schedule goes
        #: through :meth:`_persist`, which absorbs failures so the trading loop never
        #: stops for the store; absorbed is not hidden — the counts reach the health
        #: endpoint, the system status and the metrics, and a failure in the last ten
        #: minutes reports the ``persistence`` component degraded.
        self._persist_writes = 0
        self._persist_failures = 0
        self._persist_last_error: str | None = None
        self._persist_last_failed_at: datetime | None = None
        self._request_errors = 0
        self._recent_backtests: deque[dict[str, Any]] = deque(maxlen=25)
        #: The read-only Advisor and the behaviour auditor. The Advisor is built lazily and
        #: cached so its language-model budget (the governor) is shared across questions;
        #: the monitor is pure and stateless.
        self._advisor: Any | None = None
        self._antipatterns = AntiPatternMonitor()
        #: The Mentor: proposals regenerated from the record on every read; only the
        #: currently-validated set is applicable, and applies are remembered for the report.
        self._mentor = MentorEngine()
        self._mentor_validated: dict[str, Any] = {}
        self._mentor_applied: list[dict[str, Any]] = []
        #: Curated macro/crypto headlines. Built lazily; informs the UI and the Advisor,
        #: never the trading pipeline.
        self._intel: Any | None = None
        #: Cross-venue price-gap monitor. Built lazily, samples in the background once
        #: someone asks for it; reads public tickers and nothing else.
        self._arbitrage: Any | None = None
        #: Perpetual funding and basis monitor. Same discipline as the arbitrage monitor:
        #: public data, read-only, informs the operator and the Advisor.
        self._funding: Any | None = None
        #: Market-making market data (phase 2): depth, trades, local book, recorder.
        #: Started at boot only when settings.mm.enabled; quotes nothing.
        self._mm_market: Any | None = None
        self._mm_maker: Any | None = None  # phase 3: the paper market maker, when enabled
        self._mm_maker_error = ""
        #: Phase 4: the live market maker. Never built at boot; only by start_mm_live from
        #: an operator's explicit request. Tests inject an in-memory venue through the
        #: factory; production builds the Binance adapter inside _build_mm_live_provider.
        self._mm_live: Any | None = None
        self._mm_live_error = ""
        self._mm_live_provider_factory: Callable[..., Awaitable[Any]] | None = None
        self._mm_user_stream_factory: Callable[..., Awaitable[Any]] | None = None
        #: Keeps spawned-subprocess reaper tasks alive until they finish.
        self._background_tasks: set[asyncio.Task[Any]] = set()
        #: Evidence rows the running 24/7 session has already been given. Trades it
        #: closed itself are in here too — see :meth:`refresh_session_evidence`.
        self._absorbed_evidence_ids: set[str] = set()
        #: The newest ``ingested_at`` the session has been given; the refresher reads
        #: forward from here instead of re-reading the record.
        self._evidence_watermark: datetime | None = None
        self._evidence_task: asyncio.Task[Any] | None = None
        #: The boot's deferred lease probe (Phase 1.3, G9): when the interrupted run's
        #: heartbeat is fresh, the boot waits this long and reads it again before deciding
        #: whether another process is running it (heartbeat advanced) or it died hard
        #: (heartbeat unchanged). The API comes up meanwhile.
        self._lease_probe_task: asyncio.Task[Any] | None = None
        self._lease_probe_seconds: float = LEASE_PROBE_SECONDS
        #: (computed_at, payload) for :meth:`money_record` — it scans the whole trade
        #: record, and the dashboard polls it.
        self._money_cache: tuple[float, dict[str, Any]] | None = None

    # ------------------------------------------------------------------ lifecycle

    async def startup(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self.database.ensure_schema()
        await self._maybe_resume_paper_realtime()
        if self.settings.mm.enabled:
            with contextlib.suppress(Exception):
                self._start_mm_market_data()
        if self.settings.mm.adaptive_enabled:
            try:
                await self._start_market_maker()
            except Exception as exc:  # never assumed: without its inputs the maker does not run
                self._mm_maker_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                _log.error("mm_paper_not_started", error=self._mm_maker_error)

    async def shutdown(self) -> None:
        if self._evidence_task is not None:
            self._evidence_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._evidence_task
        if self.runtime is not None and self.runtime.is_running:
            await self.runtime.stop()
        if self._lease_probe_task is not None:
            self._lease_probe_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._lease_probe_task
        if self.live_runtime is not None and self.live_runtime.is_running:
            await self.live_runtime.stop(reason="application shutdown")
            # The row stays unstamped (a shutdown is not an operator stop: the next boot
            # resumes it) but its heartbeat is released, so that boot does not have to
            # wait out the lease to tell a redeploy from a second process (G9).
            with contextlib.suppress(Exception):
                async with self.database.session() as session:
                    await RunRepository(session).release_lease(self.live_runtime.run_id)
        if self._intel is not None:
            with contextlib.suppress(Exception):
                await self._intel.close()
        if self._arbitrage is not None:
            with contextlib.suppress(Exception):
                await self._arbitrage.close()
        if self._funding is not None:
            with contextlib.suppress(Exception):
                await self._funding.close()
        if self._mm_live is not None:
            with contextlib.suppress(Exception):
                await self._mm_live.close()  # cancels what rests, reconciles, closes the provider
        if self._mm_maker is not None:
            with contextlib.suppress(Exception):
                await self._mm_maker.close()
        if self._mm_market is not None:
            with contextlib.suppress(Exception):
                await self._mm_market.close()
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
        kind = str(event.get("type", ""))
        if kind.startswith("live.") or kind == "trade.closed":
            # The activity feed: what the session did, in order, for a page opened
            # after the fact. Bounded; the journal holds the durable record.
            self._live_activity.appendleft(
                {
                    "type": kind,
                    "at": datetime.now(UTC).isoformat(),
                    "data": event.get("data", event.get("payload", {})),
                }
            )
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
        """Start a scenario run under the session lock — see :meth:`_start_run_locked`.
        Two concurrent requests cannot both pass the "already active" check: the second
        waits and is refused (Phase 1.4; the paper-live path has had this since 1.2)."""
        async with self._session_lock:
            return await self._start_run_locked(payload)

    async def _start_run_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
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

        # The row first, the loop second, the reference last (Phase 1.4, the F8 contract
        # the sessions already follow): a row that cannot be written starts nothing and
        # installs nothing, and a start that fails stamps its row as over with the
        # failure in its notes. Before, the engine was installed as "the run" before its
        # row existed or its loop ran, so a failed start left the API reporting a run the
        # store did not know and a stop stamping a row that was never written.
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
        try:
            await engine.start()
        except Exception as exc:
            with contextlib.suppress(Exception):
                async with self.database.session() as session:
                    await RunRepository(session).stop(engine.run_id, datetime.now(UTC))
                    await RunRepository(session).annotate(
                        engine.run_id, f"start_failed: {str(exc)[:300]}"
                    )
            raise
        self.runtime = engine
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
                    fees_bps=row.fees_bps,
                    gross_return_bps=row.gross_bps,
                    market_data=getattr(row, "market_data", None),
                )
                for row in rows
            ]
        except Exception as exc:
            _log.warning("edge_state_load_failed", error=str(exc)[:300])
            return []

    @staticmethod
    def _as_outcome(row: Any) -> Any:
        """One persisted round trip, as the lossy thing the edge estimator consumes."""
        from tia.domain.enums import Direction, MarketRegime
        from tia.economics.expected_value import Outcome

        return Outcome(
            regime=MarketRegime(row.regime),
            direction=Direction(row.direction),
            confidence=row.confidence,
            net_return_bps=row.net_bps,
            fees_bps=row.fees_bps,
            gross_return_bps=row.gross_bps,
            market_data=getattr(row, "market_data", None),
        )

    @staticmethod
    def _as_review(row: Any) -> dict[str, Any]:
        """The same round trip kept whole, as the retrospective needs it."""
        return {
            "regime": row.regime,
            "direction": row.direction,
            "confidence": row.confidence,
            "expected_net_bps": row.expected_net_bps,
            "net_bps": row.net_bps,
            "fees_bps": row.fees_bps,
            "closed_at": row.closed_at,
            "signal_id": row.signal_id,
            "symbol": row.symbol,
            "entry_price": row.entry_price,
            "quantity": row.quantity,
            "exploratory": bool(getattr(row, "exploratory", False)),
            "strategy_id": getattr(row, "strategy_id", None),
            # Provenance (schema v7). Null on rows that predate it: under the scoreboard's
            # ``real_only`` policy such rows judge nobody; under ``legacy`` they count.
            "market_data": getattr(row, "market_data", None),
            "execution_mode": getattr(row, "execution_mode", None),
            "strategy_version": getattr(row, "strategy_version", None),
        }

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
                    "entry_price": row.entry_price,
                    "quantity": row.quantity,
                    "exploratory": bool(getattr(row, "exploratory", False)),
                }
                for row in rows
            ]
        except Exception as exc:
            _log.warning("edge_review_load_failed", error=str(exc)[:300])
            return []

    # ---------------------------------------------------------- evidence freshness

    async def _load_live_evidence(self) -> tuple[list[Any], list[dict[str, Any]]]:
        """The whole trade record, shaped for both learners, in a single read.

        Also records which rows the starting session has been given, so the refresher
        below can tell "new since this session started" from "already in its memory".
        """
        try:
            async with self.database.session() as session:
                rows = await EdgeStateRepository(session).load_all()
        except Exception as exc:
            _log.warning("live_evidence_load_failed", error=str(exc)[:300])
            return [], []
        self._absorbed_evidence_ids = {row.outcome_id for row in rows}
        stamps = [row.ingested_at for row in rows if getattr(row, "ingested_at", None)]
        self._evidence_watermark = max(stamps) if stamps else None
        return [self._as_outcome(row) for row in rows], [self._as_review(row) for row in rows]

    async def refresh_session_evidence(self) -> dict[str, Any]:
        """Fold evidence persisted since the session last looked into the running session.

        This is what makes a finished training batch show up in Learning without a
        restart. The read is an indexed range on ``ingested_at`` — the database's own
        write clock — from the last watermark, so the cost is proportional to what is
        new, not to the size of the record. Two exclusions keep the arithmetic honest:
        rows already given to the session (by id; the range is inclusive because two
        rows can share a timestamp) and rows the session produced itself (by run id —
        its own closed trades are already in memory, and re-feeding them would count
        each twice, inflating both the evidence and the paper track record).
        """
        session = self.live_runtime
        if session is None or not session.is_running:
            return {"absorbed": 0, "reason": "no 24/7 session is running"}
        try:
            async with self.database.session() as db:
                rows = await EdgeStateRepository(db).load_since(self._evidence_watermark)
        except Exception as exc:
            _log.warning("evidence_refresh_failed", error=str(exc)[:300])
            return {"absorbed": 0, "error": str(exc)[:200]}

        fresh = [
            row
            for row in rows
            if row.outcome_id not in self._absorbed_evidence_ids
            and row.run_id != session.run_id
        ]
        self._absorbed_evidence_ids.update(row.outcome_id for row in rows)
        stamps = [row.ingested_at for row in rows if getattr(row, "ingested_at", None)]
        if stamps:
            newest = max(stamps)
            if self._evidence_watermark is None or newest > self._evidence_watermark:
                self._evidence_watermark = newest
        if not fresh:
            return {"absorbed": 0, "scanned": len(rows)}

        result = session.absorb_evidence(
            outcomes=[self._as_outcome(row) for row in fresh],
            reviews=[self._as_review(row) for row in fresh],
        )
        return {"absorbed": len(fresh), "scanned": len(rows), **result}

    async def journal_setups(self, *, source: str | None = None) -> list[dict[str, Any]]:
        """Per-setup record — see EdgeStateRepository.setups."""
        try:
            async with self.database.session() as db:
                return await EdgeStateRepository(db).setups(source=source)
        except Exception as exc:
            _log.warning("journal_setups_failed", error=str(exc)[:300])
            return []

    async def journal_exits(self, *, source: str | None = None) -> list[dict[str, Any]]:
        """Per-exit-reason record — see EdgeStateRepository.exits."""
        try:
            async with self.database.session() as db:
                return await EdgeStateRepository(db).exits(source=source)
        except Exception as exc:
            _log.warning("journal_exits_failed", error=str(exc)[:300])
            return []

    async def journal(self, **filters: Any) -> dict[str, Any]:
        """The complete trade record with filters — see EdgeStateRepository.journal."""
        try:
            async with self.database.session() as db:
                return await EdgeStateRepository(db).journal(**filters)
        except Exception as exc:
            _log.warning("journal_failed", error=str(exc)[:300])
            return {
                "rows": [],
                "total": 0,
                "offset": 0,
                "limit": int(filters.get("limit", 50)),
                "summary": {"trades": 0, "wins": 0, "win_rate": 0.0, "pnl_usd": 0.0,
                            "mean_trade_usd": 0.0},
                "error": "the trade record could not be read",
            }

    async def money_record(self) -> dict[str, Any]:
        """"If this had been real money, where would we be?" — answered carefully.

        Two numbers, kept apart because pooling them would state something false:

        * **The 24/7 session** is one continuous account against the real market. Its
          equity is a genuine answer to the question, for the trades it has taken.
        * **The training simulations** come from thousands of *independent* runs. Their
          sum is "what these trades made", not the balance of an account that took them
          in order — nothing ever held that position sequence. It answers a different and
          still useful question: at these trade sizes, did the strategy make money?

        The starting balance is the configured simulated capital, so the headline reads
        as a balance rather than a delta. Every figure here is simulated money.
        """
        cached = self._money_cache
        now = datetime.now(UTC).timestamp()
        if cached is not None and now - cached[0] < MONEY_RECORD_CACHE_SECONDS:
            return cached[1]

        base = float(self.settings.initial_capital)
        try:
            async with self.database.session() as db:
                repository = EdgeStateRepository(db)
                by_source = await repository.dollar_record()
                sim_curve = await repository.dollar_curve(source="sim")
                live_curve = await repository.dollar_curve(source="live")
        except Exception as exc:
            _log.warning("money_record_failed", error=str(exc)[:300])
            return {"available": False, "reason": "the trade record could not be read"}

        session_base = float(self.settings.live.paper_capital)

        def shaped(key: str, base: float = base) -> dict[str, Any]:
            row = by_source.get(key) or {}
            trades = int(row.get("trades", 0))
            pnl = float(row.get("pnl_usd", 0.0))
            return {
                "starting_usd": round(base, 2),
                "trades": trades,
                "wins": int(row.get("wins", 0)),
                "win_rate": round(row.get("wins", 0) / trades, 4) if trades else 0.0,
                "pnl_usd": round(pnl, 2),
                "ending_usd": round(base + pnl, 2),
                "return_pct": round(pnl / base * 100.0, 4) if base else 0.0,
                "mean_trade_usd": round(pnl / trades, 2) if trades else 0.0,
                "typical_notional_usd": (
                    round(row.get("notional_sum_usd", 0.0) / trades, 2) if trades else 0.0
                ),
            }

        payload = {
            "available": True,
            "starting_usd": round(base, 2),
            "simulated": True,
            "session_starting_usd": round(session_base, 2),
            "session": {**shaped("live", session_base), "curve": live_curve},
            "training": {**shaped("sim"), "curve": sim_curve},
            "demo": shaped("paper"),
            "explanation": (
                "Simulated money throughout — no real account exists. The 24/7 session is "
                "one continuous account against the live market, so its balance is a real "
                "answer for the trades it took. The training total is the sum of what "
                "thousands of independent simulations made at their own trade sizes; it "
                "says whether the strategy makes money at that size, not what a single "
                "account holding them in sequence would be worth."
            ),
        }
        self._money_cache = (now, payload)
        return payload

    async def _evidence_refresh_loop(self) -> None:
        """Keep the running session's lessons current, without anyone asking.

        The 24/7 session used to read the evidence store once, at startup: a training
        batch that finished overnight was invisible until someone restarted the engine,
        which read as the Learning page being broken rather than merely behind.
        """
        while True:
            await asyncio.sleep(EVIDENCE_REFRESH_SECONDS)
            with contextlib.suppress(Exception):  # a refresh must never kill the loop
                result = await self.refresh_session_evidence()
                if result.get("absorbed"):
                    self.broadcast({"type": "live.evidence_absorbed", "data": result})

    def _start_evidence_refresh(self) -> None:
        """Idempotent: one refresher for the process, started with the first session."""
        if self._evidence_task is not None and not self._evidence_task.done():
            return
        self._evidence_task = asyncio.get_running_loop().create_task(
            self._evidence_refresh_loop()
        )

    async def stop_run(self) -> dict[str, Any]:
        """Stop the scenario run, under the session lock (Phase 1.5).

        One lock for start, stop and reset of a run: a stop that arrives while a start is
        still writing its row waits for it and then stops the engine it installed, instead
        of answering "no run was active" while that engine goes on. The lock is held for
        the engine's bounded stop (loop timeout plus persistence flush), never for an
        operation without a bound.
        """
        async with self._session_lock:
            return await self._stop_run_locked()

    async def _stop_run_locked(self) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is None:
            return {"state": "stopped", "detail": "no run was active"}
        await runtime.stop()
        async with self.database.session() as session:
            await RunRepository(session).stop(runtime.run_id, datetime.now(UTC))
        return runtime.snapshot()

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

        Under the session lock (Phase 1.5): a reset racing a start would otherwise see no
        run, delete nothing, and let the start install a run the operator believed reset.
        """
        async with self._session_lock:
            return await self._reset_account_locked(initial_capital, by=by)

    async def _reset_account_locked(self, initial_capital: float, *, by: str) -> dict[str, Any]:
        runtime = self.runtime
        if runtime is not None:
            run_id = runtime.run_id
            if runtime.is_running:
                await runtime.stop()
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
                elif kind == "mm_journal":
                    await MarketMakerRepository(session).append_journal(payload["run_id"], int(payload["seq"]), payload["row"])
                elif kind == "mm_fill":
                    await MarketMakerRepository(session).upsert_fill(payload["run_id"], payload["fill"])
                elif kind == "mm_markout":
                    await MarketMakerRepository(session).set_markout(str(payload["fill_id"]), payload["markout_bps"])
                elif kind == "mm_ledger":
                    await MarketMakerRepository(session).save_ledger(
                        payload["run_id"],
                        state=payload["state"],
                        config_id=payload["config_id"],
                        profile_id=payload["profile_id"],
                        latency_scenario=payload["latency_scenario"],
                        at=datetime.now(UTC),
                    )
                elif kind == "account_event":
                    await EventRepository(session).append(payload["run_id"], payload["envelope"])
                elif kind == "account_events":
                    # Several account events that belong together — a funding settlement
                    # and the plan that records it as settled — in one session, so they
                    # commit together or not at all (Phase 1.8).
                    repository = EventRepository(session)
                    for envelope in payload["envelopes"]:
                        await repository.append(payload["run_id"], envelope)
                elif kind == "run_stop":
                    # The runtime ended its own session (deadline): stamp the run row so
                    # the next boot does not resume it as crash-interrupted. A stamped run
                    # holds no lease (G9).
                    await RunRepository(session).stop(payload["run_id"], payload["stopped_at"])
                    await RunRepository(session).release_lease(payload["run_id"])
                elif kind == "run_heartbeat":
                    # The session is alive: another process reads this before it resumes
                    # or starts a session over the same account (Phase 1.3, G9).
                    await RunRepository(session).heartbeat(payload["run_id"], payload["at"])
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
            self._persist_writes += 1
        except Exception as exc:
            # Absorbed so the loop goes on; counted so it is not hidden (Phase 1.4). The
            # payload never reaches the log: it may carry an order or an account event.
            self._persist_failures += 1
            self._persist_last_error = f"{kind}: {type(exc).__name__}: {str(exc)[:200]}"
            self._persist_last_failed_at = datetime.now(UTC)
            _log.warning("persist_failed", kind=kind, error=str(exc)[:300])

    def persistence_status(self) -> dict[str, Any]:
        """What the store has absorbed: writes, failures, the last failure and when."""
        return {
            "writes": self._persist_writes,
            "failures": self._persist_failures,
            "last_error": self._persist_last_error,
            "last_failed_at": (
                self._persist_last_failed_at.isoformat() if self._persist_last_failed_at else None
            ),
            "degraded": self._persistence_recently_failed(),
        }

    def _persistence_recently_failed(self, *, window: timedelta = timedelta(minutes=10)) -> bool:
        at = self._persist_last_failed_at
        return at is not None and datetime.now(UTC) - at < window

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
        """The 24/7 session's orders first, then the demo run's. The page used to show
        only the demo, so a session that had been trading all night looked idle."""
        rows: list[dict[str, Any]] = []
        if self.live_runtime is not None:
            rows.extend(list(self.live_runtime.recent_orders))
        if self.runtime is not None:
            rows.extend(list(self.runtime.recent_orders))
        return rows[:limit]

    def fills(self, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if self.live_runtime is not None:
            rows.extend(list(self.live_runtime.recent_fills))
        if self.runtime is not None:
            rows.extend(list(self.runtime.recent_fills))
        return rows[:limit]

    def live_activity(self, limit: int = 60) -> list[dict[str, Any]]:
        """The session's recent actions, newest first, for the dashboard feed."""
        return list(self._live_activity)[:limit]

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

    # ------------------------------------------------------------------ advisor / audit

    def _get_advisor(self) -> Any:
        """Build the read-only Advisor once and cache it. Never raises — a missing key
        downgrades the provider to the deterministic mock, which the Advisor handles."""
        if self._advisor is None:
            from tia.core.clock import SystemClock
            from tia.llm.advisor import AdvisorService
            from tia.llm.governance import LLMGovernor
            from tia.llm.provider import build_provider

            key = (
                self.settings.anthropic_api_key.get_secret_value()
                if self.settings.anthropic_api_key
                else None
            )
            provider = build_provider(self.settings.llm, api_key=key)
            governor = LLMGovernor(self.settings.llm, SystemClock())
            self._advisor = AdvisorService(provider, governor, self.settings.llm)
        return self._advisor

    def _advisor_context(self) -> dict[str, Any]:
        """Assemble the grounded facts the Advisor may answer from. Read-only; each source
        is guarded so one missing panel cannot deny an answer built from the rest."""
        context: dict[str, Any] = {}
        for key, getter in (
            ("state", self.runtime_snapshot),
            ("positions", self.positions),
            ("decisions", lambda: self.decisions(8, actionable_only=False)),
            ("economics", self.economics),
            ("learning", self.learning_report),
            ("antipatterns", self.antipattern_report),
            ("mentor", self.mentor_report),
            ("intel", self.intel_snapshot),
            ("funding", self.funding_snapshot),
            ("live_session", self.live_context_snapshot),
        ):
            with contextlib.suppress(Exception):
                context[key] = getter()
        return context

    async def advisor_ask(self, question: str) -> dict[str, Any]:
        """Answer a free-form question about the running system, grounded in its state."""
        answer = await self._get_advisor().answer(question, self._advisor_context())
        return answer.as_dict()

    async def advisor_explain(self, decision_id: str) -> dict[str, Any]:
        """Explain one decision: why the system took or refused it, on what grounds."""
        focus = self.decision(decision_id)
        if focus is None:
            return {
                "question": f"explain decision {decision_id}",
                "answer": (
                    "There is no decision with that id in the current session. Open the AI "
                    "Decisions tab and pick one that is still in the journal."
                ),
                "grounded_on": [],
                "used_llm": False,
                "model": "",
                "note": "decision not found",
            }
        context = self._advisor_context()
        context["focus_decision"] = focus
        question = (
            f"Explain decision {decision_id} for {focus.get('symbol')}: why did the system "
            f"take or refuse this {focus.get('direction')} trade, and on what grounds?"
        )
        answer = await self._get_advisor().answer(question, context)
        return answer.as_dict()

    def _antipattern_snapshot(self) -> dict[str, Any] | None:
        """A read of recent behaviour for the audit, uniform across demo and live sessions.

        Recent trades come from the learning report (which already prefers the live
        session); the exposure and streak figures come from the demo runtime's snapshot.
        Returns ``None`` when nothing is running.
        """
        running = self.runtime is not None or (
            self.live_runtime is not None and self.live_runtime.is_running
        )
        if not running:
            return None
        learning = self.learning_report()
        lessons = learning.get("recent_lessons", []) if learning.get("available") else []
        recent_trades = [
            {
                "net_bps": lesson.get("realised_net_bps", 0.0),
                "gross_bps": lesson.get("realised_net_bps", 0.0) + lesson.get("fees_bps", 0.0),
                "fees_bps": lesson.get("fees_bps", 0.0),
                "direction": lesson.get("direction"),
                "symbol": lesson.get("symbol"),
                "closed_at": lesson.get("closed_at"),
            }
            for lesson in lessons
        ]
        snapshot = self.runtime_snapshot()
        risk = snapshot.get("risk", {}) or {}
        capital = snapshot.get("capital", {}) or {}
        limits = risk.get("limits", {}) or {}
        streak = getattr(self.live_runtime, "_consecutive_losses", None)
        if streak is None:
            streak = getattr(self.runtime, "_consecutive_losses", 0)
        return {
            "recent_trades": recent_trades,
            "trades_today": risk.get("trades_today", 0),
            "max_trades_per_day": limits.get("max_trades_per_day", 0),
            "consecutive_losses": streak or 0,
            "positions": [
                {
                    "symbol": p.get("symbol"),
                    "direction": p.get("direction"),
                    "notional": p.get("notional", 0.0),
                }
                for p in self.positions()
            ],
            "equity": capital.get("equity", 0.0),
            "new_trades_allowed": risk.get("new_trades_allowed", True),
            "risk_mode": risk.get("mode", ""),
        }

    def antipattern_report(self) -> dict[str, Any]:
        """Audit recent trading against the curated set of trading anti-patterns."""
        snapshot = self._antipattern_snapshot()
        if snapshot is None:
            return {
                "available": False,
                "reason": "no session is running; the behaviour audit needs recent trades.",
            }
        return {"available": True, **self._antipatterns.report(snapshot)}

    # ------------------------------------------------------------------ market intel

    def _get_intel(self) -> Any:
        if self._intel is None:
            from tia.core.clock import SystemClock
            from tia.data.intel import MarketIntelService

            self._intel = MarketIntelService(clock=SystemClock())
        return self._intel

    async def market_intel(self, *, force: bool = False) -> dict[str, Any]:
        """Curated macro/crypto headlines, freshly polled if the cache window has passed.

        Always answers: with every source unreachable the items list is empty and the
        per-source health rows say exactly which feed failed and how — the honest state,
        not an error page.
        """
        service = self._get_intel()
        await service.refresh(force=force)
        return {"available": True, **service.report()}

    def intel_snapshot(self) -> dict[str, Any]:
        """Already-fetched intel for the Advisor's grounding — no network from here.

        Synchronous on purpose: the Advisor context is assembled inline and must never
        block a question on five feed requests. It sees whatever the last poll brought.
        """
        if self._intel is None:
            return {"available": False, "items": []}
        return {"available": True, **self._intel.report()}

    # ------------------------------------------------------------------ arbitrage

    def _get_arbitrage(self) -> Any:
        if self._arbitrage is None:
            from tia.core.clock import SystemClock
            from tia.data.arbitrage import CrossVenueMonitor

            self._arbitrage = CrossVenueMonitor(clock=SystemClock())
        return self._arbitrage

    async def arbitrage_report(self, *, force: bool = False) -> dict[str, Any]:
        """The measured cross-venue gaps, with the sampler started on first request.

        The first call polls inline so the page opens with numbers; after that the
        background sampler keeps the record and a read is just a read. ``force`` polls now
        regardless. Always answers: with every venue unreachable the gap list is empty and
        the per-venue rows say which endpoint failed and how.
        """
        monitor = self._get_arbitrage()
        if force or monitor.report()["polls"] == 0:
            await monitor.poll()
        monitor.start()
        return {"available": True, **monitor.report()}

    # ------------------------------------------------------------------ market making

    def _start_mm_market_data(self) -> Any:
        """Phase 2 of the market maker: the book and the tape, nothing that quotes."""
        from pathlib import Path

        from tia.data.providers.binance_public import BinancePublicProvider
        from tia.mm.market_data import MarketDataService
        from tia.mm.order_book import snapshot_from_levels
        from tia.mm.recorder import TickRecorder
        from tia.mm.streams import MarketDataStream

        cfg = self.settings.mm
        rest = BinancePublicProvider(base_url=self.settings.live.public_data_url)

        async def fetch_snapshot():  # type: ignore[no-untyped-def]
            book = await rest.depth_snapshot(cfg.symbol, limit=cfg.depth_snapshot_limit)
            return snapshot_from_levels(
                book.last_update_id or 0,
                [(lvl.price, lvl.size) for lvl in book.bids],
                [(lvl.price, lvl.size) for lvl in book.asks],
            )

        recorder = (
            TickRecorder(
                Path(cfg.ticks_dir), cfg.symbol,
                retention_days=cfg.ticks_retention_days,
                max_total_bytes=int(cfg.ticks_max_gb * 1024**3),
            )
            if cfg.record_ticks
            else None
        )
        service = MarketDataService(
            cfg.symbol,
            stream=MarketDataStream(cfg.symbol, depth_speed=cfg.depth_speed),
            fetch_snapshot=fetch_snapshot,
            recorder=recorder,
            max_data_age_s=cfg.max_data_age_s,
            max_venue_age_s=cfg.max_venue_age_s,
            venue_clock_offset_ms=cfg.venue_clock_offset_ms,
        )
        service.start()
        self._mm_market = service
        _log.info("mm_market_data_started", symbol=cfg.symbol, record=cfg.record_ticks)
        return service

    # ------------------------------------------------------------------ market maker (paper)

    def _mm_maker_base(self) -> dict[str, Any]:
        cfg = self.settings.mm
        return {
            "enabled": cfg.adaptive_enabled,
            "market_data_enabled": cfg.enabled,
            "real_money": False,  # by construction; nothing in tia/mm reads the flag
            "execution": "simulated only — the paper maker holds no execution provider; live quoting is a separate service behind /api/mm/live",
            "latency": {"profile_path": cfg.latency_profile_path, "scenario": cfg.latency_scenario},
            "fees": {"status": cfg.maker_fee_status, "scenarios_bps": cfg.fee_scenarios()},
            "paper_capital": cfg.paper_capital,
        }

    def mm_maker_snapshot(self) -> dict[str, Any]:
        base = self._mm_maker_base()
        if self._mm_maker is None:
            reason = (
                "paper quoting is not enabled (TIA_MM__ADAPTIVE_ENABLED)"
                if not self.settings.mm.adaptive_enabled
                else f"paper quoting is enabled but the service did not start: {self._mm_maker_error or 'see the logs'}"
            )
            return {**base, "running": False, "phase3_status": "IMPLEMENTATION", "reason": reason}
        running = bool(getattr(self._mm_maker, "is_running", False))
        return {
            **base,
            "running": running,
            "phase3_status": "PAPER_RUNNING" if running else "IMPLEMENTATION",
            "evidence_status": "EVIDENCE_PENDING",
            **self._mm_maker.snapshot(),
        }

    def mm_maker_journal(self, *, limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
        if self._mm_maker is None:
            return []
        return list(self._mm_maker.journal(limit=limit, kind=kind))

    def mm_maker_metrics(self) -> dict[str, Any]:
        if self._mm_maker is None:
            return {"available": False, "reason": "paper quoting is not running", "edge": {"verdict": "NO EDGE DETECTED", "failed_rules": ["no paper run"]}}
        return {"available": True, **self._mm_maker.metrics()}

    async def _start_market_maker(self) -> Any:
        """Phase 3 live paper mode: the engine on the real feed, simulated orders only.

        Requires the market-data service (TIA_MM__ENABLED) and a latency profile
        measured on this host; either missing is an error, never a default.
        """
        from tia.mm.latency_model import LatencyProfile
        from tia.mm.service import MarketMakerService

        cfg = self.settings.mm
        if self._mm_market is None:
            raise RuntimeError("market data is not running (TIA_MM__ENABLED=false or it failed to start)")
        profile = LatencyProfile.load(cfg.latency_profile_path)
        config = self._mm_config()
        run_id = f"mm-paper-{cfg.symbol}"
        service = MarketMakerService(
            market=self._mm_market,
            config=config,
            profile=profile,
            scenario=cfg.latency_scenario,
            run_id=run_id,
            risk_state=self._session_risk_state,
            persist=self._persist,
            broadcast=self.broadcast,
        )
        try:
            async with self.database.session() as session:
                saved = await MarketMakerRepository(session).load_ledger(run_id)
            if saved is not None and saved.config_id == config.config_id:
                service.restore(dict(saved.state))
            elif saved is not None:
                _log.warning("mm_paper_ledger_not_restored", reason="configuration changed", saved=saved.config_id, current=config.config_id)
        except Exception as exc:  # a missing ledger is a fresh start; a broken one is logged
            _log.warning("mm_paper_ledger_load_failed", error=str(exc)[:160])
        service.start()
        self._mm_maker = service
        self._mm_maker_error = ""
        _log.info("mm_paper_running", run_id=run_id, scenario=cfg.latency_scenario, profile=profile.profile_id, restored=service.restored_from)
        return service

    def _mm_config(self) -> Any:
        """The maker's configuration from settings; the paper and the live maker share it."""
        from tia.mm.costs import MarketMakerCostConfig
        from tia.mm.engine import MarketMakerConfig

        cfg = self.settings.mm
        return MarketMakerConfig(
            symbol=cfg.symbol,
            starting_equity_usd=cfg.paper_capital,
            costs=MarketMakerCostConfig(
                maker_fee_bps=cfg.maker_fee_bps,
                maker_fee_status=cfg.maker_fee_status,
                maker_fee_verified_bps=cfg.maker_fee_verified_bps,
                maker_fee_adverse_bps=cfg.maker_fee_adverse_bps,
            ),
        )

    def _session_risk_state(self) -> Any | None:
        # Read-only: the session's RiskEngine state, never the engine itself.
        runtime = self.live_runtime
        engine = getattr(runtime, "_risk", None) if runtime is not None else None
        return getattr(engine, "state", None)

    # ------------------------------------------------------------------ market maker (live)

    def mm_live_status(self) -> dict[str, Any]:
        """The live market maker, as it is. Never started at boot; ``real_money`` is True
        only while a service runs over a live (non-simulated) provider, which requires an
        activation token the gate minted."""
        live = self.settings.live
        base = {
            "mode": "live",
            "market_data_enabled": self.settings.mm.enabled,
            "live_path_enabled": live.enabled,
            "use_testnet": live.use_testnet,
            "real_money_flag": "TIA_MM__REAL_MONEY is read by nothing; it cannot start or arm anything",
            "how_to_start": (
                "POST /api/mm/live/start as an operator with the confirmation phrase. On the real "
                "venue every activation check must pass first; on the testnet the provider is "
                "simulated by construction."
            ),
        }
        if self._mm_live is None:
            return {
                **base,
                "running": False,
                "real_money": False,
                "state": "not_started",
                "reason": self._mm_live_error or "the live market maker has not been started",
                "activation": None,
            }
        status = self._mm_live.status()
        return {**base, **status, "real_money": bool(status.get("is_live"))}

    async def start_mm_live(self, *, operator: str, confirmation: str) -> dict[str, Any]:
        """Start the live market maker from an explicit operator action.

        Requirements, in order: the live path enabled in configuration; the exact
        confirmation phrase; no live maker already running; market data running and
        usable; the latency profile measured on this host. On the **real venue** the
        activation gate then has to pass every check (the same gate, probes and phrase as
        the directional session), and the token it mints goes to the provider and to the
        maker's risk authorization; the attempt is recorded either way. On the **testnet**
        the provider is simulated by construction and no token exists. The venue's symbol
        filters are read, the quoting grid is checked against them, and the service
        reconciles the account before its first quote.
        """
        from tia.core.clock import SystemClock
        from tia.core.errors import LiveActivationError
        from tia.core.ids import new_ulid
        from tia.live.gate import CONFIRMATION_PHRASE, LiveActivationGate, configuration_fingerprint
        from tia.mm.authorization import EconomicsConfig
        from tia.mm.execution import SymbolFilters
        from tia.mm.latency_model import LatencyProfile
        from tia.mm.live_service import LiveMarketMakerService

        live = self.settings.live
        cfg = self.settings.mm
        if not live.enabled:
            raise PermissionError(
                "the live path is disabled in configuration (TIA_LIVE__ENABLED=false); the live "
                "market maker cannot start. Enabling it is a deliberate configuration change, "
                "and it still only permits the gate to be consulted."
            )
        if confirmation != CONFIRMATION_PHRASE:
            raise PermissionError("the confirmation phrase does not match; nothing was started")
        if self._mm_live is not None and self._mm_live.is_running:
            raise LiveActivationError("the live market maker is already running; stop it before starting another")
        if self._mm_market is None or not self._mm_market.is_running:
            raise RuntimeError("market data is not running (TIA_MM__ENABLED=false or it failed to start)")
        if not self._mm_market.usable:
            raise RuntimeError(f"market data is not usable: {self._mm_market.snapshot(levels=1)['not_usable_reason']}")
        profile = LatencyProfile.load(cfg.latency_profile_path)
        config = self._mm_config()
        clock = SystemClock()
        token: Any | None = None
        fingerprint: str | None = None
        attempt_id = ""
        if not live.use_testnet:
            from tia.api.gate_probes import build_probes

            gate = LiveActivationGate(clock, environment=self.settings.env.value, ttl_seconds=live.activation_ttl_seconds)
            probes = build_probes(self, **await self._gate_inputs())
            fingerprint = configuration_fingerprint(self.settings.risk, self.settings.live)
            attempt_id = f"arm_mm_{new_ulid(clock)}"
            try:
                token = gate.arm(
                    probes,
                    operator=operator,
                    confirmation=confirmation,
                    max_live_capital=live.max_live_capital,
                    fingerprint=fingerprint,
                )
            except LiveActivationError as exc:
                report = gate.last_report
                await self._record_activation(
                    attempt_id=attempt_id,
                    operator=operator,
                    passed=False,
                    report=report.as_dict() if report else {},
                    failed_checks=[c.name.value for c in report.failures] if report else ["unknown"],
                    fingerprint=fingerprint,
                    token_fingerprint="",
                    runtime_started=False,
                    runtime_state="mm-live",
                    detail=str(exc)[:1000],
                )
                raise
        venue_label = "binance-spot-testnet" if live.use_testnet else "binance-spot"
        provider = await self._build_mm_live_provider(token, clock)
        try:
            info = await provider.get_exchange_info(cfg.symbol)
            to_venue = getattr(provider, "to_venue_symbol", None)
            venue_symbol = to_venue(cfg.symbol) if to_venue is not None else cfg.symbol.replace("-USD", "USDT").replace("-", "")
            filters = SymbolFilters.from_exchange_info(info, symbol=cfg.symbol, venue_symbol=venue_symbol)
            service = LiveMarketMakerService(
                market=self._mm_market,
                config=config,
                profile=profile,
                scenario=cfg.latency_scenario,
                run_id=f"mm-{'testnet' if live.use_testnet else 'live'}-{cfg.symbol}",
                risk_state=self._session_risk_state,
                provider=provider,
                clock=clock,
                filters=filters,
                activation=token,
                fingerprint=fingerprint,
                capital_cap_usd=live.max_live_capital if live.max_live_capital > 0 else None,
                economics=EconomicsConfig(min_net_edge_bps=cfg.live_min_net_edge_bps),
                expiry_margin_s=cfg.live_activation_expiry_margin_s,
                reconcile_interval_s=cfg.live_reconcile_interval_s,
                trades_poll_interval_s=cfg.live_trades_poll_interval_s,
                open_sync_interval_s=cfg.live_open_orders_sync_interval_s,
                max_api_errors_per_minute=cfg.live_max_api_errors_per_minute,
                strict_cancel_replace=cfg.live_strict_cancel_replace,
                venue_label=venue_label,
                persist=self._persist,
                broadcast=self.broadcast,
            )
            stream = await self._build_mm_user_stream(provider, service, clock)
            if stream is not None:
                service.attach_user_stream(stream)
            report = await service.start_live()
        except Exception as exc:
            with contextlib.suppress(Exception):
                await provider.close()
            self._mm_live_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            if token is not None:
                await self._record_activation(
                    attempt_id=attempt_id, operator=operator, passed=True, report=token.report.as_dict(), failed_checks=[],
                    fingerprint=fingerprint, token_fingerprint=_hash_token(token), runtime_started=False, runtime_state="mm-live-error",
                    detail=f"gate passed but the live market maker did not start: {exc}"[:1000],
                )
            raise
        self._mm_live = service
        self._mm_live_error = ""
        if token is not None:
            await self._record_activation(
                attempt_id=attempt_id, operator=operator, passed=True, report=token.report.as_dict(), failed_checks=[],
                fingerprint=fingerprint, token_fingerprint=_hash_token(token), runtime_started=True, runtime_state=f"mm-live-{service.state_label}",
                detail=f"live market maker started; initial reconciliation {report.summary}",
            )
        _log.info("mm_live_started_by_operator", operator=operator, venue=venue_label, state=service.state_label, reconciliation=report.summary)
        return {"started": True, "operator": operator, "initial_reconciliation": report.as_dict(), **self.mm_live_status()}

    async def _build_mm_live_provider(self, token: Any | None, clock: Any) -> Any:
        """The execution provider for the live maker: the Binance adapter, over the testnet
        (simulated, no token) or the real venue (the gate's token). Tests inject a venue."""
        if self._mm_live_provider_factory is not None:
            return await self._mm_live_provider_factory(token, clock)
        from tia.data.providers.binance_live import BinanceExecutionProvider
        from tia.data.providers.binance_signing import signer_from_live_config

        live = self.settings.live
        try:
            signer = signer_from_live_config(live, clock)
        except ValueError as exc:
            raise PermissionError(str(exc)) from exc
        return BinanceExecutionProvider(
            signer=signer,
            clock=clock,
            activation=None if live.use_testnet else token,
            base_url=live.base_url,
            simulated=live.use_testnet,
        )

    async def _build_mm_user_stream(self, provider: Any, service: Any, clock: Any) -> Any | None:
        """The account stream (execution reports, balances) for the live maker: the
        venue's, when the provider can sign a stream subscription; a test's, through the
        factory; none otherwise (the maker then relies on the trade-history poll alone)."""
        if self._mm_user_stream_factory is not None:
            return await self._mm_user_stream_factory(provider, service, clock)
        if not hasattr(provider, "user_stream_subscribe_params"):
            return None
        from tia.data.providers.binance_user_stream import BinanceUserDataStream

        execution = service.execution
        return BinanceUserDataStream(
            provider,
            now_ms=clock.timestamp_ms,
            on_report=execution.absorb_execution_report,
            on_balances=execution.absorb_balances,
            on_status=execution.absorb_stream_status,
            base_url=self.settings.live.user_stream_url,
        )

    async def stop_mm_live(self, *, reason: str, actor: str) -> dict[str, Any]:
        if self._mm_live is None:
            return {**self.mm_live_status(), "stopped": False}
        status = await self._mm_live.stop(reason=reason, actor=actor)
        return {**self.mm_live_status(), "stopped": True, "final": status}

    async def kill_mm_live(self, *, reason: str, actor: str) -> dict[str, Any]:
        if self._mm_live is None or not self._mm_live.is_running:
            return {**self.mm_live_status(), "engaged": False}
        await self._mm_live.engage_kill_switch(reason=reason, actor=actor)
        return {**self.mm_live_status(), "engaged": True}

    async def reconcile_mm_live(self) -> dict[str, Any]:
        if self._mm_live is None or not self._mm_live.is_running:
            return {**self.mm_live_status(), "reconciled": False}
        report = await self._mm_live.reconcile()
        return {**self.mm_live_status(), "reconciled": True, "report": report.as_dict()}

    def mm_market_snapshot(self) -> dict[str, Any]:
        cfg = self.settings.mm
        base = {
            "enabled": cfg.enabled,
            "real_money": False,  # by construction; the flag is never read by execution
            "quoting": "disabled — phase 2 is market data only",
            "fees": {"status": cfg.maker_fee_status, "scenarios_bps": cfg.fee_scenarios()},
        }
        if self._mm_market is None:
            return {**base, "running": False, "reason": "market-making market data is not enabled (TIA_MM__ENABLED)"}
        return {**base, "running": self._mm_market.is_running, **self._mm_market.snapshot()}

    # ------------------------------------------------------------------ funding

    def _get_funding(self) -> Any:
        if self._funding is None:
            from tia.core.clock import SystemClock
            from tia.data.funding import FundingMonitor

            self._funding = FundingMonitor(
                clock=SystemClock(),
                max_age_seconds=float(self.settings.live.funding_max_age_seconds),
            )
        return self._funding

    async def funding_report(self, *, force: bool = False) -> dict[str, Any]:
        """The perpetual's funding and basis, with the sampler started on first request."""
        monitor = self._get_funding()
        if force or monitor.report()["polls"] == 0:
            await monitor.poll()
        monitor.start()
        return {"available": True, **monitor.report()}

    def funding_snapshot(self) -> dict[str, Any]:
        """Already-fetched funding for the Advisor's grounding — no network from here."""
        if self._funding is None:
            return {"available": False}
        report = self._funding.report()
        return {
            "available": report["latest"] is not None,
            "latest": report["latest"],
            "percentile": report["percentile"],
            "stance": report["stance"],
            "verdict": report["verdict"],
        }

    def live_context_snapshot(self) -> dict[str, Any]:
        """The 24/7 session's tide, sizing and strategy standings, for the Advisor."""
        if self.live_runtime is None:
            return {"available": False}
        snapshot = self.live_runtime.snapshot()
        return {
            "available": True,
            "state": snapshot.get("state"),
            "trend": snapshot.get("trend"),
            "sizing": snapshot.get("sizing"),
            "market": snapshot.get("market"),
            "strategies": snapshot.get("strategies"),
            "position": snapshot.get("position"),
        }

    # ------------------------------------------------------------------ training

    def _training_pid(self) -> int | None:
        """PID of a live trainer, or None. A stale lock (dead owner) counts as absent."""
        if not TRAINING_LOCK.exists():
            return None
        try:
            pid = int(TRAINING_LOCK.read_text().strip() or 0)
        except (ValueError, OSError):
            return None
        if pid <= 0:
            return None
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError):
            return None
        except PermissionError:
            return pid
        return pid

    def training_status(self) -> dict[str, Any]:
        """What the trainer last reported, plus whether its process is actually alive.

        The liveness check is the PID, not the file: a trainer that died mid-run leaves a
        status saying "running", and this reports that honestly as ``interrupted``.
        """
        status: dict[str, Any] = {}
        if TRAINING_STATUS.exists():
            with contextlib.suppress(Exception):
                status = json.loads(TRAINING_STATUS.read_text())
        running = self._training_pid() is not None
        if not running and status.get("state") == "running":
            status["state"] = "interrupted"
        status.setdefault("state", "idle")
        status["running"] = running
        # The trainer reports per-trade returns in basis points, which are honest but
        # unreadable; the typical trade size lets the dashboard translate them to dollars.
        session = self.live_runtime or self.runtime
        if session is not None:
            with contextlib.suppress(Exception):
                status["typical_notional_usd"] = round(session.typical_trade_notional_usd, 2)
        return status

    async def training_start(self, *, runs: int, actor: str) -> dict[str, Any]:
        """Launch the trainer as a detached subprocess. The script's own PID lock makes a
        double click (or a second operator) harmless — the second launch refuses itself."""
        if self._training_pid() is not None:
            raise ValueError("a training run is already active")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "scripts/train_sims.py",
            "--runs",
            str(runs),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Reap the child when it exits so it never lingers as a zombie.
        task = asyncio.get_running_loop().create_task(process.wait())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        _log.info("training_started", runs=runs, actor=actor, pid=process.pid)
        return {"started": True, "runs": runs, "pid": process.pid}

    async def training_stop(self, *, actor: str) -> dict[str, Any]:
        """SIGTERM the trainer; it unwinds, keeps every completed run's evidence, writes
        its final status and frees the lock. Nothing already persisted is lost."""
        pid = self._training_pid()
        if pid is None:
            raise ValueError("no training run is active")
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
        for _ in range(20):  # give it up to ~5s to unwind cleanly
            await asyncio.sleep(0.25)
            if self._training_pid() is None:
                break
        _log.info("training_stopped", actor=actor, pid=pid)
        return {"stopped": self._training_pid() is None, "pid": pid}

    def training_reload(self, *, actor: str) -> dict[str, Any]:
        """Load freshly trained evidence by restarting the engine process.

        The estimator, retrospective and Mentor read the evidence store at session
        construction, so a reload IS a restart. The process exits cleanly; the container
        supervisor (restart: unless-stopped) brings it back, and the 24/7 paper session
        auto-resumes — the exact crash-recovery path the restart drills exercise.
        """
        if self._training_pid() is not None:
            raise ValueError("a training run is active; stop it or let it finish first")
        _log.info("training_reload_restart", actor=actor)
        loop = asyncio.get_running_loop()
        loop.call_later(0.7, os._exit, 0)
        return {
            "restarting": True,
            "detail": (
                "the engine is restarting to load the new evidence; the 24/7 session "
                "resumes by itself. Give it ~30 seconds, then refresh."
            ),
        }

    # ------------------------------------------------------------------ mentor

    def _current_ev_threshold(self) -> float:
        """The bar trades must clear right now, read from whichever engine is enforcing."""
        session = self.live_runtime
        if session is not None and session.is_running:
            ev = getattr(session, "_ev", None)
            if ev is not None:
                return float(ev.threshold_bps)
        return float(self.settings.live.ev_threshold_bps)

    def mentor_report(self) -> dict[str, Any]:
        """The Mentor's current proposals, each with its replay verdict attached.

        Regenerated from the record on every call, so a proposal disappears on its own
        once the condition that raised it clears — there is nothing stale to dismiss.
        Validated proposals are cached by id for :meth:`mentor_apply`.
        """
        learning = self.learning_report()
        if not learning.get("available"):
            return {
                "available": False,
                "reason": (
                    "no session is running. The Mentor reads the closed-trade record; "
                    "start the 24/7 paper session (or a demo run) and it reviews as "
                    "trades close."
                ),
            }

        audit = self.antipattern_report()
        snapshot = self._antipattern_snapshot() or {}
        proposals = self._mentor.review(
            lessons=learning.get("recent_lessons", []),
            current_threshold_bps=self._current_ev_threshold(),
            consecutive_losses=int(snapshot.get("consecutive_losses", 0)),
            risk_profile=self.settings.live.risk_profile,
            audit_checks=audit.get("checks", []) if audit.get("available") else [],
        )
        self._mentor_validated = {
            p.proposal_id: p for p in proposals if p.validation.passed
        }
        live_acting = self.live_runtime is not None and self.live_runtime.is_running
        # A proposal whose effect is already in place must not offer an Apply button:
        # applying it would be a no-op, and a no-op behind a button reads as a bug.
        halted = live_acting and not self.live_runtime.state.accepts_new_orders
        already = {"halt_new_entries"} if halted else set()

        def _shaped(proposal: Any) -> dict[str, Any]:
            payload = proposal.as_dict()
            payload["in_effect"] = proposal.action["kind"] in already
            return payload

        return {
            "available": True,
            "proposals": [_shaped(p) for p in proposals],
            "validated": sum(1 for p in proposals if p.validation.passed),
            "rejected": sum(1 for p in proposals if not p.validation.passed),
            "applied": list(self._mentor_applied),
            "can_apply_now": live_acting,
            "reviewed_trades": len(learning.get("recent_lessons", [])),
            "explanation": (
                "The Mentor proposes only tighter risk — a higher expected-value bar, a "
                "halt, a smaller profile — and every proposal is validated by replaying "
                "the recorded trades under the proposed rule. A proposal whose replay "
                "shows no benefit is rejected and shown as rejected. Nothing is applied "
                "without an explicit operator action, and nothing here can loosen a limit."
            ),
        }

    async def mentor_apply(self, *, proposal_id: str, actor: str) -> dict[str, Any]:
        """Apply one *validated* proposal, as the named operator. Tighten-only by
        construction: every dispatch below goes to a method that itself refuses to loosen."""
        proposal = self._mentor_validated.get(proposal_id)
        if proposal is None:
            raise ValueError(
                f"no validated proposal {proposal_id!r}. Proposals are regenerated from "
                "the record on every read — refresh the Mentor panel and try again."
            )

        kind = proposal.action["kind"]
        session = self.live_runtime
        live_running = session is not None and session.is_running

        if kind == "raise_ev_threshold":
            if not live_running:
                raise ValueError(
                    "raising the expected-value bar acts on the running paper-live "
                    "session; start it first"
                )
            result = session.tighten_ev_threshold(
                float(proposal.action["to_bps"]), actor=actor
            )
        elif kind == "halt_new_entries":
            if live_running:
                acted = session.halt_new_orders(
                    reason=f"mentor: {proposal.rationale[:140]}", actor=actor
                )
                if not acted:
                    # Already halted. Reporting success here is what let the same button
                    # be clicked six times with nothing happening and no explanation.
                    raise ValueError(
                        "the 24/7 session is already halted, so this proposal is "
                        "already in effect. Lift the halt from Live Trading before "
                        "applying it again."
                    )
                result = {"halted": True, "session": "paper-live"}
            elif self.runtime is not None and self.runtime.is_running:
                self.runtime.stop_new_trades()
                result = {"halted": True, "session": "demo"}
            else:
                raise ValueError("no running session to halt")
        elif kind == "switch_profile_conservative":
            # Reuses the audited profile-change path, including its refusal to change a
            # profile under a running live session — that refusal surfaces to the caller.
            result = await self.change_risk_profile(
                profile="conservative", actor=actor, confirmed=True
            )
        else:  # pragma: no cover - the catalog is closed; a new kind must be wired here
            raise ValueError(f"unknown proposal kind {kind!r}")

        self._mentor_applied = [
            entry for entry in self._mentor_applied if entry.get("proposal_id") != proposal_id
        ]
        self._mentor_applied.append(
            {
                "proposal_id": proposal_id,
                "kind": kind,
                "actor": actor,
                "at": datetime.now(UTC).isoformat(),
                "title": proposal.title,
            }
        )
        with contextlib.suppress(Exception):
            from tia.core.ids import deterministic_id

            async with self.database.session() as session_db:
                await IncidentRepository(session_db).record(
                    {
                        "incident_id": deterministic_id(
                            "inc", "mentor", proposal_id, datetime.now(UTC)
                        ),
                        "at": datetime.now(UTC),
                        "kind": "mentor_apply",
                        "actor": actor,
                        "reason": proposal.title,
                        "detail": proposal.as_dict(),
                    }
                )
        return {"applied": proposal_id, "result": result}

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
        """Arm under the session lock — see :meth:`_arm_live_locked`."""
        async with self._session_lock:
            return await self._arm_live_locked(operator=operator, confirmation=confirmation)

    async def _arm_live_locked(self, *, operator: str, confirmation: str) -> dict[str, Any]:
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
            from tia.runtime.session_limits import encode_session_notes

            runtime = await self._build_live_runtime(token)
            # The same contract as the paper path (Phase 1.3, G10): the run row exists
            # before the loop takes a decision, and a start that fails leaves a stamped
            # row, never a session. Nothing of an earlier run is stamped "orphaned" here —
            # a real venue keeps its orders; the reconciliation reports what it finds.
            await self._start_session_with_run_row(
                runtime,
                mode="live",
                scenario="live",
                initial_capital=float(self.settings.live.max_live_capital),
                seed=0,
                symbols=(self.settings.live.symbol,),
                notes=encode_session_notes(
                    deadline=getattr(runtime, "session_deadline", None),
                    max_hours=self.settings.live.session_max_hours or None,
                ),
                orphan_earlier_orders=False,
            )
            self.live_runtime = runtime
            self._start_evidence_refresh()
            runtime_started = runtime.state.value == "running"
            runtime_state = runtime.state.value
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
        prior_outcomes, prior_reviews = await self._load_live_evidence()
        # Today's entries and the last entry's time, rebuilt from the execution record
        # the way the paper path does (Phase 1.3, G10): a live restart must not hand the
        # day's frequency limits a fresh zero. The account itself is NOT restored from
        # the journal here — over a real venue the venue is the authority on cash and
        # position, and the reconciliation reads it. The configured span becomes the
        # session's deadline, as it does for a paper session.
        risk_restore = await self._load_risk_restore()
        hours = float(live.session_max_hours or 0.0)
        return LiveRuntime(
            self.settings,
            activation=token,
            market_data=market,
            execution=execution,
            clock=clock,
            venue_time_ms=market.server_time_ms,
            persist=self._persist,
            on_event=self.broadcast,
            prior_outcomes=prior_outcomes,
            prior_reviews=prior_reviews,
            prior_risk_state=risk_restore,
            session_deadline=(datetime.now(UTC) + timedelta(hours=hours)) if hours > 0 else None,
            session_max_hours=hours if hours > 0 else None,
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

    async def start_paper_realtime(
        self,
        *,
        actor: str,
        max_duration_hours: float | None = None,
        session_deadline: datetime | None = None,
    ) -> dict[str, Any]:
        """Start a 24/7 paper-realtime session under the session lock — see
        :meth:`_start_paper_realtime_locked`. Two concurrent requests cannot both pass the
        "already active" check: the second waits and is refused."""
        async with self._session_lock:
            return await self._start_paper_realtime_locked(
                actor=actor, max_duration_hours=max_duration_hours, session_deadline=session_deadline,
            )

    async def _start_paper_realtime_locked(
        self,
        *,
        actor: str,
        max_duration_hours: float | None = None,
        session_deadline: datetime | None = None,
    ) -> dict[str, Any]:
        """Start a 24/7 paper-realtime session: real market data, simulated fills.

        No activation token — nothing here can spend real money, and the provider layer
        guarantees it independently. This is the session the 7-day paper track record
        runs on; its closed round trips persist as source="paper" evidence.

        A *validation* session is the same session with a deadline: ``max_duration_hours``
        (else the configured ``live.session_max_hours``) is enforced by the runtime itself
        and written into the run row, so a restart resumes under the same deadline
        (``session_deadline``) rather than a fresh one. Semantics of the argument (F15):
        ``None`` means "the configured span"; an explicit ``0`` means "no deadline at all"
        and **overrides** a configured ``session_max_hours`` — an operator asking for the
        24/7 session on purpose — exactly as ``session_max_hours = 0`` in configuration
        means the 24/7 session.
        """
        from tia.core.clock import SystemClock
        from tia.core.errors import LiveActivationError
        from tia.core.rng import RngRegistry
        from tia.data.providers.binance_public import BinancePublicProvider
        from tia.domain.instruments import DEFAULT_UNIVERSE
        from tia.execution.paper import PaperExecutionProvider
        from tia.runtime.live import LiveRuntime
        from tia.runtime.session_limits import encode_session_notes

        if self.live_runtime is not None and self.live_runtime.is_running:
            raise LiveActivationError(
                "a realtime session is already active; stop it before starting another"
            )
        # Another *process* over the same store (a second container, a stale deploy): its
        # run row carries a fresh heartbeat. Two sessions over one account is the F5 race
        # across processes, and the lock above cannot see it (Phase 1.3, G9).
        held = await self._foreign_session_lease(mode="paper-live")
        if held is not None:
            run_id, age = held
            raise LiveActivationError(
                f"another process holds an active paper session (run {run_id}, heartbeat "
                f"{age:.0f}s ago); stop it before starting another"
            )

        clock = SystemClock()
        # Mainnet public data on purpose, whatever use_testnet says: paper's execution
        # is simulated, and a track record needs real spreads, not testnet's thin market.
        rest = BinancePublicProvider(base_url=self.settings.live.public_data_url, clock=clock)
        market: Any = rest
        if self.settings.live.market_stream:
            from tia.data.providers.binance_stream import BinanceStreamProvider

            market = BinanceStreamProvider(
                rest,
                symbol=self.settings.live.symbol,
                timeframe=self.settings.market_data.timeframe,
                stream_url=self.settings.live.stream_url,
                clock=clock,
            )
            market.start()
        # One account across restarts. The engine is seeded from the account's own
        # journal — cash, position, realised P&L, fees, the equity peak and the UTC day's
        # opening equity — never from base capital plus a sum of strategy outcomes. A
        # journal that cannot be read or does not reconcile leaves the engine at base
        # capital *and* the runtime refusing entries until a person reconciles.
        capital = float(self.settings.live.paper_capital)
        symbol = self.settings.live.symbol
        account_restore = await self._load_account_restore(symbol=symbol, initial_capital=capital)
        execution = PaperExecutionProvider(
            self.settings.execution,
            DEFAULT_UNIVERSE,
            clock,
            RngRegistry(self.settings.seed),
            initial_capital=capital,
        )
        if account_restore.complete:
            execution.restore_portfolio(account_restore.portfolio_state())
        prior_pnl = float(account_restore.realized_pnl) if account_restore.complete else 0.0
        funding_rate = None
        funding_status = None
        funding_rate_at = None
        if self.settings.live.charge_funding:
            monitor = self._get_funding()
            monitor.start()
            funding_rate = monitor.latest_rate
            funding_status = monitor.status
            funding_rate_at = monitor.rate_at
        prior_outcomes, prior_reviews = await self._load_live_evidence()
        # Today's entries, by symbol, and the last entry's time, rebuilt from the orders
        # and fills earlier sessions persisted — so a restart does not hand the day's
        # frequency limits a fresh zero. An unreadable store yields an *incomplete*
        # rebuild, and the runtime then refuses new entries until one succeeds.
        risk_restore = await self._load_risk_restore()
        hours = (
            float(max_duration_hours)
            if max_duration_hours is not None
            else float(self.settings.live.session_max_hours)
        )
        span: float | None = None
        if session_deadline is None and hours > 0:
            session_deadline = datetime.now(UTC) + timedelta(hours=hours)
            span = hours
        runtime = LiveRuntime(
            self.settings,
            activation=None,
            market_data=market,
            execution=execution,
            clock=clock,
            venue_time_ms=market.server_time_ms,
            persist=self._persist,
            on_event=self.broadcast,
            prior_outcomes=prior_outcomes,
            prior_reviews=prior_reviews,
            prior_realised_pnl=prior_pnl,
            funding_rate=funding_rate,
            funding_status=funding_status,
            funding_rate_at=funding_rate_at,
            poll_interval_seconds=10.0,
            prior_risk_state=risk_restore,
            session_deadline=session_deadline,
            session_max_hours=span,
            prior_account_state=account_restore,
        )
        # The run row — deadline included — exists before the loop takes its first
        # decision, and a start that fails leaves a stamped row (F8). Orders earlier
        # paper sessions left open belong to an engine that no longer exists and are
        # stamped as orphaned — paper sessions only: a live run's orders are the venue's.
        orphaned = await self._start_session_with_run_row(
            runtime,
            mode="paper-live",
            scenario="realtime",
            initial_capital=capital,
            seed=self.settings.seed,
            symbols=(symbol,),
            notes=encode_session_notes(deadline=runtime.session_deadline, max_hours=hours or None),
            orphan_earlier_orders=True,
            market=market,
        )
        self.live_runtime = runtime
        self._start_evidence_refresh()
        _log.info(
            "paper_realtime_started", run_id=runtime.run_id, actor=actor,
            deadline=runtime.session_deadline.isoformat() if runtime.session_deadline else None,
            account_verified=account_restore.complete, orphaned_orders=orphaned,
        )
        return runtime.snapshot()

    async def _start_session_with_run_row(
        self,
        runtime: Any,
        *,
        mode: str,
        scenario: str,
        initial_capital: float,
        seed: int,
        symbols: Sequence[str],
        notes: str = "",
        orphan_earlier_orders: bool,
        market: Any | None = None,
    ) -> int:
        """Write the run row, then start the loop — in that order, for every session kind.

        The row exists before the loop takes its first decision: an order persisted for a
        run the store does not know is an order the store refuses, and a session the
        store does not know cannot be resumed or rebuilt from (F8). If the row cannot be
        written, nothing starts. If the start fails, the row is stamped as over with the
        failure in its notes, so a boot neither resumes it nor rebuilds on it, and the
        feed (``market``) is closed. Returns how many earlier orders were stamped
        orphaned (paper sessions only: an engine that restarts holds none of them; a real
        venue keeps its orders and the reconciliation reports them).
        Shared by the paper and the live path since Phase 1.3 (G10).
        """
        from tia.core.errors import LiveActivationError

        async def close_feed() -> None:
            closer = getattr(market, "close", None) if market is not None else None
            if callable(closer):
                with contextlib.suppress(Exception):
                    await closer()

        started_at = datetime.now(UTC)
        orphaned = 0
        try:
            async with self.database.session() as session:
                await RunRepository(session).create(
                    run_id=runtime.run_id,
                    mode=mode,
                    scenario=scenario,
                    started_at=started_at,
                    initial_capital=initial_capital,
                    seed=seed,
                    symbols=tuple(symbols),
                    notes=notes,
                )
                if orphan_earlier_orders:
                    orphaned = await AccountJournalRepository(session).orphan_open_orders(
                        exclude_run_id=runtime.run_id, at=started_at, modes=(mode,)
                    )
        except Exception as exc:
            await close_feed()
            raise LiveActivationError(
                f"the session's run row could not be persisted; nothing was started: {exc}"
            ) from exc
        try:
            await runtime.start()
        except Exception as exc:
            await close_feed()
            with contextlib.suppress(Exception):
                async with self.database.session() as session:
                    await RunRepository(session).stop(runtime.run_id, datetime.now(UTC))
                    await RunRepository(session).annotate(
                        runtime.run_id, f"start_failed: {str(exc)[:300]}"
                    )
            raise
        return orphaned

    async def _foreign_session_lease(self, *, mode: str) -> tuple[str, float] | None:
        """``(run_id, heartbeat age)`` of an open run of ``mode`` another process is still
        running — its heartbeat is younger than the lease — or ``None`` (Phase 1.3, G9).
        The session this process runs, if any, is not foreign."""
        from tia.runtime.session_limits import lease_age_seconds, lease_is_held

        own = self.live_runtime.run_id if self.live_runtime is not None else None
        now = datetime.now(UTC)
        try:
            async with self.database.session() as session:
                rows = await RunRepository(session).open_sessions(mode=mode)
        except Exception as exc:
            _log.warning("session_lease_check_failed", error=str(exc)[:300])
            return None
        for run_id, notes in rows:
            if run_id == own:
                continue
            if lease_is_held(notes, now=now):
                return run_id, float(lease_age_seconds(notes, now=now) or 0.0)
        return None

    async def _load_account_restore(self, *, symbol: str, initial_capital: float) -> Any:
        """Rebuild the paper account from its journal; incomplete on any failure.

        Never degrades to base capital: a store that cannot be read is an account that
        cannot be trusted, and the runtime refuses entries on it until
        :meth:`reconcile_session_state` succeeds.
        """
        from tia.portfolio.account_journal import AccountRestore

        try:
            async with self.database.session() as session:
                # Paper-live runs only (Phase 1.3, G11): a live run's fills belong to the
                # venue's account, and folding them here would move the paper account.
                return await AccountJournalRepository(session).rebuild(
                    now=datetime.now(UTC), initial_capital=initial_capital, symbol=symbol,
                    modes=("paper-live",),
                )
        except Exception as exc:
            _log.error("account_restore_failed", error=str(exc)[:300])
            return AccountRestore.failed(str(exc), initial_capital=initial_capital)

    async def _load_risk_restore(self) -> Any:
        """Rebuild the frequency state from the store; incomplete on any failure.

        Unlike the evidence loaders this does **not** degrade to "nothing": a session
        that cannot read today's entries must not start taking entries as if there had
        been none. The runtime receives the failure and refuses new entries until
        :meth:`reconcile_risk_state` succeeds.
        """
        from tia.risk.restore import RiskRestore

        now = datetime.now(UTC)
        # The read must cover the longest cooldown the configuration can ask for; two
        # days was a fixed assumption, now the floor (F10).
        lookback = max(
            timedelta(days=2), timedelta(seconds=2 * int(self.settings.risk.trade_cooldown_seconds))
        )
        try:
            async with self.database.session() as session:
                return await RiskStateRepository(session).rebuild(now=now, lookback=lookback)
        except Exception as exc:
            _log.error("risk_state_restore_failed", error=str(exc)[:300])
            return RiskRestore.failed(str(exc), day=now.date().isoformat())

    async def reconcile_risk_state(self, *, actor: str) -> dict[str, Any]:
        """Kept for the earlier route: reconciliation is now whole — see
        :meth:`reconcile_session_state`."""
        return await self.reconcile_session_state(actor=actor)

    async def reconcile_session_state(self, *, actor: str) -> dict[str, Any]:
        """Re-read the store into the running session: frequency state **and** account.

        The operator's path out of a start that could not read the store, or a session
        whose venue and record disagreed. Entries are allowed again only when both the
        frequency rebuild and the account rebuild are complete and the engine's own
        position agrees with the journal. Counters alone never lift the block.
        """
        live = self.live_runtime
        if live is None:
            return {"verified": False, "reason": "no 24/7 session is running"}
        risk_restore = await self._load_risk_restore()
        risk_report = live.restore_risk_state(risk_restore)
        account_restore = await self._load_account_restore(
            symbol=self.settings.live.symbol, initial_capital=float(self.settings.live.paper_capital),
        )
        venue_position: float | None = None
        with contextlib.suppress(Exception):
            positions = await live._execution.get_positions()
            held = positions.get(self.settings.live.symbol)
            venue_position = float(held.quantity) if held is not None else 0.0
        account_report = live.restore_account_state(account_restore, venue_position=venue_position)
        verified = not live.entry_blocks
        _log.info(
            "session_state_reconciled", actor=actor, verified=verified,
            risk_complete=risk_restore.complete, account_complete=account_restore.complete,
            blocks=list(live.entry_blocks),
        )
        return {
            "verified": verified,
            "entry_blocks": live.entry_blocks,
            "risk_state": risk_report,
            "account_state": account_report,
            "venue_position": venue_position,
        }

    async def stop_realtime_session(self, *, reason: str) -> dict[str, Any]:
        """Stop the live/paper-realtime session AND stamp its run row.

        The stamp is what makes operator intent survive a restart: startup resumes only
        runs with no ``stopped_at``, so a session stopped through this method stays
        stopped, while one interrupted by a crash or redeploy comes back on its own.

        Under the session lock (Phase 1.4): a stop that arrives while a start is still
        building the session waits for it and then stops it, instead of answering
        "disarmed" to the operator while the session it did not see goes on running.
        """
        async with self._session_lock:
            return await self._stop_realtime_session_locked(reason=reason)

    async def _stop_realtime_session_locked(self, *, reason: str) -> dict[str, Any]:
        live = self.live_runtime
        if live is None:
            return {"active": False, "state": "disarmed"}
        await live.stop(reason=reason)
        with contextlib.suppress(Exception):  # the stop itself must not fail on a stamp
            async with self.database.session() as session:
                await RunRepository(session).stop(live.run_id, datetime.now(UTC))
                # A stamped run holds no lease: its heartbeat goes with it (G9).
                await RunRepository(session).release_lease(live.run_id)
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

        from tia.runtime.session_limits import resume_decision

        try:
            async with self.database.session() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT run_id, notes FROM runs WHERE mode = 'paper-live' "
                            "AND stopped_at IS NULL ORDER BY started_at DESC LIMIT 1"
                        )
                    )
                ).first()
                if row is None:
                    return
                interrupted = str(row[0])
                notes = str(row[1] or "")
                halts = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM incidents WHERE run_id = :run AND "
                            "kind IN ('kill_switch', 'emergency_flatten', 'safe_mode')"
                        ),
                        {"run": interrupted},
                    )
                ).scalar()
                decision = resume_decision(
                    notes=notes, halts=int(halts or 0), now=datetime.now(UTC)
                )
                if decision.held_by_other:
                    # A fresh heartbeat: either another process is running this run, or
                    # the process died hard moments ago and nothing released the lease.
                    # The row is left alone for now — stamping it would make a running
                    # session look over — and the question is answered after a probe
                    # interval, in the background, by whether the heartbeat advanced
                    # (Phase 1.3, G9). The API comes up meanwhile.
                    _log.warning(
                        "paper_realtime_lease_held", run_id=interrupted,
                        reason=decision.reason, probe_seconds=self._lease_probe_seconds,
                    )
                    self._lease_probe_task = asyncio.get_running_loop().create_task(
                        self._probe_lease_then_resume(interrupted, notes, int(halts or 0))
                    )
                    return
                # The run is over either way — the process that owned it is gone; the
                # question is only whether a new one starts unattended.
                await RunRepository(session).stop(interrupted, datetime.now(UTC))
        except Exception as exc:
            _log.warning("paper_realtime_resume_check_failed", error=str(exc)[:300])
            return

        if not decision.resume:
            _log.warning(
                "paper_realtime_not_resumed", run_id=interrupted, reason=decision.reason,
            )
            return

        try:
            await self.start_paper_realtime(
                actor="startup-recovery", session_deadline=decision.deadline
            )
            _log.info(
                "paper_realtime_resumed", interrupted_run=interrupted, reason=decision.reason,
            )
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

    async def _probe_lease_then_resume(self, run_id: str, notes_before: str, halts: int) -> None:
        """Wait a probe interval, read the run's heartbeat again, and decide.

        Advanced: another process is running the session — alert, touch nothing.
        Unchanged: the writer is dead — stamp the row and resume as a crash-interrupted
        run, under the same rules as a boot that found a stale heartbeat (G9).
        """
        from tia.runtime.session_limits import decode_heartbeat, resume_decision

        await asyncio.sleep(self._lease_probe_seconds)
        try:
            async with self.database.session() as session:
                run = await RunRepository(session).get(run_id)
                if run is None or run.stopped_at is not None:
                    return  # stamped meanwhile by whoever owns it
                notes_after = str(run.notes or "")
                if decode_heartbeat(notes_after) != decode_heartbeat(notes_before):
                    reason = (
                        f"run {run_id}'s heartbeat advanced during the {self._lease_probe_seconds:.0f}s "
                        "probe: another process is running this session; nothing started here"
                    )
                    _log.warning("paper_realtime_held_by_other_process", run_id=run_id, reason=reason)
                    self._dispatch_alert(
                        {
                            "kind": "paper_session_held_by_other_process", "reason": reason,
                            "actor": "startup-recovery", "run_id": run_id,
                            "at": datetime.now(UTC).isoformat(),
                        }
                    )
                    return
                # Dead: decide as for any interrupted run, the lease set aside.
                decision = resume_decision(
                    notes=notes_after, halts=halts, now=datetime.now(UTC), lease_seconds=0.0
                )
                await RunRepository(session).stop(run_id, datetime.now(UTC))
        except Exception as exc:
            _log.warning("paper_realtime_lease_probe_failed", run_id=run_id, error=str(exc)[:300])
            return
        if not decision.resume:
            _log.warning("paper_realtime_not_resumed", run_id=run_id, reason=decision.reason)
            return
        try:
            await self.start_paper_realtime(actor="startup-recovery", session_deadline=decision.deadline)
            _log.info("paper_realtime_resumed", interrupted_run=run_id, reason=decision.reason)
        except Exception as exc:
            _log.warning("paper_realtime_resume_failed", run_id=run_id, error=str(exc)[:300])
            self._dispatch_alert(
                {
                    "kind": "paper_resume_failed", "reason": str(exc)[:300],
                    "actor": "startup-recovery", "run_id": run_id,
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
            # A write the store refused in the last ten minutes: the engines went on
            # (by design), the record did not (Phase 1.4).
            "persistence": "degraded" if self._persistence_recently_failed() else "online",
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
            # Why a session stopped taking entries is the whole content of the news that
            # it did. A halt with no reason on screen reads as a fault; the reason is
            # usually mundane (a stale feed, a network blip) and self-healing.
            history = (snapshot.get("state_machine") or {}).get("history") or []
            live_view = {
                "mode": snapshot.get("mode"),
                "state": snapshot.get("state"),
                "state_reason": history[-1].get("reason") if history else None,
                "state_since": history[-1].get("at") if history else None,
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
            "persistence": self.persistence_status(),
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
            "# HELP tia_persist_writes_total Persistence writes that landed",
            "# TYPE tia_persist_writes_total counter",
            f"tia_persist_writes_total {self._persist_writes}",
            "# HELP tia_persist_failures_total Persistence writes the store refused",
            "# TYPE tia_persist_failures_total counter",
            f"tia_persist_failures_total {self._persist_failures}",
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
