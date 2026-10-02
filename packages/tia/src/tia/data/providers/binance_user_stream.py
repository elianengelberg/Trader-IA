"""Binance's account stream (the "user data stream"): execution reports and balances.

A keyed WebSocket, opened with a listen key the REST adapter creates with the API key alone
and keeps alive every thirty minutes (the venue drops it after sixty). It delivers, for the
key's account only, one ``executionReport`` per order event (acknowledged, traded, cancelled,
expired, rejected) and an ``outboundAccountPosition`` after every balance change.

This module parses those frames into the venue-neutral :class:`~tia.domain.orders.ExecutionReport`
and :class:`~tia.domain.portfolio.AccountBalance` and hands them to callbacks. It knows
nothing about orders, ledgers or quoting: the market maker consumes the reports behind its
own execution contract and never imports this module.

Integration status: **REQUIRES VALIDATION.** Field names follow the venue's documentation;
no frame has been received from a Binance host in this build environment. What is proven
here is the parser against documented shapes and the reconnect discipline: a dropped socket
is reported as such, never papered over, and the consumer is told so it can stop trusting
the stream until a reconciliation says what the account really holds.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from tia.core.logging import get_logger
from tia.data.providers.binance_live import venue_status_to_state
from tia.domain.enums import Side
from tia.domain.orders import ExecutionReport
from tia.domain.portfolio import AccountBalance

_log = get_logger("execution.binance_user_stream")

DEFAULT_USER_STREAM_URL = "wss://stream.binance.com:9443/ws"
TESTNET_USER_STREAM_URL = "wss://testnet.binance.vision/ws"
#: The venue expires a listen key after sixty minutes without a keepalive.
LISTEN_KEY_KEEPALIVE_S = 1_800.0
BACKOFF = (1.0, 2.0, 4.0, 8.0, 15.0, 30.0)

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

Connector = Callable[[str], AbstractAsyncContextManager[AsyncIterator[str | bytes]]]
ReportSink = Callable[[ExecutionReport, int], None]
BalanceSink = Callable[[list[AccountBalance], int], None]
StatusSink = Callable[[bool, str, int], None]


def _default_connector(url: str) -> AbstractAsyncContextManager[AsyncIterator[str | bytes]]:
    import websockets

    return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20)


class ListenKeySource(Protocol):
    async def create_listen_key(self) -> str: ...

    async def keepalive_listen_key(self, listen_key: str) -> None: ...

    async def close_listen_key(self, listen_key: str) -> None: ...


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
    """Owns the socket and the listen key; delivers parsed events to the callbacks.

    ``on_report(report, received_at_ms)`` for each execution report, ``on_balances``
    for each balance update, ``on_status(connected, reason, at_ms)`` on every transition.
    Callbacks are synchronous and are called on this task; they must not block.
    """

    def __init__(
        self,
        keys: ListenKeySource,
        *,
        now_ms: Callable[[], int],
        on_report: ReportSink,
        on_balances: BalanceSink | None = None,
        on_status: StatusSink | None = None,
        base_url: str = DEFAULT_USER_STREAM_URL,
        connector: Connector | None = None,
        keepalive_s: float = LISTEN_KEY_KEEPALIVE_S,
    ) -> None:
        self._keys = keys
        self._now_ms = now_ms
        self._on_report = on_report
        self._on_balances = on_balances
        self._on_status = on_status
        self._base_url = base_url.rstrip("/")
        self._connector = connector or _default_connector
        self._keepalive_s = keepalive_s
        self._task: asyncio.Task[Any] | None = None
        self._listen_key: str | None = None
        self.connected = False
        self.connections = 0
        self.disconnects = 0
        self.connect_failures = 0
        self.reconnects = 0
        self.messages = 0
        self.reports = 0
        self.balance_updates = 0
        self.other_events = 0
        self.parse_errors = 0
        self.keepalives = 0
        self.keepalive_failures = 0
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
        if self._listen_key is not None:
            with contextlib.suppress(Exception):
                await self._keys.close_listen_key(self._listen_key)
            self._listen_key = None

    async def _run(self) -> None:
        attempt = 0
        while True:
            keepalive: asyncio.Task[Any] | None = None
            try:
                self._listen_key = await self._keys.create_listen_key()
                async with self._connector(f"{self._base_url}/{self._listen_key}") as socket:
                    self.connected = True
                    self.connections += 1
                    self._connected_at_ms = self._now_ms()
                    self.last_error = ""
                    attempt = 0
                    keepalive = asyncio.get_running_loop().create_task(self._keepalive_loop(self._listen_key), name="binance-user-stream-keepalive")
                    self._status(True, "connected")
                    _log.info("binance_user_stream_connected")
                    async for raw in socket:
                        self.on_message(raw)
                    raise ConnectionError("account stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                was_up = self.connected
                self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                self._mark_down(self.last_error)
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
            finally:
                if keepalive is not None:
                    keepalive.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await keepalive

    async def _keepalive_loop(self, listen_key: str) -> None:
        while True:
            await asyncio.sleep(self._keepalive_s)
            try:
                await self._keys.keepalive_listen_key(listen_key)
                self.keepalives += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.keepalive_failures += 1
                _log.warning("binance_user_stream_keepalive_failed", error=str(exc)[:160])

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

    def on_message(self, raw: str | bytes) -> None:
        received_at_ms = self._now_ms()
        self.messages += 1
        self._last_message_ms = received_at_ms
        try:
            frame = json.loads(raw)
        except (TypeError, ValueError):
            self.parse_errors += 1
            return
        data = frame.get("data", frame) if isinstance(frame, dict) else None
        if not isinstance(data, dict):
            self.parse_errors += 1
            return
        kind = str(data.get("e", ""))
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
            "connections": self.connections,
            "disconnects": self.disconnects,
            "connect_failures": self.connect_failures,
            "reconnects": self.reconnects,
            "uptime_s": round((now - self._connected_at_ms) / 1000.0, 1) if self._connected_at_ms is not None else 0.0,
            "messages": self.messages,
            "reports": self.reports,
            "balance_updates": self.balance_updates,
            "other_events": self.other_events,
            "parse_errors": self.parse_errors,
            "keepalives": self.keepalives,
            "keepalive_failures": self.keepalive_failures,
            "last_message_age_s": round((now - self._last_message_ms) / 1000.0, 1) if self._last_message_ms is not None else None,
            "last_error": self.last_error,
            "note": "REQUIRES VALIDATION: frame shapes follow the documentation; none has been received from the venue in this build",
        }


__all__ = [
    "BACKOFF",
    "DEFAULT_USER_STREAM_URL",
    "LISTEN_KEY_KEEPALIVE_S",
    "TESTNET_USER_STREAM_URL",
    "BinanceUserDataStream",
    "ListenKeySource",
    "UnknownReportStatusError",
    "parse_account_position",
    "parse_execution_report",
]
