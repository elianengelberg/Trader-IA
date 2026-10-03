"""The live execution adapter against an in-memory venue: post-only or nothing, unique
ids, cancels that wait for the venue, timeouts that become UNKNOWN and are resolved by
asking, fills only from the venue's trade history, and a hot path that never waits.

Every venue response here is scripted. These tests prove the adapter's logic, not the
venue's contract; the contract is what Binance Testnet validation is for.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.unit.mm.fake_venue import FakeVenue, exchange_info
from tia.core.clock import SimulatedClock, millis_from_utc
from tia.core.errors import LiveActivationError
from tia.domain.enums import OrderType
from tia.live.gate import CONFIRMATION_PHRASE, REQUIRED_CHECKS, LiveActivationGate, passing
from tia.mm.execution import (
    CLIENT_ID_PREFIX,
    LiveMarketMakerExecution,
    SymbolFilters,
    validate_maker_order,
)
from tia.mm.order_book import LocalOrderBook, snapshot_from_levels
from tia.mm.quoting import QuoteDecision

START = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
FILTERS = SymbolFilters.from_exchange_info(exchange_info(), symbol="BTC-USD", venue_symbol="BTCUSDT")
SRC = Path(__file__).resolve().parents[3] / "packages" / "tia" / "src" / "tia" / "mm" / "execution.py"


def _book(bid: float = 100_000.0, ask: float = 100_000.2) -> LocalOrderBook:
    book = LocalOrderBook("BTC-USD")
    book.begin_sync()
    assert book.apply_snapshot(snapshot_from_levels(100, [(bid, 2.0), (bid - 0.1, 5.0)], [(ask, 1.0), (ask + 0.1, 4.0)]))
    return book


def _quote(bid: float | None = 99_999.9, ask: float | None = 100_000.3, size: float = 0.001, t_ms: int = 0, ttl_ms: int = 5_000) -> QuoteDecision:
    return QuoteDecision(t_ms, bid, ask, size if bid else 0.0, size if ask else 0.0, size, 2.0, 1.0, 100_000.1, 0.9, "test quote", ttl_ms)


class Harness:
    def __init__(self, venue: FakeVenue, execution: LiveMarketMakerExecution, clock: SimulatedClock, criticals: list[tuple[str, str]]) -> None:
        self.venue, self.execution, self.clock, self.criticals = venue, execution, clock, criticals
        self.book = _book()

    @property
    def t(self) -> int:
        return millis_from_utc(self.clock.now())

    def tick(self, ms: int = 100) -> int:
        self.clock.advance_by(timedelta(milliseconds=ms))
        return self.t

    async def settle(self, rounds: int = 6, advance_ms: int = 100):  # type: ignore[no-untyped-def]
        """Let the worker run, apply what it learnt on a market event; twice, so a
        follow-up the first pass queued (a poll, a resolution) is applied as well."""
        produced = []
        for _ in range(2):
            for _ in range(rounds):
                await asyncio.sleep(0.005)
            produced.extend(self.execution.on_event("depth", None, self.book, self.tick(advance_ms)))
        return produced


async def _harness(venue: FakeVenue | None = None, **kw) -> Harness:  # type: ignore[no-untyped-def]
    clock = SimulatedClock(START)
    venue = venue or FakeVenue(clock)
    criticals: list[tuple[str, str]] = []
    settings = {"trades_poll_interval_ms": 0, "idle_trades_poll_interval_ms": 0, "open_sync_interval_ms": 0, "resolve_backoff_s": 0.0}
    settings.update(kw)
    execution = LiveMarketMakerExecution(
        venue, clock=clock, filters=FILTERS, symbol="BTC-USD", run_tag="testrun1",
        on_critical=lambda kind, reason: criticals.append((kind, reason)), **settings,
    )
    await execution.start()
    harness = Harness(venue, execution, clock, criticals)
    # The adapter learns the book from the feed, as it does under the engine.
    execution.on_event("snapshot", None, harness.book, harness.t)
    return harness


# ------------------------------------------------------------------ the order type


async def test_every_order_is_post_only_with_a_unique_client_id_on_the_venue_grid() -> None:
    h = await _harness()
    placed = h.execution.place(_quote(t_ms=h.t), h.t)
    assert [o.state for o in placed] == ["pending_arrival", "pending_arrival"]
    await h.settle()
    assert [o.state for o in placed] == ["resting", "resting"]
    assert len(h.venue.submits) == 2
    assert all(i.order_type is OrderType.LIMIT_MAKER and i.limit_price is not None for i in h.venue.submits)
    ids = [i.client_order_id for i in h.venue.submits]
    assert len(set(ids)) == 2 and all(i.startswith(CLIENT_ID_PREFIX) and len(i) <= 36 and re.fullmatch(r"[A-Za-z0-9_-]+", i) for i in ids)
    assert all(o.venue_order_id and o.t_ack_ms is not None for o in placed)
    assert h.execution.stats()["latency"]["submit_to_ack_ms"]["count"] == 2
    # Many placements, never a repeated id.
    seen = set(ids)
    for _ in range(20):
        h.execution.cancel_all(h.t, reason="requote")
        await h.settle()
        for order in h.execution.place(_quote(t_ms=h.t), h.t):
            assert order.order_id not in seen
            seen.add(order.order_id)
        await h.settle()
    await h.execution.close()


def test_the_adapter_has_no_code_path_to_a_market_or_plain_limit_order() -> None:
    source = SRC.read_text(encoding="utf-8")
    assert "OrderType.LIMIT_MAKER" in source
    assert not re.search(r"OrderType\.MARKET|OrderType\.LIMIT\b|OrderType\.STOP|TimeInForce", source)


# ------------------------------------------------------------------ maker-only validation


def test_validation_refuses_what_the_venue_would_refuse_or_fill_as_a_taker() -> None:
    ok = validate_maker_order("buy", 99_999.9, 0.001, FILTERS, best_bid=100_000.0, best_ask=100_000.2)
    assert ok.ok
    assert "tick grid" in validate_maker_order("buy", 99_999.905, 0.001, FILTERS, best_bid=100_000.0, best_ask=100_000.2).reason
    assert "lot step" in validate_maker_order("buy", 99_999.9, 0.0010005, FILTERS, best_bid=100_000.0, best_ask=100_000.2).reason
    assert "lot step" in validate_maker_order("buy", 99_999.9, 0.000005, FILTERS, best_bid=100_000.0, best_ask=100_000.2).reason
    coarse = SymbolFilters.from_exchange_info(exchange_info(min_qty="0.00010000"), symbol="BTC-USD", venue_symbol="BTCUSDT")
    assert "below the minimum" in validate_maker_order("buy", 99_999.9, 0.00005, coarse, best_bid=100_000.0, best_ask=100_000.2).reason
    assert "notional" in validate_maker_order("buy", 1.0, 0.00001, FILTERS, best_bid=1.1, best_ask=1.2).reason
    assert "would take" in validate_maker_order("buy", 100_000.2, 0.001, FILTERS, best_bid=100_000.0, best_ask=100_000.2).reason
    assert "would take" in validate_maker_order("sell", 100_000.0, 0.001, FILTERS, best_bid=100_000.0, best_ask=100_000.2).reason
    assert "no valid top of book" in validate_maker_order("sell", 100_000.5, 0.001, FILTERS, best_bid=None, best_ask=None).reason


async def test_a_quote_that_fails_validation_is_never_sent() -> None:
    h = await _harness()
    h.execution.on_event("depth", None, h.book, h.t)  # the adapter learns the book from the feed
    assert h.execution.place(_quote(bid=100_000.3, ask=100_000.1, t_ms=h.t), h.t) == []  # bid >= ask
    assert h.execution.place(_quote(bid=100_000.2, ask=None, t_ms=h.t), h.t) == []  # at the ask: taker
    assert h.execution.place(_quote(bid=99_999.905, ask=None, t_ms=h.t), h.t) == []  # off the tick grid
    assert h.execution.place(_quote(bid=None, ask=100_000.3, size=0.000005, t_ms=h.t), h.t) == []  # below min qty
    await h.settle()
    assert h.venue.received == [] and h.execution.counters["refused_validation"] == 4
    assert "lot step" in h.execution.last_refusal
    await h.execution.close()


def test_symbol_filters_come_from_the_venue_and_refuse_a_symbol_without_post_only() -> None:
    assert FILTERS.tick_size == 0.01 and FILTERS.step_size == 0.00001 and FILTERS.min_notional == 5.0 and "LIMIT_MAKER" in FILTERS.order_types
    with pytest.raises(ValueError, match="LIMIT_MAKER"):
        SymbolFilters.from_exchange_info(exchange_info(order_types=("LIMIT", "MARKET")), symbol="BTC-USD", venue_symbol="BTCUSDT")
    with pytest.raises(ValueError, match="does not describe"):
        SymbolFilters.from_exchange_info({"symbols": [{"symbol": "ETHUSDT"}, {"symbol": "BNBUSDT"}]}, symbol="BTC-USD", venue_symbol="BTCUSDT")
    with pytest.raises(ValueError, match="notional"):
        SymbolFilters.from_exchange_info({"symbols": [{"symbol": "BTCUSDT", "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"}, {"filterType": "LOT_SIZE", "stepSize": "0.00001", "minQty": "0.00001"}]}]}, symbol="BTC-USD", venue_symbol="BTCUSDT")


# ------------------------------------------------------------------ rejections and unknowns


async def test_a_post_only_order_the_venue_would_fill_as_taker_is_rejected_and_never_resent() -> None:
    h = await _harness()
    h.venue.next_submit = ["reject:-2010"]
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "refused" and "code -2010" in order.reject_reason
    stats = h.execution.stats()
    assert stats["rejected"] == 1 and stats["rejected_would_cross"] == 1 and stats["refused_crossed"] == 1
    assert len(h.venue.received) == 1 and h.venue.received[0].order_type is OrderType.LIMIT_MAKER and h.venue.submits == []
    assert h.execution.blocked_reason == ""  # a rejection is a known state; nothing is blocked
    assert order.order_id not in h.execution.orders
    await h.execution.close()


async def test_a_timeout_is_unknown_blocks_new_orders_and_is_resolved_by_asking_never_by_resending() -> None:
    h = await _harness(resolve_attempts=1)
    h.venue.next_submit = ["timeout"]
    h.venue.fail_queries = "hang"
    h.venue.hang_seconds = 0.15
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await asyncio.sleep(0.02)  # the submit timed out; the resolution query is in flight
    h.execution.on_event("depth", None, h.book, h.tick())
    assert order.state == "unknown" and h.execution.blocked_reason.startswith("order ")
    assert h.criticals and h.criticals[0][0] == "unknown_order_state"
    assert h.execution.place(_quote(t_ms=h.t), h.t) == [] and h.execution.counters["refused_blocked"] == 1
    await asyncio.sleep(0.2)
    h.execution.on_event("depth", None, h.book, h.tick())
    # The venue never had it: dropped, not resent. One submit in total.
    assert order.state == "refused" and "resolved absent" in order.reject_reason
    assert h.execution.blocked_reason == "" and h.execution.counters["resolved_absent"] == 1
    assert len(h.venue.submits) == 0 and h.venue.calls.count("submit") == 1
    assert h.execution.place(_quote(t_ms=h.t), h.t)  # unblocked
    await h.execution.close()


async def test_a_timeout_after_the_venue_accepted_is_adopted_not_duplicated() -> None:
    h = await _harness()
    h.venue.next_submit = ["timeout_after_accept"]
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.venue_order_id and h.execution.counters["resolved_present"] == 1
    assert h.venue.calls.count("submit") == 1 and len(h.venue.orders) == 1
    assert h.execution.blocked_reason == ""
    await h.execution.close()


async def test_a_cancel_asked_for_while_the_order_was_unknown_goes_out_once_it_is_known_to_rest() -> None:
    h = await _harness(resolve_attempts=1)
    h.venue.next_submit = ["timeout_after_accept"]
    h.venue.fail_queries = "hang"
    h.venue.hang_seconds = 0.15
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await asyncio.sleep(0.02)
    h.execution.on_event("depth", None, h.book, h.tick())
    assert order.state == "unknown"
    h.execution.cancel(order.order_id, h.t, reason="requote")  # nothing can be sent yet
    assert h.venue.cancels == []
    await asyncio.sleep(0.2)
    h.venue.fail_queries = None
    await h.settle()
    await h.settle()  # the worker first finishes the polls that were queued while the venue hung
    assert h.venue.cancels == [order.order_id] and order.state == "cancelled"
    assert h.execution.counters["resolved_present"] == 1 and h.execution.blocked_reason == ""
    await h.execution.close()


async def test_a_resolution_that_keeps_failing_leaves_the_order_blocked_and_trips_the_error_budget() -> None:
    h = await _harness(resolve_attempts=2, max_api_errors_per_minute=1)
    h.venue.next_submit = ["timeout"]
    h.venue.fail_queries = "transport"
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "unknown" and h.execution.counters["unresolved"] == 1
    assert h.execution.blocked_reason.startswith("order ") and h.execution.counters["api_errors"] >= 2
    kinds = [k for k, _ in h.criticals]
    assert "unknown_order_state" in kinds and "excessive_api_errors" in kinds and "unresolved_order" in kinds
    assert h.execution.place(_quote(t_ms=h.t), h.t) == []
    await h.execution.close()


async def test_a_rate_limited_submission_was_not_sent_so_it_is_refused_not_unknown() -> None:
    h = await _harness()
    h.venue.next_submit = ["rate_limited"]
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "refused" and "not sent" in order.reject_reason
    assert h.execution.blocked_reason == "" and h.execution.counters["api_errors"] == 1
    await h.execution.close()


# ------------------------------------------------------------------ cancels


async def test_cancel_and_cancel_all_wait_for_the_venue_before_the_order_is_gone() -> None:
    h = await _harness()
    placed = h.execution.place(_quote(t_ms=h.t), h.t)
    await h.settle()
    assert h.execution.cancel_all(h.t, reason="requote") == 2
    assert all(o.state == "resting" and o.t_cancel_requested_ms is not None for o in placed)  # requested, not gone
    assert h.execution.cancel_all(h.t, reason="again") == 0  # idempotent while pending
    await h.settle()
    assert all(o.state == "cancelled" and o.t_cancel_effective_ms is not None for o in placed)
    assert sorted(h.venue.cancels) == sorted(o.order_id for o in placed)
    assert h.execution.open_orders() == [] and h.execution.stats()["cancelled"] == 2
    assert h.execution.stats()["latency"]["cancel_to_ack_ms"]["count"] == 2
    await h.execution.close()


async def test_strict_cancel_replace_defers_the_new_side_until_the_old_one_is_confirmed_gone() -> None:
    h = await _harness()
    h.execution.place(_quote(t_ms=h.t), h.t)
    await h.settle()
    h.execution.cancel_all(h.t, reason="requote")
    assert h.execution.place(_quote(t_ms=h.t), h.t) == []  # the cancels are still pending
    assert h.execution.counters["deferred_cancel_pending"] == 2
    await h.settle()
    assert len(h.execution.place(_quote(t_ms=h.t), h.t)) == 2
    await h.execution.close()


async def test_a_cancel_requested_before_the_submit_went_out_sends_nothing() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    h.execution.cancel(order.order_id, h.t, reason="changed my mind")
    await h.settle()
    assert order.state == "cancelled" and h.venue.submits == [] and h.venue.cancels == []
    assert h.execution.counters["cancelled_before_submit"] == 1
    await h.execution.close()


async def test_a_fill_that_races_the_cancel_is_booked_and_the_order_ends_filled() -> None:
    h = await _harness()
    h.venue.reject_cancel_of_closed = False
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.venue.venue_fill(order.order_id, 0.001)  # filled at the venue...
    h.execution.cancel(order.order_id, h.t, reason="requote")  # ...just as we asked to cancel
    fills = await h.settle()
    assert order.state == "filled" and h.execution.counters["cancel_raced_fill"] == 1
    assert [f.quantity for f in fills] == [0.001] and fills[0].order_id == order.order_id
    await h.execution.close()


async def test_a_cancel_the_venue_rejects_as_already_closed_resolves_the_true_state() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.venue.venue_fill(order.order_id, 0.001)
    h.execution.cancel(order.order_id, h.t, reason="requote")  # the venue answers -2011: unknown order
    await h.settle()
    await h.settle()
    c = h.execution.counters
    # Two legitimate paths to the same truth: the trade poll booked the fill first (the
    # rejection then asks nothing), or the rejection came first and the resolve read FILLED.
    assert order.state == "filled" and c["resolved_present"] + c["cancel_rejected_after_close"] == 1
    assert "cancel rejected (code -2011)" in order.cancel_reason
    await h.execution.close()


async def test_an_order_that_vanishes_at_the_venue_is_asked_about_not_assumed() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.venue.venue_cancel(order.order_id)  # the venue expired or cancelled it on its own
    await h.settle()
    await h.settle()
    assert order.state == "cancelled" and h.execution.counters["missing_at_venue"] >= 1
    await h.execution.close()


async def test_a_quote_past_its_ttl_is_cancelled_through_the_venue() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t, ttl_ms=1_000), h.t)
    await h.settle()
    h.execution.on_event("depth", None, h.book, h.tick(2_000))
    assert order.t_cancel_requested_ms is not None and order.cancel_reason == "ttl expired" and h.execution.counters["expired"] == 1
    await h.settle()
    assert order.state == "cancelled"
    await h.execution.close()


# ------------------------------------------------------------------ fills


async def test_fills_come_only_from_the_venue_trade_history_with_fee_maker_flag_and_ids() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert h.execution.counters["fills"] == 0
    h.venue.venue_fill(order.order_id, 0.0004)
    fills = await h.settle()
    assert len(fills) == 1 and fills[0].quantity == 0.0004 and fills[0].liquidity == "maker"
    assert fills[0].fill_id == "5001" and fills[0].venue_trade_ids == (5001,) and fills[0].venue_order_id == order.venue_order_id
    assert fills[0].fee_usd == pytest.approx(99_999.9 * 0.0004 * 1.0 / 10_000.0) and fills[0].fee_status == "venue"
    assert fills[0].mid_at_fill == pytest.approx(100_000.1)
    assert order.state == "resting" and order.filled == 0.0004
    assert await h.settle() == []  # the same trade is never booked twice
    h.venue.venue_fill(order.order_id, 0.0006)
    fills = await h.settle()
    assert [f.quantity for f in fills] == [0.0006] and order.state == "filled" and order.order_id not in h.execution.orders
    stats = h.execution.stats()
    assert stats["fills"] == 2 and stats["maker_fills"] == 2 and stats["states"]["filled"] == 1
    await h.execution.close()


async def test_a_fee_in_a_third_asset_is_flagged_and_a_fee_in_the_base_asset_is_converted() -> None:
    h = await _harness()
    orders = h.execution.place(_quote(t_ms=h.t), h.t)
    await h.settle()
    buy = next(o for o in orders if o.side == "buy")
    sell = next(o for o in orders if o.side == "sell")
    h.venue.venue_fill(buy.order_id, 0.001, fee_asset="BNB")
    h.venue.venue_fill(sell.order_id, 0.001, fee_asset="BTC")
    fills = await h.settle()
    by_side = {f.side: f for f in fills}
    assert by_side["buy"].fee_status == "unconverted:BNB" and by_side["buy"].fee_usd == 0.0 and by_side["buy"].fee_asset == "BNB"
    assert by_side["sell"].fee_status == "converted_from_base" and by_side["sell"].fee_usd == pytest.approx(by_side["sell"].fee * by_side["sell"].price)
    await h.execution.close()


async def test_a_taker_fill_on_our_order_is_booked_but_counted_as_the_anomaly_it_is() -> None:
    h = await _harness()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    h.venue.venue_fill(order.order_id, 0.001, is_maker=False)
    fills = await h.settle()
    assert fills[0].liquidity == "taker" and h.execution.counters["taker_fills"] == 1
    await h.execution.close()


async def test_a_trade_on_an_order_this_maker_did_not_place_is_critical_and_old_trades_are_history() -> None:
    h = await _harness()
    old = h.venue.foreign_trade(price=99_000.0, quantity=0.01, at=START - timedelta(hours=1))
    assert h.execution.set_trade_baseline([old], at_ms=h.t) == 1
    h.execution.on_event("depth", None, h.book, h.tick())
    await h.settle()
    assert h.execution.counters["unknown_fills"] == 0 and h.criticals == []
    h.clock.advance_by(timedelta(seconds=90))
    h.venue.foreign_trade(price=100_000.1, quantity=0.01)
    fills = await h.settle()
    assert fills == [] and h.execution.counters["unknown_fills"] == 1
    assert h.criticals and h.criticals[-1][0] == "unknown_fill"
    await h.execution.close()


# ------------------------------------------------------------------ open orders at the venue


async def test_an_open_order_this_maker_did_not_place_is_critical_unless_told_otherwise() -> None:
    h = await _harness()
    h.venue.add_foreign_open_order()
    await h.settle()
    assert h.execution.counters["foreign_open_orders"] >= 1 and h.criticals[0][0] == "foreign_open_order"
    await h.execution.close()
    lenient = await _harness(foreign_orders_critical=False)
    lenient.venue.add_foreign_open_order()
    await lenient.settle()
    assert lenient.execution.counters["foreign_open_orders"] >= 1 and lenient.criticals == []
    await lenient.execution.close()


async def test_a_market_maker_order_the_venue_holds_but_this_run_does_not_know_is_critical() -> None:
    h = await _harness()
    h.venue.add_foreign_open_order(client_order_id=f"{CLIENT_ID_PREFIX}oldrun00-1-000001")
    await h.settle()
    assert h.execution.counters["venue_orders_unknown_locally"] >= 1 and h.criticals[0][0] == "venue_order_unknown_locally"
    await h.execution.close()


# ------------------------------------------------------------------ activation


def _live_token(clock: SimulatedClock):  # type: ignore[no-untyped-def]
    gate = LiveActivationGate(clock, environment="live")
    return gate.arm({name: passing(name, "verified") for name in REQUIRED_CHECKS}, operator="elian", confirmation=CONFIRMATION_PHRASE, max_live_capital=500.0, fingerprint="fp-1")


def test_a_provider_that_claims_to_be_live_without_a_token_is_refused_at_construction() -> None:
    clock = SimulatedClock(START)
    impostor = SimpleNamespace(is_live=True, activation=None, name="impostor", get_trades=lambda **k: None, get_orders=lambda **k: None)
    with pytest.raises(LiveActivationError, match="without an activation token"):
        LiveMarketMakerExecution(impostor, clock=clock, filters=FILTERS, symbol="BTC-USD", run_tag="x")  # type: ignore[arg-type]
    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        FakeVenue(clock, simulated=False)  # the provider layer refuses first, independently


async def test_an_expired_activation_stops_the_next_order_and_blocks_the_adapter() -> None:
    clock = SimulatedClock(START)
    venue = FakeVenue(clock, simulated=False, activation=_live_token(clock), name="fake-live")
    h = await _harness(venue)
    assert h.execution.is_live
    h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert len(venue.submits) == 1
    clock.advance_by(timedelta(hours=3))
    [late] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert late.state == "refused" and "activation refused" in late.reject_reason
    assert h.execution.blocked_reason.startswith("activation") and h.criticals[-1][0] == "activation"
    assert len(venue.submits) == 1  # nothing was sent
    assert h.execution.place(_quote(ask=None, t_ms=h.t), h.t) == []
    await h.execution.close()


# ------------------------------------------------------------------ latency


async def test_the_hot_path_never_awaits_the_network() -> None:
    for name in ("on_event", "place", "cancel", "cancel_all", "open_orders", "stats"):
        assert not inspect.iscoroutinefunction(getattr(LiveMarketMakerExecution, name))
    h = await _harness(trades_poll_interval_ms=10**9, open_sync_interval_ms=10**9)
    h.venue.hang_seconds = 10.0
    h.venue.next_submit = ["hang", "hang"]
    h.venue.fail_queries = "hang"
    started = time.perf_counter()
    placed = h.execution.place(_quote(t_ms=h.t), h.t)
    h.execution.on_event("depth", None, h.book, h.tick())
    h.execution.on_event("trade", None, h.book, h.tick())
    elapsed = time.perf_counter() - started
    assert len(placed) == 2 and elapsed < 0.5
    assert h.venue.calls == []  # not a single venue call happened on the hot path
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert h.venue.calls[:1] == ["submit"]  # the worker, on its own turn of the loop, now hanging
    started = time.perf_counter()
    assert h.execution.cancel_all(h.t, reason="requote") == 2  # the hot path does not wait for it
    h.execution.on_event("depth", None, h.book, h.tick())
    assert time.perf_counter() - started < 0.5 and h.venue.calls == ["submit"]
    h.execution._worker.cancel()  # type: ignore[union-attr]
    await asyncio.sleep(0)


async def test_stats_carry_what_the_metrics_module_reads() -> None:
    h = await _harness()
    stats = h.execution.stats()
    for key in ("placed", "states", "cancelled", "unresolved_fill_events", "partial_orders", "refused_crossed", "expired", "mode", "venue", "filters", "latency", "blocked_reason"):
        assert key in stats
    assert stats["mode"] == "live" and stats["is_live"] is False and stats["worker_running"] is True
    await h.execution.close()
    assert h.execution.stats()["worker_running"] is False


# ------------------------------------------------------------------ the account stream


async def _streamed(**kw):  # type: ignore[no-untyped-def]
    """A harness whose venue also speaks over the account stream."""
    from tests.unit.mm.fake_venue import FakeUserStream

    h = await _harness(**kw)
    stream = FakeUserStream(h.venue, now_ms=lambda: h.t, on_report=h.execution.absorb_execution_report, on_balances=h.execution.absorb_balances, on_status=h.execution.absorb_stream_status)
    stream.start()
    h.execution.accepting_reports = True
    return h, stream


async def test_a_new_report_acknowledges_the_order_before_the_rest_response_and_only_once() -> None:
    from tia.domain.enums import OrderState

    h, stream = await _streamed()
    h.venue.hang_seconds = 0.2
    h.venue.next_submit = ["hang"]  # the REST answer is slow; the stream is not
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await asyncio.sleep(0.02)
    stream.report(order.order_id, execution_type="new", status=OrderState.ACKNOWLEDGED, venue_order_id="4242")
    assert order.state == "resting" and order.ack_source == "stream" and order.venue_order_id == "4242"  # immediately, no settle
    c = h.execution.counters
    assert c["acked"] == 1 and c["reports_before_rest_ack"] == 1 and c["reports"] == 1
    await asyncio.sleep(0.25)
    await h.settle()
    assert order.state == "resting" and order.rest_acked and c["acked"] == 1  # the REST answer confirmed, it did not count again
    lat = h.execution.stats()["latency"]
    assert lat["submit_to_first_ack_ms"]["count"] == 1 and lat["submit_to_ack_ms"]["count"] == 1 and lat["rest_submit_rtt_ms"]["count"] == 1
    assert lat["decision_to_enqueue_ms"]["count"] == 1 and lat["enqueue_to_submit_ms"]["count"] == 1 and lat["report_to_local_ms"]["count"] == 1
    await h.execution.close()


async def test_partial_and_full_fills_arrive_as_reports_book_once_each_and_the_poll_finds_nothing_new() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    stream.fill_with_report(order.order_id, 0.0004)
    assert order.filled == 0.0004 and order.state == "resting"  # applied the instant the venue said so
    fills = h.execution.on_event("depth", None, h.book, h.tick())  # handed to the engine on its next event
    assert len(fills) == 1 and fills[0].attribution_source == "report" and fills[0].liquidity == "maker" and fills[0].fee_status == "venue"
    assert fills[0].fill_id == "5001" and fills[0].venue_trade_ids == (5001,) and fills[0].fee_usd > 0
    stream.fill_with_report(order.order_id, 0.0006)
    assert order.state == "filled" and order.order_id not in h.execution.orders
    assert [f.quantity for f in h.execution.on_event("depth", None, h.book, h.tick())] == [0.0006]
    await h.settle()  # the trade-history poll sees the same two trades: nothing booked twice
    c = h.execution.counters
    assert c["fills"] == 2 and c["report_fills"] == 2 and c["trade_poll_fills"] == 0 and c["duplicate_trades"] >= 2
    assert h.execution.stats()["states"]["filled"] == 1 and h.execution.on_event("depth", None, h.book, h.tick()) == []
    await h.execution.close()


async def test_a_duplicate_report_and_a_duplicate_trade_book_nothing_twice() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    report = stream.fill_with_report(order.order_id, 0.001)
    h.execution.absorb_execution_report(report)  # the venue resent it
    h.execution.absorb_execution_report(report)
    c = h.execution.counters
    assert c["fills"] == 1 and c["duplicate_reports"] == 2
    trade = h.venue.trades[-1]
    h.execution.absorb_trades([trade, trade])  # the history poll describes the same trade
    h.execution.on_event("depth", None, h.book, h.tick())
    assert c["fills"] == 1 and c["duplicate_trades"] >= 2 and order.filled == 0.001
    await h.execution.close()


async def test_a_fill_reported_after_the_rest_ack_books_normally_and_the_rest_cancel_cannot_undo_it() -> None:
    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()  # REST ack first
    assert order.ack_source == "rest"
    stream.fill_with_report(order.order_id, 0.001)  # then the fill, as a report
    assert order.state == "filled" and h.execution.counters["fills"] == 1
    h.execution.cancel(order.order_id, h.t, reason="requote")  # too late: already closed here
    await h.settle()
    assert h.venue.cancels == [] and order.state == "filled"
    await h.execution.close()


async def test_canceled_expired_and_rejected_reports_close_the_order_as_the_venue_says() -> None:
    from tia.domain.enums import OrderState

    h, stream = await _streamed()
    orders = h.execution.place(_quote(t_ms=h.t), h.t)
    await h.settle()
    buy = next(o for o in orders if o.side == "buy")
    sell = next(o for o in orders if o.side == "sell")
    h.execution.cancel(buy.order_id, h.t, reason="requote")
    # The venue's report of the cancel refers to the original id; the cancel request's own id differs.
    stream.report("web_cancel_1", execution_type="canceled", status=OrderState.CANCELLED, orig_client_order_id=buy.order_id, venue_order_id=buy.venue_order_id)
    assert buy.state == "cancelled" and h.execution.counters["cancelled"] == 1
    await h.settle()  # the REST cancel response arrives afterwards: the order stays cancelled, counted once
    assert buy.state == "cancelled" and h.execution.counters["cancelled"] == 1
    stream.report(sell.order_id, execution_type="expired", status=OrderState.EXPIRED)
    assert sell.state == "cancelled" and h.execution.open_orders() == []
    # A rejection reported by the stream before any REST answer refuses the order with the venue's reason.
    h.venue.hang_seconds = 0.2
    h.venue.next_submit = ["hang"]
    [late] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await asyncio.sleep(0.02)
    stream.report(late.order_id, execution_type="rejected", status=OrderState.REJECTED, reject_reason="INSUFFICIENT_BALANCE")
    assert late.state == "refused" and "INSUFFICIENT_BALANCE" in late.reject_reason and h.execution.blocked_reason == ""
    await asyncio.sleep(0.25)
    await h.settle()
    assert late.state == "refused" and h.execution.stats()["states"]["refused"] == 1
    await h.execution.close()


async def test_a_rest_cancel_rejected_after_the_stream_reported_canceled_changes_nothing_and_asks_nothing() -> None:
    """The race: the CANCELED report lands first, then the REST cancel's own answer is a
    rejection (the venue has nothing left to cancel). The report is the evidence; the order
    stays cancelled, counted once, and no resolve goes out for it."""
    from tia.domain.enums import OrderState

    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting"
    h.venue.hang_seconds = 0.15
    h.venue.next_cancel = ["hang"]  # the REST cancel is slow
    h.execution.cancel(order.order_id, h.t, reason="requote")
    await asyncio.sleep(0.02)
    h.venue.venue_cancel(order.order_id)  # the venue cancels, and reports it before answering the REST call
    stream.report("web_cancel_9", execution_type="canceled", status=OrderState.CANCELLED, orig_client_order_id=order.order_id, venue_order_id=order.venue_order_id)
    assert order.state == "cancelled" and order.closed and h.execution.counters["cancelled"] == 1
    calls_before = h.venue.calls.count("resolve")
    await asyncio.sleep(0.2)  # the hanging DELETE now answers: -2011, the order is already closed there
    await h.settle()
    c = h.execution.counters
    assert order.state == "cancelled" and c["cancelled"] == 1 and c["cancel_rejected_after_close"] == 1
    assert "cancel rejected (code -2011)" in order.cancel_reason
    assert h.venue.calls.count("resolve") == calls_before  # nothing to ask: the venue already said
    assert h.execution.blocked_reason == "" and not any(k == "unknown_order_state" for k, _ in h.criticals)
    await h.execution.close()


async def test_a_venue_that_denies_an_order_it_acknowledged_leaves_it_unknown_until_a_report_says_otherwise() -> None:
    """-2013 without evidence: the venue refused the cancel and then says the order does not
    exist, although it acknowledged it. Nothing is assumed in either direction; the order is
    unknown, quoting blocks, and the first unequivocal report resolves it."""
    from tia.domain.enums import OrderState

    h, stream = await _streamed()
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.venue_order_id
    h.venue.venue_cancel(order.order_id)  # cancelled at the venue, no report reached us
    h.venue.resolve_absent.add(order.order_id)  # and a resolve by client id answers -2013
    h.execution.cancel(order.order_id, h.t, reason="requote")
    await h.settle()
    await h.settle()
    c = h.execution.counters
    # The rejection and the open-orders sync each asked once; both answers were "absent".
    assert order.state == "unknown" and not order.closed and c["resolved_absent"] >= 1 and c["unknown"] == 1
    assert "now says it does not exist" in order.unknown_reason
    assert h.execution.blocked_reason and any(k == "unknown_order_state" for k, _ in h.criticals)
    assert c["cancelled"] == 0 and h.execution.stats()["states"].get("refused", 0) == 0
    # The venue's own word, when it arrives, is what resolves it: cancelled, counted once, unblocked.
    stream.report("web_cancel_10", execution_type="canceled", status=OrderState.CANCELLED, orig_client_order_id=order.order_id, venue_order_id=order.venue_order_id)
    assert order.state == "cancelled" and order.closed and c["cancelled"] == 1 and c["stream_resolved"] == 1
    assert h.execution.blocked_reason == ""
    await h.execution.close()


async def test_a_report_about_an_order_this_run_does_not_know_is_critical_and_old_or_early_reports_are_not() -> None:
    from tia.domain.enums import OrderState

    h, stream = await _streamed()
    h.execution.accepting_reports = False
    stream.report("someone-else-7", execution_type="new", status=OrderState.ACKNOWLEDGED, venue_order_id="555")
    assert h.execution.counters["reports_before_start"] == 1 and h.criticals == []
    h.execution.accepting_reports = True
    h.execution.set_trade_baseline([], at_ms=h.t)
    stream.report("someone-else-8", execution_type="trade", status=OrderState.FILLED, last_qty=0.01, last_price=100_000.0, trade_id="9", at=START - timedelta(hours=2))
    assert h.criticals == [] and h.execution.counters["historical_trades"] == 1  # about the account's past
    h.clock.advance_by(timedelta(seconds=90))
    stream.report("someone-else-9", execution_type="new", status=OrderState.ACKNOWLEDGED, venue_order_id="556")
    assert h.execution.counters["unknown_reports"] == 1 and h.criticals[-1][0] == "unknown_execution_report"
    stream.report(f"{CLIENT_ID_PREFIX}oldrun00-1-000001", execution_type="trade", status=OrderState.FILLED, last_qty=0.001, last_price=100_000.0, trade_id="10", venue_order_id="557")
    assert h.execution.counters["venue_orders_unknown_locally"] == 1 and h.criticals[-1][0] == "venue_order_unknown_locally"
    assert h.execution.counters["fills"] == 0  # nothing of someone else's was ever booked
    await h.execution.close()


async def test_attribution_follows_the_venue_and_is_unknown_when_the_venue_does_not_say() -> None:
    h, stream = await _streamed()
    orders = h.execution.place(_quote(t_ms=h.t), h.t)
    await h.settle()
    buy = next(o for o in orders if o.side == "buy")
    sell = next(o for o in orders if o.side == "sell")
    stream.fill_with_report(buy.order_id, 0.0005, is_maker=False)
    stream.fill_with_report(buy.order_id, 0.0005, is_maker=None)
    stream.fill_with_report(sell.order_id, 0.001, is_maker=True)
    fills = h.execution.on_event("depth", None, h.book, h.tick())
    assert [f.liquidity for f in fills] == ["taker", "unknown", "maker"]
    c = h.execution.counters
    assert c["taker_fills"] == 1 and c["unknown_attribution_fills"] == 1 and c["maker_fills"] == 1
    await h.execution.close()


async def test_a_dropped_account_stream_invents_no_state_asks_for_the_trade_history_and_is_critical() -> None:
    h, stream = await _streamed(trades_poll_interval_ms=10**9, idle_trades_poll_interval_ms=10**9)
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert h.execution.stream_connected is True and h.venue.calls.count("trades") == 0  # the stream is up: no polling
    stream.drop("socket closed by the venue")
    assert h.execution.stream_connected is False and h.execution.counters["stream_drops"] == 1
    assert h.criticals[-1][0] == "user_stream_down" and order.state == "resting"  # nothing invented about the order
    await h.settle()
    assert h.venue.calls.count("trades") == 1  # the history was read at once to cover the gap
    stream.reconnect()
    assert h.execution.stream_connected is True and h.execution.stats()["stream"]["connected"] is True
    await h.execution.close()


async def test_with_the_stream_up_the_trade_history_is_a_slow_cross_check_and_a_fast_fallback_when_it_is_down() -> None:
    h, stream = await _streamed(trades_poll_interval_ms=0, idle_trades_poll_interval_ms=10**9)
    h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    await h.settle()
    assert h.venue.calls.count("trades") == 0  # up: idle cadence (never, here)
    stream.drop()
    await h.settle()
    await h.settle()
    polls_after_drop = h.venue.calls.count("trades")
    assert polls_after_drop >= 2  # down with an open order: every event polls
    await h.execution.close()


async def test_a_fill_embedded_in_the_submit_response_is_never_booked_the_report_is() -> None:
    from tia.domain.enums import OrderState
    from tia.domain.orders import Fill

    h, stream = await _streamed()
    venue = h.venue
    real_submit = venue.submit_order

    async def submit_with_embedded_fill(intent):  # type: ignore[no-untyped-def]
        order = await real_submit(intent)
        # The venue matched 0.0004 on arrival and says so in the FULL response, with a
        # fill that carries no maker attribution. The order rests for the remainder.
        stored = venue.orders[intent.client_order_id]
        stored.filled_quantity = 0.0004
        stored.state = OrderState.PARTIALLY_FILLED
        embedded = Fill(fill_id="emb-1", order_id=order.order_id, sequence=0, symbol="BTC-USD", side=order.side, quantity=0.0004, price=order.limit_price or 0.0, fee=0.04, liquidity="taker", filled_at=venue.clock.now())
        copy = stored.model_copy()
        copy.fills.append(embedded)
        return copy

    venue.submit_order = submit_with_embedded_fill  # type: ignore[method-assign]
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "resting" and order.venue_executed_qty == 0.0004 and order.filled == 0.0 and h.execution.counters["fills"] == 0
    assert h.venue.calls.count("trades") >= 1  # the gap between executed and booked asked the history
    stream.fill_with_report(order.order_id, 0.0004, is_maker=True)  # the venue's attribution arrives
    assert order.filled == 0.0004 and h.execution.counters["fills"] == 1 and order.fills[0].liquidity == "maker"
    await h.execution.close()


async def test_balances_from_the_stream_are_recorded_and_handed_to_the_sink() -> None:
    h, stream = await _streamed()
    seen: list[dict] = []  # type: ignore[type-arg]
    h.execution.balances_sink = lambda balances, t: seen.append(balances)
    h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    stream.push_balances()
    assert h.execution.counters["balance_updates"] == 1 and seen and set(seen[-1]) == {"USDT", "BTC"}
    usdt = h.execution.venue_balances["USDT"]
    assert usdt.locked == pytest.approx(99_999.9 * 0.001) and usdt.free == pytest.approx(5_000.0 - 99_999.9 * 0.001)  # the resting bid locks its notional
    assert h.execution.stats()["venue_balances"]["USDT"]["locked"] == pytest.approx(99_999.9 * 0.001)
    await h.execution.close()


async def test_the_fill_sink_books_the_moment_the_venue_reports_and_on_event_then_hands_nothing() -> None:
    h, stream = await _streamed()
    booked: list[tuple[Any, int]] = []
    h.execution.fill_sink = lambda fill, t: booked.append((fill, t))
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    stream.fill_with_report(order.order_id, 0.001)
    assert len(booked) == 1 and booked[0][0].order_id == order.order_id
    assert h.execution.on_event("depth", None, h.book, h.tick()) == [] and h.execution.stats()["fill_sink_installed"] is True
    assert h.execution.stats()["latency"]["fill_to_ledger_ms"]["count"] == 1
    await h.execution.close()


async def test_a_timeout_still_ends_unknown_and_is_never_resent_even_with_the_stream_up() -> None:
    h, _stream = await _streamed(resolve_attempts=1)
    h.venue.next_submit = ["timeout"]
    h.venue.fail_queries = "transport"
    [order] = h.execution.place(_quote(ask=None, t_ms=h.t), h.t)
    await h.settle()
    assert order.state == "unknown" and h.execution.blocked_reason.startswith("order ") and h.venue.calls.count("submit") == 1
    assert h.execution.place(_quote(t_ms=h.t), h.t) == []
    await h.settle()
    assert h.venue.calls.count("submit") == 1  # the stream being up changes nothing about resending
    await h.execution.close()
