"""The Binance account stream: parsing the documented frames, the listen-key discipline
and the reconnect behaviour, against a scripted socket and a scripted key source.

REQUIRES VALIDATION on the venue: the frame shapes below are the documentation's. What is
proven here is ours: a known status maps, an unknown one is refused rather than guessed,
a dropped socket is reported as a drop, and the listen key is created with the key alone.
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


class ScriptedSocket:
    def __init__(self) -> None:
        self.queues: list[asyncio.Queue[str | None]] = []
        self.urls: list[str] = []

    def connector(self):  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def connect(url: str):  # type: ignore[no-untyped-def]
            self.urls.append(url)
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            self.queues.append(queue)

            async def frames():  # type: ignore[no-untyped-def]
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    yield item

            yield frames()

        return connect

    async def send(self, frame: dict[str, Any] | str) -> None:
        await self.queues[-1].put(frame if isinstance(frame, str) else json.dumps(frame))
        await asyncio.sleep(0.01)

    async def drop(self) -> None:
        await self.queues[-1].put(None)
        await asyncio.sleep(0.03)


class ScriptedKeys:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.kept_alive: list[str] = []
        self.closed: list[str] = []
        self.fail_create = False

    async def create_listen_key(self) -> str:
        if self.fail_create:
            raise ConnectionError("no key for you")
        key = f"key-{len(self.created) + 1}"
        self.created.append(key)
        return key

    async def keepalive_listen_key(self, listen_key: str) -> None:
        self.kept_alive.append(listen_key)

    async def close_listen_key(self, listen_key: str) -> None:
        self.closed.append(listen_key)


async def _stream(*, keepalive_s: float = 3600.0):  # type: ignore[no-untyped-def]
    import tia.data.providers.binance_user_stream as module

    module.BACKOFF = (0.01,)
    socket, keys = ScriptedSocket(), ScriptedKeys()
    clock = {"ms": T_MS}
    reports: list[tuple[Any, int]] = []
    balances: list[tuple[list[Any], int]] = []
    statuses: list[tuple[bool, str, int]] = []
    stream = BinanceUserDataStream(
        keys, now_ms=lambda: clock["ms"], on_report=lambda r, t: reports.append((r, t)), on_balances=lambda b, t: balances.append((b, t)),
        on_status=lambda c, reason, t: statuses.append((c, reason, t)), base_url="wss://testnet.binance.vision/ws", connector=socket.connector(), keepalive_s=keepalive_s,
    )
    stream.start()
    await asyncio.sleep(0.03)
    return stream, socket, keys, clock, reports, balances, statuses


async def test_the_stream_opens_with_a_listen_key_delivers_reports_and_balances_and_reports_its_status() -> None:
    stream, socket, keys, clock, reports, balances, statuses = await _stream()
    assert keys.created == ["key-1"] and socket.urls == ["wss://testnet.binance.vision/ws/key-1"]
    assert stream.connected and statuses == [(True, "connected", T_MS)]
    clock["ms"] += 7
    await socket.send(_report(x="TRADE", X="FILLED", l="0.00100000", z="0.00100000", L="99990.0", t=42, m=True))
    await socket.send({"e": "outboundAccountPosition", "E": T_MS, "u": T_MS, "B": [{"a": "USDT", "f": "10", "l": "0"}]})
    await socket.send({"e": "balanceUpdate", "a": "USDT", "d": "1"})  # another event kind: counted, not delivered
    await socket.send("not json")
    assert len(reports) == 1 and reports[0][0].trade_id == "42" and reports[0][1] == T_MS + 7
    assert len(balances) == 1 and balances[0][0][0].asset == "USDT"
    snap = stream.as_dict()
    assert snap["reports"] == 1 and snap["balance_updates"] == 1 and snap["other_events"] == 1 and snap["parse_errors"] == 1 and snap["connected"]
    await stream.close()
    assert not stream.connected and keys.closed == ["key-1"] and statuses[-1][0] is False and statuses[-1][1] == "closed"


async def test_a_dropped_socket_is_reported_as_a_drop_and_a_new_key_is_minted_on_reconnect() -> None:
    stream, socket, keys, _clock, _reports, _balances, statuses = await _stream()
    await socket.drop()
    await asyncio.sleep(0.05)
    assert any(s[0] is False and "account stream ended" in s[1] for s in statuses)
    assert stream.disconnects == 1 and stream.reconnects >= 1 and keys.created == ["key-1", "key-2"]
    assert stream.connected and statuses[-1][0] is True
    await stream.close()


async def test_a_key_that_cannot_be_created_keeps_retrying_without_pretending_to_be_connected() -> None:
    import tia.data.providers.binance_user_stream as module

    module.BACKOFF = (0.01,)
    keys = ScriptedKeys()
    keys.fail_create = True
    statuses: list[tuple[bool, str, int]] = []
    stream = BinanceUserDataStream(keys, now_ms=lambda: T_MS, on_report=lambda r, t: None, on_status=lambda c, reason, t: statuses.append((c, reason, t)), connector=ScriptedSocket().connector())
    stream.start()
    await asyncio.sleep(0.06)
    assert not stream.connected and stream.connect_failures >= 2 and statuses == [] and "no key for you" in stream.last_error
    await stream.close()


async def test_the_listen_key_is_kept_alive_and_an_unreadable_report_is_reported_not_guessed() -> None:
    stream, socket, keys, _clock, reports, _balances, statuses = await _stream(keepalive_s=0.02)
    await asyncio.sleep(0.07)
    assert keys.kept_alive and set(keys.kept_alive) == {"key-1"} and stream.keepalives >= 1
    await socket.send(_report(X="SOMETHING_NEW"))
    assert reports == [] and stream.parse_errors == 1
    assert statuses[-1][0] is True and statuses[-1][1].startswith("unparseable report")
    await stream.close()


# ------------------------------------------------------------------ the adapter's side of it


async def test_the_adapter_creates_keeps_alive_and_closes_a_listen_key_with_the_key_header_alone() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"listenKey": "pqia91ma19a5s61cv6a81va65sdf19v8a65a1a5s61cv6a81va65sdf19v8a65a1"})
        return httpx.Response(200, json={})

    adapter = provider(handler, simulated=True, clock=SimulatedClock(START))
    key = await adapter.create_listen_key()
    await adapter.keepalive_listen_key(key)
    await adapter.close_listen_key(key)
    assert [r.method for r in seen] == ["POST", "PUT", "DELETE"]
    for request in seen:
        assert request.url.path == "/api/v3/userDataStream"
        assert request.headers.get("X-MBX-APIKEY") == "pub-key-abc"
        assert "signature" not in request.url.query.decode() and "timestamp" not in request.url.query.decode()
    assert seen[1].url.params["listenKey"] == key and seen[2].url.params["listenKey"] == key


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
