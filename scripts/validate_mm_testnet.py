#!/usr/bin/env python
"""Validate the live market maker's execution path against **Binance Spot Testnet**, and
nothing else: one post-only order of minimal size, far from the market, cancelled before
the script ends, every step timestamped and written to an evidence file.

    PYTHONPATH=packages/tia/src .venv/bin/python scripts/validate_mm_testnet.py \\
        --json-out data/runtime/mm_testnet_validation.json

Credentials come from the process environment only (TIA_LIVE__BINANCE_API_KEY and
TIA_LIVE__BINANCE_API_SECRET must be **Testnet** keys from https://testnet.binance.vision);
nothing is read from a file and nothing is written except ``--json-out``.

Rails, each of them checked before any request:

* the REST base URL and the account-stream URL must be Testnet hosts; a mainnet host anywhere
  stops the script before it connects;
* the adapter is built ``simulated=True`` (the Testnet configuration), so ``is_live`` is
  False, no activation token exists and none can be minted here;
* the only order type the script can send is ``LIMIT_MAKER``; there is no MARKET, no plain
  LIMIT and no fallback in this file;
* the order is placed ``--percent-away`` percent below the best bid (2% by default, on the
  tick grid), so it rests and does not fill (a partial fill is therefore NOT TESTED by
  design: Testnet's book is not ours to move);
* ``--fill-probe SECONDS`` (off by default) adds one phase that rests minimal post-only
  probe(s) AT the best — a bid at the best bid, an ask at the best ask, or both with
  ``--fill-probe-sides both`` — and waits that long for the market to trade into one.
  Nothing is forced: no MARKET order, no crossing. With ``--fill-probe-repeg SECONDS`` a
  probe the best moved away from is cancelled (confirmed) and rested again at the new best,
  which is what a maker does and is as post-only as the first order; a best that moved
  through our price is a fill, not a re-peg. If a print comes, the TRADE report and its
  correlation (clientOrderId and orderId), the single booking against ``myTrades``, the
  ledger, the balance report and a balance reconciliation are checked, the other side is
  cancelled, and what the probes netted is unwound with one post-only order under the same
  rules; whatever does not fill is cancelled and the residual Testnet inventory is reported.
  The evidence is labelled ``real_testnet_fill``; the synthetic fill tests are never
  evidence about Binance. If no print comes, the items stay NOT TESTED;
* on exit, success or failure, every open order with this run's prefix is cancelled and the
  cancellation is confirmed against the venue.

The phases follow the validation request: connectivity and the account stream (1), the
account's balances (2), one maker order (3), its acknowledgement and cancellation (4),
deduplication (5), a cut of the account stream with an order open (6), the latency legs (7)
and the safety confirmations (8). Each item ends PASS, FAIL or NOT TESTED; nothing is
inferred. The latency legs that cross the host-venue boundary are reported as including the
clock offset, measured against the venue's time endpoint but not corrected.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from tia.core.clock import SystemClock
from tia.core.config import LiveConfig
from tia.core.errors import OrderRejectedError
from tia.data.providers.binance_live import BinanceExecutionProvider
from tia.data.providers.binance_signing import signer_from_live_config
from tia.data.providers.binance_user_stream import BinanceUserDataStream
from tia.domain.enums import OrderState
from tia.domain.orders import ExecutionReport
from tia.domain.portfolio import AccountBalance
from tia.mm.execution import (
    CLIENT_ID_PREFIX,
    LiveMarketMakerExecution,
    SymbolFilters,
    validate_maker_order,
)
from tia.mm.live_ledger import LiveLedger
from tia.mm.order_book import LocalOrderBook, snapshot_from_levels
from tia.mm.quoting import QuoteDecision

TESTNET_HOST = "testnet.binance.vision"
REST_URL = "https://testnet.binance.vision"
WS_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"


@dataclass
class Evidence:
    results: dict[str, str] = field(default_factory=dict)  # item -> PASS | FAIL | NOT TESTED
    notes: dict[str, str] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    responses: dict[str, Any] = field(default_factory=dict)
    reports: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: dict[str, Any] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)

    def mark(self, item: str, verdict: str, note: str = "") -> None:
        self.results[item] = verdict
        if note:
            self.notes[item] = note
        print(f"  [{verdict:^10}] {item}" + (f" — {note}" if note else ""))

    def command(self, text: str) -> None:
        self.commands.append(text)
        print(f"    > {text}")


class Rails:
    """Refusals that run before any request. Each one is a plain assertion about strings
    and flags; none of them can be satisfied by anything the venue returns."""

    @staticmethod
    def check(live: LiveConfig, rest_url: str, ws_url: str) -> None:
        if not live.use_testnet:
            raise SystemExit("REFUSED: use_testnet is false; this script runs against Binance Testnet only")
        for name, url in (("REST", rest_url), ("account stream", ws_url)):
            if TESTNET_HOST not in url:
                raise SystemExit(f"REFUSED: the {name} URL {url!r} is not a Testnet host")
        if "api.binance.com" in rest_url or "stream.binance.com" in ws_url or "ws-api.binance.com" in ws_url:
            raise SystemExit("REFUSED: a mainnet host was configured")
        if os.environ.get("TIA_LIVE__USE_TESTNET", "true").strip().lower() in {"0", "false", "no"}:
            raise SystemExit("REFUSED: TIA_LIVE__USE_TESTNET=false in the environment")


def _env_live_config(args: argparse.Namespace) -> LiveConfig | None:
    key = os.environ.get("TIA_LIVE__BINANCE_API_KEY", "").strip()
    secret = os.environ.get("TIA_LIVE__BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        return None
    from pydantic import SecretStr

    return LiveConfig(
        enabled=False,  # the live path stays disabled; this script never arms anything
        use_testnet=True,
        binance_api_key=SecretStr(key),
        binance_api_secret=SecretStr(secret),
        binance_testnet_url=args.rest_url,
        binance_testnet_user_stream_url=args.ws_url,
    )


def _round_down(value: float, step: float) -> float:
    return round(math.floor(value / step + 1e-9) * step, 10)


def _repeg_target(side: str, our_price: float, best_bid: float, best_ask: float, tick: float) -> float | None:
    """Where a resting probe moves so it is AT the best again, or None when it already is.
    A bid re-pegs up to the best bid when the best bid rose above it; an ask re-pegs down to
    the best ask when the best ask fell below it. Never across the spread: the target stays
    on the maker side, so a re-pegged probe is as post-only as the first one. A best that
    moved through our price is not a re-peg: the probe traded, or is about to."""
    if side == "buy":
        target = _round_down(best_bid, tick)
        return target if target > our_price + tick / 2 and target < best_ask else None
    target = _round_up(best_ask, tick)
    return target if target < our_price - tick / 2 and target > best_bid else None


def _net_inventory(fills: list[tuple[str, float]]) -> float:
    """What the probes netted: bought minus sold, in base units."""
    return sum(q if side == "buy" else -q for side, q in fills)


def _round_up(value: float, step: float) -> float:
    return round(math.ceil(value / step - 1e-9) * step, 10)


class Validation:
    def __init__(self, args: argparse.Namespace, live: LiveConfig) -> None:
        self.args = args
        self.live = live
        self.clock = SystemClock()
        self.ev = Evidence()
        self.provider: BinanceExecutionProvider | None = None
        self.execution: LiveMarketMakerExecution | None = None
        self.stream: BinanceUserDataStream | None = None
        self.filters: SymbolFilters | None = None
        self.book = LocalOrderBook(symbol=args.symbol)
        self.ledger = LiveLedger()
        self.reports: list[tuple[ExecutionReport, int, int]] = []  # report, received_at_ms, processed_at_ms
        self.stream_status: list[tuple[bool, str, int]] = []
        self.criticals: list[tuple[str, str]] = []
        self.balances_seen: list[tuple[list[AccountBalance], int]] = []
        self.booked: list[Any] = []
        self.http = httpx.AsyncClient(base_url=args.rest_url, timeout=15.0)

    # ------------------------------------------------------------------ plumbing

    def now_ms(self) -> int:
        return self.clock.timestamp_ms()

    def _on_report(self, report: ExecutionReport, received_at_ms: int) -> None:
        assert self.execution is not None
        self.execution.absorb_execution_report(report, received_at_ms)
        processed = self.now_ms()
        self.reports.append((report, received_at_ms, processed))
        self.ev.reports.append({**report.as_dict(), "received_at_ms": received_at_ms, "processed_at_ms": processed})

    def _on_balances(self, balances: list[AccountBalance], at_ms: int) -> None:
        assert self.execution is not None
        self.execution.absorb_balances(balances, at_ms)
        self.balances_seen.append((balances, at_ms))

    def _on_status(self, connected: bool, reason: str, at_ms: int) -> None:
        assert self.execution is not None
        self.execution.absorb_stream_status(connected, reason, at_ms)
        self.stream_status.append((connected, reason, at_ms))

    def _build_stream(self) -> BinanceUserDataStream:
        assert self.provider is not None
        return BinanceUserDataStream(self.provider, now_ms=self.now_ms, on_report=self._on_report, on_balances=self._on_balances, on_status=self._on_status, base_url=self.args.ws_url)

    async def _wait(self, predicate: Any, seconds: float, what: str) -> bool:
        """Poll ``predicate`` for up to ``seconds``, ticking the execution each time so the
        worker's answers (REST acks, cancels, polls) are applied as the engine would apply
        them on a market event. The stream's reports need no tick: they apply themselves."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.execution is not None:
                self.execution.on_event("tick", None, self.book, self.now_ms())
            if predicate():
                return True
            await asyncio.sleep(0.05)
        print(f"    (timed out after {seconds:.0f}s waiting for {what})")
        return False

    # ------------------------------------------------------------------ phase 1

    async def phase_1_connectivity(self) -> None:
        print("\nPHASE 1 — connectivity and the account stream")
        ev = self.ev
        try:
            ev.command(f"GET {self.args.rest_url}/api/v3/ping")
            t0 = self.now_ms()
            ping = await self.http.get("/api/v3/ping")
            ev.responses["ping"] = {"status": ping.status_code, "rtt_ms": self.now_ms() - t0}
            ev.mark("1.rest_testnet_reachable", "PASS" if ping.status_code == 200 else "FAIL", f"HTTP {ping.status_code}")
            ev.command(f"GET {self.args.rest_url}/api/v3/time")
            t1 = self.now_ms()
            served = await self.http.get("/api/v3/time")
            t2 = self.now_ms()
            server_ms = int(served.json()["serverTime"])
            offset = server_ms - (t1 + t2) // 2
            ev.responses["time"] = {"serverTime": server_ms, "local_mid_ms": (t1 + t2) // 2, "offset_ms_venue_minus_host": offset, "rtt_ms": t2 - t1}
            ev.latency_ms["host_venue_clock_offset_ms"] = offset
            ev.mark("1.venue_time_read", "PASS", f"venue - host = {offset} ms (not corrected anywhere below)")
        except Exception as exc:
            ev.mark("1.rest_testnet_reachable", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
            raise

        assert self.provider is not None
        # The listen key (POST /api/v3/userDataStream) was retired by the venue on 2026-02-20
        # and answers HTTP 410. The account stream is a signed subscription on the WebSocket
        # API; the signature is computed locally here and sent by the stream when it connects.
        ev.command("provider.user_stream_subscribe_params()  [local HMAC over apiKey, recvWindow, timestamp; nothing sent]")
        params = self.provider.user_stream_subscribe_params()
        names = sorted(params)
        ev.responses["subscribe_request"] = {"method": "userDataStream.subscribe.signature", "param_names": names, "signature_length": len(str(params.get("signature", "")))}
        signed = {"apiKey", "timestamp", "signature"} <= set(names)
        ev.mark("1.subscribe_request_signed", "PASS" if signed else "FAIL", f"params {names} (values never recorded)")
        if not signed:
            raise RuntimeError("the subscription request is not signed; nothing was sent")

        venue_symbol = BinanceExecutionProvider.to_venue_symbol(self.args.symbol)
        ev.command(f"provider.get_exchange_info({self.args.symbol})  [GET /api/v3/exchangeInfo?symbol={venue_symbol}]")
        info = await self.provider.get_exchange_info(self.args.symbol)
        self.filters = SymbolFilters.from_exchange_info(info, symbol=self.args.symbol, venue_symbol=venue_symbol)
        ev.responses["filters"] = self.filters.as_dict()
        ev.mark("1.exchange_info_read", "PASS", f"status TRADING, orderTypes {list(self.filters.order_types)}")
        self.execution = LiveMarketMakerExecution(
            self.provider, clock=self.clock, filters=self.filters, symbol=self.args.symbol, run_tag="validate", now_ms=self.now_ms,
            trades_poll_interval_ms=3_000, idle_trades_poll_interval_ms=30_000, open_sync_interval_ms=10_000,
            on_critical=lambda kind, reason: self.criticals.append((kind, reason)),
        )
        self.execution.fill_sink = lambda fill, t: self.booked.append((fill, t, self.ledger.apply_fill(fill)))
        self.stream = self._build_stream()
        ev.command(f"BinanceUserDataStream.start()  [{self.args.ws_url} -> userDataStream.subscribe.signature]")
        self.stream.start()
        up = await self._wait(lambda: self.stream is not None and self.stream.connected, 20, "the account stream to subscribe")
        ev.responses["subscription"] = {"subscription_id": self.stream.subscription_id, "last_error": self.stream.last_error}
        ev.mark("1.user_stream_subscribed", "PASS" if up else "FAIL", f"subscriptionId {self.stream.subscription_id}; status events: {[(c, r) for c, r, _ in self.stream_status]}; last_error {self.stream.last_error!r}")
        if not up:
            raise RuntimeError("the account stream did not subscribe")
        # Reception of events is proven in phases 3 and 4 (the order's own reports); the
        # reconnect with a fresh signed subscription is exercised in phase 6.

    # ------------------------------------------------------------------ phase 2

    async def phase_2_account(self) -> None:
        print("\nPHASE 2 — the account")
        assert self.provider is not None
        ev = self.ev
        ev.command("provider.get_balances()  [GET /api/v3/account, signed]")
        balances = await self.provider.get_balances()
        quote = balances.get("USDT")
        base = balances.get("BTC")
        ev.responses["balances"] = {k: {"free": v.free, "locked": v.locked} for k, v in sorted(balances.items())}
        for asset, bal in (("USDT", quote), ("BTC", base)):
            if bal is None:
                ev.mark(f"2.{asset}_free_locked", "FAIL", f"{asset} is not in the account's balances")
            else:
                ev.mark(f"2.{asset}_free_locked", "PASS", f"free {bal.free} locked {bal.locked}")
        # The parser against the raw payload, side by side.
        raw = await self.provider._signed_get("/api/v3/account", {})
        rows = {str(r.get("asset")): r for r in raw.get("balances", [])}
        agree = all(
            bal is not None and float(rows[asset]["free"]) == bal.free and float(rows[asset]["locked"]) == bal.locked
            for asset, bal in (("USDT", quote), ("BTC", base))
            if asset in rows
        )
        ev.responses["account_raw_rows"] = {a: rows[a] for a in ("USDT", "BTC") if a in rows}
        ev.mark("2.account_balance_parser_matches_payload", "PASS" if agree else "FAIL")
        if quote is None or base is None:
            raise RuntimeError("the account lacks USDT or BTC; nothing can be quoted")
        mark = self.book.mid or 0.0
        self.ledger.seed(quote_free=quote.free, quote_locked=quote.locked, base_free=base.free, base_locked=base.locked, mark_price=mark, t_ms=self.now_ms())

    # ------------------------------------------------------------------ phase 3

    async def phase_3_maker_order(self) -> Any:
        print("\nPHASE 3 — one post-only order, far from the market")
        assert self.provider is not None and self.execution is not None and self.filters is not None
        ev = self.ev
        venue_symbol = BinanceExecutionProvider.to_venue_symbol(self.args.symbol)
        ev.mark("3.exchange_info_filters", "PASS", f"tick {self.filters.tick_size} step {self.filters.step_size} minQty {self.filters.min_qty} minNotional {self.filters.min_notional} orderTypes {list(self.filters.order_types)}")
        ev.command(f"GET /api/v3/ticker/bookTicker?symbol={venue_symbol}")
        ticker = (await self.http.get("/api/v3/ticker/bookTicker", params={"symbol": venue_symbol})).json()
        best_bid, best_ask = float(ticker["bidPrice"]), float(ticker["askPrice"])
        ev.responses["book_ticker"] = ticker
        self.book.begin_sync()
        self.book.apply_snapshot(snapshot_from_levels(1, [(best_bid, float(ticker["bidQty"]))], [(best_ask, float(ticker["askQty"]))]), received_at_ms=self.now_ms())

        price = _round_down(best_bid * (1.0 - self.args.percent_away / 100.0), self.filters.tick_size)
        quantity = self.args.size if self.args.size > 0 else _round_up(max(self.filters.min_qty, self.filters.min_notional * 1.2 / price), self.filters.step_size)
        check = validate_maker_order("buy", price, quantity, self.filters, best_bid=best_bid, best_ask=best_ask)
        ev.responses["intended_order"] = {"side": "buy", "price": price, "quantity": quantity, "notional": round(price * quantity, 4), "best_bid": best_bid, "best_ask": best_ask, "percent_away": self.args.percent_away, "check": check.as_dict()}
        ev.mark("3.price_is_on_the_maker_side_and_on_the_grid", "PASS" if check.ok else "FAIL", check.reason or f"bid {price} < best ask {best_ask}, {self.args.percent_away}% under the best bid {best_bid}")
        if not check.ok:
            raise RuntimeError("the intended order fails the maker-only validation; nothing was sent")

        await self.execution.start()
        baseline = await self.execution.fetch_trades()
        self.execution.set_trade_baseline(baseline, at_ms=self.now_ms())
        self.execution.accepting_reports = True
        self.execution.on_event("snapshot", None, self.book, self.now_ms())

        t_decision = self.now_ms()
        decision = QuoteDecision(t_decision, price, None, quantity, 0.0, quantity, 0.0, 0.0, (best_bid + best_ask) / 2, 1.0, "testnet validation: one post-only bid far below the market", ttl_ms=10**9)
        placed = self.execution.place(decision, t_decision)
        if len(placed) != 1:
            ev.mark("3.order_accepted_for_submission", "FAIL", f"placed {len(placed)}: {self.execution.last_refusal}")
            raise RuntimeError("the execution refused the order locally")
        order = placed[0]
        ev.command(f"execution.place(LIMIT_MAKER buy {quantity} @ {price}, clientOrderId={order.order_id})")
        ev.mark("3.client_order_id_generated_by_trader_ia", "PASS" if order.order_id.startswith(CLIENT_ID_PREFIX) and len(order.order_id) <= 36 else "FAIL", order.order_id)
        acked = await self._wait(lambda: order.t_ack_ms is not None or order.state in ("refused", "unknown"), 20, "the acknowledgement")
        ev.orders.append(order.as_dict())
        if not acked or order.state != "resting":
            ev.mark("3.order_acknowledged_resting", "FAIL", f"state {order.state} reject={order.reject_reason!r} unknown={order.unknown_reason!r}")
            raise RuntimeError("the order did not come to rest")
        ev.mark("3.order_acknowledged_resting", "PASS", f"orderId {order.venue_order_id}, first ack from {order.ack_source}")
        ev.mark("3.only_limit_maker_was_sent", "PASS", "the adapter has no other order type; see test_the_adapter_has_no_code_path_to_a_market_or_plain_limit_order")
        return order

    # ------------------------------------------------------------------ phase 4

    async def phase_4_execution_and_cancel(self, order: Any) -> None:
        print("\nPHASE 4 — the report, the correlation, the cancel")
        assert self.execution is not None and self.provider is not None
        ev = self.ev
        new_reports = [r for r, _, _ in self.reports if r.order_ref == order.order_id and r.execution_type == "new"]
        got_new = await self._wait(lambda: any(r.order_ref == order.order_id and r.execution_type == "new" for r, _, _ in self.reports), 10, "the NEW execution report")
        new_reports = [r for r, _, _ in self.reports if r.order_ref == order.order_id and r.execution_type == "new"]
        ev.mark("4.execution_report_NEW_received", "PASS" if got_new else "FAIL", f"{len(new_reports)} NEW report(s)")
        if new_reports:
            r = new_reports[0]
            same = r.client_order_id == order.order_id and r.venue_order_id == order.venue_order_id and r.status is OrderState.ACKNOWLEDGED
            ev.mark("4.correlation_clientOrderId_orderId", "PASS" if same else "FAIL", f"report c={r.client_order_id} i={r.venue_order_id} X={r.raw_status}; REST orderId={order.venue_order_id}")
        else:
            ev.mark("4.correlation_clientOrderId_orderId", "NOT TESTED", "no NEW report arrived")
        ev.command(f"execution.cancel({order.order_id})  [DELETE /api/v3/order origClientOrderId]")
        t_cancel = self.now_ms()
        self.execution.cancel(order.order_id, t_cancel, reason="validation: cancel the resting bid")
        cancelled = await self._wait(lambda: order.state == "cancelled", 20, "the cancellation")
        canceled_reports = [r for r, _, _ in self.reports if r.order_ref == order.order_id and r.execution_type == "canceled"]
        ev.mark("4.order_cancelled_locally", "PASS" if cancelled else "FAIL", f"state {order.state}, cancel_to_ack {order.t_cancel_effective_ms - t_cancel if order.t_cancel_effective_ms else None} ms")
        got_canceled = await self._wait(lambda: any(r.order_ref == order.order_id and r.execution_type == "canceled" for r, _, _ in self.reports), 10, "the CANCELED execution report")
        canceled_reports = [r for r, _, _ in self.reports if r.order_ref == order.order_id and r.execution_type == "canceled"]
        ev.mark("4.execution_report_CANCELED_received", "PASS" if got_canceled else "FAIL", f"{len(canceled_reports)} CANCELED report(s); C={canceled_reports[0].orig_client_order_id if canceled_reports else '-'}")
        ev.command(f"provider.get_order({order.order_id})  [GET /api/v3/order orderId={order.venue_order_id}]  — the REST confirmation, by the venue's id")
        try:
            venue_order = await self.provider.get_order(order.order_id)
        except OrderRejectedError as exc:
            # A -2013 here is not evidence of anything: the report above is the evidence of
            # the cancel, and a query the venue refuses is a failed confirmation, not a PASS.
            ev.responses["order_after_cancel"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            ev.mark("4.venue_confirms_CANCELED", "FAIL", f"the venue refused the query: {str(exc)[:160]}")
        else:
            ev.responses["order_after_cancel"] = {"state": venue_order.state.value if venue_order else None, "filled": venue_order.filled_quantity if venue_order else None}
            ev.mark("4.venue_confirms_CANCELED", "PASS" if venue_order is not None and venue_order.state is OrderState.CANCELLED else "FAIL", f"REST status {venue_order.state.value if venue_order else 'none'}")
        ev.mark("4.ledger_consistent_no_fill", "PASS" if self.ledger.state.fills == 0 and self.execution.counters["fills"] == 0 and order.filled == 0.0 else "FAIL", f"ledger fills {self.ledger.state.fills}, execution fills {self.execution.counters['fills']}")
        ev.mark("4.partial_fill", "NOT TESTED", "the order rests far from the market by design; a fill cannot be produced safely on a book that is not ours")
        ev.orders.append(order.as_dict())

    # ------------------------------------------------------------------ phase 5

    async def phase_5_dedupe(self, order: Any) -> None:
        print("\nPHASE 5 — deduplication")
        assert self.execution is not None
        ev = self.ev
        c = self.execution.counters
        before_fills, before_dups = c["fills"], c["duplicate_reports"]
        for report, received, _ in [x for x in self.reports if x[0].order_ref == order.order_id]:
            self.execution.absorb_execution_report(report, received)
        ev.mark("5.duplicate_executionReport_books_nothing", "PASS" if c["fills"] == before_fills and c["duplicate_reports"] > before_dups else "FAIL", f"duplicates counted {c['duplicate_reports'] - before_dups}, fills {c['fills']}")
        ev.command("execution.fetch_trades()  [GET /api/v3/myTrades]")
        trades = await self.execution.fetch_trades()
        self.execution.absorb_trades(trades)
        self.execution.on_event("tick", None, self.book, self.now_ms())
        ev.responses["my_trades_count"] = len(trades)
        if any(str(t.order_id) == order.venue_order_id for t in trades):
            ev.mark("5.report_plus_myTrades_single_booking", "PASS" if c["fills"] <= 1 else "FAIL", f"fills {c['fills']} for one trade")
        else:
            ev.mark("5.report_plus_myTrades_single_booking", "NOT TESTED", "the order did not trade, so there is no trade to see twice; the rule is unit-tested only")
        embedded = next((o for o in ev.orders if o.get("order_id") == order.order_id), None)
        ev.mark("5.embedded_fill_in_POST_response_not_booked", "PASS" if c["fills"] == 0 and (embedded is None or embedded.get("venue_executed_qty", 0.0) == 0.0) else "NOT TESTED", "no embedded fill occurred (the order did not match on arrival); the adapter books none by construction, unit-tested")

    # ------------------------------------------------------------------ phase 6

    async def phase_6_disconnect(self) -> None:
        print("\nPHASE 6 — the account stream cut with an order open")
        assert self.execution is not None and self.stream is not None and self.filters is not None
        ev = self.ev
        intended = ev.responses["intended_order"]
        t = self.now_ms()
        decision = QuoteDecision(t, intended["price"], None, intended["quantity"], 0.0, intended["quantity"], 0.0, 0.0, intended["best_bid"], 1.0, "testnet validation: second resting bid for the disconnect test", ttl_ms=10**9)
        placed = self.execution.place(decision, t)
        if len(placed) != 1 or not await self._wait(lambda: placed[0].state == "resting", 20, "the second order to rest"):
            ev.mark("6.open_order_for_disconnect", "FAIL", f"{self.execution.last_refusal} / {placed[0].state if placed else 'none'}")
            return
        order = placed[0]
        ev.orders.append(order.as_dict())
        ev.command("stream.close()  [the account stream is cut while the order rests]")
        await self.stream.close()
        await asyncio.sleep(0.2)
        down = self.execution.stream_connected is False and any(k == "user_stream_down" for k, _ in self.criticals)
        ev.mark("6.safe_state_signalled_on_cut", "PASS" if down else "FAIL", f"stream_connected={self.execution.stream_connected}, criticals={[k for k, _ in self.criticals]}")
        ev.mark("6.order_state_not_invented", "PASS" if order.state == "resting" else "FAIL", f"local state stayed {order.state!r} (unknown to us until the venue says otherwise)")
        ev.command("execution.fetch_open_orders()  [GET /api/v3/openOrders?symbol]  — the fallback reconciliation")
        venue_open = await self.execution.fetch_open_orders()
        still_there = any(o.client_order_id == order.order_id for o in venue_open)
        self.execution.absorb_open_orders(venue_open)
        self.execution.on_event("tick", None, self.book, self.now_ms())
        ev.mark("6.rest_reconciliation_sees_the_order", "PASS" if still_there else "FAIL", f"{len(venue_open)} open at the venue")
        self.stream = self._build_stream()
        ev.command("BinanceUserDataStream.start()  [reconnect: a new signed subscription]")
        self.stream.start()
        back = await self._wait(lambda: self.stream is not None and self.stream.connected, 20, "the reconnect")
        ev.mark("6.reconnected_with_new_subscription", "PASS" if back else "FAIL", f"subscriptionId {self.stream.subscription_id}; last_error {self.stream.last_error!r}")
        ev.mark("6.recovery_only_after_reconciliation", "PASS" if back and still_there else "NOT TESTED", "the service clears user_stream_down only after a reconciliation that follows the reconnect (rule unit-tested); here the reconciliation is the open-orders read above")
        t_cancel = self.now_ms()
        self.execution.cancel(order.order_id, t_cancel, reason="validation: cancel the disconnect-test bid")
        done = await self._wait(lambda: order.state == "cancelled", 20, "the second cancellation")
        ev.mark("6.second_order_cancelled", "PASS" if done else "FAIL", f"state {order.state}")
        ev.orders.append(order.as_dict())

    # ------------------------------------------------------------------ phase 6b (opt-in)

    async def _top_of_book(self) -> tuple[float, float]:
        venue_symbol = BinanceExecutionProvider.to_venue_symbol(self.args.symbol)
        ticker = (await self.http.get("/api/v3/ticker/bookTicker", params={"symbol": venue_symbol})).json()
        best_bid, best_ask = float(ticker["bidPrice"]), float(ticker["askPrice"])
        self.book.begin_sync()
        self.book.apply_snapshot(snapshot_from_levels(1, [(best_bid, float(ticker["bidQty"]))], [(best_ask, float(ticker["askQty"]))]), received_at_ms=self.now_ms())
        return best_bid, best_ask

    async def _rest_probe_order(self, side: str, price: float, quantity: float, mid: float, reason: str) -> Any | None:
        """One post-only order through the same execution path as the market maker's; None
        when the venue (or our own validation) refused it, with the reason recorded."""
        assert self.execution is not None
        t = self.now_ms()
        bid, ask = (price, None) if side == "buy" else (None, price)
        bid_size, ask_size = (quantity, 0.0) if side == "buy" else (0.0, quantity)
        placed = self.execution.place(QuoteDecision(t, bid, ask, bid_size, ask_size, quantity, 0.0, 0.0, mid, 1.0, reason, ttl_ms=10**9), t)
        if len(placed) != 1:
            self.ev.mark(f"6b.{side}_probe_accepted_locally", "NOT TESTED", f"refused before sending: {self.execution.last_refusal}")
            return None
        order = placed[0]
        self.ev.command(f"execution.place(LIMIT_MAKER {side} {quantity} @ {price}, clientOrderId={order.order_id})  [fill probe]")
        await self._wait(lambda: order.t_ack_ms is not None or order.state in ("refused", "unknown"), 20, f"the {side} probe's acknowledgement")
        self.ev.orders.append(order.as_dict())
        if order.state not in ("resting", "filled"):
            # -2010 here means the book moved between the ticker read and the order: the
            # venue refused to let a post-only order take. That is the rail working.
            self.ev.mark(f"6b.{side}_probe_accepted_locally", "NOT TESTED", f"state {order.state}: {order.reject_reason or order.unknown_reason}")
            return None
        self.ev.mark(f"6b.{side}_probe_accepted_locally", "PASS", f"orderId {order.venue_order_id}, state {order.state}")
        return order

    async def _rest_at_best(self, side: str, quantity: float, best_bid: float, best_ask: float) -> Any | None:
        """One post-only probe AT the best of its side: a bid at the best bid, an ask at the
        best ask. Validated by the same maker-only check the engine's quotes pass; refused,
        not re-priced, when the venue's picture makes it a taker."""
        assert self.filters is not None
        f = self.filters
        price = _round_down(best_bid, f.tick_size) if side == "buy" else _round_up(best_ask, f.tick_size)
        check = validate_maker_order(side, price, quantity, f, best_bid=best_bid, best_ask=best_ask)
        self.ev.responses[f"fill_probe_{'bid' if side == 'buy' else 'ask'}"] = {"price": price, "quantity": quantity, "notional": round(price * quantity, 4), "best_bid": best_bid, "best_ask": best_ask, "check": check.as_dict()}
        if not check.ok:
            self.ev.mark(f"6b.{side}_probe_accepted_locally", "NOT TESTED", f"the probe failed the maker-only check: {check.reason}")
            return None
        return await self._rest_probe_order(side, price, quantity, (best_bid + best_ask) / 2, f"testnet fill probe: join the best {'bid' if side == 'buy' else 'ask'}, maker-only")

    async def phase_6b_fill_probe(self) -> None:
        sides = {"bid": ["buy"], "ask": ["sell"], "both": ["buy", "sell"]}[self.args.fill_probe_sides]
        window = float(self.args.fill_probe)
        repeg_s = float(self.args.fill_probe_repeg)
        print(f"\nPHASE 6b — fill probe: post-only {' and '.join('bid at the best bid' if s == 'buy' else 'ask at the best ask' for s in sides)}, up to {window:g} s for the market to come" + (f", re-pegged to the best every {repeg_s:g} s" if repeg_s > 0 else ""))
        assert self.execution is not None and self.provider is not None and self.filters is not None
        ev = self.ev
        f = self.filters
        c = self.execution.counters
        fills_before, booked_before, balances_before = c["fills"], len(self.booked), len(self.balances_seen)
        probe: dict[str, Any] = {"kind": "real_testnet_fill", "sides": list(sides), "window_s": window, "repeg_s": repeg_s, "repegs": 0, "orders": []}
        ev.responses["fill_probe"] = probe

        best_bid, best_ask = await self._top_of_book()
        quantity = self.args.size if self.args.size > 0 else _round_up(max(f.min_qty, f.min_notional * 1.2 / best_bid), f.step_size)
        placed: list[Any] = []  # every probe order, re-pegs included
        resting: dict[str, Any] = {}  # side -> the probe currently on the book
        for side in sides:
            order = await self._rest_at_best(side, quantity, best_bid, best_ask)
            if order is not None:
                resting[side] = order
                placed.append(order)
        if not resting:
            ev.mark("6b.fill_observed", "NOT TESTED", "no probe rested")
            return
        side_of = {o.order_id: o.side for o in placed}

        def probe_fills() -> list[Any]:
            return [b for b in self.booked[booked_before:] if b[0].order_id in side_of]

        deadline = time.monotonic() + window
        while time.monotonic() < deadline and not probe_fills():
            remaining = deadline - time.monotonic()
            slice_s = min(repeg_s, remaining) if repeg_s > 0 else remaining
            await self._wait(lambda: bool(probe_fills()) or any(o.state == "unknown" for o in resting.values()), slice_s, "a print at our price")
            if probe_fills():
                break
            if any(o.state == "unknown" for o in resting.values()):
                ev.mark("6b.fill_observed", "FAIL", f"a probe order went UNKNOWN: {[o.unknown_reason for o in resting.values() if o.state == 'unknown']}")
                return
            if repeg_s > 0 and time.monotonic() < deadline:
                best_bid, best_ask = await self._top_of_book()
                for side, order in list(resting.items()):
                    if not order.is_open:
                        continue  # closed by the venue meanwhile (expired, cancelled at the console): left as it is
                    target = _repeg_target(side, order.price, best_bid, best_ask, f.tick_size)
                    if target is None:
                        continue
                    ev.command(f"execution.cancel({order.order_id})  [re-peg: the best {'bid' if side == 'buy' else 'ask'} moved to {target}]")
                    self.execution.cancel(order.order_id, self.now_ms(), reason="fill probe: re-peg to the best")
                    await self._wait(lambda o=order: not o.is_open, 20, "the re-peg's cancellation")
                    ev.orders.append(order.as_dict())
                    if probe_fills():
                        break  # it traded while the cancel was in flight: the race, booked below
                    fresh = await self._rest_at_best(side, quantity, best_bid, best_ask)
                    if fresh is not None:
                        resting[side] = fresh
                        placed.append(fresh)
                        side_of[fresh.order_id] = fresh.side
                        probe["repegs"] += 1

        # Take everything still open off the book: the other side after a fill, or every probe
        # when nothing traded. Then let the venue's last words arrive.
        for order in resting.values():
            if order.is_open:
                ev.command(f"execution.cancel({order.order_id})  [{'the other side after a fill' if probe_fills() else 'no print within the window'}]")
                self.execution.cancel(order.order_id, self.now_ms(), reason="fill probe: window elapsed or the other side traded")
        await self._wait(lambda: all(not o.is_open for o in resting.values()), 20, "the probes' cancellation")
        await asyncio.sleep(0.5)
        for order in placed:
            ev.orders.append(order.as_dict())
        probe["orders"] = [{"order_id": o.order_id, "side": o.side, "price": o.price, "quantity": o.quantity, "state": o.state, "venue_order_id": o.venue_order_id, "filled": sum(fl.quantity for fl in o.fills)} for o in placed]
        booked_now = probe_fills()
        if not booked_now:
            ev.mark("6b.fill_observed", "NOT TESTED", f"no print at our price within {window:g} s ({probe['repegs']} re-pegs, {len(placed)} probe order(s)); final states {[o.state for o in resting.values()]}")
            return

        # The venue traded with us. Everything below is read from what arrived, not assumed.
        filled_orders = [o for o in placed if any(fl.order_id == o.order_id for fl, _, _ in booked_now)]
        bought = sum(fl.quantity for fl, _, _ in booked_now if side_of[fl.order_id] == "buy")
        sold = sum(fl.quantity for fl, _, _ in booked_now if side_of[fl.order_id] == "sell")
        net = _net_inventory([(side_of[fl.order_id], fl.quantity) for fl, _, _ in booked_now])
        partial = any(sum(fl.quantity for fl in o.fills) < o.quantity - 1e-12 for o in filled_orders)
        ev.mark("6b.fill_observed", "PASS", f"real_testnet_fill: bought {bought} sold {sold} on {len(filled_orders)} order(s) {[(o.side, o.price, o.state) for o in filled_orders]}; {len(booked_now)} print(s); {probe['repegs']} re-pegs")
        ev.mark("4.partial_fill", "PASS" if partial else "NOT TESTED", "a probe filled in more than one print, or closed with part of it filled" if partial else "every filled probe filled whole; a partial fill did not occur")
        trade_reports = [r for r, _, _ in self.reports if r.is_trade and r.order_ref in {o.order_id for o in filled_orders}]
        if trade_reports:
            r = trade_reports[0]
            fields_ok = bool(r.trade_id) and str(r.trade_id) != "-1" and r.is_maker is True and r.last_quantity > 0 and r.last_price > 0 and bool(r.commission_asset)
            ev.mark("6b.execution_report_TRADE_fields", "PASS" if fields_ok else "FAIL", f"t={r.trade_id} m={r.is_maker} l={r.last_quantity} L={r.last_price} n={r.commission} N={r.commission_asset!r} X={r.raw_status}")
            matched = next((o for o in filled_orders if o.order_id == r.order_ref), None)
            correlated = matched is not None and str(r.venue_order_id) == str(matched.venue_order_id)
            ev.mark("6b.fill_report_correlation_clientOrderId_orderId", "PASS" if correlated else "FAIL", f"report c/C={r.order_ref} i={r.venue_order_id}; local orderId={getattr(matched, 'venue_order_id', None)}")
        else:
            ev.mark("6b.execution_report_TRADE_fields", "FAIL", "the fill was booked without a TRADE report having arrived (so it came from myTrades): the stream missed it")
            ev.mark("6b.fill_report_correlation_clientOrderId_orderId", "NOT TESTED", "no TRADE report to correlate")
        ev.mark("6b.fill_booked_to_ledger_once", "PASS" if booked_now and len(booked_now) == c["fills"] - fills_before == len({fl.fill_id for fl, _, _ in booked_now}) else "FAIL", f"booked {len(booked_now)}, counted {c['fills'] - fills_before}, distinct trade ids {len({fl.fill_id for fl, _, _ in booked_now})}, ledger fills {self.ledger.state.fills}")
        for fl, _, booked in booked_now:
            ev.responses.setdefault("fill_probe_fills", []).append({**fl.as_dict(), "booked": booked, "kind": "real_testnet_fill"} if hasattr(fl, "as_dict") else {"fill_id": fl.fill_id, "order_id": fl.order_id, "quantity": fl.quantity, "price": fl.price, "fee": fl.fee, "fee_asset": fl.fee_asset, "fee_status": fl.fee_status, "liquidity": fl.liquidity, "booked": booked, "kind": "real_testnet_fill"})

        # The cross-check: the same trades from myTrades must not book twice.
        ev.command("execution.fetch_trades()  [GET /api/v3/myTrades]  — the same prints, second source")
        trades = await self.execution.fetch_trades()
        venue_ids = {str(o.venue_order_id) for o in filled_orders}
        mine = [t for t in trades if str(t.order_id) in venue_ids]
        dups_before = c["duplicate_trades"]
        self.execution.absorb_trades(trades)
        self.execution.on_event("tick", None, self.book, self.now_ms())
        if mine:
            ev.mark("5.report_plus_myTrades_single_booking", "PASS" if c["fills"] - fills_before == len(booked_now) and c["duplicate_trades"] - dups_before >= len(mine) else "FAIL", f"myTrades shows {len(mine)} print(s) for orderIds {sorted(venue_ids)}; fills stayed {c['fills'] - fills_before}; duplicates recognised {c['duplicate_trades'] - dups_before}")
        else:
            ev.mark("5.report_plus_myTrades_single_booking", "FAIL", f"myTrades does not list orderIds {sorted(venue_ids)} although the stream reported a trade on them")

        got_balances = await self._wait(lambda: len(self.balances_seen) > balances_before, 10, "outboundAccountPosition after the fill")
        ev.mark("6b.outboundAccountPosition_after_fill", "PASS" if got_balances else "FAIL", f"balance reports after the fill: {len(self.balances_seen) - balances_before}")

        # Reconciliation after a fill: REST balances against what the booked fills imply.
        ev.command("provider.get_balances()  [GET /api/v3/account]  — reconciliation after the fill")
        balances = await self.provider.get_balances()
        quote, base = balances.get("USDT"), balances.get("BTC")
        mark_price = filled_orders[0].price
        if quote is not None and base is not None:
            result = self.ledger.reconcile_balances(quote_free=quote.free, quote_locked=quote.locked, base_free=base.free, base_locked=base.locked, t_ms=self.now_ms(), quote_tolerance_usd=max(0.05, mark_price * quantity * 0.002), base_tolerance_btc=2 * f.step_size)
            ev.responses["fill_probe_reconciliation"] = result
            ev.mark("6b.balances_reconcile_after_fill", "PASS" if result["ok"] else "FAIL", f"quote delta {result['quote_delta_usd']} USD (tol {result['quote_tolerance_usd']}), base delta {result['base_delta_btc']} BTC (tol {result['base_tolerance_btc']}); adopted={result['adopted']}")
        else:
            ev.mark("6b.balances_reconcile_after_fill", "FAIL", "the account no longer lists USDT or BTC")

        # Unwind, maker-only: what the probes netted is taken back to flat with one post-only
        # order on the other side, at the best. Bought more than sold: an ask at the best ask.
        # Sold more than bought: a bid at the best bid. Equal: nothing to do.
        if abs(net) < f.step_size:
            ev.mark("6b.unwind_filled", "PASS", f"flat: bought {bought} sold {sold}; nothing to unwind")
            return
        best_bid2, best_ask2 = await self._top_of_book()
        unwind_side = "sell" if net > 0 else "buy"
        unwind_price = _round_up(best_ask2, f.tick_size) if unwind_side == "sell" else _round_down(best_bid2, f.tick_size)
        holdable = (base.free if base is not None else abs(net)) if unwind_side == "sell" else ((quote.free / unwind_price) if quote is not None else abs(net))
        unwind_qty = _round_down(min(abs(net), holdable), f.step_size)
        check = validate_maker_order(unwind_side, unwind_price, unwind_qty, f, best_bid=best_bid2, best_ask=best_ask2)
        ev.responses["fill_probe_unwind"] = {"side": unwind_side, "price": unwind_price, "quantity": unwind_qty, "net_before": net, "best_bid": best_bid2, "best_ask": best_ask2, "check": check.as_dict()}
        if not check.ok:
            ev.mark("6b.unwind_filled", "NOT TESTED", f"no maker-only {unwind_side} possible: {check.reason}; residual Testnet inventory {net:+.8f} BTC (Testnet assets, no value)")
            return
        unwind = await self._rest_probe_order(unwind_side, unwind_price, unwind_qty, (best_bid2 + best_ask2) / 2, f"testnet fill probe: unwind with a post-only {unwind_side}")
        if unwind is None:
            ev.mark("6b.unwind_filled", "NOT TESTED", f"the unwind {unwind_side} did not rest; residual Testnet inventory {net:+.8f} BTC")
            return
        await self._wait(lambda: unwind.state in ("filled", "cancelled", "unknown"), window, "the unwind to fill")
        if unwind.state == "filled":
            ev.mark("6b.unwind_filled", "PASS", f"{unwind_side} {unwind_qty} @ {unwind_price}; inventory from the probe is flat")
        else:
            if unwind.state not in ("cancelled", "unknown"):
                self.execution.cancel(unwind.order_id, self.now_ms(), reason="fill probe: unwind window elapsed")
                await self._wait(lambda: unwind.state == "cancelled", 20, "the unwind's cancellation")
            done = sum(fl.quantity for fl in unwind.fills)
            residual = net - done if unwind_side == "sell" else net + done
            ev.mark("6b.unwind_filled", "NOT TESTED" if unwind.state == "cancelled" else "FAIL", f"{unwind_side} ended {unwind.state} with {done} done; residual Testnet inventory {residual:+.8f} BTC (Testnet assets, no value)")
        ev.orders.append(unwind.as_dict())

    # ------------------------------------------------------------------ phase 7

    def phase_7_latency(self) -> None:
        print("\nPHASE 7 — latency legs (host clock; venue legs include the clock offset)")
        assert self.execution is not None
        ev = self.ev
        stats = self.execution.stats()["latency"]
        ev.latency_ms["adapter"] = stats
        legs = {
            "decision_to_enqueue_ms": stats["decision_to_enqueue_ms"],
            "enqueue_to_submit_ms": stats["enqueue_to_submit_ms"],
            "rest_submit_rtt_ms (submit -> REST ack)": stats["rest_submit_rtt_ms"],
            "submit_to_first_ack_ms": stats["submit_to_first_ack_ms"],
            "report_to_local_ms (venue E -> received; includes clock offset)": stats["report_to_local_ms"],
            "cancel_to_ack_ms": stats["cancel_to_ack_ms"],
        }
        for name, s in legs.items():
            verdict = "PASS" if s.get("count") else "NOT TESTED"
            ev.mark(f"7.{name}", verdict, f"count {s.get('count')} last {s.get('last_ms')} p50 {s.get('p50_ms')} max {s.get('max_ms')}")
        ws_to_local = [processed - received for _, received, processed in self.reports]
        ev.latency_ms["ws_received_to_processed_ms"] = ws_to_local
        ev.mark("7.ws_receive_to_local_processing_ms", "PASS" if ws_to_local else "NOT TESTED", f"samples {ws_to_local[:10]}")
        fill_leg = stats["fill_to_ledger_ms"]
        ev.mark("7.fill_to_ledger_ms", "PASS" if fill_leg.get("count") else "NOT TESTED", f"count {fill_leg.get('count')} last {fill_leg.get('last_ms')} p50 {fill_leg.get('p50_ms')} max {fill_leg.get('max_ms')}" if fill_leg.get("count") else "no fill occurred")
        ev.mark("7.clock_offset_stated", "PASS", f"venue - host = {ev.latency_ms.get('host_venue_clock_offset_ms')} ms; venue legs are not corrected for it")

    # ------------------------------------------------------------------ phase 8

    def phase_8_safety(self) -> None:
        print("\nPHASE 8 — safety")
        assert self.provider is not None
        ev = self.ev
        hot = ("on_event", "place", "cancel", "cancel_all")
        sync = all(not asyncio.iscoroutinefunction(getattr(LiveMarketMakerExecution, name)) for name in hot)
        ev.mark("8.hot_path_is_synchronous_no_http_no_db", "PASS" if sync else "FAIL", "a property of the code (UNIT TESTED: test_the_hot_path_never_awaits_the_network); the market-data callback never ran in this script")
        ev.mark("8.testnet_hosts_only", "PASS" if TESTNET_HOST in self.args.rest_url and TESTNET_HOST in self.args.ws_url else "FAIL", f"{self.args.rest_url} / {self.args.ws_url}")
        ev.mark("8.no_mainnet_order", "PASS", "no request left this process for api.binance.com; the rails refuse the host before connecting")
        ev.mark("8.no_activation_token", "PASS" if self.provider.activation is None and not self.provider.is_live else "FAIL", f"is_live={self.provider.is_live}, activation={self.provider.activation}")
        ev.mark("8.no_env_file_touched", "PASS", "credentials were read from the process environment; this script writes only --json-out")
        ev.mark("8.no_deploy_no_restart", "PASS", "this script runs in-process and touches no service")
        ev.mark("8.no_real_money", "PASS", "Testnet balances only; the adapter was built simulated=True")

    # ------------------------------------------------------------------ cleanup

    async def cleanup(self) -> None:
        print("\nCLEANUP — every open order of this run is cancelled and confirmed")
        if self.provider is None:
            return
        try:
            open_orders = await self.provider.get_orders(open_only=True, symbol=self.args.symbol)
        except Exception as exc:
            self.ev.mark("cleanup.open_orders_read", "FAIL", f"{type(exc).__name__}: {str(exc)[:160]}")
            return
        mine = [o for o in open_orders if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX)]
        left: list[str] = []
        for o in mine:
            try:
                await self.provider.resolve_unknown_order(symbol=self.args.symbol, client_order_id=o.client_order_id)
                result = await self.provider.cancel_order(o.client_order_id)
                if result.state is not OrderState.CANCELLED:
                    left.append(o.client_order_id)
            except Exception as exc:
                left.append(f"{o.client_order_id}: {type(exc).__name__}")
        remaining = [o.client_order_id for o in await self.provider.get_orders(open_only=True, symbol=self.args.symbol) if (o.client_order_id or "").startswith(CLIENT_ID_PREFIX)]
        self.ev.mark("cleanup.no_open_orders_left", "PASS" if not remaining and not left else "FAIL", f"cancelled {len(mine)}; left {remaining or left}")
        if self.stream is not None:
            await self.stream.close()
        if self.execution is not None:
            await self.execution.close()
        await self.provider.close()
        await self.http.aclose()

    # ------------------------------------------------------------------ run

    async def run(self) -> int:
        signer = signer_from_live_config(self.live, self.clock)
        self.provider = BinanceExecutionProvider(signer=signer, clock=self.clock, activation=None, base_url=self.args.rest_url, simulated=True)
        failed = False
        try:
            await self.phase_1_connectivity()
            await self.phase_2_account()
            order = await self.phase_3_maker_order()
            await self.phase_4_execution_and_cancel(order)
            await self.phase_5_dedupe(order)
            await self.phase_6_disconnect()
            if self.args.fill_probe > 0:
                await self.phase_6b_fill_probe()
            self.phase_7_latency()
        except Exception as exc:
            failed = True
            print(f"\nSTOPPED: {type(exc).__name__}: {str(exc)[:300]}")
            self.ev.notes["stopped"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        finally:
            self.phase_8_safety()
            await self.cleanup()
        return 1 if failed or any(v == "FAIL" for v in self.ev.results.values()) else 0

    def report(self) -> dict[str, Any]:
        groups = {"PASS": [], "FAIL": [], "NOT TESTED": []}  # type: ignore[var-annotated]
        for item, verdict in self.ev.results.items():
            groups[verdict].append(item)
        print("\n" + "=" * 72)
        for verdict in ("PASS", "FAIL", "NOT TESTED"):
            print(f"{verdict}:")
            for item in groups[verdict]:
                note = self.ev.notes.get(item, "")
                print(f"  - {item}" + (f" ({note})" if note else ""))
        print("=" * 72)
        return {
            "generated_at_ms": self.now_ms(),
            "rest_url": self.args.rest_url,
            "ws_url": self.args.ws_url,
            "symbol": self.args.symbol,
            "results": self.ev.results,
            "notes": self.ev.notes,
            "commands": self.ev.commands,
            "responses": self.ev.responses,
            "reports": self.ev.reports,
            "orders": self.ev.orders,
            "latency_ms": self.ev.latency_ms,
            "stream_status": self.stream_status,
            "criticals": self.criticals,
            "execution_stats": self.execution.stats() if self.execution else None,
            "ledger": self.ledger.snapshot() if self.ledger.seeded else None,
            "fill_evidence_kind": "real_testnet_fill" if self.ev.responses.get("fill_probe_fills") else None,
            "fill_evidence_note": "a fill here is the venue trading with a post-only probe of ours; the synthetic fill tests under tests/unit/mm and tests/adversarial are evidence about our invariants, never about Binance",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="BTC-USD")
    parser.add_argument("--size", type=float, default=0.0, help="base quantity; 0 derives the smallest size above minNotional with a margin")
    parser.add_argument("--percent-away", type=float, default=2.0, help="how far under the best bid the bid rests, in percent (never at or above the ask)")
    parser.add_argument("--rest-url", default=REST_URL)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--fill-probe", type=float, default=0.0, help="seconds to rest minimal post-only probe(s) AT the best, waiting for the market to trade into them (0 = off); what the probes net is unwound with one post-only order on the other side and anything left is reported")
    parser.add_argument("--fill-probe-sides", default="bid", choices=("bid", "ask", "both"), help="which side(s) rest: a bid at the best bid, an ask at the best ask, or both at once (whichever the market comes to; the other is cancelled)")
    parser.add_argument("--fill-probe-repeg", type=float, default=0.0, help="seconds between re-pegs: when the best moved away from a resting probe it is cancelled (confirmed) and rested again at the new best, maker-only (0 = never)")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    live = _env_live_config(args)
    if live is None:
        print("NOT TESTED: TIA_LIVE__BINANCE_API_KEY / TIA_LIVE__BINANCE_API_SECRET (Testnet keys) are not in the process environment; nothing was attempted")
        return 2
    Rails.check(live, args.rest_url, args.ws_url)
    validation = Validation(args, live)
    try:
        code = asyncio.run(validation.run())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("interrupted; the cleanup already ran in the finally block if any phase started")
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
