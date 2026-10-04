#!/usr/bin/env python
"""Run the live market-making **service** against Binance Spot Testnet for a few minutes.

``scripts/validate_mm_testnet.py`` proves the building blocks one at a time: REST, the signed
account stream, one post-only order, its cancel, the reconciliation. This script proves the
assembly the operator would actually start: ``LiveMarketMakerService.start_live()`` — the
initial reconciliation, the ledger seeded from the venue's balances, the engine quoting on
Testnet market data, cancel/replace through the real adapter, the account stream feeding
execution reports, periodic reconciliation, the kill switch, and ``stop()`` with its final
reconciliation. It is the path ``POST /api/mm/live/start`` takes, without the API, without the
database and without the production configuration.

Rails, every one checked before anything connects:

* Testnet only: REST, account stream and market data stream must all be ``testnet.binance.vision``
  hosts; a mainnet host in any of the three is a refusal;
* the provider is simulated by construction (``is_live`` False) and no activation token exists
  or can be minted here; ``TIA_MM__REAL_MONEY`` is read by nothing;
* the market maker's own rules apply unchanged: LIMIT_MAKER only, the maker-only validation
  against the local book, the risk and economics authorizers, the kill switch, the strict
  cancel/replace. This script configures sizes and caps; it relaxes nothing;
* on exit, success or failure, the service is stopped (cancel everything, wait for the venue,
  reconcile) and the venue is asked again, with a fresh client, whether any order of this
  maker is still open.

What a run can and cannot show. Testnet's book is thin and its prices are its own, so the
economics authorizer may deny every quote and the engine may cancel more than it rests; both
are recorded as what happened, not as failures of the plumbing. A fill is welcome and is
checked, never provoked. Nothing here is evidence about profitability.

Usage (from the VPS, in the same one-off container as the block validation):

    python scripts/validate_mm_live_service_testnet.py --minutes 3 \\
        --profile /app/data/runtime/mm/latency_profile.json --json-out /out/mm_service_testnet.json

The latency profile is the one measured on that host (``mm_market_data_check.py
--write-latency-profile``); the engine refuses to run without a measured one, by design.
For a Testnet run, measure it against Testnet (``--rest-url https://testnet.binance.vision
--stream-url wss://stream.testnet.binance.vision/stream``) into a directory of its own and
bind-mount that directory at ``/app/data/runtime`` read-only; the production data volume
holds the profile the paper maker measured against Mainnet public data and is not the
place for it. ``scripts/run_mm_service_testnet_validation.sh`` does the whole sequence.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from validate_mm_testnet import REST_URL, TESTNET_HOST, WS_URL, Evidence, Rails, _env_live_config

from tia.core.clock import SystemClock
from tia.data.providers.binance_live import BinanceExecutionProvider
from tia.data.providers.binance_public import BinancePublicProvider
from tia.data.providers.binance_signing import signer_from_live_config
from tia.data.providers.binance_user_stream import BinanceUserDataStream
from tia.mm.authorization import EconomicsConfig
from tia.mm.engine import MarketMakerConfig
from tia.mm.execution import CLIENT_ID_PREFIX, SymbolFilters
from tia.mm.latency_model import LatencyProfile, LatencyProfileError
from tia.mm.live_service import LiveMarketMakerService
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.quoting import QuotingConfig
from tia.mm.streams import MarketDataStream

STREAM_URL = "wss://stream.testnet.binance.vision/stream"
MAINNET_MARKERS = ("api.binance.com", "stream.binance.com", "ws-api.binance.com", "data-stream.binance.vision")


async def _wait_until(predicate: Any, seconds: float, step: float = 0.1) -> bool:
    """Poll ``predicate`` for up to ``seconds``; True as soon as it holds."""
    deadline = time.monotonic() + seconds
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(step)


def _check_stream_rail(stream_url: str) -> None:
    if TESTNET_HOST not in stream_url:
        raise SystemExit(f"REFUSED: the market data stream URL {stream_url!r} is not a Testnet host")
    if any(marker in stream_url for marker in MAINNET_MARKERS):
        raise SystemExit("REFUSED: a mainnet market data host was configured")


class ServiceValidation:
    def __init__(self, args: argparse.Namespace, live: Any) -> None:
        self.args = args
        self.live = live
        self.ev = Evidence()
        self.clock = SystemClock()
        self.samples: list[dict[str, Any]] = []
        self.service: LiveMarketMakerService | None = None
        self.market: MarketDataService | None = None
        self.provider: BinanceExecutionProvider | None = None
        self.public: BinancePublicProvider | None = None
        self.filters: SymbolFilters | None = None
        self.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.final_status: dict[str, Any] | None = None
        self.stop_result: dict[str, Any] | None = None
        self.open_after_stop: list[str] | None = None
        self.config: MarketMakerConfig | None = None
        self.profile: LatencyProfile | None = None
        self.first_run_status: dict[str, Any] | None = None  # the recovery drill's dead run, as it was when it died

    def now_ms(self) -> int:
        return self.clock.timestamp_ms()

    # ------------------------------------------------------------------ assembly

    async def build(self) -> None:
        ev = self.ev
        args = self.args
        signer = signer_from_live_config(self.live, self.clock)
        self.provider = BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=args.rest_url, simulated=True)
        self.public = BinancePublicProvider(base_url=args.rest_url, clock=self.clock)
        ev.mark("S0.provider_is_simulated_without_token", "PASS" if not self.provider.is_live and self.provider.activation is None else "FAIL", f"is_live={self.provider.is_live} activation={self.provider.activation}")

        try:
            profile = LatencyProfile.load(args.profile)
        except LatencyProfileError as exc:
            ev.mark("S0.latency_profile_measured_on_this_host", "NOT TESTED", str(exc)[:200])
            raise SystemExit(f"NOT TESTED: {exc}") from exc
        ev.mark("S0.latency_profile_measured_on_this_host", "PASS", f"profile {profile.profile_id} commit {profile.commit} measured {profile.measured_at_utc} source {profile.source or 'not recorded'}")

        ev.command(f"provider.get_exchange_info({args.symbol})  [GET /api/v3/exchangeInfo]")
        info = await self.provider.get_exchange_info(args.symbol)
        venue_symbol = BinanceExecutionProvider.to_venue_symbol(args.symbol)
        self.filters = SymbolFilters.from_exchange_info(info, symbol=args.symbol, venue_symbol=venue_symbol)
        f = self.filters
        ev.responses["filters"] = f.as_dict()
        ev.mark("S0.exchange_filters_read", "PASS", f"tick {f.tick_size} step {f.step_size} minQty {f.min_qty} minNotional {f.min_notional}")

        quote_size = args.quote_size
        quoting = QuotingConfig(base_quote_size_btc=quote_size, tick_size=f.tick_size, size_step=f.step_size, min_size_btc=max(0.0001, f.min_qty))
        config = MarketMakerConfig(symbol=args.symbol, quoting=quoting)
        ev.responses["quoting"] = {"base_quote_size_btc": quote_size, "tick_size": f.tick_size, "size_step": f.step_size, "min_size_btc": quoting.min_size_btc, "limits": config.limits.as_dict()}

        public = self.public

        async def fetch_snapshot():  # type: ignore[no-untyped-def]
            book = await public.depth_snapshot(args.symbol, limit=args.depth_limit)
            return snapshot_from_levels(book.last_update_id or 0, [(lvl.price, lvl.size) for lvl in book.bids], [(lvl.price, lvl.size) for lvl in book.asks])

        stream = MarketDataStream(args.symbol, stream_url=args.stream_url, depth_speed="100ms")
        self.market = MarketDataService(args.symbol, stream=stream, fetch_snapshot=fetch_snapshot, recorder=None)
        self.config, self.profile = config, profile
        self.service = self._assemble_service(run_id="mm-testnet-service")
        ev.mark("S0.service_assembled_like_the_api_would", "PASS", "LiveMarketMakerService + BinanceUserDataStream + MarketDataService on Testnet URLs; capital cap " + (f"{args.capital_cap_usd} USD" if args.capital_cap_usd > 0 else "none"))

    def _new_provider(self) -> BinanceExecutionProvider:
        signer = signer_from_live_config(self.live, self.clock)
        return BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=self.args.rest_url, simulated=True)

    def _assemble_service(self, *, run_id: str) -> LiveMarketMakerService:
        """The service exactly as ``POST /api/mm/live/start`` would build it, on the current
        provider: the maker, its account stream, the market data already running."""
        assert self.market is not None and self.provider is not None and self.filters is not None and self.config is not None and self.profile is not None
        args = self.args
        service = LiveMarketMakerService(
            market=self.market,
            config=self.config,
            profile=self.profile,
            scenario=args.scenario,
            run_id=run_id,
            risk_state=lambda: None,  # no directional session here: the gate reads data validity and the kill switch
            provider=self.provider,
            clock=self.clock,
            filters=self.filters,
            activation=None,
            capital_cap_usd=args.capital_cap_usd if args.capital_cap_usd > 0 else None,
            economics=EconomicsConfig(min_net_edge_bps=args.min_net_edge_bps),
            reconcile_interval_s=args.reconcile_interval,
            trades_poll_interval_s=3.0,
            open_sync_interval_s=10.0,
            venue_label="binance-spot-testnet",
        )
        user_stream = BinanceUserDataStream(
            self.provider,
            now_ms=self.now_ms,
            on_report=service.execution.absorb_execution_report,
            on_balances=service.execution.absorb_balances,
            on_status=service.execution.absorb_stream_status,
            base_url=args.ws_url,
        )
        service.attach_user_stream(user_stream)
        return service

    async def _own_open_at_venue(self) -> list[str]:
        """The venue's open orders of this maker's prefix, asked with a fresh client so the
        answer does not depend on any adapter's mirror."""
        fresh = self._new_provider()
        try:
            open_orders = await fresh.get_orders(open_only=True, symbol=self.args.symbol)
            return sorted(o.client_order_id for o in open_orders if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX))
        finally:
            await fresh.close()

    # ------------------------------------------------------------------ the run

    async def run(self) -> int:
        ev = self.ev
        args = self.args
        failed = False
        try:
            await self.build()
            assert self.market is not None and self.service is not None
            ev.command(f"MarketDataService.start()  [{args.stream_url}; snapshot GET {args.rest_url}/api/v3/depth]")
            self.market.start()
            await _wait_until(lambda: bool(self.market and self.market.usable), 60.0)
            snap = self.market.snapshot(levels=1)
            ev.responses["market_at_start"] = {k: snap.get(k) for k in ("usable", "not_usable_reason", "freshness")}
            ev.mark("S1.testnet_market_data_usable", "PASS" if self.market.usable else "FAIL", f"usable={self.market.usable} {snap.get('not_usable_reason') or ''}".strip())
            if not self.market.usable:
                raise RuntimeError("Testnet market data never became usable; the engine would not quote")

            ev.command("service.start_live()  [check_grid, worker, account stream, initial reconciliation, ledger seed, subscribe]")
            report = await self.service.start_live()
            ev.responses["initial_reconciliation"] = report.as_dict()
            ev.mark("S2.initial_reconciliation_completed", "PASS" if not report.critical else "FAIL", report.summary)
            ledger = self.service.live_ledger.snapshot()
            ev.responses["ledger_after_seed"] = ledger
            ev.mark("S2.ledger_seeded_from_venue_balances", "PASS" if self.service.live_ledger.seeded else "FAIL", f"seeded={self.service.live_ledger.seeded}")
            up = await _wait_until(lambda: self.service is not None and self.service.user_stream is not None and bool(self.service.user_stream.connected), 20.0)
            ev.mark("S3.account_stream_subscribed_through_the_service", "PASS" if up else "FAIL", f"connected={up} subscriptionId={getattr(self.service.user_stream, 'subscription_id', None)} last_error={getattr(self.service.user_stream, 'last_error', '')!r}")

            await self._observe(args.minutes * 60.0)
            if args.recovery_drill:
                await self.recovery_drill()
        except SystemExit:
            raise
        except Exception as exc:
            failed = True
            print(f"\nSTOPPED: {type(exc).__name__}: {str(exc)[:300]}")
            ev.notes["stopped"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            await self.shutdown()
        self.judge()
        return 1 if failed or any(v == "FAIL" for v in ev.results.values()) else 0

    async def recovery_drill(self) -> None:
        """RECOVERY — the running service dies with quotes resting: no stop(), no cancel (the
        engine stops hearing the market, the loops are cancelled, the account stream and the
        worker are cut). A second service starts on the same account with a fresh client, as a
        restarted process would: it must find the dead run's orders under its own prefix and
        cancel them before placing anything, reconcile clean, quote with its own ids, and never
        resubmit a client id. The venue is asked with a fresh client at every step; the
        S-items that follow judge the second run, and stop() runs on it."""
        ev = self.ev
        first = self.service
        assert first is not None and self.provider is not None
        print("\nRECOVERY DRILL — the first run dies with orders resting; a second run starts on the same account")
        await _wait_until(lambda: any(o.state == "resting" for o in first.execution.open_orders()), 60.0)
        left = sorted(o.order_id for o in first.execution.open_orders() if o.state == "resting")
        drill: dict[str, Any] = {"left_by_first_run": left}
        ev.responses["recovery_drill"] = drill
        if not left:
            ev.mark("R1.first_run_died_with_orders_resting", "NOT TESTED", f"nothing was resting to leave behind: {first.engine.last_block_reason!r}")
            return
        ev.command("first run dies: market subscription dropped, loops cancelled, account stream and worker cut — no stop(), no cancel")
        if first._unsubscribe is not None:
            first._unsubscribe()
            first._unsubscribe = None
        for task in (first._reconcile_task, first._heartbeat_task):
            if task is not None:
                task.cancel()
        with contextlib.suppress(Exception):
            if first.user_stream is not None:
                await first.user_stream.close()
        worker = getattr(first.execution, "_worker", None)
        if worker is not None:
            worker.cancel()  # a crash does not drain its queue
        await asyncio.sleep(0.2)
        self.first_run_status = first.status()
        still = await self._own_open_at_venue()
        drill["open_at_venue_after_death"] = still
        ev.command(f"GET /api/v3/openOrders  [fresh client]  — the venue still holds the dead run's orders: {still}")
        ev.mark("R1.first_run_died_with_orders_resting", "PASS" if set(left) <= set(still) else "FAIL", f"resting locally when it died {left}; open at the venue {still}")

        # The second run: a fresh provider, a fresh account stream, the same market data.
        with contextlib.suppress(Exception):
            await self.provider.close()
        self.provider = self._new_provider()
        second = self._assemble_service(run_id="mm-testnet-service-restarted")
        self.service = second
        ev.command("second run: service.start_live()  [orphan sweep by id, initial reconciliation, ledger seed]")
        report = await second.start_live()
        sweep = second.orphan_sweep or {}
        drill["sweep"] = sweep
        drill["initial_reconciliation_second_run"] = report.as_dict()
        cancelled = sorted(c["order_id"] for c in sweep.get("cancelled", []))
        ev.mark("R2.orphans_found_and_cancelled_before_quoting", "PASS" if sorted(sweep.get("found", [])) == still and cancelled == still and not sweep.get("failed") else "FAIL", f"found {sweep.get('found')} cancelled {cancelled} failed {sweep.get('failed')}")
        ev.mark("R3.initial_reconciliation_clean_after_the_sweep", "PASS" if not report.critical else "FAIL", report.summary)
        after = await self._own_open_at_venue()
        drill["open_at_venue_after_sweep"] = after
        ev.mark("R4.no_order_of_the_dead_run_open_at_the_venue", "PASS" if not (set(after) & set(left)) else "FAIL", f"open at the venue after the sweep {after}")
        up = await _wait_until(lambda: bool(second.user_stream is not None and second.user_stream.connected), 20.0)
        ev.mark("R5.second_run_account_stream_subscribed", "PASS" if up else "FAIL", f"connected={up} subscriptionId={getattr(second.user_stream, 'subscription_id', None)}")
        await self._observe(min(60.0, max(20.0, self.args.minutes * 60.0 / 3)))
        placed = second.execution.counters["placed"]
        own = f"{CLIENT_ID_PREFIX}{second.execution.run_tag[:8]}"
        open_now = await self._own_open_at_venue()
        drill["open_at_venue_while_second_run_quotes"] = open_now
        not_ours = [cid for cid in open_now if not cid.startswith(own)]
        ev.mark("R6.second_run_quotes_with_its_own_ids_only", "PASS" if placed > 0 and not not_ours else ("NOT TESTED" if placed == 0 and not not_ours else "FAIL"), f"placed {placed}; open at the venue {open_now}; not this run's {not_ours}")
        known = {o.order_id for o in list(second.execution.closed) + list(second.execution.orders.values())}
        ev.mark("R7.no_client_id_of_the_dead_run_adopted_or_resubmitted", "PASS" if not (known & set(left)) and second.execution.counters["venue_orders_unknown_locally"] == 0 else "FAIL", f"dead run's ids known to the second run {sorted(known & set(left))}; venue_orders_unknown_locally {second.execution.counters['venue_orders_unknown_locally']}")

    async def _observe(self, seconds: float) -> None:
        assert self.service is not None
        print(f"\nOBSERVING for {seconds:g} s — the engine quotes (or says why not), the adapter cancels and replaces, the stream reports")
        start = time.monotonic()
        next_sample = start
        while time.monotonic() - start < seconds:
            if time.monotonic() >= next_sample:
                self.samples.append(self._sample())
                s = self.samples[-1]
                print(f"  t+{s['t_s']:>5.0f}s quotes {s['counts']['quotes']:>4} placed {s['placed']:>4} acked {s['acked']:>4} cancelled {s['cancelled']:>4} would_cross {s['rejected_would_cross']:>3} fills {s['fills']:>2} unknown {s['unknown_open']} open {s['open_orders']} kill={s['kill_engaged']} gate={s['gate_state']} block={s['last_block_reason'][:60]!r}")
                next_sample += self.args.sample_seconds
            await asyncio.sleep(0.2)

    def _sample(self) -> dict[str, Any]:
        assert self.service is not None
        st = self.service.status()
        c = st["execution"]  # the adapter's counters are flattened into its stats
        kill = st["kill_switch"]
        return {
            "t_s": round(time.monotonic() - self._t0(), 1),
            "counts": st["counts"],
            "placed": c["placed"], "acked": c["acked"], "cancelled": c["cancelled"], "rejected": c["rejected"], "rejected_would_cross": c["rejected_would_cross"],
            "fills": c["fills"], "unknown": c["unknown"], "unknown_open": len(st["unknown_orders"]), "open_orders": len(st["open_orders"]),
            "refused_validation": c["refused_validation"], "refused_blocked": c["refused_blocked"], "deferred_cancel_pending": c["deferred_cancel_pending"],
            "kill_engaged": kill.get("engaged"), "kill": kill,
            "gate_state": (st["gate"] or {}).get("state"), "last_block_reason": st["last_block_reason"] or "",
            "authorization_blocks": st["authorization_blocks"], "authorization_side_removals": st["authorization_side_removals"],
            "authorizations": st["authorizations"],
            "reconciliations": st["reconciliation"]["count"], "reconciliation_failures": st["reconciliation"]["failures"],
            "stream_connected": st["user_stream"].get("connected"), "stream_reports": st["user_stream"].get("reports"),
            "heartbeats": st["heartbeats"], "data_usable": st["data"]["usable"], "engine_errors": st["engine_errors"],
            "ledger": {k: st["ledger"].get(k) for k in ("cash_usd", "inventory_btc", "fills", "realised_pnl_usd", "fees_usd") if k in st["ledger"]},
        }

    def _t0(self) -> float:
        if not hasattr(self, "_t0_value"):
            self._t0_value = time.monotonic()
        return self._t0_value

    # ------------------------------------------------------------------ shutdown and verdicts

    async def shutdown(self) -> None:
        ev = self.ev
        print("\nSHUTDOWN — stop (cancel, wait for the venue, reconcile), then ask the venue again with a fresh client")
        if self.service is not None and (self.service.is_running or self.service.execution.open_orders()):
            try:
                ev.command("service.stop()  [cancel_all, drain until quiet, final reconciliation, close]")
                self.stop_result = await self.service.stop(reason="validation window elapsed", actor="validate_mm_live_service_testnet")
                self.final_status = self.stop_result
            except Exception as exc:
                ev.mark("S12.stop_completed", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
        elif self.service is not None:
            self.final_status = self.service.status()
        if self.service is not None:
            with contextlib.suppress(Exception):
                await self.service.close()
        if self.market is not None:
            with contextlib.suppress(Exception):
                await self.market.close()
        if self.public is not None:
            with contextlib.suppress(Exception):
                await self.public.close()
        # A fresh client, so the question does not depend on what stop() closed.
        try:
            signer = signer_from_live_config(self.live, self.clock)
            fresh = BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=self.args.rest_url, simulated=True)
            try:
                ev.command(f"GET /api/v3/openOrders?symbol={BinanceExecutionProvider.to_venue_symbol(self.args.symbol)}  [fresh client]")
                open_orders = await fresh.get_orders(open_only=True, symbol=self.args.symbol)
                self.open_after_stop = [o.client_order_id for o in open_orders if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX)]
                for cid in list(self.open_after_stop):
                    # Should never happen after stop(); if it does, cancel and say so.
                    with contextlib.suppress(Exception):
                        await fresh.resolve_unknown_order(symbol=self.args.symbol, client_order_id=cid)
                        await fresh.cancel_order(cid)
            finally:
                await fresh.close()
        except Exception as exc:
            ev.notes["open_orders_check"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    def judge(self) -> None:
        ev = self.ev
        st = self.final_status
        if st is None:
            ev.mark("S12.stop_completed", "FAIL", "no final status: the service never reached stop()")
            return
        c = st["execution"]  # the adapter's counters are flattened into its stats
        counts = st["counts"]
        last = self.samples[-1] if self.samples else None
        ev.responses["final_status"] = st
        ev.responses["samples"] = self.samples
        ev.mark("S4.engine_processed_market_events", "PASS" if counts["events"] > 0 and counts["decisions"] > 0 else "FAIL", f"events {counts['events']} decisions {counts['decisions']} heartbeats {st['heartbeats']} engine_errors {st['engine_errors']} {st['last_engine_error']!r}")
        blocks = {"gate_blocks": counts["gate_blocks"], "data_blocks": counts["data_blocks"], "authorization_blocks": st["authorization_blocks"], "authorization_side_removals": st["authorization_side_removals"], "refused_validation": c["refused_validation"], "refused_blocked": c["refused_blocked"], "deferred_cancel_pending": c["deferred_cancel_pending"], "last_block_reason": st["last_block_reason"], "last_authorizations": st["authorizations"]}
        ev.responses["why_not_quoting"] = blocks
        if c["placed"] > 0:
            ev.mark("S5.quotes_placed_through_the_real_adapter", "PASS", f"placed {c['placed']} (engine quotes {counts['quotes']}, requotes {counts['requotes']})")
        else:
            ev.mark("S5.quotes_placed_through_the_real_adapter", "NOT TESTED", f"the engine sent nothing: {json.dumps(blocks, default=str)[:400]}")
        if c["placed"] > 0:
            ev.mark("S6.orders_acknowledged_by_the_venue", "PASS" if c["acked"] > 0 else "FAIL", f"acked {c['acked']} rejected {c['rejected']} (would cross: {c['rejected_would_cross']}, the post-only rail) unknown {c['unknown']}")
            ev.mark("S7.cancel_replace_through_the_venue", "PASS" if c["cancelled"] > 0 and c["unknown"] == 0 else ("NOT TESTED" if c["cancelled"] == 0 and c["unknown"] == 0 else "FAIL"), f"cancel requests {c['cancel_requests']} cancelled {c['cancelled']} expired {c['expired']} unknown {c['unknown']} cancel_rejected_after_close {c['cancel_rejected_after_close']}")
        else:
            ev.mark("S6.orders_acknowledged_by_the_venue", "NOT TESTED", "nothing was placed")
            ev.mark("S7.cancel_replace_through_the_venue", "NOT TESTED", "nothing was placed")
        ledger = st["ledger"]
        if c["fills"] > 0:
            ev.mark("S8.fills_booked_once_into_the_ledger", "PASS" if ledger.get("fills") == c["fills"] and c["duplicate_trades"] >= 0 else "FAIL", f"real_testnet_fill: execution fills {c['fills']} (reports {c['report_fills']}, trade poll {c['trade_poll_fills']}, duplicates recognised {c['duplicate_trades']}) ledger fills {ledger.get('fills')} inventory {ledger.get('inventory_btc')}")
        else:
            ev.mark("S8.fills_booked_once_into_the_ledger", "NOT TESTED", "no fill occurred (not provoked); the fill paths are SYNTHETIC ONLY here (tests/unit/mm, tests/adversarial), which is not evidence about Binance")
        rec = st["reconciliation"]
        ev.mark("S9.periodic_reconciliation_ran", "PASS" if rec["count"] >= 2 and rec["failures"] == 0 else ("FAIL" if rec["failures"] else "NOT TESTED"), f"reconciliations {rec['count']} failures {rec['failures']} interval {rec['interval_s']} s last ok={((rec.get('last') or {}).get('ok'))} critical={((rec.get('last') or {}).get('critical'))}")
        # The kill switch, in two readings. Before stop(): a sticky engagement means a critical
        # finding stopped the maker for good during the run — that is what the item judges;
        # transient engagements (stale market data, a stream drop) are the rails working and
        # are recorded, not failed. After stop(): a deliberate shutdown is its own state, not
        # a safety engagement — it must be recorded as such, no sticky safety engagement may
        # remain (one would mean a critical finding preceded the stop), and no transient
        # condition may survive a service that can no longer observe it.
        kill_before = (last or {}).get("kill") or {}
        history = (st["kill_switch"].get("history") or [])
        engagements = [(h.get("trigger"), h.get("sticky"), h.get("action")) for h in history if h.get("action") == "engage"]
        ev.responses["kill_switch_engagements"] = history
        if kill_before.get("sticky"):
            ev.mark("S10.no_sticky_kill_during_the_run", "FAIL", f"sticky before stop: trigger={kill_before.get('trigger')!r} reason={kill_before.get('reason')!r}; engagements {engagements}")
        else:
            ev.mark("S10.no_sticky_kill_during_the_run", "PASS", f"transient engagements during the run: {[t for t, sticky, _ in engagements if not sticky]}; none sticky")
        kill = st["kill_switch"]
        shutdown_ok = bool(kill.get("shutdown")) and not kill.get("sticky") and not kill.get("transient") and not kill.get("engaged")
        ev.mark("S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left", "PASS" if shutdown_ok else "FAIL", json.dumps({k: kill.get(k) for k in ("engaged", "sticky", "trigger", "reason", "severity", "transient", "shutdown", "blocks_quoting")}, default=str)[:400])
        ev.mark("S11.no_unknown_orders", "PASS" if not st["unknown_orders"] and c["unknown"] == 0 else "FAIL", f"unknown counter {c['unknown']} open unknown {len(st['unknown_orders'])}")
        stream = st["user_stream"]
        ev.mark("S3b.account_stream_reports_received", "PASS" if (stream.get("reports") or 0) > 0 else ("NOT TESTED" if c["placed"] == 0 else "FAIL"), f"reports {stream.get('reports')} balance_updates {stream.get('balance_updates')} disconnects {stream.get('disconnects')} reconnects {stream.get('reconnects')}")
        if self.stop_result is not None:
            ev.mark("S12.stop_completed", "PASS" if not st["running"] and not st["open_orders"] else "FAIL", f"running={st['running']} open locally {len(st['open_orders'])} stop_reason={st['stop_reason']!r}")
        if self.open_after_stop is not None:
            ev.mark("S12b.no_open_orders_at_the_venue_after_stop", "PASS" if not self.open_after_stop else "FAIL", f"{len(self.open_after_stop)} open {CLIENT_ID_PREFIX} order(s) found and cancelled: {self.open_after_stop}" if self.open_after_stop else "none")
        else:
            ev.mark("S12b.no_open_orders_at_the_venue_after_stop", "FAIL", ev.notes.get("open_orders_check", "the venue could not be asked"))
        ev.mark("S13.testnet_only_no_token_no_real_money", "PASS" if st["is_live"] is False and st["activation"] is None and all(TESTNET_HOST in u for u in (self.args.rest_url, self.args.ws_url, self.args.stream_url)) else "FAIL", f"is_live={st['is_live']} activation={st['activation']} venue={st['venue']}")
        if last is not None:
            ev.latency_ms["service"] = st["latency"]

    def report(self) -> dict[str, Any]:
        groups: dict[str, list[str]] = {"PASS": [], "FAIL": [], "NOT TESTED": []}
        for item, verdict in self.ev.results.items():
            groups.setdefault(verdict, []).append(item)
        print("\n" + "=" * 72)
        for verdict in ("PASS", "FAIL", "NOT TESTED"):
            print(f"{verdict}:")
            for item in groups[verdict]:
                note = self.ev.notes.get(item, "")
                print(f"  - {item}" + (f": {note}" if note else ""))
        return {
            "script": "validate_mm_live_service_testnet.py",
            "started_utc": self.started_utc,
            "args": dict(vars(self.args)),
            "results": self.ev.results,
            "notes": self.ev.notes,
            "commands": self.ev.commands,
            "responses": self.ev.responses,
            "latency_ms": self.ev.latency_ms,
            "journal_tail": self.service.journal(limit=300) if self.service is not None else [],
            "first_run_status_before_death": self.first_run_status,
            "fill_evidence_kind": "real_testnet_fill" if (self.final_status or {}).get("execution", {}).get("fills", 0) > 0 else None,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--minutes", type=float, default=3.0, help="how long the service runs before stop()")
    parser.add_argument("--profile", default="data/runtime/mm/latency_profile.json", help="the latency profile measured on this host (mm_market_data_check.py --write-latency-profile)")
    parser.add_argument("--scenario", default="baseline", choices=("optimistic", "baseline", "conservative"))
    parser.add_argument("--quote-size", type=float, default=0.0002, help="base quote size in BTC (Testnet assets; above the venue minimum)")
    parser.add_argument("--capital-cap-usd", type=float, default=200.0, help="the maker's capital cap, as the activation token would impose it (0 = none)")
    parser.add_argument("--min-net-edge-bps", type=float, default=0.0)
    parser.add_argument("--reconcile-interval", type=float, default=15.0)
    parser.add_argument("--sample-seconds", type=float, default=5.0)
    parser.add_argument("--depth-limit", type=int, default=1000)
    parser.add_argument("--rest-url", default=REST_URL)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--stream-url", default=STREAM_URL)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--recovery-drill", action="store_true", help="after the window: the service dies with quotes resting (no stop, no cancel) and a second service starts on the same account, which must sweep the dead run's orders before quoting (items R1-R7); stop() then runs on the second run")
    args = parser.parse_args()

    live = _env_live_config(args)
    if live is None:
        print("NOT TESTED: TIA_LIVE__BINANCE_API_KEY / TIA_LIVE__BINANCE_API_SECRET (Testnet keys) are not in the process environment; nothing was attempted")
        return 2
    Rails.check(live, args.rest_url, args.ws_url)
    _check_stream_rail(args.stream_url)
    validation = ServiceValidation(args, live)
    try:
        code = asyncio.run(validation.run())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("interrupted; the shutdown ran in the finally block if the service had started")
        return 130
    payload = validation.report()
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=1, default=str))
        print(f"evidence written to {out}")
    return code


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(main())
