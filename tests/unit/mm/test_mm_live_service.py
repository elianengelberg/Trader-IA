"""The live market-making service end to end over the in-memory venue: reconciliation
before the first quote, post-only orders from the engine's decisions, fills booked from
the venue's trades with its fees, the kill switch and its triggers, stop with a cancel of
everything and a final reconciliation. No network, no token unless the test mints one.

The economics floor is lowered in these tests so the plumbing can be exercised; nothing
here says anything about whether quoting is worth doing."""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.unit.mm.fake_venue import FakeVenue, exchange_info
from tests.unit.mm.test_mm_execution_live import START, _live_token
from tests.unit.mm.test_replay import Scripted
from tests.unit.mm.test_service import PROFILE, _config, _depth, _trade
from tia.core.clock import SimulatedClock
from tia.core.errors import LiveActivationError
from tia.domain.enums import OrderType, Side
from tia.mm.authorization import EconomicsConfig
from tia.mm.engine import MarketMakerConfig
from tia.mm.execution import SymbolFilters
from tia.mm.live_service import LiveMarketMakerService
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.quoting import QuotingConfig
from tia.mm.streams import MarketDataStream
from tia.risk.engine import RiskState

FILTERS = SymbolFilters.from_exchange_info(exchange_info(), symbol="BTC-USD", venue_symbol="BTCUSDT")


async def _market(clock: SimulatedClock) -> tuple[MarketDataService, Scripted]:
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    bids = [(round(100_000.0 - i * 0.1, 1), 1.0) for i in range(80)]
    asks = [(round(100_000.2 + i * 0.1, 1), 1.0) for i in range(80)]

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        return snapshot_from_levels(100, bids, asks)

    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=clock.timestamp_ms)
    market = MarketDataService("BTC-USD", stream=stream, fetch_snapshot=fetch_snapshot, resync_cooldown_s=0.01, now_ms=clock.timestamp_ms)
    market.start()
    await asyncio.sleep(0.05)
    assert market.usable
    return market, scripted


class Live:
    def __init__(self, clock: SimulatedClock, market: MarketDataService, scripted: Scripted, venue: FakeVenue, service: LiveMarketMakerService) -> None:
        self.clock, self.market, self.scripted, self.venue, self.service = clock, market, scripted, venue, service
        self.uid = 101
        self.tid = 500
        self.risk_state = RiskState()

    async def until_resting(self, rounds: int = 12) -> list[str]:
        """Feed until the venue holds a resting order of ours (quotes expire after their
        TTL and the strict cancel/replace defers the replacement by a cycle)."""
        for _ in range(rounds):
            resting = [cid for cid, o in self.venue.orders.items() if not o.state.is_terminal]
            if resting:
                return resting
            await self.feed(2)
        raise AssertionError("no order came to rest at the venue")

    async def feed(self, events: int = 8, *, step_ms: int = 150) -> None:
        for i in range(events):
            self.clock.advance_by(timedelta(milliseconds=step_ms))
            await self.scripted.send(_depth(self.uid, self.uid, self.clock.timestamp_ms(), bids=[(99_993.0, 1.0 + (i % 3))]))
            self.uid += 1
            if i % 2:
                self.clock.advance_by(timedelta(milliseconds=10))
                self.tid += 1
                await self.scripted.send(_trade(self.tid, self.clock.timestamp_ms(), 99_995.0, 0.002, seller=True))
            await asyncio.sleep(0.01)


async def _live(*, venue: FakeVenue | None = None, venue_kwargs: dict | None = None, config: MarketMakerConfig | None = None, activation=None, run_id: str = "mm-live-test", **kw) -> Live:  # type: ignore[no-untyped-def, type-arg]
    clock = SimulatedClock(START)
    market, scripted = await _market(clock)
    venue = venue or FakeVenue(clock, **(venue_kwargs or {"quote_balance": 5_000.0, "base_balance": 0.05}))
    persisted: list[tuple[str, dict]] = []  # type: ignore[type-arg]

    async def persist(kind: str, payload: dict) -> None:  # type: ignore[type-arg]
        persisted.append((kind, payload))

    state = RiskState()
    settings = {
        "economics": EconomicsConfig(min_net_edge_bps=-10.0),  # plumbing, not profitability
        "reconcile_interval_s": 1_000.0,
        "trades_poll_interval_s": 0.0,
        "open_sync_interval_s": 0.0,
        "cancel_wait_s": 2.0,
        "heartbeat_s": 0.02,
    }
    settings.update(kw)
    service = LiveMarketMakerService(
        market=market, config=config or _config(), profile=PROFILE, scenario="optimistic", run_id=run_id,
        risk_state=lambda: state, provider=venue, clock=clock, filters=FILTERS, activation=activation,
        persist=persist, broadcast=lambda _e: None, now_ms=clock.timestamp_ms, state_push_interval_ms=500, ledger_save_interval_ms=1_000,
        **settings,
    )
    live = Live(clock, market, scripted, venue, service)
    live.risk_state = state
    live.persisted = persisted  # type: ignore[attr-defined]
    return live


async def _teardown(live: Live) -> None:
    if live.service.is_running:
        await live.service.stop(reason="test teardown", actor="test")
    await live.market.close()


# ------------------------------------------------------------------ the whole path


async def test_the_service_reconciles_first_quotes_post_only_books_venue_fills_and_stops_clean() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    with pytest.raises(RuntimeError, match="start_live"):
        service.start()
    report = await service.start_live()
    assert report.ok and report.initial and service.is_running and service.state_label == "quoting"
    assert service.live_ledger.seeded and service.live_ledger.state.starting_equity_usd == 5_000.0 and service.live_ledger.baseline_base_btc == 0.05
    assert service.status()["is_live"] is False and service.status()["venue"] == "fake-venue" and service.status()["activation"] is None

    await live.feed(10)
    assert venue.submits, "the engine's decisions should have reached the venue"
    assert all(i.order_type is OrderType.LIMIT_MAKER and i.limit_price is not None for i in venue.submits)
    status = service.status()
    assert status["execution"]["acked"] >= 1 and status["state"] in ("quoting", "no_quote")
    decisions = [r for r in service.engine.journal if r.get("kind") == "decision" and r.get("decision") == "quote"]
    assert decisions and [a["stage"] for a in decisions[0]["authorizations"]] == ["risk", "economics"]

    resting = await live.until_resting()
    venue.venue_fill(resting[0], venue.orders[resting[0]].quantity)
    await live.feed(6)
    assert service.live_ledger.state.fills == 1 and service.live_ledger.fees_venue_usd > 0
    fill_rows = [r for r in service.engine.journal if r.get("kind") == "fill"]
    assert fill_rows and fill_rows[0]["fee_status"] == "venue" and fill_rows[0]["liquidity"] == "maker" and fill_rows[0]["resolution"] == "confirmed"
    assert service.metrics()["counts"]["fills"] == 1 and service.metrics()["edge"]["verdict"] == "NO EDGE DETECTED"
    kinds = {k for k, _ in live.persisted}  # type: ignore[attr-defined]
    assert {"mm_journal", "mm_fill"} <= kinds

    again = await service.reconcile()
    assert again.ok, again.as_dict()
    assert service.reconciliations == 2 and any(r.get("kind") == "reconciliation" for r in service.engine.journal)

    stopped = await service.stop(reason="done", actor="elian")
    assert stopped["state"] == "stopped" and stopped["running"] is False and "done (by elian)" in stopped["stop_reason"]
    assert all(o.state.is_terminal for o in venue.orders.values()), "every order was cancelled or filled at the venue"
    assert service.execution.open_orders() == [] and stopped["kill_switch"]["shutdown"]["reason"] == "done (by elian)"
    assert stopped["kill_switch"]["engaged"] is False and stopped["kill_switch"]["blocks_quoting"] is True
    assert stopped["operator_events"][-1]["action"] == "stop"
    await live.market.close()


async def test_a_discrepancy_at_start_leaves_the_service_up_in_a_safe_state_that_never_quotes() -> None:
    live = await _live()
    live.venue.add_foreign_open_order()
    report = await live.service.start_live()
    assert report.critical and live.service.state_label == "safe" and live.service.kill.engaged
    assert live.service.kill.trigger == "reconciliation" and "foreign_open_order" in live.service.kill.reason
    await live.feed(8)
    assert live.venue.submits == [] and live.service.engine.gate_blocks >= 1
    assert live.service.status()["gate"]["state"] == "system_unsafe"
    await _teardown(live)


async def test_the_operators_kill_switch_cancels_everything_and_reconciles() -> None:
    live = await _live()
    await live.service.start_live()
    await live.until_resting()
    status = await live.service.engage_kill_switch(reason="operator says stop", actor="elian")
    assert status["state"] == "safe" and status["kill_switch"]["actor"] == "elian" and status["kill_switch"]["sticky"]
    assert all(o.state.is_terminal for o in live.venue.orders.values()) and status["open_orders"] == []
    assert live.service.reconciliations >= 2
    await live.feed(4)
    assert all(o.state.is_terminal for o in live.venue.orders.values())  # nothing new while engaged
    with pytest.raises(ValueError, match="named actor"):
        await live.service.engage_kill_switch(reason="x", actor=" ")
    await _teardown(live)


async def test_a_silent_feed_is_seen_by_the_heartbeat_which_cancels_and_the_switch_clears_on_fresh_data() -> None:
    live = await _live()
    await live.service.start_live()
    await live.until_resting()
    live.clock.advance_by(timedelta(seconds=5))  # the feed goes silent: no event arrives
    await asyncio.sleep(0.15)  # the heartbeat ticks the engine on its own
    assert live.service.heartbeats >= 1
    assert live.service.kill.engaged and "data" in live.service.kill.as_dict()["transient"]
    assert live.service.engine.data_blocks >= 1
    await asyncio.sleep(0.1)
    assert all(o.state.is_terminal for o in live.venue.orders.values()), "what rested was cancelled at the venue"
    await live.feed(3, step_ms=100)  # fresh data again
    assert not live.service.kill.sticky and "data" not in live.service.kill.as_dict()["transient"]
    assert any(e.action == "clear" for e in live.service.kill.history)
    await _teardown(live)


async def test_a_breached_limit_of_the_makers_own_controller_is_mirrored_and_sticky() -> None:
    live = await _live()
    await live.service.start_live()
    await live.feed(4)
    live.service.engine.controller.engage_kill_switch("daily loss 100.00 USD reached the limit 100.00")
    await live.feed(3)
    assert live.service.kill.sticky and live.service.kill.trigger == "risk_limit" and "daily loss" in live.service.kill.reason
    await _teardown(live)


async def test_an_unknown_fill_on_the_account_is_critical_and_cancels() -> None:
    live = await _live()
    await live.service.start_live()
    await live.feed(6)
    live.clock.advance_by(timedelta(seconds=90))
    live.venue.foreign_trade(price=100_000.1, quantity=0.01)
    await live.feed(6)
    assert live.service.kill.sticky and live.service.kill.trigger == "unknown_fill"
    assert all(o.state.is_terminal for o in live.venue.orders.values())
    await _teardown(live)


# ------------------------------------------------------------------ activation and refusals


async def test_the_activations_expiry_margin_stops_quoting_before_the_token_lapses() -> None:
    clock = SimulatedClock(START)
    token = _live_token(clock)  # one hour, minted by the gate
    venue = FakeVenue(clock, simulated=False, activation=token, name="fake-live", quote_balance=5_000.0, base_balance=0.05)
    live = await _live(venue=venue, activation=token, expiry_margin_s=120.0)
    assert live.clock is not clock  # the harness has its own clock; align the token's view on it
    live.service.activation = token
    await live.service.start_live()
    status = live.service.status()
    assert status["is_live"] is True and status["activation"]["present"] and status["activation"]["issued_by"] == "elian"
    await live.feed(6)
    assert live.venue.submits, "with the whole hour left the maker quotes"
    live.clock.advance_by(timedelta(minutes=59))  # inside the 120 s margin
    before = len(live.venue.submits)
    await live.feed(6)
    assert len(live.venue.submits) == before
    blocks = [r for r in live.service.engine.journal if r.get("kind") == "block" and r.get("layer") == "authorization"]
    assert blocks and "expires in" in blocks[-1]["reason"]
    assert live.service.engine.authorization_blocks >= 1
    await _teardown(live)


def test_a_live_provider_without_a_token_cannot_reach_the_service() -> None:
    impostor = SimpleNamespace(is_live=True, activation=None, name="impostor", get_trades=lambda **k: None, get_orders=lambda **k: None)
    with pytest.raises((ValueError, LiveActivationError), match="activation token"):
        LiveMarketMakerService(
            market=SimpleNamespace(), config=_config(), profile=PROFILE, scenario="optimistic", run_id="x", risk_state=lambda: None,
            provider=impostor, clock=SimulatedClock(START), filters=FILTERS,  # type: ignore[arg-type]
        )


async def test_a_quoting_grid_that_disagrees_with_the_venue_refuses_to_start() -> None:
    config = MarketMakerConfig(quoting=QuotingConfig(tick_size=0.1))
    live = await _live(config=config)
    with pytest.raises(ValueError, match=re.escape("tick_size 0.1 != venue tick 0.01")):
        await live.service.start_live()
    assert not live.service.is_running and live.venue.calls == []
    await live.market.close()


async def test_a_reconciliation_that_fails_mid_run_engages_the_switch_and_is_reported() -> None:
    live = await _live()
    await live.service.start_live()
    live.venue.fail_queries = "transport"
    report = await live.service.reconcile()
    assert report.critical and report.discrepancies[0]["kind"] == "reconciliation_failed"
    assert live.service.reconciliation_failures == 1 and live.service.kill.sticky and live.service.kill.trigger == "reconciliation"
    assert live.service.status()["reconciliation"]["failures"] == 1
    live.venue.fail_queries = None
    await _teardown(live)


# ------------------------------------------------------------------ the account stream in the service


def _attach_stream(live: Live):  # type: ignore[no-untyped-def]
    from tests.unit.mm.fake_venue import FakeUserStream

    execution = live.service.execution
    stream = FakeUserStream(live.venue, now_ms=live.clock.timestamp_ms, on_report=execution.absorb_execution_report, on_balances=execution.absorb_balances, on_status=execution.absorb_stream_status)
    live.service.attach_user_stream(stream)
    return stream


async def test_fills_reported_by_the_stream_are_booked_at_once_and_balances_follow_the_venue() -> None:
    live = await _live(venue_kwargs={"quote_balance": 5_000.0, "base_balance": 0.04, "base_locked": 0.01})
    stream = _attach_stream(live)
    report = await live.service.start_live()
    assert stream.started and live.service.execution.accepting_reports and report.ok
    ledger = live.service.live_ledger
    assert ledger.state.starting_equity_usd == 5_000.0 and ledger.baseline_base_btc == pytest.approx(0.05)
    assert ledger.venue_base_locked == pytest.approx(0.01) and ledger.balances() == (5_000.0, pytest.approx(0.04))
    assert report.balances["venue_base_locked"] == pytest.approx(0.01) and report.balances["capital_cap_usd"] is None
    resting = await live.until_resting()
    stream.fill_with_report(resting[0], live.venue.orders[resting[0]].quantity)
    # Booked on the stream's turn, before any market event: ledger, journal, counters.
    assert ledger.state.fills == 1 and ledger.fees_venue_usd > 0
    rows = [r for r in live.service.engine.journal if r.get("kind") == "fill"]
    assert rows and rows[0]["attribution_source"] == "report" and rows[0]["liquidity"] == "maker"
    assert ledger.venue_balances_at_ms is not None and ledger.venue_quote_free < 5_000.0  # the venue's balances after the fill
    status = live.service.status()
    assert status["user_stream"]["connected"] is True and status["execution"]["report_fills"] == 1 and status["execution"]["fill_sink_installed"]
    assert status["latency"]["market_event_to_processed_ms"]["count"] > 0 and status["latency"]["callback_ms"]["count"] > 0
    assert "report_to_local_ms" in status["latency"] and "decision_to_enqueue_ms" in status["latency"]
    stopped = await live.service.stop(reason="done", actor="elian")
    assert stream.closed and stopped["state"] == "stopped"
    await live.market.close()


async def test_a_dropped_account_stream_degrades_to_a_safe_state_until_a_reconciliation_after_it_is_back() -> None:
    live = await _live()
    stream = _attach_stream(live)
    await live.service.start_live()
    await live.until_resting()
    stream.drop("socket closed by the venue")
    await live.feed(2)
    kill = live.service.kill
    assert kill.engaged and not kill.sticky and "user_stream_down" in kill.as_dict()["transient"]
    assert all(o.state.is_terminal for o in live.venue.orders.values()), "what rested was cancelled: nothing is assumed about it"
    stream.reconnect()
    await live.feed(2)
    assert "user_stream_down" in kill.as_dict()["transient"], "back online is not enough: the account has to be read first"
    await live.service.reconcile()
    await live.feed(2)
    assert "user_stream_down" not in kill.as_dict()["transient"] and not kill.engaged
    await _teardown(live)


async def test_a_partial_fill_the_stream_never_reported_is_booked_by_the_final_reconciliation_at_stop() -> None:
    """Found by trying to falsify stop(): a partial fill known only to the trade history,
    then an immediate stop. The cancel response closes the order, the trade poll it
    triggers answers after the drain loop has already seen no open orders, and the final
    reconciliation used to absorb the trades without applying them — so the ledger ended
    without the fill and the final report downgraded the mismatch to "re-checked next
    time", when there is no next time. Now the final pass books what the history holds
    and adopts the venue's figures if anything still differs."""
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    [cid, *_] = await live.until_resting()
    order = venue.orders[cid]
    part = round(order.quantity / 2, 5)
    venue.venue_fill(cid, part)  # no stream is wired: the history is the only witness
    assert venue.orders[cid].state.value == "partially_filled"
    status = await service.stop(reason="test", actor="test")
    report = service.last_report
    assert report is not None and report.ok and not report.critical, report.as_dict()
    ledger = status["ledger"]
    assert ledger["fills"] == 1 and abs(ledger["inventory_btc"] - part) < 1e-12
    assert abs(report.balances["expected_base_btc"] - report.balances["venue_base_btc"]) <= 2e-5
    assert status["execution"]["trade_poll_fills"] == 1 and status["execution"]["fills"] == 1
    assert not status["open_orders"] and not venue.get_open_orders_sync() if hasattr(venue, "get_open_orders_sync") else not status["open_orders"]
    await live.market.close()


async def test_a_sticky_kill_of_the_maker_is_persisted_as_an_incident_and_an_operator_stop_is_not() -> None:
    """Observability, not just a journal row: a sticky engagement reaches the incidents
    table (and from there the alert webhook) with its trigger, reason and severity. The
    operator's own stop engages the switch too, and is deliberately not an incident."""
    live = await _live()
    service = live.service
    await service.start_live()
    await live.feed(4)
    await service.engage_kill_switch(reason="operator hit the button", actor="elian")
    incidents = [payload for kind, payload in live.persisted if kind == "incident"]  # type: ignore[attr-defined]
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc["kind"] == "mm_operator" and inc["actor"] == "elian" and "operator hit the button" in inc["reason"]
    assert inc["run_id"] == service.run_id and inc["detail"]["severity"] == "cancel_open" and inc["detail"]["is_live"] is False
    assert inc["incident_id"].startswith("inc") and inc["at"] is not None
    await service.stop(reason="done", actor="elian")
    incidents_after = [payload for kind, payload in live.persisted if kind == "incident"]  # type: ignore[attr-defined]
    assert len(incidents_after) == 1  # the stop is not an incident
    await live.market.close()


async def _delayed_snapshot(venue: FakeVenue, delay_s: float, *, replay: list | None = None):  # type: ignore[no-untyped-def, type-arg]
    """The venue answers openOrders at once, then the balances and trades reads take time
    (as they do on Testnet); the maker keeps quoting meanwhile. With ``replay`` the same
    stale picture is served again on later calls."""
    original = venue.get_orders

    async def slow(**kw):  # type: ignore[no-untyped-def]
        if replay is not None and replay:
            snapshot = list(replay[0])
        else:
            snapshot = await original(**kw)
            if replay is not None:
                replay.append(snapshot)
        await asyncio.sleep(delay_s)
        return snapshot

    venue.get_orders = slow  # type: ignore[method-assign]


async def test_a_quote_cancelled_while_the_reconciliation_was_reading_the_venue_is_the_snapshots_age_not_a_zombie() -> None:
    """The S10 FAIL of the Testnet service run (2026-10-04): between the venue's open-orders
    snapshot and the comparison, the maker cancelled both quotes (TTL 1 s, requote 500 ms);
    the comparison saw two orders the venue listed open that the local picture no longer
    held open, called them orders this run does not manage — critical — and engaged the
    sticky kill switch. Now the orders the run closed are known to the comparison: the
    picture's age is a warning, the venue is asked by id, and quoting goes on."""
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    await live.until_resting()
    await _delayed_snapshot(venue, 0.15)
    task = asyncio.create_task(service.reconcile())
    await asyncio.sleep(0.02)  # the snapshot is taken; the maker requotes while balances are read
    assert service.execution.cancel_all(live.clock.timestamp_ms(), reason="requote") == 2
    for _ in range(8):
        await asyncio.sleep(0.01)
        service.engine.on_event("tick", None, live.clock.timestamp_ms())
    assert service.execution.open_orders() == [] and len(service.execution.closed) == 2
    report = await task
    assert not report.critical and report.summary == "local_closed_venue_open x2"
    assert all(i["severity"] == "warning" and i["consecutive"] == 1 for i in report.discrepancies)
    assert not service.kill.engaged and service.state_label in ("quoting", "no_quote")
    await live.feed(2)  # the venue confirmed both cancels itself: the stale picture is only counted
    c = service.execution.counters
    assert c["closed_open_at_venue"] == 2 and c["reopened_from_venue"] == 0
    assert not service.kill.engaged
    await _teardown(live)


async def test_an_order_the_venue_keeps_listing_open_after_we_closed_it_is_critical_on_the_second_sighting() -> None:
    """Once is the picture's age. Twice in a row is an order the venue holds and nobody
    manages — the finding the critical classification was meant for."""
    live = await _live()
    service, venue = live.service, live.venue
    await service.start_live()
    await live.until_resting()
    replay: list = []  # type: ignore[type-arg]
    await _delayed_snapshot(venue, 0.05, replay=replay)
    task = asyncio.create_task(service.reconcile())
    await asyncio.sleep(0.01)
    service.execution.cancel_all(live.clock.timestamp_ms(), reason="requote")
    for _ in range(6):
        await asyncio.sleep(0.01)
        service.engine.on_event("tick", None, live.clock.timestamp_ms())
    first = await task
    assert not first.critical and all(i["consecutive"] == 1 for i in first.discrepancies)
    second = await service.reconcile()  # the venue serves the same picture again: still open there
    assert second.critical and all(i["kind"] == "local_closed_venue_open" and i["severity"] == "critical" and i["consecutive"] == 2 for i in second.discrepancies)
    assert service.kill.engaged and service.kill.sticky and service.kill.trigger == "reconciliation"
    assert "local_closed_venue_open" in service.kill.reason and service.state_label == "safe"
    await _teardown(live)


async def test_the_stops_own_close_of_the_account_stream_is_not_a_drop_and_leaves_no_transient_condition() -> None:
    """Seen on Testnet: after stop() the status carried a transient ``user_stream_down``
    ("account stream dropped: closed") — the stop closing the stream it owns, read as the
    venue dropping it. The stop is the only cause left engaged, and nothing transient."""
    from tests.unit.mm.fake_venue import FakeUserStream

    live = await _live()
    service, venue = live.service, live.venue
    stream = FakeUserStream(venue, now_ms=live.clock.timestamp_ms, on_report=service.execution.absorb_execution_report, on_balances=service.execution.absorb_balances, on_status=service.execution.absorb_stream_status)
    service.attach_user_stream(stream)
    await service.start_live()
    await live.until_resting()
    status = await service.stop(reason="done", actor="test")
    kill = status["kill_switch"]
    assert kill["shutdown"]["actor"] == "test" and not kill["engaged"] and not kill["sticky"] and kill["transient"] == {}
    assert service.execution.stream_connected is False and service.execution.counters["stream_drops"] == 1  # counted, not escalated
    assert status["open_orders"] == [] and not venue_has_open(venue)
    await live.market.close()


def venue_has_open(venue: FakeVenue) -> bool:
    return any(not o.state.is_terminal for o in venue.orders.values())


async def test_a_stale_data_condition_engaged_just_before_stop_does_not_survive_the_shutdown() -> None:
    """The Testnet S10b FAIL of 2026-10-04: market data went stale in the last heartbeat
    before stop(); _watch — the only thing that clears the transient — never ran again,
    and the final status carried a ghost ``data`` condition next to a stop recorded as a
    sticky kill. The shutdown now clears what nothing can observe any more and is reported
    as a shutdown, with no safety engagement left."""
    live = await _live()
    service = live.service
    await service.start_live()
    await live.until_resting()
    live.clock.advance_by(timedelta(seconds=5))  # the feed goes silent
    await asyncio.sleep(0.15)  # the heartbeat sees it: transient data kill, quotes cancelled
    assert service.kill.engaged and "data" in service.kill.as_dict()["transient"]
    status = await service.stop(reason="validation window elapsed", actor="validator")
    kill = status["kill_switch"]
    assert kill["shutdown"]["reason"].startswith("validation window elapsed") and kill["transient"] == {}
    assert kill["engaged"] is False and kill["sticky"] is False and kill["blocks_quoting"] is True
    assert status["state"] == "stopped" and status["open_orders"] == []
    assert any(e.action == "clear" and e.trigger == "data" and "shut down" in e.reason for e in service.kill.history)
    await live.market.close()


async def test_repeated_stale_and_recovery_cycles_leave_no_residue_and_quoting_resumes_each_time() -> None:
    live = await _live()
    service = live.service
    await service.start_live()
    await live.until_resting()
    for cycle in range(3):
        live.clock.advance_by(timedelta(seconds=5))
        await asyncio.sleep(0.15)
        assert service.kill.engaged and not service.kill.sticky and "data" in service.kill.as_dict()["transient"], cycle
        assert all(o.state.is_terminal for o in live.venue.orders.values()), "stale data: what rested was cancelled"
        placed_before = service.execution.counters["placed"]
        await asyncio.sleep(0.1)
        assert service.execution.counters["placed"] == placed_before, "nothing is placed on stale data"
        await live.feed(3, step_ms=100)  # fresh data
        assert not service.kill.engaged and service.kill.as_dict()["transient"] == {} and service.kill.severity is None
        await live.until_resting()  # quoting resumed through the real path
    history = service.kill.history
    assert sum(1 for e in history if e.action == "engage" and e.trigger == "data") == 3
    assert sum(1 for e in history if e.action == "clear" and e.trigger == "data") == 3
    assert service.kill.engagements == 3 and not service.kill.sticky and not service.kill.shut_down
    await _teardown(live)


async def test_a_stop_with_nothing_open_is_a_clean_shutdown_too() -> None:
    """An account that cannot fund either side: the authorizer removes both, nothing is ever
    placed, and the stop has nothing to cancel. Still a shutdown, still clean."""
    live = await _live(venue_kwargs={"quote_balance": 0.0, "base_balance": 0.0})
    service = live.service
    await service.start_live()
    await live.feed(6)
    assert service.execution.counters["placed"] == 0 and service.execution.open_orders() == []
    status = await service.stop(reason="nothing to do", actor="test")
    kill = status["kill_switch"]
    assert kill["shutdown"] and not kill["engaged"] and kill["transient"] == {} and status["open_orders"] == []
    assert service.last_report is not None and service.last_report.ok and status["state"] == "stopped"
    await live.market.close()


async def test_the_initial_reconciliation_notes_when_an_asset_cannot_fund_a_side() -> None:
    live = await _live(venue_kwargs={"quote_balance": 5_000.0, "base_balance": 0.0})
    report = await live.service.start_live()
    assert report.ok and "funding_note_ask" in report.balances and "no ask can be funded" in report.balances["funding_note_ask"]
    assert live.service.live_ledger.balances() == (5_000.0, 0.0)
    await live.feed(6)
    quotes = [r for r in live.service.engine.journal if r.get("kind") == "decision" and r.get("decision") == "quote"]
    assert quotes and all(r["ask"] is None for r in quotes), "with no base asset the risk authorizer removes the ask"
    await _teardown(live)


# ------------------------------------------------------------------ orders a previous run left open


async def test_orders_of_a_previous_run_found_open_at_start_are_cancelled_before_quoting_and_reported() -> None:
    """A run that died with orders resting: the next run finds them at the venue under its own
    prefix, cancels each by id before placing anything, records the sweep in the journal and
    as an incident, and quotes. Nothing is adopted, nothing is resent."""
    from tia.mm.execution import CLIENT_ID_PREFIX

    live = await _live()
    service, venue = live.service, live.venue
    old = [venue.add_orphan_open_order(f"{CLIENT_ID_PREFIX}oldrun00-1790000000000-00000{i}", side=side) for i, side in ((1, Side.BUY), (2, Side.SELL))]
    old_ids = [o.client_order_id for o in old]
    report = await service.start_live()
    assert not report.critical and not service.kill.engaged, report.as_dict()
    sweep = service.orphan_sweep
    assert sweep is not None and sweep["found"] == old_ids and [c["order_id"] for c in sweep["cancelled"]] == old_ids and sweep["failed"] == []
    assert all(venue.orders[cid].state.is_terminal for cid in old_ids) and all(venue.cancels.count(cid) == 1 for cid in old_ids)
    assert service.status()["orphan_sweep"]["found"] == old_ids
    assert any(r.get("kind") == "orphan_sweep" and r.get("found") == old_ids for r in service.engine.journal)
    await live.until_resting()  # quoting proceeds through the real path
    incidents = [p for k, p in live.persisted if k == "incident"]  # type: ignore[attr-defined]  # the writer runs once the service is started
    assert len(incidents) == 1 and incidents[0]["kind"] == "mm_orphans_swept" and incidents[0]["detail"]["cancelled"] == old_ids
    assert all(i.client_order_id.startswith(f"{CLIENT_ID_PREFIX}{service.execution.run_tag[:8]}") for i in venue.submits)  # only this run submits
    assert service.execution.counters["venue_orders_unknown_locally"] == 0
    await _teardown(live)


async def test_an_orphan_the_venue_will_not_cancel_is_left_to_the_initial_reconciliation_which_is_critical() -> None:
    from tia.mm.execution import CLIENT_ID_PREFIX

    live = await _live()
    service, venue = live.service, live.venue
    cid = f"{CLIENT_ID_PREFIX}oldrun00-1790000000000-000007"
    venue.add_orphan_open_order(cid)
    venue.next_cancel = ["transport"]  # the venue does not take the cancel
    report = await service.start_live()
    sweep = service.orphan_sweep
    assert sweep is not None and sweep["found"] == [cid] and sweep["cancelled"] == [] and sweep["failed"][0]["order_id"] == cid
    assert report.critical and "venue_order_unknown_locally" in report.summary
    assert service.kill.engaged and service.kill.sticky and service.state_label == "safe"
    await live.feed(4)
    assert service.execution.counters["placed"] == 0  # nothing is placed over an order nobody manages
    assert not venue.orders[cid].state.is_terminal  # still the venue's fact; a person decides
    await _teardown(live)


async def test_a_foreign_open_order_at_start_is_not_swept_and_stays_critical() -> None:
    live = await _live()
    service, venue = live.service, live.venue
    foreign = venue.add_foreign_open_order("someone-else-3")
    report = await service.start_live()
    assert service.orphan_sweep == {"t_ms": service.orphan_sweep["t_ms"], "found": [], "cancelled": [], "failed": []}  # type: ignore[index]
    assert venue.cancels == [] and not foreign.state.is_terminal
    assert report.critical and "foreign_open_order" in report.summary and service.kill.sticky
    await _teardown(live)
