"""The Binance execution adapter, against a mock transport.

Integration status of the code under test: **REQUIRES VALIDATION.** These tests exercise
the adapter's *logic* against responses shaped the way the documentation describes. They
cannot and do not verify that the documentation is right — no request in this repository
has ever reached a Binance host, because every one of them is blocked in the build
environment. ``scripts/validate_binance.py`` is what closes that gap.

So what is actually proven here is the part that is ours to get right: idempotency,
refusing to guess at an unknown order state, refusing to retry after a timeout, keeping the
secret out of everything, and having no code path that moves funds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from tia.core.clock import FrozenClock, SimulatedClock
from tia.core.errors import (
    ExecutionError,
    LiveActivationError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.data.providers.binance_live import BinanceExecutionProvider
from tia.data.providers.binance_signing import (
    MAX_RECV_WINDOW_MS,
    BinanceCredentials,
    BinanceSigner,
)
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import OrderIntent
from tia.live.gate import CONFIRMATION_PHRASE, REQUIRED_CHECKS, LiveActivationGate, passing
from tia.live.permissions import check_permissions

START = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
SECRET = "not-a-real-secret-value"  # noqa: S105 - fixture material, never a live key


def credentials() -> BinanceCredentials:
    return BinanceCredentials.from_values(api_key="pub-key-abc", secret=SECRET)


def signer(clock: Any = None) -> BinanceSigner:
    return BinanceSigner(credentials(), clock or FrozenClock(START))


def live_token(clock: Any = None) -> Any:
    gate = LiveActivationGate(clock or FrozenClock(START), environment="live")
    return gate.arm(
        {name: passing(name, "verified") for name in REQUIRED_CHECKS},
        operator="elian",
        confirmation=CONFIRMATION_PHRASE,
        max_live_capital=500.0,
        fingerprint="fp-1",
    )


def intent(*, quantity: float = 0.01, signal_id: str = "sig-1") -> OrderIntent:
    return OrderIntent(
        intent_id="int-1",
        client_order_id=OrderIntent.build_client_order_id(
            signal_id=signal_id,
            symbol="BTC-USD",
            side=Side.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
        ),
        signal_id=signal_id,
        risk_decision_id="risk-1",
        symbol="BTC-USD",
        side=Side.BUY,
        quantity=quantity,
        created_at=START,
    )


FILLED_RESPONSE = {
    "symbol": "BTCUSDT",
    "orderId": 987654,
    "clientOrderId": "",
    "transactTime": int(START.timestamp() * 1000),
    "price": "0.00000000",
    "origQty": "0.01000000",
    "executedQty": "0.01000000",
    "cummulativeQuoteQty": "500.00000000",
    "status": "FILLED",
    "side": "BUY",
    "fills": [
        {"price": "50000.00", "qty": "0.01", "commission": "0.05", "tradeId": 111}
    ],
}


def provider(
    handler: Any, *, simulated: bool = False, clock: Any = None
) -> BinanceExecutionProvider:
    clock = clock or SimulatedClock(START)
    return BinanceExecutionProvider(
        signer=signer(clock),
        clock=clock,
        activation=None if simulated else live_token(clock),
        simulated=simulated,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.binance.test"
        ),
    )


# --------------------------------------------------------------------------- the gate


def test_the_adapter_cannot_be_built_live_without_an_activation_token() -> None:
    with pytest.raises(LiveActivationError, match="LiveActivationToken"):
        BinanceExecutionProvider(
            signer=signer(), clock=SimulatedClock(START), activation=None, simulated=False
        )


async def test_an_expired_activation_stops_the_next_order_not_the_next_restart() -> None:
    """The gate is checked immediately before the request, so a session that has been
    running for hours cannot keep trading on an activation that lapsed."""
    clock = SimulatedClock(START)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={**FILLED_RESPONSE, "clientOrderId": "x"})

    adapter = provider(handler, clock=clock)
    await adapter.submit_order(intent())
    assert len(calls) == 1

    clock.advance_by(timedelta(hours=3))
    with pytest.raises(LiveActivationError, match="expired"):
        await adapter.submit_order(intent(signal_id="sig-2"))
    assert len(calls) == 1  # nothing was sent


# --------------------------------------------------------------------------- idempotency


ACK_RESPONSE = {
    "symbol": "BTCUSDT",
    "orderId": 987654,
    "orderListId": -1,
    "clientOrderId": "",
    "transactTime": int(START.timestamp() * 1000),
    "price": "50000.00",
    "origQty": "0.01000000",
    "executedQty": "0.00000000",
    "cummulativeQuoteQty": "0.00000000",
    "status": "NEW",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "side": "BUY",
}


async def test_cancel_and_query_name_the_order_by_the_venue_id_and_keep_our_client_id() -> None:
    """The venue re-keys a cancelled order's ``clientOrderId`` to the cancel's own id (its
    cancel response says so: ``origClientOrderId`` is ours, ``clientOrderId`` is the cancel's).
    Observed on Testnet: a query by that id answered -2013 for an order that had just been
    cancelled. So once the venue has given us an orderId, every cancel and query uses it,
    and the local mirror keeps the client id *we* chose."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        params = dict(httpx.QueryParams(request.url.query.decode()))
        ours = intent().client_order_id
        if request.method == "POST":
            return httpx.Response(200, json={**ACK_RESPONSE, "clientOrderId": ours})
        if request.method == "DELETE":
            assert params["orderId"] == "987654" and "origClientOrderId" not in params
            return httpx.Response(200, json={**ACK_RESPONSE, "status": "CANCELED", "origClientOrderId": ours, "clientOrderId": "cancel-auto-7f3a"})
        assert params["orderId"] == "987654" and "origClientOrderId" not in params
        return httpx.Response(200, json={**ACK_RESPONSE, "status": "CANCELED", "clientOrderId": "cancel-auto-7f3a"})

    adapter = provider(handler, simulated=True)
    placed = await adapter.submit_order(intent())
    assert placed.order_id == "987654" and placed.client_order_id == intent().client_order_id

    cancelled = await adapter.cancel_order(placed.client_order_id)
    assert cancelled.state is OrderState.CANCELLED
    assert cancelled.client_order_id == placed.client_order_id  # not the cancel's id
    assert cancelled.order_id == "987654"

    confirmed = await adapter.get_order(placed.client_order_id)
    assert confirmed is not None and confirmed.state is OrderState.CANCELLED and confirmed.client_order_id == placed.client_order_id
    assert [r.method for r in seen] == ["POST", "DELETE", "GET"]


async def test_before_any_acknowledgement_the_order_is_named_by_our_client_id() -> None:
    """Without an orderId there is nothing else to name it by; ``origClientOrderId`` is the
    documented handle, and -2013 then means the venue never saw it."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})

    adapter = provider(handler, simulated=True)
    resolved = await adapter.resolve_unknown_order(symbol="BTC-USD", client_order_id="tiamm-never-sent-1")
    assert resolved is None
    params = dict(httpx.QueryParams(seen[0].url.query.decode()))
    assert params["origClientOrderId"] == "tiamm-never-sent-1" and "orderId" not in params


async def test_resolving_an_acknowledged_order_the_venue_now_denies_is_unknown_not_absent() -> None:
    """-2013 after an acknowledgement is a contradiction, not a confirmation: the order
    existed. It is reported as unknown so nothing retries the intent and nothing assumes
    a cancel or a fill."""
    from tia.core.errors import ExecutionError

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={**ACK_RESPONSE, "clientOrderId": intent().client_order_id})
        return httpx.Response(400, json={"code": -2013, "msg": "Order does not exist."})

    adapter = provider(handler, simulated=True)
    placed = await adapter.submit_order(intent())
    with pytest.raises(ExecutionError, match="UNKNOWN, not absent"):
        await adapter.resolve_unknown_order(symbol="BTC-USD", client_order_id=placed.client_order_id)
    params = dict(httpx.QueryParams(seen[-1].url.query.decode()))
    assert params["orderId"] == "987654" and "origClientOrderId" not in params



async def test_a_resubmitted_intent_does_not_send_a_second_order() -> None:
    """The failure mode that turns one signal into two positions.

    ``client_order_id`` is deterministic in the signal's content, so a redelivered event or
    a retried call is recognised as the same logical order and answered from the local
    mirror instead of hitting the venue again.
    """
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        client_order_id = dict(httpx.QueryParams(request.url.query.decode()))[
            "newClientOrderId"
        ]
        return httpx.Response(
            200, json={**FILLED_RESPONSE, "clientOrderId": client_order_id}
        )

    adapter = provider(handler)
    first = await adapter.submit_order(intent())
    second = await adapter.submit_order(intent())

    assert len(sent) == 1
    assert second.order_id == first.order_id
    assert first.state is OrderState.FILLED


async def test_the_client_order_id_is_sent_to_the_venue_so_it_can_reject_duplicates() -> None:
    """Local dedup only survives a process that stays up. The venue-side id is what makes
    a retry safe across a restart."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.url.query.decode())))
        return httpx.Response(
            200, json={**FILLED_RESPONSE, "clientOrderId": captured["newClientOrderId"]}
        )

    adapter = provider(handler)
    order = await adapter.submit_order(intent())

    assert captured["newClientOrderId"] == order.client_order_id
    assert captured["newClientOrderId"] == intent().client_order_id  # deterministic


# --------------------------------------------------------------------------- unknown state


async def test_a_timeout_reports_an_unknown_order_state_and_does_not_retry() -> None:
    """The single most valuable refusal in the adapter.

    A timeout means the venue may or may not have the order. Retrying is how a network
    hiccup becomes two positions; assuming it failed is how a real position goes untracked.
    The only correct move is to say the state is unknown and reconcile.
    """
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    adapter = provider(handler)
    with pytest.raises(ReconciliationError, match="UNKNOWN"):
        await adapter.submit_order(intent())

    assert attempts == 1, "a retry after a timeout is exactly the duplicate-order bug"


async def test_an_unrecognised_order_status_raises_instead_of_being_guessed() -> None:
    """Defaulting an unknown status to ACKNOWLEDGED would mean the system believes an
    order is live when the venue may have killed it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={**FILLED_RESPONSE, "status": "SOMETHING_NEW", "clientOrderId": "x"}
        )

    adapter = provider(handler)
    with pytest.raises(ExecutionError, match="does not recognise"):
        await adapter.submit_order(intent())


async def test_a_transport_error_is_distinguished_from_a_venue_rejection() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(ProviderUnavailableError):
        await provider(refuse).submit_order(intent())

    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -2010, "msg": "insufficient balance"})

    with pytest.raises(OrderRejectedError, match="insufficient balance"):
        await provider(reject).submit_order(intent())


async def test_rate_limiting_is_reported_as_back_off_not_as_a_rejection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": -1003, "msg": "too many requests"})

    with pytest.raises(ProviderUnavailableError, match="rate limited"):
        await provider(handler).submit_order(intent())


async def test_a_refused_key_points_at_the_key_rather_than_at_the_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": -2015, "msg": "invalid api key"})

    with pytest.raises(LiveActivationError, match="API key was refused"):
        await provider(handler).submit_order(intent())


# --------------------------------------------------------------------------- no withdrawals


def test_the_adapter_has_no_method_that_moves_funds() -> None:
    """Not "does not call the endpoint" — there is no method to call.

    ``tests/unit/test_scope_boundary.py`` checks the same property by inspecting every
    source file for endpoint strings; this checks the public surface.
    """
    surface = [name for name in dir(BinanceExecutionProvider) if not name.startswith("_")]
    forbidden = ("withdraw", "transfer", "send", "payout", "redeem", "convert")

    for name in surface:
        assert not any(word in name.lower() for word in forbidden), (
            f"BinanceExecutionProvider exposes {name!r}, which sounds like it moves funds"
        )


def test_a_key_that_can_withdraw_is_refused_before_anything_else_happens() -> None:
    report = check_permissions(
        {"enableReading": True, "enableSpotAndMarginTrading": True, "enableWithdrawals": True}
    )
    assert not report.acceptable
    assert "FORBIDDEN" in report.explain()


def test_futures_and_margin_permissions_are_refused_too() -> None:
    """This system models spot positions only. Its sizing assumes no leverage and no
    liquidation, and a key with futures permission is one bug away from both."""
    report = check_permissions(
        {"enableReading": True, "enableSpotAndMarginTrading": True, "enableFutures": True}
    )
    assert not report.acceptable


def test_an_unverified_permission_set_is_treated_as_unacceptable() -> None:
    """Not having asked the venue is not the same as having asked and been told yes."""
    report = check_permissions(
        {"enableReading": True, "enableSpotAndMarginTrading": True},
        verified_at_source=False,
    )
    assert not report.acceptable
    assert "have not been read from the venue" in report.explain()


def test_a_correctly_scoped_key_is_accepted_and_ip_restriction_is_advised() -> None:
    report = check_permissions(
        {"enableReading": True, "enableSpotAndMarginTrading": True, "ipRestrict": False}
    )
    assert report.acceptable
    assert "not IP-restricted" in report.explain()


def test_string_booleans_from_the_venue_are_read_correctly() -> None:
    """``"false"`` is not falsy in Python, and a permission checker that got this wrong
    would approve a withdrawal-enabled key."""
    report = check_permissions(
        {
            "enableReading": "true",
            "enableSpotAndMarginTrading": "true",
            "enableWithdrawals": "true",
        }
    )
    assert not report.acceptable


# --------------------------------------------------------------------------- the secret


def test_the_secret_does_not_appear_in_any_representation() -> None:
    creds = credentials()

    assert SECRET not in repr(creds)
    assert SECRET not in str(creds)
    assert SECRET not in f"{creds}"
    assert SECRET not in repr(creds._secret)
    assert SECRET not in f"{creds._secret}"
    assert creds.key_fingerprint.startswith("key:")
    assert SECRET not in creds.key_fingerprint


def test_a_signed_request_can_be_logged_without_leaking_key_or_signature() -> None:
    signed = signer().sign({"symbol": "BTCUSDT", "side": "BUY"})
    redacted = signed.redacted()

    assert "signature=" not in redacted["query"]
    assert "symbol=BTCUSDT" in redacted["query"]
    assert redacted["headers"]["X-MBX-APIKEY"] == "***redacted***"


def test_the_signature_covers_the_exact_string_that_is_sent() -> None:
    """A signature computed over a differently-ordered rendering of the same parameters
    fails with an opaque venue error that sends people looking in the wrong place."""
    import hashlib
    import hmac

    signed = signer().sign({"symbol": "BTCUSDT", "quantity": "0.01"})
    canonical, _, signature = signed.query_string.rpartition("&signature=")
    expected = hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()

    assert signature == expected


def test_websocket_api_parameters_are_signed_over_the_alphabetically_sorted_payload() -> None:
    """The venue's WebSocket API rule: every parameter but ``signature``, sorted by name,
    joined as name=value with ``&``; the key travels as the ``apiKey`` parameter."""
    import hashlib
    import hmac

    params = signer().sign_ws_params({"symbol": "BTCUSDT"})
    assert set(params) == {"apiKey", "recvWindow", "symbol", "timestamp", "signature"}
    assert params["apiKey"] == "pub-key-abc" and params["timestamp"] == int(START.timestamp() * 1000)
    canonical = f"apiKey=pub-key-abc&recvWindow={params['recvWindow']}&symbol=BTCUSDT&timestamp={params['timestamp']}"
    assert params["signature"] == hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert SECRET not in repr(params)


def test_signing_is_deterministic_under_a_frozen_clock() -> None:
    """Which is what lets the validation script compare against a known vector."""
    assert signer().sign({"a": 1}).query_string == signer().sign({"a": 1}).query_string


def test_a_timestamp_and_a_bounded_recv_window_are_always_included() -> None:
    params = dict(httpx.QueryParams(signer().sign({"symbol": "BTCUSDT"}).query_string))

    assert params["timestamp"] == str(int(START.timestamp() * 1000))
    assert 0 < int(params["recvWindow"]) <= MAX_RECV_WINDOW_MS


def test_the_receive_window_cannot_be_widened_without_limit() -> None:
    """Widening it to tolerate a broken clock trades a correct rejection for an unbounded
    replay window."""
    with pytest.raises(ValueError, match="recv_window_ms"):
        BinanceSigner(credentials(), FrozenClock(START), recv_window_ms=MAX_RECV_WINDOW_MS + 1)


def test_credentials_refuse_to_be_built_from_blanks() -> None:
    with pytest.raises(ValueError, match="API key and a secret"):
        BinanceCredentials.from_values(api_key="", secret=SECRET)
    with pytest.raises(ValueError, match="API key and a secret"):
        BinanceCredentials.from_values(api_key="k", secret="   ")  # noqa: S106 - blank on purpose


def test_empty_environment_values_count_as_no_credentials() -> None:
    """A compose ``${VAR:-}`` with nothing behind it hands the process two empty strings.
    That is the absence of a credential — reported with the variable names the
    configuration actually reads — not a malformed one."""
    from pydantic import SecretStr

    from tia.core.config import LiveConfig
    from tia.data.providers.binance_signing import signer_from_live_config

    live = LiveConfig(binance_api_key=SecretStr(""), binance_api_secret=SecretStr(" "))
    assert live.has_credentials is False
    with pytest.raises(ValueError, match="TIA_LIVE__BINANCE_API_KEY"):
        signer_from_live_config(live, FrozenClock(START))

    present = LiveConfig(binance_api_key=SecretStr("k"), binance_api_secret=SecretStr(SECRET))
    assert present.has_credentials is True


# --------------------------------------------------------------------------- formatting


async def test_small_quantities_are_not_sent_in_scientific_notation() -> None:
    """``1e-05`` in a quantity field is rejected by the venue, and the rejection does not
    say why."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.url.query.decode())))
        return httpx.Response(
            200,
            json={
                **FILLED_RESPONSE,
                "clientOrderId": captured["newClientOrderId"],
                "origQty": "0.00001",
                "executedQty": "0.00001",
            },
        )

    await provider(handler).submit_order(intent(quantity=0.00001))
    assert captured["quantity"] == "0.00001"
    assert "e-" not in captured["quantity"]


def test_symbol_translation_round_trips() -> None:
    assert BinanceExecutionProvider.to_venue_symbol("BTC-USD") == "BTCUSDT"
    assert BinanceExecutionProvider.from_venue_symbol("BTCUSDT") == "BTC-USD"


# --------------------------------------------------------------------------- account


async def test_the_balance_is_read_from_the_venue_and_never_computed_locally() -> None:
    """A locally-computed balance that has drifted is indistinguishable from a correct one
    until it sizes a position."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "balances": [
                    {"asset": "USDT", "free": "412.50", "locked": "0.00"},
                    {"asset": "BTC", "free": "0.0100", "locked": "0.0050"},
                ]
            },
        )

    adapter = provider(handler)
    assert await adapter.get_balance() == pytest.approx(412.50)

    positions = await adapter.get_positions()
    assert set(positions) == {"BTC-USD"}
    assert positions["BTC-USD"].quantity == pytest.approx(0.015)


async def test_pnl_is_not_asked_of_a_venue_that_does_not_compute_it() -> None:
    """Binance reports balances, not attributed P&L. Returning zeros here rather than a
    plausible-looking number keeps the attribution in the one place that does it properly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balances": []})

    assert await provider(handler).get_pnl() == {"realized": 0.0, "unrealized": 0.0}


# --------------------------------------------------------------------------- post-only


def limit_maker_intent(*, price: float = 49_900.0, quantity: float = 0.01) -> OrderIntent:
    return OrderIntent(
        intent_id="int-lm",
        client_order_id="tiamm-test-000001",
        signal_id="mm-1",
        risk_decision_id="auth-1",
        symbol="BTC-USD",
        side=Side.BUY,
        order_type=OrderType.LIMIT_MAKER,
        quantity=quantity,
        limit_price=price,
        created_at=START,
    )


async def test_a_post_only_order_is_sent_as_limit_maker_with_a_price_and_no_time_in_force() -> None:
    """The market maker's only order type. REQUIRES VALIDATION on the venue: the
    documented contract is type=LIMIT_MAKER, quantity, price, and no timeInForce."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(httpx.QueryParams(request.url.query.decode())))
        return httpx.Response(
            200,
            json={
                **FILLED_RESPONSE,
                "status": "NEW",
                "executedQty": "0",
                "cummulativeQuoteQty": "0",
                "price": "49900.00000000",
                "fills": [],
                "clientOrderId": captured["newClientOrderId"],
            },
        )

    adapter = provider(handler)
    order = await adapter.submit_order(limit_maker_intent())

    assert captured["type"] == "LIMIT_MAKER"
    assert captured["price"] == "49900"
    assert "timeInForce" not in captured
    assert captured["newClientOrderId"] == "tiamm-test-000001"
    assert order.state is OrderState.ACKNOWLEDGED and order.order_type is OrderType.LIMIT_MAKER


async def test_a_post_only_order_that_would_take_is_rejected_and_never_retried_as_anything_else() -> None:
    """The venue's refusal (-2010) is the point of the order type. The adapter reports it
    as a rejection with the code; it does not resend as LIMIT, MARKET or anything."""
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(dict(httpx.QueryParams(request.url.query.decode()))["type"])
        return httpx.Response(
            400, json={"code": -2010, "msg": "Order would immediately match and take."}
        )

    adapter = provider(handler)
    with pytest.raises(OrderRejectedError, match="immediately match") as excinfo:
        await adapter.submit_order(limit_maker_intent())
    assert excinfo.value.context.get("code") == -2010
    assert attempts == ["LIMIT_MAKER"]


async def test_trades_can_be_read_for_a_symbol_before_any_order_was_placed_and_carry_the_fee_asset() -> None:
    """A reconciliation at start needs the account's trades for the symbol it is about to
    quote, before the mirror holds a single order; and a fee charged in BNB is not a
    quote-currency amount, so the asset travels with the fill."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(httpx.QueryParams(request.url.query.decode()))
        seen.append(params["symbol"])
        return httpx.Response(
            200,
            json=[
                {
                    "id": 501, "orderId": 987654, "price": "50000.00", "qty": "0.01",
                    "commission": "0.00001", "commissionAsset": "BNB", "time": int(START.timestamp() * 1000),
                    "isBuyer": True, "isMaker": True,
                }
            ],
        )

    adapter = provider(handler)
    assert await adapter.get_trades(limit=10) == []  # nothing in the mirror: nothing to ask for
    fills = await adapter.get_trades(limit=10, symbol="BTC-USD")
    assert seen == ["BTCUSDT"]
    assert fills[0].fill_id == "501" and fills[0].liquidity == "maker" and fills[0].fee_asset == "BNB"
