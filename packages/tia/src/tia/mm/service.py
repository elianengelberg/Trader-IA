"""Live paper mode: the market-maker engine fed by the real market-data service.

The service subscribes to the Phase 2 market-data service and hands the engine the
same kinds of events a replay of the tape would hand it — snapshot, depth, trade,
book, disconnect — with the receive time as the clock. It writes every journal row
and fill to the maker's own tables through the application's persistence callback,
saves the maker's ledger periodically and at close so a restart resumes it, and
pushes a compact state to the browser every few seconds.

It constructs no execution provider and accepts none: quotes and fills exist only in
the simulator. The flags that gate it are ``TIA_MM__ENABLED`` (market data) and
``TIA_MM__ADAPTIVE_ENABLED`` (this service); ``TIA_MM__REAL_MONEY`` is read by nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from tia.core.clock import SystemClock
from tia.core.logging import get_logger
from tia.mm.engine import MarketMakerConfig, MarketMakerEngine
from tia.mm.latency_model import LatencyProfile
from tia.mm.ledger import MarketMakerLedger
from tia.mm.market_data import MarketDataService
from tia.mm.metrics import compute_metrics
from tia.mm.safety import GlobalTradingSafetyGate

_log = get_logger("mm.service")

Persist = Callable[[str, dict[str, Any]], Awaitable[None]]
Broadcast = Callable[[dict[str, Any]], None]
PUSHED_KINDS = ("decision", "fill", "block")


class MarketMakerService:
    def __init__(
        self,
        *,
        market: MarketDataService,
        config: MarketMakerConfig,
        profile: LatencyProfile,
        scenario: str,
        run_id: str,
        risk_state: Callable[[], Any | None],
        system_unsafe: Callable[[], str] | None = None,
        persist: Persist | None = None,
        broadcast: Broadcast | None = None,
        now_ms: Callable[[], int] | None = None,
        state_push_interval_ms: int = 3_000,
        ledger_save_interval_ms: int = 10_000,
    ) -> None:
        self.market = market
        self.config = config
        self.profile = profile
        self.scenario = scenario
        self.run_id = run_id
        self.latency = profile.scenario(scenario)
        self._persist = persist
        self._broadcast = broadcast
        self._now_ms = now_ms or SystemClock().timestamp_ms
        self._push_interval_ms = state_push_interval_ms
        self._save_interval_ms = ledger_save_interval_ms
        self.gate = GlobalTradingSafetyGate(
            risk_state=risk_state,
            data_usable=self._data_usable,
            system_unsafe=system_unsafe,
        )
        self.engine = MarketMakerEngine(config, latency=self.latency, gate=self.gate, journal_sink=self._on_journal)
        self._unsubscribe: Callable[[], None] | None = None
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue(maxsize=50_000)
        self._writer: asyncio.Task[Any] | None = None
        self._running = False
        self._last_push_ms = 0
        self._last_save_ms = 0
        self._seq = 0
        self.engine_errors = 0
        self.last_engine_error = ""
        self.journal_queued = 0
        self.journal_dropped = 0
        self.journal_written = 0
        self.persist_errors = 0
        self.restored_from: str | None = None

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_running(self) -> bool:
        return self._running

    def restore(self, ledger_state: dict[str, Any] | None, *, source: str = "database") -> None:
        """Resume the maker's own ledger from a saved state (restart persistence)."""
        if not ledger_state:
            return
        self.engine.ledger = MarketMakerLedger.restore(ledger_state, self.engine.costs)
        self.restored_from = source

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._unsubscribe = self.market.subscribe(self._on_market_event)
        if self._persist is not None:
            self._writer = asyncio.get_running_loop().create_task(self._write_loop(), name="mm-paper-persist")
        _log.info("mm_paper_started", run_id=self.run_id, scenario=self.scenario, profile=self.profile.profile_id, config=self.config.config_id)

    async def close(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        t = self._now_ms()
        self.engine.execution.cancel_all(t, reason="service closing")
        await self._save_ledger(t)
        if self._writer is not None:
            await self._queue.put(None)
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._writer, timeout=5.0)
            self._writer = None

    # ------------------------------------------------------------------ feed

    def _data_usable(self) -> tuple[bool, str]:
        if self.market.usable:
            return True, ""
        return False, self.market.snapshot(levels=1)["not_usable_reason"]

    def _on_market_event(self, kind: str, event: Any, t_ms: int) -> None:
        try:
            self.engine.on_event(kind, event, t_ms)
        except Exception as exc:  # the feed must survive an engine fault; the fault is visible
            self.engine_errors += 1
            self.last_engine_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.error("mm_engine_failed", error=self.last_engine_error)
            return
        if self._broadcast is not None and t_ms - self._last_push_ms >= self._push_interval_ms:
            self._last_push_ms = t_ms
            self._broadcast({"type": "mm.state", "data": self.compact_state()})
        if self._persist is not None and t_ms - self._last_save_ms >= self._save_interval_ms:
            self._last_save_ms = t_ms
            self._enqueue("mm_ledger", self._ledger_payload(t_ms))

    def _on_journal(self, row: dict[str, Any]) -> None:
        self._seq += 1
        kind = str(row.get("kind", ""))
        if self._persist is not None:
            self._enqueue("mm_journal", {"run_id": self.run_id, "seq": self._seq, "row": row})
            if kind == "fill":
                self._enqueue("mm_fill", {"run_id": self.run_id, "fill": row})
            elif kind == "markout":
                self._enqueue("mm_markout", {"fill_id": row.get("fill_id"), "markout_bps": row.get("markout_bps", {})})
        if self._broadcast is not None and kind in PUSHED_KINDS:
            self._broadcast({"type": "mm.journal", "data": row})

    def _enqueue(self, kind: str, payload: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((kind, payload))
            self.journal_queued += 1
        except asyncio.QueueFull:
            self.journal_dropped += 1

    async def _write_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            kind, payload = item
            try:
                if self._persist is not None:
                    await self._persist(kind, payload)
                    self.journal_written += 1
            except Exception as exc:  # persistence failures are counted, never fatal
                self.persist_errors += 1
                _log.warning("mm_persist_failed", kind=kind, error=str(exc)[:160])

    def _ledger_payload(self, t_ms: int) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": self.engine.ledger.export(),
            "config_id": self.config.config_id,
            "profile_id": self.profile.profile_id,
            "latency_scenario": self.scenario,
            "t_ms": t_ms,
        }

    async def _save_ledger(self, t_ms: int) -> None:
        if self._persist is None:
            return
        try:
            await self._persist("mm_ledger", self._ledger_payload(t_ms))
        except Exception as exc:
            self.persist_errors += 1
            _log.warning("mm_persist_failed", kind="mm_ledger", error=str(exc)[:160])

    # ------------------------------------------------------------------ reading

    def compact_state(self) -> dict[str, Any]:
        snap = self.engine.snapshot()
        return {
            "running": self._running,
            "gate": snap["gate"],
            "book": snap["book"],
            "features": snap["features"],
            "last_decision": snap["last_decision"],
            "active_orders": snap["active_orders"],
            "ledger": snap["ledger"],
            "decisions": snap["decisions"],
            "quotes": snap["quotes"],
            "cancels": snap["cancels"],
            "journal_rows": snap["journal_rows"],
            "journal_hash": snap["journal_hash"],
        }

    def snapshot(self) -> dict[str, Any]:
        market = self.market.snapshot(levels=1)
        snap = self.engine.snapshot()
        snap["execution_stats"] = snap.pop("execution")
        return {
            **snap,
            "run_id": self.run_id,
            "profile": {"id": self.profile.profile_id, "commit": self.profile.commit, "measured_at_utc": self.profile.measured_at_utc, "scenario": self.scenario},
            "data_quality": {
                "usable": market["usable"],
                "not_usable_reason": market["not_usable_reason"],
                "data_age_s": market["data_age_s"],
                "stream_connected": market["stream"]["connected"],
                "book_state": market["book"]["state"],
                "gaps": market["book"]["metrics"]["gaps"],
                "stale_episodes": market["integrity"]["stale_episodes"],
                "latency_depth_ms": market["stream"]["latency_depth_ms"],
                "processing_us": market["processing_us"],
            },
            "persistence": {
                "queued": self.journal_queued,
                "written": self.journal_written,
                "dropped": self.journal_dropped,
                "errors": self.persist_errors,
                "restored_from": self.restored_from,
            },
            "engine_errors": self.engine_errors,
            "last_engine_error": self.last_engine_error,
        }

    def journal(self, *, limit: int = 100, kind: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in self.engine.journal if kind is None or r.get("kind") == kind]
        return rows[-limit:]

    def metrics(self) -> dict[str, Any]:
        return compute_metrics(
            journal=list(self.engine.journal),
            ledger=self.engine.ledger.snapshot(),
            execution=self.engine.execution.stats(),
            markouts=self.engine.markouts.summary(),
            limits=self.config.limits.as_dict(),
            latency_scenario=self.scenario,
            fee_scenario=self.config.fee_scenario,
        )


__all__ = ["MarketMakerService"]
