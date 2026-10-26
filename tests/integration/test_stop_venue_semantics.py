"""Mission v3 — the protective stop against what the venue documents, not what we expected.

Two defects found by holding the code against the Spot API documentation (developers.binance.com,
"HTTP Return Codes", "Error codes" and "Filters", read 2026-10-26), and one documented gap:

* **An internal error is not a refusal.** HTTP ``5XX``: "It is important to NOT treat this as a
  failure operation; the execution status is UNKNOWN and could have been a success". Code
  ``-1007``: "Send status unknown; execution status unknown". The adapter read both as a definite
  rejection (``OrderRejectedError``), and a connection that broke after the request was sent as
  "unavailable". For a protective stop that meant ``failed`` and, on the next bar, a *second* stop
  under a new client id over the one that may rest; for an entry, an exception out of the cycle
  and an order nobody tracks.
* **The stop quantity was not on the lot grid.** The venue reports the position as the base
  asset it holds; after a fee paid in that asset the balance is off the step grid, and LOT_SIZE
  refuses ``quantity % stepSize != 0``. Every other order of the session is quantized down
  (``_build_intent``); the stop was sent as the raw balance and refused.
* **Documented, not changed (needs a person's decision, D25):** a stop the venue refuses because
  its level is already crossed ("Order would trigger immediately.") leaves the position open
  and unprotected; the session halts new orders and says so, but does not exit. The paper venue
  fills such a stop at once. The characterization test below pins today's behavior.

What these tests cannot prove: that the venue answers exactly this way. That is Testnet's job
(``scripts/validate_binance.py``), and it has not been run here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest

from tests.integration.test_account_restore import build, open_position
from tests.integration.test_paper_cancellations import working
from tests.integration.test_protection_invariants import incidents, recorder, status
from tests.unit.test_binance_live import provider
from tests.unit.test_binance_protective_stop import Venue, accepted, params_of, stop_intent
from tia.core.errors import OrderRejectedError, ProviderUnavailableError, ReconciliationError
from tia.domain.enums import OrderState, OrderType
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.runtime.states import LiveState

SYMBOL_STEP = Decimal(repr(DEFAULT_UNIVERSE.get("BTC-USD").lot_size))


# ============================================================== the adapter: what a failure means


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
async def test_an_internal_error_answering_an_order_is_unknown_not_a_refusal(status_code: int) -> None:
    intent = stop_intent()
    venue = Venue((status_code, {"code": -1000, "msg": "An unknown error occurred while processing the request."}),
                  (200, accepted(intent.client_order_id)))
    adapter = provider(venue, simulated=True)
    with pytest.raises(ReconciliationError, match="UNKNOWN"):
        await adapter.submit_order(intent)
    # The only correct next step is the venue's own answer, by our id; the same intent is then
    # answered locally: one POST in total.
    found = await adapter.resolve_unknown_order(symbol="BTC-USD", client_order_id=intent.client_order_id)
    assert found is not None and found.state is OrderState.ACKNOWLEDGED
    assert params_of(venue.requests[-1])["origClientOrderId"] == intent.client_order_id
    again = await adapter.submit_order(intent)
    assert again.order_id == found.order_id and len(venue.posts()) == 1


async def test_an_internal_error_with_a_non_json_body_is_unknown_too() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    with pytest.raises(ReconciliationError):
        await provider(handler, simulated=True).submit_order(stop_intent())


@pytest.mark.parametrize("status_code", [400, 500])
async def test_code_1007_send_status_unknown_is_unknown(status_code: int) -> None:
    venue = Venue((status_code, {"code": -1007, "msg": "Timeout waiting for response from backend server. "
                                 "Send status unknown; execution status unknown."}))
    with pytest.raises(ReconciliationError):
        await provider(venue, simulated=True).submit_order(stop_intent())


@pytest.mark.parametrize("error", [httpx.ReadError("connection reset by peer"),
                                   httpx.RemoteProtocolError("server disconnected without sending a response"),
                                   httpx.WriteError("broken pipe")],
                         ids=["read", "protocol", "write"])
async def test_a_connection_that_breaks_in_flight_is_unknown(error: Exception) -> None:
    venue = Venue(error)
    with pytest.raises(ReconciliationError, match="UNKNOWN"):
        await provider(venue, simulated=True).submit_order(stop_intent())


async def test_a_connection_never_made_is_unavailable_the_request_never_left() -> None:
    venue = Venue(httpx.ConnectError("connection refused"))
    with pytest.raises(ProviderUnavailableError):
        await provider(venue, simulated=True).submit_order(stop_intent())


async def test_a_cancel_answered_with_an_internal_error_is_unknown() -> None:
    intent = stop_intent()
    venue = Venue((200, accepted(intent.client_order_id)), (503, {"code": -1000, "msg": "internal"}))
    adapter = provider(venue, simulated=True)
    await adapter.submit_order(intent)
    with pytest.raises(ReconciliationError):
        await adapter.cancel_order(intent.client_order_id)


async def test_an_internal_error_on_a_read_is_an_outage_not_a_refusal() -> None:
    intent = stop_intent()
    venue = Venue((200, accepted(intent.client_order_id)), (503, {"code": -1000, "msg": "internal"}))
    adapter = provider(venue, simulated=True)
    await adapter.submit_order(intent)
    with pytest.raises(ProviderUnavailableError):
        await adapter.get_order(intent.client_order_id)


@pytest.mark.parametrize("code,msg", [(-2010, "Order would trigger immediately."),
                                      (-1013, "Filter failure: LOT_SIZE"),
                                      (-2010, "Account has insufficient balance for requested action.")])
async def test_a_venue_refusal_is_still_a_definite_rejection(code: int, msg: str) -> None:
    venue = Venue((400, {"code": code, "msg": msg}))
    with pytest.raises(OrderRejectedError) as raised:
        await provider(venue, simulated=True).submit_order(stop_intent())
    assert raised.value.context.get("code") == code


# ============================================================== the runtime: what it does with it


async def _adapter_error(status_code: int, body: Any) -> Exception:
    """The exception the Binance adapter of *this* tree raises for that answer to a POST."""
    adapter = provider(Venue((status_code, body)), simulated=True)
    try:
        await adapter.submit_order(stop_intent())
    except Exception as exc:  # the point is which one it is
        return exc
    raise AssertionError("the adapter accepted an error answer")


async def test_a_stop_answered_503_after_the_venue_took_it_is_resolved_not_doubled(monkeypatch: pytest.MonkeyPatch) -> None:
    """The venue placed the stop and its answer was a 503. One stop must rest, under one id."""
    error = await _adapter_error(503, {"code": -1000, "msg": "internal"})
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        real = execution.submit_order
        held: dict[str, Any] = {}
        sent: list[str] = []

        async def submit(intent):  # type: ignore[no-untyped-def]
            if intent.order_type is OrderType.STOP:
                sent.append(intent.client_order_id)
                if not held:
                    held["order"] = await real(intent)  # it rests at the venue
                    raise error
            return await real(intent)

        async def resolve(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            return held["order"] if held and held["order"].client_order_id == client_order_id else None

        monkeypatch.setattr(execution, "submit_order", submit)
        monkeypatch.setattr(execution, "resolve_unknown_order", resolve, raising=False)
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
        stops = await working(execution, OrderType.STOP)
        assert len(stops) == 1, f"{len(stops)} stops rest on one position: {[s.client_order_id for s in stops]}"
        assert set(sent) == {held["order"].client_order_id}, "no stop under a second id"
        assert status(runtime) == "confirmed"
    finally:
        await runtime.stop()


async def test_an_entry_answered_503_after_the_venue_filled_it_is_adopted(monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry the venue executed while answering 503: the session must know it holds it."""
    error = await _adapter_error(503, {"code": -1000, "msg": "internal"})
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        real = execution.submit_order
        held: dict[str, Any] = {}

        async def submit(intent):  # type: ignore[no-untyped-def]
            if not intent.reduce_only and intent.order_type is not OrderType.STOP and not held:
                held["order"] = await real(intent)
                raise error
            return await real(intent)

        async def resolve(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            return held["order"] if held and held["order"].client_order_id == client_order_id else None

        monkeypatch.setattr(execution, "submit_order", submit)
        monkeypatch.setattr(execution, "resolve_unknown_order", resolve, raising=False)
        await open_position(runtime, market)
        assert held, "the injected answer was used"
        assert held["order"].client_order_id in {o["client_order_id"] for o in runtime.recent_orders}, (
            "the executed entry is the session's own order")
        assert runtime.counters.get("unknown_order_states", 0) >= 1, "it was read as unknown, then resolved"
    finally:
        await runtime.stop()


def _report_held(monkeypatch: pytest.MonkeyPatch, execution: Any, held_of: Any) -> None:
    """The venue's view of the position: what the account holds of the base asset."""
    real = execution.get_portfolio

    async def get_portfolio():  # type: ignore[no-untyped-def]
        portfolio = await real()
        position = portfolio.positions.get("BTC-USD")
        if position is not None and not position.is_flat:
            position.quantity = held_of(position.quantity)
        return portfolio

    monkeypatch.setattr(execution, "get_portfolio", get_portfolio)


def _stops_sent(monkeypatch: pytest.MonkeyPatch, execution: Any) -> list[Any]:
    real = execution.submit_order
    seen: list[Any] = []

    async def submit(intent):  # type: ignore[no-untyped-def]
        if intent.order_type is OrderType.STOP:
            seen.append(intent)
        return await real(intent)

    monkeypatch.setattr(execution, "submit_order", submit)
    return seen


async def test_a_held_quantity_off_the_lot_grid_gets_a_stop_on_the_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """The venue reports what the account holds of the base asset; here a fraction of a lot
    less than the tracked leg (within the size check's one-lot tolerance) and off the grid.
    The stop is replaced by one the venue's LOT_SIZE accepts: a whole number of lots, never
    more than is held."""
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        _report_held(monkeypatch, execution, lambda q: q - float(SYMBOL_STEP) * 0.37)
        seen = _stops_sent(monkeypatch, execution)
        market.advance()
        await runtime._cycle_once()
        assert seen, "the runtime re-protected the position at the size the venue reports"
        held = runtime._last_position[0]
        q = Decimal(repr(seen[-1].quantity))
        assert q % SYMBOL_STEP == 0, f"stop quantity {q} is off the lot step {SYMBOL_STEP}"
        assert 0 < seen[-1].quantity <= held and held - seen[-1].quantity < float(SYMBOL_STEP)
        assert status(runtime) == "confirmed", runtime.protection_status
        [stop] = await working(execution, OrderType.STOP)
        assert stop.client_order_id == seen[-1].client_order_id
    finally:
        await runtime.stop()


async def test_a_position_below_one_lot_sends_no_stop_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        await open_position(runtime, market)
        seen = _stops_sent(monkeypatch, execution)
        await runtime._sync_protective_stop(float(SYMBOL_STEP) * 0.4)
        assert seen == [], "an order the venue's LOT_SIZE refuses is not sent"
        assert status(runtime) == "failed" and runtime.protection_status.get("error") == "below_lot"
        assert incidents(saved, "protection_failed")
        assert "protection_failed" in runtime.entry_blocks
    finally:
        await runtime.stop()


async def test_an_unknown_stop_is_resolved_before_a_dust_position_is_declared_unprotectable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Order matters: a stop whose submission timed out may have executed and left the dust.
    The venue is asked about it first; only then is the dust said to be unprotectable."""
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        real = execution.submit_order
        held: dict[str, Any] = {}

        async def submit_then_time_out(intent):  # type: ignore[no-untyped-def]
            if intent.order_type is OrderType.STOP and not held:
                held["order"] = await real(intent)  # the venue took it; the answer was lost
                raise ReconciliationError("timed out; state UNKNOWN")
            return await real(intent)

        asked: list[str] = []

        async def resolve(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            asked.append(client_order_id)
            return held["order"] if held and held["order"].client_order_id == client_order_id else None

        monkeypatch.setattr(execution, "submit_order", submit_then_time_out)
        monkeypatch.setattr(execution, "resolve_unknown_order", resolve, raising=False)
        await runtime._cancel_protective()
        await runtime._sync_protective_stop(runtime._last_position[0])
        assert status(runtime) == "unknown" and held, "the stop's fate is unknown"
        await runtime._sync_protective_stop(float(SYMBOL_STEP) * 0.4)
        assert asked == [held["order"].client_order_id], "the venue is asked before anything else"
        assert runtime._protective is not None and runtime._protective["order_id"] == held["order"].order_id
    finally:
        await runtime.stop()


@pytest.mark.xfail(strict=True, reason=(
    "D26 (mission v3, a person's decision): on Binance spot a BUY pays its commission in the base "
    "asset unless BNB pays it. The session books the fill's gross quantity, the venue holds the net; "
    "a difference over one lot is read as 'position size disagrees', the session halts and the stop "
    "is never placed. Paper charges fees in quote, so no paper evidence shows it."))
async def test_d26_a_buy_that_paid_its_fee_in_the_base_asset_is_still_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        _report_held(monkeypatch, execution, lambda q: q * 0.999)  # 0.1 % taker fee, in BTC
        for _ in range(2):
            market.advance()
            await runtime._cycle_once()
        assert "position_unverified" not in runtime.entry_blocks, runtime.entry_blocks
        assert runtime.machine.state is not LiveState.HALT_NEW_ORDERS
        assert status(runtime) == "confirmed"
    finally:
        await runtime.stop()


async def test_characterization_a_stop_refused_as_already_triggered_halts_but_does_not_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Today's behavior, pinned (D25, a decision for a person): the venue refuses the stop because
    the price is already through it; the session says so loudly and halts new orders, and the
    position stays open with no exit. Not an endorsement: if D25 is decided, this test changes."""
    error = OrderRejectedError("binance rejected /api/v3/order: HTTP 400 code=-2010 Order would trigger immediately.",
                               code=-2010, path="/api/v3/order")
    saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        await open_position(runtime, market)
        real = execution.submit_order
        refused: list[str] = []

        async def submit(intent):  # type: ignore[no-untyped-def]
            if intent.order_type is OrderType.STOP:
                refused.append(intent.client_order_id)
                raise error
            return await real(intent)

        monkeypatch.setattr(execution, "submit_order", submit)
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
        assert len(refused) >= 2, "each bar tries again"
        assert status(runtime) == "failed" and incidents(saved, "protection_failed")
        assert runtime.machine.state is LiveState.HALT_NEW_ORDERS
        assert runtime._open_trade is not None and runtime._pending_exit is None, "no exit is sent"
    finally:
        await runtime.stop()
