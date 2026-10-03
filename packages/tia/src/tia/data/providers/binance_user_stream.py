"""Binance's account stream (the "user data stream"): execution reports and balances.

A signed subscription on the venue's **WebSocket API**. One socket is opened to the API
endpoint, one ``userDataStream.subscribe.signature`` request is sent (any API key type; no
session logon), and from the venue's ``status: 200`` answer onwards every event of the key's
account arrives on that same connection, wrapped as ``{"subscriptionId": n, "event": {...}}``:
one ``executionReport`` per order event (acknowledged, traded, cancelled, expired, rejected)
and an ``outboundAccountPosition`` after every balance change.

The listen-key stream this module first spoke (``POST /api/v3/userDataStream`` and a keyed
``wss://.../ws/<listenKey>`` socket) was deprecated by the venue on 2025-04-07 and retired on
2026-02-20; the endpoint now answers HTTP 410. There is no keepalive any more: the
subscription lives exactly as long as the connection, which the venue closes at the 24-hour
mark and on ``serverShutdown``. Both are reconnects here, and a reconnect is reported as a
drop first — the consumer stops trusting the stream until a reconciliation says what the
account really holds.

This module parses the frames into the venue-neutral :class:`~tia.domain.orders.ExecutionReport`
and :class:`~tia.domain.portfolio.AccountBalance` and hands them to callbacks. It knows
nothing about orders, ledgers or quoting: the market maker consumes the reports behind its
own execution contract and never imports this module. The signature comes from the signing
module through the subscription source; this file never sees the secret.

Integration status: **REQUIRES VALIDATION.** Field names follow the venue's documentation
(``web-socket-api.md``, ``user-data-stream.md``, 2026-09); the request shape, the wrapped
event shape and the parser are proven against documented frames, the subscription against
the venue only by ``scripts/validate_mm_testnet.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from tia.core.logging import get_logger
from tia.data.providers.binance_live import USER_STREAM_SUBSCRIBE_METHOD, venue_status_to_state
from tia.domain.enums import Side
from tia.domain.orders import ExecutionReport
from tia.domain.portfolio import AccountBalance

_log = get_logger("execution.binance_user_stream")

DEFAULT_USER_STREAM_URL = "wss://ws-api.binance.com:443/ws-api/v3"
TESTNET_USER_STREAM_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"
#: How long the venue gets to answer the subscription request before the attempt is a failure.
SUBSCRIBE_TIMEOUT_S = 10.0
BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)

#: Events that end the subscription or announce the connection's end. Each one is a drop:
#: the loop reconnects and re-subscribes, and the consumer is told in between.
_ENDING_EVENTS = {
    "eventStreamTerminated": "subscription terminated by the venue",
    "serverShutdown": "venue announced a server shutdown",
}

#: The venue's execution types to ours. ``TRADE_PREVENTION`` is the venue expiring an order
#: under self-trade prevention: for us it expired.
_EXECUTION_TYPES = {
    "NEW": "new",
    "TRADE": "trade",
    "CANCELED": "canceled",
    "REJECTED": "rejected",
    "EXPIRED": "expired",
    "REPLACED": "replaced",
    "TRADE_PREVENTION": "expired",
}


class Socket(Protocol):
    """What the stream needs from a connection: text frames out, frames in."""

    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


Connector = Callable[[str], AbstractAsyncContextManager[Socket]]
ReportSink = Callable[[ExecutionReport, int], None]
BalanceSink = Callable[[list[AccountBalance], int], None]
StatusSink = Callable[[bool, str, int], None]


def _default_connector(url: str) -> AbstractAsyncContextManager[Socket]:
    import websockets

    # The venue pings every 20 s and drops a connection that owes a pong for a minute; the
    # library answers pings itself. ``ping_interval`` adds our own liveness check on top.
    return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20)


class SubscriptionSource(Protocol):
    """Whoever can sign the subscription: the live adapter, over the signing module."""

    def user_stream_subscribe_params(self) -> dict[str, Any]: ...


class UnknownReportStatusError(ValueError):
    """The venue sent an order status this build does not know. Not guessed."""


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_execution_report(data: dict[str, Any]) -> ExecutionReport:
    """``executionReport`` to :class:`ExecutionReport`. Raises on a status this adapter does
    not know, because an unknown status is an order whose true state is unknown."""
    raw_status = str(data.get("X", "")).upper()
    status = venue_status_to_state(raw_status)
    if status is None:
        raise UnknownReportStatusError(f"execution report carries an unknown order status {raw_status!r}")
    execution_type = _EXECUTION_TYPES.get(str(data.get("x", "")).upper(), "other")
    trade_id_raw = data.get("t")
    trade_id = str(trade_id_raw) if trade_id_raw is not None and int(_f(trade_id_raw, -1)) >= 0 else None
    is_maker = data.get("m")
    return ExecutionReport(
        event_time_ms=int(_f(data.get("E"))),
        transaction_time_ms=int(_f(data.get("T"), _f(data.get("E")))),
        symbol=str(data.get("s", "")),
        client_order_id=str(data.get("c", "") or ""),
        orig_client_order_id=str(data.get("C", "") or "") if execution_type == "canceled" or data.get("C") else "",
        venue_order_id=str(data.get("i", "") or ""),
        side=Side(str(data.get("S", "BUY")).lower()),
        status=status,
        execution_type=execution_type,
        order_quantity=_f(data.get("q")),
        cumulative_quantity=_f(data.get("z")),
        last_quantity=_f(data.get("l")),
        last_price=_f(data.get("L")),
        cumulative_quote_quantity=_f(data.get("Z")),
        trade_id=trade_id if execution_type == "trade" else None,
        is_maker=bool(is_maker) if execution_type == "trade" and isinstance(is_maker, bool) else None,
        commission=_f(data.get("n")),
        commission_asset=str(data.get("N") or ""),
        reject_reason=str(data.get("r", "") or "") if str(data.get("r", "NONE")).upper() != "NONE" else "",
        raw_status=raw_status,
    )


def parse_account_position(data: dict[str, Any]) -> list[AccountBalance]:
    """``outboundAccountPosition`` to the balances it carries (only the assets that changed)."""
    out: list[AccountBalance] = []
    for row in data.get("B", []) or []:
        asset = str(row.get("a", "")).upper()
        if asset:
            out.append(AccountBalance(asset=asset, free=max(0.0, _f(row.get("f"))), locked=max(0.0, _f(row.get("l")))))
    return out


class BinanceUserDataStream:
    """Owns the socket and the subscription; delivers parsed events to the callbacks.

    ``on_report(report, received_at_ms)`` for each execution report, ``on_balances``
    for each balance update, ``on_status(connected, reason, at_ms)`` on every transition.
    ``connected`` means *subscribed*: the socket alone, before the venue's acknowledgement,
    delivers nothing and is not reported as up. Callbacks are synchronous and are called on
    this task; they must not block.
    """

    def __init__(
        self,
        source: SubscriptionSource,
        *,
        now_ms: Callable[[], int],
        on_report: ReportSink,
        on_balances: BalanceSink | None = None,
        on_status: StatusSink | None = None,
        base_url: str = DEFAULT_USER_STREAM_URL,
        connector: Connector | None = None,
        subscribe_timeout_s: float = SUBSCRIBE_TIMEOUT_S,
    ) -> None:
        self._source = source
        self._now_ms = now_ms
        self._on_report = on_report
        self._on_balances = on_balances
        self._on_status = on_status
        self._base_url = base_url.rstrip("/")
        self._connector = connector or _default_connector
        self._subscribe_timeout_s = subscribe_timeout_s
        self._task: asyncio.Task[Any] | None = None
        self._ending: str = ""
        self.subscription_id: int | None = None
        self.connected = False
        self.connections = 0
        self.disconnects = 0
        self.connect_failures = 0
        self.reconnects = 0
        self.messages = 0
        self.reports = 0
        self.balance_updates = 0
        self.other_events = 0
        self.responses = 0
        self.parse_errors = 0
        self.last_error = ""
        self._connected_at_ms: int | None = None
        self._last_message_ms: int | None = None

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.is_running:
            return
        self._task = asyncio.get_running_loop().create_task(self._run(), name="binance-user-stream")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._mark_down("closed")
        self.subscription_id = None

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                async with self._connector(self._base_url) as socket:
                    self.subscription_id = await self._subscribe(socket)
                    self.connected = True
                    self.connections += 1
                    self._connected_at_ms = self._now_ms()
                    self.last_error = ""
                    self._ending = ""
                    attempt = 0
                    self._status(True, "connected")
                    _log.info("binance_user_stream_subscribed", subscription_id=self.subscription_id)
                    while True:
                        self.on_message(await socket.recv())
                        if self._ending:
                            raise ConnectionError(self._ending)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                was_up = self.connected
                self.last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
                self._mark_down(self.last_error)
                self.subscription_id = None
                self.reconnects += 1
                delay = BACKOFF[min(attempt, len(BACKOFF) - 1)]
                attempt += 1
                if was_up:
                    self.disconnects += 1
                    _log.warning("binance_user_stream_dropped", error=self.last_error, retry_in=delay)
                else:
                    self.connect_failures += 1
                    _log.warning("binance_user_stream_connect_failed", error=self.last_error, retry_in=delay)
                await asyncio.sleep(delay)

    async def _subscribe(self, socket: Socket) -> int:
        """Send the signed subscription and wait for the venue's answer to *this* request.

        Anything else that arrives meanwhile is handled as a message. A refusal carries the
        venue's status and error code (``-1022`` bad signature, ``-2015`` key/IP/permission,
        ``-1021`` timestamp) and nothing from the request: the parameters hold the key.
        """
        request_id = str(uuid.uuid4())
        params = self._source.user_stream_subscribe_params()
        await socket.send(json.dumps({"id": request_id, "method": USER_STREAM_SUBSCRIBE_METHOD, "params": params}))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._subscribe_timeout_s
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"no answer to the subscription request within {self._subscribe_timeout_s:g} s")
            raw = await asyncio.wait_for(socket.recv(), remaining)
            frame = self._decode(raw)
            if isinstance(frame, dict) and frame.get("id") == request_id:
                self.responses += 1
                status = frame.get("status")
                if status == 200:
                    result = frame.get("result") or {}
                    return int(result.get("subscriptionId", 0)) if isinstance(result, dict) else 0
                error = frame.get("error") or {}
                code = error.get("code") if isinstance(error, dict) else None
                message = str(error.get("msg", ""))[:160] if isinstance(error, dict) else ""
                raise ConnectionError(f"subscription refused: status {status} code {code} {message}".rstrip())
            self.on_message(raw)
            if self._ending:
                raise ConnectionError(self._ending)

    def _mark_down(self, reason: str) -> None:
        was_up = self.connected
        self.connected = False
        self._connected_at_ms = None
        if was_up:
            self._status(False, reason)

    def _status(self, connected: bool, reason: str) -> None:
        if self._on_status is not None:
            with contextlib.suppress(Exception):
                self._on_status(connected, reason, self._now_ms())

    # ------------------------------------------------------------------ messages

    @staticmethod
    def _decode(raw: str | bytes) -> Any:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def on_message(self, raw: str | bytes) -> None:
        received_at_ms = self._now_ms()
        self.messages += 1
        self._last_message_ms = received_at_ms
        frame = self._decode(raw)
        if not isinstance(frame, dict):
            self.parse_errors += 1
            return
        if "event" in frame:
            # The WebSocket API's shape: {"subscriptionId": n, "event": {...}}.
            data = frame["event"]
        elif "id" in frame and "status" in frame:
            # An answer to a request nobody is waiting for; counted, never interpreted.
            self.responses += 1
            return
        else:
            data = frame.get("data", frame)
        if not isinstance(data, dict):
            self.parse_errors += 1
            return
        kind = str(data.get("e", ""))
        if kind in _ENDING_EVENTS:
            self.other_events += 1
            self._ending = _ENDING_EVENTS[kind]
            _log.warning("binance_user_stream_ending", venue_event=kind)
            return
        try:
            if kind == "executionReport":
                self.reports += 1
                self._on_report(parse_execution_report(data), received_at_ms)
            elif kind == "outboundAccountPosition":
                self.balance_updates += 1
                if self._on_balances is not None:
                    self._on_balances(parse_account_position(data), received_at_ms)
            else:
                self.other_events += 1
        except UnknownReportStatusError as exc:
            # An order whose status we cannot read is an order whose state is unknown. The
            # consumer learns it through the status callback and reconciles.
            self.parse_errors += 1
            _log.error("binance_user_stream_unknown_status", error=str(exc))
            self._status(self.connected, f"unparseable report: {exc}")
        except Exception as exc:  # a consumer fault must not kill the socket
            self.parse_errors += 1
            _log.error("binance_user_stream_consumer_failed", error=f"{type(exc).__name__}: {str(exc)[:160]}")

    # ------------------------------------------------------------------ reading

    def as_dict(self) -> dict[str, Any]:
        now = self._now_ms()
        return {
            "connected": self.connected,
            "running": self.is_running,
            "subscription_id": self.subscription_id,
            "connections": self.connections,
            "disconnects": self.disconnects,
            "connect_failures": self.connect_failures,
            "reconnects": self.reconnects,
            "uptime_s": round((now - self._connected_at_ms) / 1000.0, 1) if self._connected_at_ms is not None else 0.0,
            "messages": self.messages,
            "reports": self.reports,
            "balance_updates": self.balance_updates,
            "other_events": self.other_events,
            "responses": self.responses,
            "parse_errors": self.parse_errors,
            "last_message_age_s": round((now - self._last_message_ms) / 1000.0, 1) if self._last_message_ms is not None else None,
            "last_error": self.last_error,
        }


__all__ = [
    "BACKOFF",
    "DEFAULT_USER_STREAM_URL",
    "SUBSCRIBE_TIMEOUT_S",
    "TESTNET_USER_STREAM_URL",
    "BinanceUserDataStream",
    "Socket",
    "SubscriptionSource",
    "UnknownReportStatusError",
    "parse_account_position",
    "parse_execution_report",
]
