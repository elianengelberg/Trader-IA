"""The Binance account stream: parsing the documented frames, the signed subscription on the
WebSocket API and the reconnect behaviour, against a scripted socket and a scripted signer.

REQUIRES VALIDATION on the venue: the frame shapes below are the documentation's
(``web-socket-api.md``, ``user-data-stream.md``). What is proven here is ours: the request
carries the key and a signature and nothing else, ``connected`` means the venue said 200, a
known status maps, an unknown one is refused rather than guessed, a refusal or a dropped
socket is reported as what it is, and a venue-ended subscription is a reconnect.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from tests.unit.test_binance_live import START, provider
from tia.core.clock import SimulatedClock
from tia.data.providers.binance_user_stream import (
    BinanceUserDataStream,
    UnknownReportStatusError,
    parse_account_position,
    parse_execution_report,
)
from tia.domain.enums import OrderState, Side

T_MS = int(datetime(2026, 10, 2, 12, 0, tzinfo=UTC).timestamp() * 1000)


def _report(**overrides: Any) -> dict[str, Any]:
    base = {
        "e": "executionReport", "E": T_MS + 5, "s": "BTCUSDT", "c": "tiamm-abc-1-000001", "S": "BUY", "o": "LIMIT_MAKER",
        "f": "GTC", "q": "0.00100000", "p": "99990.00000000", "P": "0.00000000", "F": "0.00000000", "g": -1, "C": "",
        "x": "NEW", "X": "NEW", "r": "NONE", "i": 123456, "l": "0.00000000", "z": "0.00000000", "L": "0.00000000",
        "n": "0", "N": None, "T": T_MS, "t": -1, "I": 1, "w": True, "m": False, "M": False, "O": T_MS, "Z": "0.00000000",
        "Y": "0.00000000", "Q": "0.00000000", "W": T_MS, "V": "EXPIRE_MAKER",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ parsing


def test_a_new_report_is_an_acknowledgement_with_no_trade() -> None:
    report = parse_execution_report(_report())
    assert report.client_order_id == "tiamm-abc-1-000001" and report.order_ref == "tiamm-abc-1-000001"
    assert report.status is OrderState.ACKNOWLEDGED and report.execution_type == "new" and report.raw_status == "NEW"
    assert report.venue_order_id == "123456" and report.side is Side.BUY and report.order_quantity == 0.001
    assert report.trade_id is None and not report.is_trade and report.is_maker is None and report.reject_reason == ""
    assert report.as_dict()["status"] == "acknowledged"


def test_a_trade_report_carries_the_trade_id_the_maker_flag_the_fee_and_its_asset() -> None:
    partial = parse_execution_report(_report(x="TRADE", X="PARTIALLY_FILLED", l="0.00040000", z="0.00040000", L="99990.00000000", n="0.00399960", N="USDT", t=777, m=True))
    assert partial.is_trade and partial.trade_id == "777" and partial.is_maker is True
    assert partial.status is OrderState.PARTIALLY_FILLED and partial.last_quantity == 0.0004 and partial.last_price == 99_990.0
    assert partial.commission == pytest.approx(0.0039996) and partial.commission_asset == "USDT"
    taker = parse_execution_report(_report(x="TRADE", X="FILLED", l="0.00100000", z="0.00100000", L="99990.00000000", t=778, m=False, N="BNB", n="0.00001"))
    assert taker.is_maker is False and taker.status is OrderState.FILLED and taker.commission_asset == "BNB"
    # Two reports about different trades never share a dedupe key; the same report does.
    assert partial.dedupe_key() != taker.dedupe_key() and partial.dedupe_key() == parse_execution_report(_report(x="TRADE", X="PARTIALLY_FILLED", l="0.00040000", z="0.00040000", L="99990.00000000", n="0.00399960", N="USDT", t=777, m=True)).dedupe_key()


def test_a_cancel_report_refers_to_the_original_order_id() -> None:
    report = parse_execution_report(_report(c="web_cancel_9f3", C="tiamm-abc-1-000001", x="CANCELED", X="CANCELED"))
    assert report.client_order_id == "web_cancel_9f3" and report.orig_client_order_id == "tiamm-abc-1-000001"
    assert report.order_ref == "tiamm-abc-1-000001" and report.status is OrderState.CANCELLED and report.execution_type == "canceled"


def test_expiry_prevention_and_rejection_are_read_as_what_they_are() -> None:
    expired = parse_execution_report(_report(x="EXPIRED", X="EXPIRED"))
    assert expired.status is OrderState.EXPIRED and expired.execution_type == "expired"
    prevented = parse_execution_report(_report(x="TRADE_PREVENTION", X="EXPIRED_IN_MATCH"))
    assert prevented.status is OrderState.EXPIRED and prevented.execution_type == "expired"
    rejected = parse_execution_report(_report(x="REJECTED", X="REJECTED", r="INSUFFICIENT_BALANCE"))
    assert rejected.status is OrderState.REJECTED and rejected.execution_type == "rejected" and rejected.reject_reason == "INSUFFICIENT_BALANCE"


def test_an_unknown_status_is_refused_not_guessed() -> None:
    with pytest.raises(UnknownReportStatusError, match="SOMETHING_NEW"):
        parse_execution_report(_report(X="SOMETHING_NEW"))


def test_an_account_position_lists_the_assets_that_changed_free_and_locked() -> None:
    balances = parse_account_position({"e": "outboundAccountPosition", "E": T_MS, "u": T_MS, "B": [{"a": "USDT", "f": "4899.90000000", "l": "100.00000000"}, {"a": "BTC", "f": "0.04000000", "l": "0.01000000"}]})
    assert [(b.asset, b.free, b.locked, b.total) for b in balances] == [("USDT", 4_899.9, 100.0, 4_999.9), ("BTC", 0.04, 0.01, pytest.approx(0.05))]


# ------------------------------------------------------------------ the socket and the key


SUBSCRIBE_METHOD = "userDataStream.subscribe.signature"


class _Conn:
    """One scripted connection: frames in through a queue, frames out recorded. The
    subscription request is answered the way the venue documents it, unless told to refuse."""

    def __init__(self, owner: ScriptedSocket) -> None:
        self.owner = owner
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []

    async def send(self, message: str) -> None:
        frame = json.loads(message)
        self.sent.append(frame)
        self.owner.sent.append(frame)
        if frame.get("method") == SUBSCRIBE_METHOD and self.owner.answer_subscriptions:
            if self.owner.refuse is not None:
                status, code, msg = self.owner.refuse
                await self.queue.put(json.dumps({"id": frame["id"], "status": status, "error": {"code": code, "msg": msg}}))
            else:
                self.owner.subscriptions += 1
                await self.queue.put(json.dumps({"id": frame["id"], "status": 200, "result": {"subscriptionId": self.owner.subscriptions - 1}}))

    async def recv(self) -> str:
        item = await self.queue.get()
        if item is None:
            raise ConnectionError("scripted drop")
        return item


class ScriptedSocket:
    def __init__(self) -> None:
        self.conns: list[_Conn] = []
        self.urls: list[str] = []
        self.sent: list[dict[str, Any]] = []
        self.subscriptions = 0
        self.refuse: tuple[int, int, str] | None = None
        self.answer_subscriptions = True

    def connector(self):  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def connect(url: str):  # type: ignore[no-untyped-def]
            self.urls.append(url)
            conn = _Conn(self)
            self.conns.append(conn)
            yield conn

        return connect

    async def send(self, frame: dict[str, Any] | str) -> None:
        await self.conns[-1].queue.put(frame if isinstance(frame, str) else json.dumps(frame))
        await asyncio.sleep(0.01)

    async def event(self, data: dict[str, Any], subscription_id: int = 0) -> None:
        """A venue event, in the WebSocket API's wrapped shape."""
        await self.send({"subscriptionId": subscription_id, "event": data})

    async def drop(self) -> None:
        await self.conns[-1].queue.put(None)
        await asyncio.sleep(0.03)


class ScriptedSigner:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def user_stream_subscribe_params(self) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("no signer for you")
        self.calls += 1
        return {"apiKey": "pub-key-abc", "timestamp": T_MS + self.calls, "recvWindow": 5000, "signature": f"sig-{self.calls}"}


WS_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"


async def _stream(*, socket: ScriptedSocket | None = None, signer: ScriptedSigner | None = None):  # type: ignore[no-untyped-def]
    import tia.data.providers.binance_user_stream as module

    module.BACKOFF = (0.01,)
    socket, signer = socket or ScriptedSocket(), signer or ScriptedSigner()
    clock = {"ms": T_MS}
    reports: list[tuple[Any, int]] = []
    balances: list[tuple[list[Any], int]] = []
    statuses: list[tuple[bool, str, int]] = []
    stream = BinanceUserDataStream(
        signer, now_ms=lambda: clock["ms"], on_report=lambda r, t: reports.append((r, t)), on_balances=lambda b, t: balances.append((b, t)),
        on_status=lambda c, reason, t: statuses.append((c, reason, t)), base_url=WS_URL, connector=socket.connector(), subscribe_timeout_s=0.5,
    )
    stream.start()
    await asyncio.sleep(0.05)
    return stream, socket, signer, clock, reports, balances, statuses


async def test_the_stream_subscribes_with_a_signed_request_delivers_reports_and_balances_and_reports_its_status() -> None:
    stream, socket, signer, clock, reports, balances, statuses = await _stream()
    assert socket.urls == [WS_URL] and signer.calls == 1
    request = socket.sent[0]
    assert request["method"] == SUBSCRIBE_METHOD and request["id"]
    assert set(request["params"]) == {"apiKey", "timestamp", "recvWindow", "signature"}
    assert "secret" not in json.dumps(request).lower()
    assert stream.connected and stream.subscription_id == 0 and statuses == [(True, "connected", T_MS)]
    clock["ms"] += 7
    await socket.event(_report(x="TRADE", X="FILLED", l="0.00100000", z="0.00100000", L="99990.0", t=42, m=True))
    await socket.event({"e": "outboundAccountPosition", "E": T_MS, "u": T_MS, "B": [{"a": "USDT", "f": "10", "l": "0"}]})
    await socket.event({"e": "balanceUpdate", "a": "USDT", "d": "1"})  # another event kind: counted, not delivered
    await socket.send({"id": "stray", "status": 200, "result": {}})  # an answer nobody waits for: counted, not interpreted
    await socket.send("not json")
    assert len(reports) == 1 and reports[0][0].trade_id == "42" and reports[0][1] == T_MS + 7
    assert len(balances) == 1 and balances[0][0][0].asset == "USDT"
    snap = stream.as_dict()
    assert snap["reports"] == 1 and snap["balance_updates"] == 1 and snap["other_events"] == 1 and snap["parse_errors"] == 1 and snap["connected"]
    assert snap["responses"] == 2 and snap["subscription_id"] == 0
    await stream.close()
    assert not stream.connected and stream.subscription_id is None and statuses[-1][0] is False and statuses[-1][1] == "closed"


async def test_a_dropped_socket_is_reported_as_a_drop_and_a_fresh_signature_is_sent_on_reconnect() -> None:
    stream, socket, signer, _clock, _reports, _balances, statuses = await _stream()
    await socket.drop()
    await asyncio.sleep(0.08)
    assert any(s[0] is False and "scripted drop" in s[1] for s in statuses)
    assert stream.disconnects == 1 and stream.reconnects >= 1 and signer.calls == 2 and len(socket.urls) == 2
    assert [f["params"]["signature"] for f in socket.sent] == ["sig-1", "sig-2"]
    assert stream.connected and statuses[-1][0] is True
    await stream.close()


async def test_a_refused_subscription_is_never_reported_as_connected_and_names_the_venue_code_only() -> None:
    socket = ScriptedSocket()
    socket.refuse = (401, -2015, "Invalid API-key, IP, or permissions for action.")
    stream, socket, _signer, _clock, _reports, _balances, statuses = await _stream(socket=socket)
    await asyncio.sleep(0.06)
    assert not stream.connected and stream.subscription_id is None and stream.connect_failures >= 2 and statuses == []
    assert "status 401" in stream.last_error and "-2015" in stream.last_error
    assert "pub-key-abc" not in stream.last_error and "sig-" not in stream.last_error
    await stream.close()


async def test_a_venue_that_does_not_answer_the_subscription_is_a_failed_attempt_not_a_connection() -> None:
    socket = ScriptedSocket()
    socket.answer_subscriptions = False
    stream, socket, _signer, _clock, _reports, _balances, statuses = await _stream(socket=socket)
    await asyncio.sleep(0.7)
    assert not stream.connected and stream.connect_failures >= 1 and statuses == [] and "TimeoutError" in stream.last_error
    await stream.close()


async def test_a_signer_that_cannot_sign_keeps_retrying_without_pretending_to_be_connected() -> None:
    signer = ScriptedSigner()
    signer.fail = True
    stream, socket, _signer, _clock, _reports, _balances, statuses = await _stream(signer=signer)
    await asyncio.sleep(0.06)
    assert not stream.connected and stream.connect_failures >= 2 and statuses == [] and "no signer for you" in stream.last_error
    assert socket.sent == []  # nothing left the process without a signature
    await stream.close()


async def test_a_subscription_the_venue_terminates_is_a_drop_followed_by_a_new_subscription() -> None:
    stream, socket, signer, _clock, _reports, _balances, statuses = await _stream()
    await socket.event({"e": "eventStreamTerminated", "E": T_MS})
    await asyncio.sleep(0.08)
    assert any(s[0] is False and "terminated" in s[1] for s in statuses)
    assert stream.disconnects == 1 and signer.calls == 2 and stream.connected and stream.subscription_id == 1
    await stream.close()


async def test_an_unreadable_report_is_reported_not_guessed() -> None:
    stream, socket, _signer, _clock, reports, _balances, statuses = await _stream()
    await socket.event(_report(X="SOMETHING_NEW"))
    assert reports == [] and stream.parse_errors == 1
    assert statuses[-1][0] is True and statuses[-1][1].startswith("unparseable report")
    await stream.close()


# ------------------------------------------------------------------ the adapter's side of it


async def test_the_adapter_signs_the_subscription_locally_with_the_key_as_a_parameter_and_no_request() -> None:
    """The WebSocket API's rule: the key is the ``apiKey`` parameter, the signature covers
    every parameter sorted by name. No REST request is made to obtain it."""
    import hashlib
    import hmac

    from tests.unit.test_binance_live import SECRET

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500, json={})

    adapter = provider(handler, simulated=True, clock=SimulatedClock(START))
    params = adapter.user_stream_subscribe_params()
    assert seen == []
    assert params["apiKey"] == "pub-key-abc" and params["timestamp"] == int(START.timestamp() * 1000) and 0 < params["recvWindow"] <= 60_000
    canonical = "&".join(f"{k}={params[k]}" for k in sorted(k for k in params if k != "signature"))
    assert canonical.startswith("apiKey=pub-key-abc&recvWindow=")
    assert params["signature"] == hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert SECRET not in json.dumps(params)
    assert not hasattr(adapter, "create_listen_key")


async def test_balances_are_read_per_asset_free_and_locked_from_the_venue() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/account"
        return httpx.Response(200, json={"balances": [
            {"asset": "USDT", "free": "4899.90000000", "locked": "100.00000000"},
            {"asset": "BTC", "free": "0.04000000", "locked": "0.01000000"},
            {"asset": "ETH", "free": "0.00000000", "locked": "0.00000000"},
        ]})

    adapter = provider(handler, simulated=True, clock=SimulatedClock(START))
    balances = await adapter.get_balances()
    assert set(balances) == {"USDT", "BTC"} and adapter.quote_asset == "USDT"
    assert balances["USDT"].free == 4_899.9 and balances["USDT"].locked == 100.0 and balances["BTC"].total == pytest.approx(0.05)
