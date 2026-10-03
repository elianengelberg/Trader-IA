"""Live market making: the Phase 3 engine on the real feed, over a real execution.

The paper service and this one share everything above the execution: the market-data
feed, the engine, its hierarchy, its journal, its persistence. This class adds what real
money needs and the paper service deliberately lacks:

* a :class:`~tia.mm.execution.LiveMarketMakerExecution` over an abstract provider — a
  testnet or a live one that already carries its activation token;
* a :class:`~tia.mm.live_ledger.LiveLedger` seeded from the account's balances;
* the two authorization stages (risk, economics) wired into the engine;
* a :class:`~tia.mm.kill_switch.MMKillSwitch` that feeds the global safety gate, engaged
  by stale data, a dropped stream, an unknown order state, an unknown fill, a foreign
  order, a reconciliation that fails or disagrees, an expired activation, a breached limit
  of the maker's own controller, too many API errors, or an operator;
* reconciliation **before the first quote** and periodically after: open orders, balances
  and trades, compared, classified and journaled. A critical discrepancy means no quote
  and a cancel of what rests. Binance wins.

It is never constructed at boot. The API builds it from an explicit operator action, with
the confirmation phrase, and on the real venue only after the activation gate passed.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections import deque
from collections.abc import Callable
from typing import Any

from tia.core.clock import Clock, utc_from_millis
from tia.core.ids import deterministic_id
from tia.core.logging import get_logger
from tia.domain.portfolio import AccountBalance
from tia.execution.provider import ExecutionProvider
from tia.mm.authorization import (
    ActivationView,
    EconomicsConfig,
    MMEconomicsAuthorizer,
    MMRiskAuthorizer,
)
from tia.mm.costs import MarketMakerCostModel
from tia.mm.engine import MarketMakerConfig
from tia.mm.execution import LiveMarketMakerExecution, SymbolFilters
from tia.mm.kill_switch import KillSeverity, MMKillSwitch
from tia.mm.latency import LatencyStats
from tia.mm.latency_model import LatencyProfile
from tia.mm.live_ledger import LiveLedger
from tia.mm.market_data import MarketDataService
from tia.mm.reconciliation import (
    MMDiscrepancy,
    MMReconciliationReport,
    build_report,
    compare_balances,
    compare_orders,
)
from tia.mm.service import Broadcast, MarketMakerService, Persist

_log = get_logger("mm.live")

#: What each critical finding of the execution does to quoting, and whether a person
#: must release it. An order in an unknown state blocks new orders until the venue
#: answers (a cancel would be one more request of unknown fate); everything else that
#: means "the account is not what we think" cancels what rests and stays engaged.
CRITICAL_RESPONSE: dict[str, tuple[KillSeverity, bool]] = {
    "unknown_order_state": (KillSeverity.NO_NEW_QUOTES, False),
    "unresolved_order": (KillSeverity.NO_NEW_QUOTES, True),
    "excessive_api_errors": (KillSeverity.NO_NEW_QUOTES, True),
    "activation": (KillSeverity.NO_NEW_QUOTES, True),
    "unknown_fill": (KillSeverity.CANCEL_OPEN, True),
    "unknown_execution_report": (KillSeverity.CANCEL_OPEN, True),
    "foreign_open_order": (KillSeverity.CANCEL_OPEN, True),
    "venue_order_unknown_locally": (KillSeverity.CANCEL_OPEN, True),
    # An order this run closed that the venue, asked by its id, still holds open: a zombie
    # the adapter reopens locally and cancels; a person looks at why it existed.
    "closed_order_open_at_venue": (KillSeverity.CANCEL_OPEN, True),
    "outcome_apply_failed": (KillSeverity.CANCEL_OPEN, True),
    # The account stream dropped: no state is invented. What rests is cancelled, nothing
    # new is quoted, and the condition clears when the stream is back and a reconciliation
    # has read the account.
    "user_stream_down": (KillSeverity.CANCEL_OPEN, False),
}


def _assets(symbol: str, provider: Any) -> tuple[str, str]:
    base, _, quote = symbol.partition("-")
    venue_quote = str(getattr(provider, "quote_asset", "") or "")
    if not venue_quote:
        venue_quote = "USDT" if quote.upper() == "USD" else quote.upper()
    return base.upper(), venue_quote.upper()


def _run_tag(run_id: str, at_ms: int) -> str:
    return hashlib.blake2s(f"{run_id}:{at_ms}".encode(), digest_size=4).hexdigest()


class LiveMarketMakerService(MarketMakerService):
    def __init__(
        self,
        *,
        market: MarketDataService,
        config: MarketMakerConfig,
        profile: LatencyProfile,
        scenario: str,
        run_id: str,
        risk_state: Callable[[], Any | None],
        provider: ExecutionProvider,
        clock: Clock,
        filters: SymbolFilters,
        activation: Any | None = None,
        fingerprint: str | None = None,
        capital_cap_usd: float | None = None,
        economics: EconomicsConfig | None = None,
        expiry_margin_s: float = 120.0,
        reconcile_interval_s: float = 30.0,
        trades_poll_interval_s: float = 3.0,
        open_sync_interval_s: float = 10.0,
        max_api_errors_per_minute: int = 10,
        strict_cancel_replace: bool = True,
        foreign_orders_critical: bool = True,
        quote_tolerance_usd: float = 0.5,
        base_tolerance_steps: float = 2.0,
        cancel_wait_s: float = 10.0,
        heartbeat_s: float = 0.5,
        venue_label: str = "",
        system_unsafe: Callable[[], str] | None = None,
        persist: Persist | None = None,
        broadcast: Broadcast | None = None,
        now_ms: Callable[[], int] | None = None,
        state_push_interval_ms: int = 3_000,
        ledger_save_interval_ms: int = 10_000,
    ) -> None:
        now = now_ms or clock.timestamp_ms
        if getattr(provider, "is_live", False) and activation is None:
            raise ValueError("a live provider reached the market maker without its activation token")
        self.provider = provider
        self.clock = clock
        self.filters = filters
        self.activation = activation
        self.capital_cap_usd = capital_cap_usd
        self.venue_label = venue_label or str(getattr(provider, "name", "venue"))
        self._reconcile_interval_s = reconcile_interval_s
        self._quote_tolerance_usd = quote_tolerance_usd
        self._base_tolerance_btc = base_tolerance_steps * filters.step_size
        self._cancel_wait_s = cancel_wait_s
        self._heartbeat_s = heartbeat_s
        self._heartbeat_task: asyncio.Task[Any] | None = None
        self._last_event_ms: int | None = None
        self.heartbeats = 0
        self.economics_config = economics or EconomicsConfig()
        self.kill = MMKillSwitch(now_ms=now, cancel_open=self._cancel_open, on_event=self._journal_event)
        execution = LiveMarketMakerExecution(
            provider,
            clock=clock,
            filters=filters,
            symbol=config.symbol,
            run_tag=_run_tag(run_id, now()),
            now_ms=now,
            fingerprint=fingerprint,
            strict_cancel_replace=strict_cancel_replace,
            trades_poll_interval_ms=int(trades_poll_interval_s * 1000),
            open_sync_interval_ms=int(open_sync_interval_s * 1000),
            max_api_errors_per_minute=max_api_errors_per_minute,
            foreign_orders_critical=foreign_orders_critical,
            on_critical=self._on_execution_critical,
        )
        cost_model = MarketMakerCostModel(config.costs)
        ledger = LiveLedger(cost_model)
        risk_authorizer = MMRiskAuthorizer(
            capital_cap_usd=lambda: self.capital_cap_usd,
            activation=self._activation_view if activation is not None else None,
            execution_health=lambda: execution.blocked_reason,
            kill_switch=self.kill.status,
            expiry_margin_s=expiry_margin_s,
        )
        economics_authorizer = MMEconomicsAuthorizer(
            self.economics_config,
            maker_fee_bps=lambda: cost_model.config.fee_bps(config.fee_scenario),
            taker_fee_bps=lambda: cost_model.config.taker_fee_bps,
            max_inventory_btc=config.limits.max_inventory_btc,
        )
        outer_unsafe = system_unsafe or (lambda: "")

        def unsafe() -> str:
            return self.kill.status() or outer_unsafe()

        super().__init__(
            market=market,
            config=config,
            profile=profile,
            scenario=scenario,
            run_id=run_id,
            risk_state=risk_state,
            system_unsafe=unsafe,
            persist=persist,
            broadcast=broadcast,
            now_ms=now,
            state_push_interval_ms=state_push_interval_ms,
            ledger_save_interval_ms=ledger_save_interval_ms,
            execution=execution,
            ledger=ledger,
            authorizers=(risk_authorizer, economics_authorizer),
        )
        self.execution = execution
        self.live_ledger = ledger
        self.risk_authorizer = risk_authorizer
        self.economics_authorizer = economics_authorizer
        self._base_asset, self._quote_asset = _assets(config.symbol, provider)
        # Fills are booked the moment the venue reports them, on the stream's task; the
        # venue's balances are recorded as they arrive.
        execution.fill_sink = self._on_live_fill
        execution.balances_sink = self._on_venue_balances
        #: The account stream, attached by the API layer (or a test); started before the
        #: initial reconciliation so no report falls between the snapshot and the socket.
        self.user_stream: Any | None = None
        self.event_to_processed_ms = LatencyStats()
        self.callback_ms = LatencyStats()
        self._reconcile_task: asyncio.Task[Any] | None = None
        self._reconciling = False
        self._balance_mismatch_streak = 0
        #: Orders closed here that the venue's snapshot listed open, by id, with how many
        #: consecutive reconciliations saw them so: one is the snapshot's age, two is a fact.
        self._closed_open_streak: dict[str, int] = {}
        self.last_report: MMReconciliationReport | None = None
        self.reconciliations = 0
        self.reconciliation_failures = 0
        self.started_at_ms: int | None = None
        self.stopped_at_ms: int | None = None
        self.stop_reason = ""
        self._stopping = False
        self._data_kill = False
        self._risk_kill_mirrored = False
        self.operator_events: deque[dict[str, Any]] = deque(maxlen=100)

    # ------------------------------------------------------------------ identity

    @property
    def is_live(self) -> bool:
        return self.execution.is_live

    @property
    def state_label(self) -> str:
        if self._stopping:
            return "stopping"
        if not self._running:
            return "stopped" if self.stopped_at_ms is not None else "created"
        if self.kill.engaged:
            return "safe"
        if self.engine.last_block_reason:
            return "no_quote"
        return "quoting"

    def _activation_view(self, t_ms: int) -> ActivationView:
        token = self.activation
        if token is None:
            return ActivationView(True, None, "no activation: simulated venue")
        moment = utc_from_millis(t_ms)
        valid = bool(token.is_valid_at(moment))
        remaining = float(token.seconds_remaining(moment))
        detail = "" if valid else f"expired at {token.expires_at.isoformat()}"
        return ActivationView(valid, remaining, detail)

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        raise RuntimeError("the live market maker starts with start_live(), which reconciles first")

    def check_grid(self) -> None:
        """The quoting engine must round to the venue's grid; refuse to start otherwise."""
        q = self.config.quoting
        problems = []
        if abs(q.tick_size - self.filters.tick_size) > 1e-12:
            problems.append(f"quoting tick_size {q.tick_size} != venue tick {self.filters.tick_size}")
        if abs(q.size_step - self.filters.step_size) > 1e-12:
            problems.append(f"quoting size_step {q.size_step} != venue step {self.filters.step_size}")
        if q.min_size_btc < self.filters.min_qty:
            problems.append(f"quoting min_size_btc {q.min_size_btc} below the venue minimum {self.filters.min_qty}")
        if problems:
            raise ValueError("quoting configuration disagrees with the venue's filters: " + "; ".join(problems))

    def attach_user_stream(self, stream: Any) -> None:
        """A started-later account stream whose callbacks already point at the execution."""
        if self._running:
            raise RuntimeError("attach the account stream before start_live()")
        self.user_stream = stream

    async def start_live(self) -> MMReconciliationReport:
        if self._running:
            return self.last_report or await self.reconcile()
        self.check_grid()
        await self.execution.start()
        if self.user_stream is not None:
            self.user_stream.start()
        report = await self.reconcile(initial=True)
        # From here on the account stream is the primary source of execution facts; what
        # it said before this instant is covered by the reconciliation just made.
        self.execution.accepting_reports = True
        if report.critical:
            self.kill.engage("reconciliation", f"initial reconciliation: {report.summary}", severity=KillSeverity.CANCEL_OPEN, sticky=True)
        MarketMakerService.start(self)
        self.started_at_ms = self._now_ms()
        loop = asyncio.get_running_loop()
        self._reconcile_task = loop.create_task(self._reconcile_loop(), name="mm-live-reconcile")
        self._heartbeat_task = loop.create_task(self._heartbeat_loop(), name="mm-live-heartbeat")
        _log.info("mm_live_started", run_id=self.run_id, venue=self.venue_label, live=self.is_live, state=self.state_label, reconciliation=report.summary)
        return report

    async def _reconcile_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._reconcile_interval_s)
            if not self._running:
                return
            with contextlib.suppress(Exception):  # the failure is recorded by reconcile itself
                await self.reconcile()

    async def _heartbeat_loop(self) -> None:
        """When the feed is silent, the engine still has to see time pass: quotes expire,
        the data-age rule blocks and cancels, the kill switch sees stale data. The tick is
        an engine event with no market content, applied off the feed's callback."""
        interval_ms = int(self._heartbeat_s * 1000)
        while self._running:
            await asyncio.sleep(self._heartbeat_s)
            if not self._running or self._stopping:
                return
            now = self._now_ms()
            if self._last_event_ms is not None and now - self._last_event_ms < interval_ms:
                continue
            self.heartbeats += 1
            try:
                self.engine.on_event("tick", None, now)
            except Exception as exc:  # the same containment as the feed's callback
                self.engine_errors += 1
                self.last_engine_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            self._watch(now)

    async def _drain_until_quiet(self) -> int:
        """Let the worker finish the cancels, applying each answer through the engine."""
        deadline = self._now_ms() + int(self._cancel_wait_s * 1000)
        for _ in range(max(1, int(self._cancel_wait_s / 0.1))):
            if self._now_ms() >= deadline:
                break
            await asyncio.sleep(0.1)
            self.engine.on_event("tick", None, self._now_ms())
            if not self.execution.open_orders():
                break
        return len(self.execution.open_orders())

    async def stop(self, *, reason: str, actor: str) -> dict[str, Any]:
        """Cancel everything, wait for the venue to confirm, reconcile, close."""
        if not self._running and self.stopped_at_ms is not None:
            return self.status()
        self._stopping = True
        self.stop_reason = f"{reason} (by {actor})"
        self._note_operator("stop", reason, actor)
        for task in (self._reconcile_task, self._heartbeat_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._reconcile_task = self._heartbeat_task = None
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.kill.engage("stop", self.stop_reason, severity=KillSeverity.CANCEL_OPEN, sticky=True, actor=actor)
        left_open = await self._drain_until_quiet()
        with contextlib.suppress(Exception):
            await self.reconcile(final=True)
        # Whatever the worker answered during the final reconciliation (a resolve, a poll)
        # is applied before the worker is closed, so the status the operator reads holds it.
        with contextlib.suppress(Exception):
            self.engine.on_event("tick", None, self._now_ms())
        await MarketMakerService.close(self)
        if self.user_stream is not None:
            with contextlib.suppress(Exception):
                await self.user_stream.close()
        await self.execution.close()
        with contextlib.suppress(Exception):
            await self.provider.close()
        self.stopped_at_ms = self._now_ms()
        self._stopping = False
        _log.info("mm_live_stopped", run_id=self.run_id, reason=self.stop_reason, orders_left_open=left_open)
        return self.status()

    async def close(self) -> None:
        if self._running:
            await self.stop(reason="service closing", actor="system")

    async def engage_kill_switch(self, *, reason: str, actor: str) -> dict[str, Any]:
        """The operator's emergency stop: no new quotes, cancel what rests, reconcile."""
        if not actor.strip():
            raise ValueError("the kill switch requires a named actor")
        self._note_operator("kill_switch", reason, actor)
        self.kill.engage("operator", reason, severity=KillSeverity.CANCEL_OPEN, sticky=True, actor=actor)
        await self._drain_until_quiet()
        with contextlib.suppress(Exception):
            await self.reconcile()
        return self.status()

    # ------------------------------------------------------------------ the feed

    def _on_market_event(self, kind: str, event: Any, t_ms: int) -> None:
        self._last_event_ms = t_ms
        started = self._now_ms()
        super()._on_market_event(kind, event, t_ms)
        done = self._now_ms()
        # Receive stamp to decision applied (features, fair value, authorization, quoting,
        # local validation, enqueue) and the callback's own duration. No network in it.
        self.event_to_processed_ms.add(done - t_ms)
        self.callback_ms.add(done - started)
        self._watch(t_ms)

    def _on_live_fill(self, fill: Any, t_ms: int) -> None:
        """A fill the venue confirmed, booked now through the engine (ledger, markouts,
        journal). Called on the stream's or the worker's turn, never on the feed."""
        try:
            self.engine._on_fill(fill, t_ms)
        except Exception as exc:
            self.engine_errors += 1
            self.last_engine_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            _log.error("mm_live_fill_booking_failed", error=self.last_engine_error)

    def _on_venue_balances(self, balances: dict[str, AccountBalance], t_ms: int) -> None:
        quote = balances.get(self._quote_asset)
        base = balances.get(self._base_asset)
        ledger = self.live_ledger
        ledger.note_venue_balances(
            quote_free=quote.free if quote is not None else (ledger.venue_quote_free or 0.0),
            quote_locked=quote.locked if quote is not None else (ledger.venue_quote_locked or 0.0),
            base_free=base.free if base is not None else (ledger.venue_base_free or 0.0),
            base_locked=base.locked if base is not None else (ledger.venue_base_locked or 0.0),
            t_ms=t_ms,
        )

    def _watch(self, t_ms: int) -> None:  # noqa: ARG002 - time is read from the kill switch's clock
        # Data: a stream that dropped or data that is not usable cancels what rests, and
        # the condition clears itself when the data is usable again.
        usable = self.market.usable
        if not usable and not self._data_kill:
            self._data_kill = True
            self.kill.engage("data", f"market data not usable: {self.market.snapshot(levels=1)['not_usable_reason']}", severity=KillSeverity.CANCEL_OPEN, sticky=False)
        elif usable and self._data_kill:
            self._data_kill = False
            self.kill.clear("data")
        # An unknown order resolved: the execution unblocked itself; the transient clears.
        if not self.execution.blocked_reason and not self.execution.unknown_orders():
            self.kill.clear("unknown_order_state")
        # The account stream is back and a reconciliation has read the account since.
        if self.execution.stream_connected is True and self.last_report is not None and self.last_report.t_ms >= (self.execution.stream_last_change_ms or 0):
            self.kill.clear("user_stream_down")
        # The maker's own controller tripped (daily loss, drawdown): mirrored, sticky.
        controller = self.engine.controller
        if controller.kill_switch and not self._risk_kill_mirrored:
            self._risk_kill_mirrored = True
            self.kill.engage("risk_limit", controller.kill_switch_reason, severity=KillSeverity.CANCEL_OPEN, sticky=True)

    def _cancel_open(self, t_ms: int, reason: str) -> int:
        cancelled = self.execution.cancel_all(t_ms, reason=reason)
        self.engine.cancels += cancelled
        return cancelled

    def _on_execution_critical(self, kind: str, reason: str) -> None:
        if kind == "user_stream_down" and self._stopping:
            return  # the stop closes the stream itself; its own close is not a drop
        severity, sticky = CRITICAL_RESPONSE.get(kind, (KillSeverity.CANCEL_OPEN, True))
        self.kill.engage(kind, reason, severity=severity, sticky=sticky)

    def _journal_event(self, row: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            self.engine._write(row)
        # A sticky engagement of the maker's kill switch is an incident like the session's
        # own: persisted in the incidents table and pushed to the alert webhook, so an
        # operator away from the dashboard hears about it. An operator stop is not one.
        if row.get("kind") == "kill_switch" and row.get("action") == "engage" and row.get("sticky") and row.get("trigger") != "stop":
            with contextlib.suppress(Exception):
                self._incident(f"mm_{row.get('trigger', 'kill_switch')}", reason=str(row.get("reason", ""))[:500], actor=str(row.get("actor", "system")), detail={"severity": row.get("severity"), "cancelled": row.get("cancelled", 0), "venue": self.venue_label, "is_live": self.is_live})

    def _incident(self, kind: str, *, reason: str, actor: str, detail: dict[str, Any]) -> None:
        now = self.clock.now()
        self._enqueue(
            "incident",
            {
                "incident_id": deterministic_id("inc", self.run_id, kind, now),
                "at": now,
                "kind": kind[:32],
                "actor": actor[:120],
                "reason": reason,
                "run_id": self.run_id,
                "detail": detail,
            },
        )

    def _note_operator(self, action: str, reason: str, actor: str) -> None:
        row = {"t": self._now_ms(), "kind": "operator", "action": action, "reason": reason, "actor": actor}
        self.operator_events.append(row)
        self._journal_event(row)

    # ------------------------------------------------------------------ reconciliation

    async def reconcile(self, *, initial: bool = False, final: bool = False) -> MMReconciliationReport:
        """Open orders, balances and trades from the venue against the adapter and the
        ledger. Critical findings engage the kill switch (except at start, where the
        caller does, so the service is up and visible in its safe state)."""
        if self._reconciling and self.last_report is not None:
            return self.last_report
        self._reconciling = True
        t = self._now_ms()
        try:
            snapshot_t = self._now_ms()  # the venue's open orders are a picture taken now, read later
            venue_open = await self.execution.fetch_open_orders()
            quote_free, quote_locked, base_free, base_locked = await self._fetch_balances()
            quote = quote_free + quote_locked
            base_total = base_free + base_locked
            trades = await self.execution.fetch_trades()
            mark = self.market.book.mid if self.market.book.is_valid else None
            balances: dict[str, Any] = {
                "venue_quote_usd": quote, "venue_quote_free": quote_free, "venue_quote_locked": quote_locked,
                "venue_base_btc": base_total, "venue_base_free": base_free, "venue_base_locked": base_locked,
                "mark_price": mark, "capital_cap_usd": self.capital_cap_usd, "max_inventory_btc": self.config.limits.max_inventory_btc,
            }
            self.execution.absorb_balances(
                [AccountBalance(asset=self._quote_asset, free=quote_free, locked=quote_locked), AccountBalance(asset=self._base_asset, free=base_free, locked=base_locked)],
                t,
            )
            balance_issue: dict[str, Any] | None = None
            if initial:
                self.live_ledger.seed(quote_free=quote_free, quote_locked=quote_locked, base_free=base_free, base_locked=base_locked, mark_price=mark or 0.0, t_ms=t)
                balances["historical_trades"] = self.execution.set_trade_baseline(trades, at_ms=t)
                if quote_free < self.filters.min_notional:
                    balances["funding_note_bid"] = f"quote free {quote_free} below the minimum notional {self.filters.min_notional}: no bid can be funded"
                if base_free < self.filters.min_qty:
                    balances["funding_note_ask"] = f"base free {base_free} below the minimum quantity {self.filters.min_qty}: no ask can be funded"
            else:
                self.execution.absorb_trades(trades)
                # Book the trades in hand before judging balances — on the final pass too: a
                # fill the stream never reported (a partial fill under a dropped stream, a
                # cancel response that carried executed quantity) is in this history and in
                # nothing else, and after stop() there is no next reconciliation to catch it.
                # The engine's tick applies the adapter's outcomes; with the stop engaged the
                # gate blocks, so the tick places nothing.
                self.engine.on_event("tick", None, t)
                expected_quote, expected_base = self.live_ledger.expected_balances()
                balances.update({"expected_quote_usd": round(expected_quote, 6), "expected_base_btc": round(expected_base, 8)})
                balance_issue = compare_balances(
                    expected_quote_usd=expected_quote, expected_base_btc=expected_base,
                    venue_quote_usd=quote, venue_base_btc=base_total,
                    quote_tolerance_usd=self._quote_tolerance_usd, base_tolerance_btc=self._base_tolerance_btc,
                )
                if balance_issue is not None:
                    # Trades the venue has not listed yet make a one-off mismatch; two in a
                    # row is a fact, and the venue's figures are adopted. The final pass has
                    # no next reconciliation: a mismatch there is adopted and reported as such.
                    self._balance_mismatch_streak += 1
                    if self._balance_mismatch_streak < 2 and not final:
                        balance_issue = {**balance_issue, "severity": "warning", "detail": "first mismatch: re-checked at the next reconciliation before anything is adopted"}
                    else:
                        self.live_ledger.reconcile_balances(quote_free=quote_free, quote_locked=quote_locked, base_free=base_free, base_locked=base_locked, t_ms=t, quote_tolerance_usd=self._quote_tolerance_usd, base_tolerance_btc=self._base_tolerance_btc)
                else:
                    self._balance_mismatch_streak = 0
                    self.live_ledger.note_venue_balances(quote_free=quote_free, quote_locked=quote_locked, base_free=base_free, base_locked=base_locked, t_ms=t)
            order_issues = compare_orders(
                local_open=self.execution.open_orders(),
                local_unknown=self.execution.unknown_orders(),
                venue_open=venue_open,
                local_closed=list(self.execution.closed),
                snapshot_t_ms=snapshot_t,
                foreign_is_critical=self.execution.foreign_orders_critical,
            )
            # An order closed here and open in the snapshot: once is the snapshot's age (the
            # adapter asks the venue by id on the next drain); seen in two consecutive
            # reconciliations it is a zombie the venue holds, and that is critical.
            seen_now: set[str] = set()
            for issue in order_issues:
                if issue["kind"] == MMDiscrepancy.LOCAL_CLOSED_VENUE_OPEN.value:
                    cid = str(issue["order_id"])
                    seen_now.add(cid)
                    streak = self._closed_open_streak.get(cid, 0) + 1
                    self._closed_open_streak[cid] = streak
                    issue["consecutive"] = streak
                    if streak >= 2:
                        issue["severity"] = "critical"
                        issue["detail"] = "closed here, still open at the venue in two consecutive reconciliations: an order nobody manages"
            for cid in [c for c in self._closed_open_streak if c not in seen_now]:
                self._closed_open_streak.pop(cid, None)
            self.execution.absorb_open_orders(venue_open)
            report = build_report(
                t_ms=t, order_issues=order_issues, balance_issue=balance_issue,
                venue_open=len(venue_open), local_open=len(self.execution.open_orders()),
                balances=balances, trades_seen=len(trades), initial=initial,
            )
        except Exception as exc:
            self.reconciliation_failures += 1
            detail = f"{type(exc).__name__}: {str(exc)[:200]}"
            _log.error("mm_live_reconciliation_failed", error=detail)
            report = build_report(
                t_ms=t,
                order_issues=[{"kind": "reconciliation_failed", "severity": "critical", "detail": detail}],
                balance_issue=None,
                venue_open=-1,
                local_open=len(self.execution.open_orders()),
                balances={},
                trades_seen=0,
                initial=initial,
            )
            if not initial:
                self.kill.engage("reconciliation", f"reconciliation failed: {detail}", severity=KillSeverity.NO_NEW_QUOTES, sticky=True)
        finally:
            self._reconciling = False
        self.reconciliations += 1
        self.last_report = report
        self._journal_event({"t": t, "kind": "reconciliation", **report.as_dict()})
        if report.critical and not initial and not final:
            self.kill.engage("reconciliation", report.summary, severity=KillSeverity.CANCEL_OPEN, sticky=True)
        return report

    async def _fetch_balances(self) -> tuple[float, float, float, float]:
        """(quote free, quote locked, base free, base locked) from the venue. A provider
        that reports free and locked per asset is asked for both; one that only reports a
        free quote balance and a base position is read as free with nothing locked."""
        per_asset = getattr(self.provider, "get_balances", None)
        if per_asset is not None:
            balances = await per_asset()
            quote = balances.get(self._quote_asset)
            base = balances.get(self._base_asset)
            return (
                float(quote.free) if quote is not None else 0.0,
                float(quote.locked) if quote is not None else 0.0,
                float(base.free) if base is not None else 0.0,
                float(base.locked) if base is not None else 0.0,
            )
        quote_free = float(await self.provider.get_balance())
        positions = await self.provider.get_positions()
        position = positions.get(self.config.symbol)
        return quote_free, 0.0, float(position.quantity) if position is not None else 0.0, 0.0

    # ------------------------------------------------------------------ reading

    def status(self) -> dict[str, Any]:
        token = self.activation
        activation = None
        if token is not None:
            now = self.clock.now()
            activation = {
                "present": True,
                "valid": bool(token.is_valid_at(now)),
                "issued_by": token.issued_by,
                "issued_at": token.issued_at.isoformat(),
                "expires_at": token.expires_at.isoformat(),
                "seconds_remaining": round(float(token.seconds_remaining(now)), 1),
                "max_live_capital": token.max_live_capital,
            }
        engine = self.engine
        return {
            "mode": "live",
            "venue": self.venue_label,
            "is_live": self.is_live,
            "running": self._running,
            "state": self.state_label,
            "run_id": self.run_id,
            "symbol": self.config.symbol,
            "started_at_ms": self.started_at_ms,
            "stopped_at_ms": self.stopped_at_ms,
            "stop_reason": self.stop_reason,
            "activation": activation,
            "capital_cap_usd": self.capital_cap_usd,
            "kill_switch": self.kill.as_dict(),
            "gate": engine.last_gate.as_dict() if engine.last_gate else None,
            "last_block_reason": engine.last_block_reason,
            "reconciliation": {
                "last": self.last_report.as_dict() if self.last_report else None,
                "count": self.reconciliations,
                "failures": self.reconciliation_failures,
                "interval_s": self._reconcile_interval_s,
                "balance_mismatch_streak": self._balance_mismatch_streak,
            },
            "execution": self.execution.stats(),
            "open_orders": [o.as_dict() for o in self.execution.open_orders()],
            "unknown_orders": [o.as_dict() for o in self.execution.unknown_orders()],
            "authorizations": engine.last_authorizations,
            "authorization_blocks": engine.authorization_blocks,
            "authorization_side_removals": engine.authorization_side_removals,
            "ledger": self.live_ledger.snapshot(),
            "heartbeats": self.heartbeats,
            "user_stream": self.user_stream.as_dict() if self.user_stream is not None and hasattr(self.user_stream, "as_dict") else {"wired": self.user_stream is not None},
            "latency": {
                "market_event_to_processed_ms": self.event_to_processed_ms.as_dict(),
                "callback_ms": self.callback_ms.as_dict(),
                **self.execution.stats()["latency"],
            },
            "counts": {"events": engine.events, "decisions": engine.decisions, "quotes": engine.quotes, "requotes": engine.requotes, "cancels": engine.cancels, "gate_blocks": engine.gate_blocks, "data_blocks": engine.data_blocks},
            "data": {"usable": self.market.usable, "freshness": self.market.freshness()[0].value},
            "economics": self.economics_config.as_dict(),
            "filters": self.filters.as_dict(),
            "operator_events": list(self.operator_events)[-10:],
            "engine_errors": self.engine_errors,
            "last_engine_error": self.last_engine_error,
        }

    def snapshot(self) -> dict[str, Any]:
        return {**super().snapshot(), "live": self.status()}


__all__ = ["CRITICAL_RESPONSE", "LiveMarketMakerService"]
