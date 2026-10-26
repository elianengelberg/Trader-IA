"""P0 — the protective stop at the Binance spot adapter, against a mock venue (no network).

The runtime protects every position with an ``OrderType.STOP`` intent (stop price, sell for a
long). Binance spot documents ``STOP_LOSS`` for exactly that: mandatory ``quantity`` and
``stopPrice`` (or ``trailingDelta``), executed as a MARKET order once the stop price is met,
no ``timeInForce`` in its mandatory set (developers.binance.com, Spot API, "New order (TRADE)",
read 2026-10-22). These tests pin the wire request, the venue's answers and the adapter's
classification of every failure. The mock transport records every request; nothing leaves
the process.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tests.unit.test_binance_live import START, provider
from tia.core.errors import (
    ExecutionError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.domain.enums import OrderState, OrderType, Side, TimeInForce
from tia.domain.orders import OrderIntent

STOP_PRICE = 49_000.0


def stop_intent(*, quantity: float = 0.01, stop_price: float | None = STOP_PRICE, signal: str = "protective:BTC-USD:run:7") -> OrderIntent:
    """Exactly the intent ``LiveRuntime._sync_protective_stop`` builds for a long."""
    return OrderIntent(
        intent_id="int-stop-1",
        client_order_id=OrderIntent.build_client_order_id(
            signal_id=signal, symbol="BTC-USD", side=Side.SELL, quantity=quantity, order_type=OrderType.STOP,
        ),
        signal_id="protective:BTC-USD",
        risk_decision_id="protective:BTC-USD",
        symbol="BTC-USD",
        side=Side.SELL,
        quantity=quantity,
        order_type=OrderType.STOP,
        stop_price=stop_price,
        time_in_force=TimeInForce.GTC,
        created_at=START,
        reduce_only=True,
    )


def params_of(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}


def accepted(cid: str, *, order_id: int = 555, status: str = "NEW") -> dict[str, Any]:
    return {"symbol": "BTCUSDT", "orderId": order_id, "orderListId": -1, "clientOrderId": cid,
            "transactTime": int(START.timestamp() * 1000), "price": "0.00000000", "origQty": "0.01000000",
            "executedQty": "0.00000000", "cummulativeQuoteQty": "0.00000000", "status": status,
            "timeInForce": "GTC", "type": "STOP_LOSS", "side": "SELL", "stopPrice": "49000.00000000",
            "workingTime": -1, "fills": []}


class Venue:
    """A scripted venue: answers in order, records every request."""

    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        return httpx.Response(status, content=json.dumps(body).encode())

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


# 1. accepted and confirmed by the exchange
async def test_1_a_protective_stop_is_sent_as_stop_loss_with_its_documented_parameters() -> None:
    intent = stop_intent()
    venue = Venue((200, accepted(intent.client_order_id)))
    order = await provider(venue, simulated=True).submit_order(intent)
    [post] = venue.posts()
    p = params_of(post)
    assert urlsplit(str(post.url)).path == "/api/v3/order"
    assert p["type"] == "STOP_LOSS" and p["side"] == "SELL" and p["symbol"] == "BTCUSDT"
    assert float(p["stopPrice"]) == STOP_PRICE and float(p["quantity"]) == 0.01
    assert p["newClientOrderId"] == intent.client_order_id
    assert "timeInForce" not in p and "price" not in p, "STOP_LOSS carries neither (documented mandatory set)"
    assert order.state is OrderState.ACKNOWLEDGED and order.order_id == "555" and order.fills == []
    assert order.stop_price == STOP_PRICE and order.order_type is OrderType.STOP


def test_1b_a_stop_intent_without_a_stop_price_cannot_even_be_built() -> None:
    """The domain refuses it (``OrderIntent`` validation), so no adapter ever sees one."""
    with pytest.raises(ValueError, match="stop requires stop_price"):
        stop_intent(stop_price=None)


# 2. order type refused for the symbol / 5. refused by a symbol filter: definite, not unknown
@pytest.mark.parametrize("msg", ["Stop loss orders are not supported for this symbol.", "Filter failure: PRICE_FILTER"])
async def test_2_5_a_venue_refusal_is_a_definite_rejection(msg: str) -> None:
    venue = Venue((400, {"code": -1013, "msg": msg}))
    with pytest.raises(OrderRejectedError) as raised:
        await provider(venue, simulated=True).submit_order(stop_intent())
    assert raised.value.context.get("code") == -1013 and len(venue.posts()) == 1


# 3. network error before an answer / 4. timeout after the venue may have accepted
async def test_3_a_transport_error_is_provider_unavailable() -> None:
    venue = Venue(httpx.ConnectError("connection refused"))
    with pytest.raises(ProviderUnavailableError):
        await provider(venue, simulated=True).submit_order(stop_intent())


async def test_4_a_timeout_is_unknown_and_resolution_asks_the_venue_by_our_id() -> None:
    intent = stop_intent()
    venue = Venue(httpx.ReadTimeout("no answer"), (200, accepted(intent.client_order_id)))
    adapter = provider(venue, simulated=True)
    with pytest.raises(ReconciliationError):
        await adapter.submit_order(intent)
    found = await adapter.resolve_unknown_order(symbol="BTC-USD", client_order_id=intent.client_order_id)
    assert found is not None and found.state is OrderState.ACKNOWLEDGED
    query = params_of(venue.requests[-1])
    assert venue.requests[-1].method == "GET" and query["origClientOrderId"] == intent.client_order_id
    # 11. the retry after resolution is answered locally: one POST in total
    again = await adapter.submit_order(intent)
    assert again.order_id == found.order_id and len(venue.posts()) == 1


# 6. accepted, then absent at the next query
async def test_6_an_acknowledged_stop_the_venue_then_denies_is_unknown_not_absent() -> None:
    intent = stop_intent()
    venue = Venue((200, accepted(intent.client_order_id)), (400, {"code": -2013, "msg": "Order does not exist."}))
    adapter = provider(venue, simulated=True)
    await adapter.submit_order(intent)
    with pytest.raises(ExecutionError):
        await adapter.resolve_unknown_order(symbol="BTC-USD", client_order_id=intent.client_order_id)


# 7. the status query itself fails
async def test_7_a_failed_status_query_raises_rather_than_reporting_a_state() -> None:
    intent = stop_intent()
    venue = Venue((200, accepted(intent.client_order_id)), httpx.ConnectError("reset"))
    adapter = provider(venue, simulated=True)
    await adapter.submit_order(intent)
    with pytest.raises(ProviderUnavailableError):
        await adapter.get_order(intent.client_order_id)


# 12. cancelling (to replace) an existing stop names it by the venue's id
async def test_12_cancelling_a_stop_uses_the_venue_order_id_and_reports_cancelled() -> None:
    intent = stop_intent()
    cancelled = {**accepted(intent.client_order_id), "status": "CANCELED", "origClientOrderId": intent.client_order_id,
                 "clientOrderId": "cancel-xyz"}
    venue = Venue((200, accepted(intent.client_order_id)), (200, cancelled))
    adapter = provider(venue, simulated=True)
    await adapter.submit_order(intent)
    order = await adapter.cancel_order(intent.client_order_id)
    delete = venue.requests[-1]
    assert delete.method == "DELETE" and params_of(delete)["orderId"] == "555"
    assert order.state is OrderState.CANCELLED and order.client_order_id == intent.client_order_id


async def test_an_open_stop_read_from_the_venue_keeps_its_type() -> None:
    """Reconciliation reads open orders without a local record (an earlier session's stop):
    the venue's ``type`` must not be read as MARKET."""
    venue = Venue((200, [accepted("earlier-session-stop", order_id=777)]))
    [order] = await provider(venue, simulated=True).get_orders(open_only=True, symbol="BTC-USD")
    assert order.order_type is OrderType.STOP and order.stop_price == STOP_PRICE
