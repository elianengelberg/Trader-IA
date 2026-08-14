"""Binance spot execution — the adapter that can spend real money.

Integration status: **REQUIRES VALIDATION.** Not one request in this file has ever been
sent. This build environment blocks every Binance host — ``api.binance.com``,
``api1.binance.com``, ``data-api.binance.vision``, ``testnet.binance.vision``,
``developers.binance.com`` — so the endpoint paths, parameter names and response fields
below were written from documentation and confirmed against nothing.

That is stated first because it is the most important thing about this module. Run
``scripts/validate_binance.py`` from a machine with egress, against the **testnet** first,
before this adapter is allowed anywhere near an account with money in it. The activation
gate independently refuses to arm while fees are unverified, so the two failures cannot
combine into a live session on guessed field names.

**What this module deliberately cannot do.**

It has no withdrawal surface and no transfer surface. Not "does not call those endpoints"
— there is no method, no code path, and no string in this file that names one, which
``tests/unit/test_scope_boundary.py`` verifies by inspection of the source. The API key is
independently required to lack the permission (:mod:`tia.live.permissions`). Two barriers,
neither relying on the other.

**Idempotency.** Every order carries ``newClientOrderId`` derived from the intent's
``client_order_id``, which is itself deterministic in the signal's content. A retry after a
timeout re-sends the same id; the venue rejects the duplicate rather than opening a second
position. This is the single most valuable property in the file: a network timeout on order
submission is common, and the naive retry is how one signal becomes two positions.

**The unknown-state rule.** When a submission fails in a way that leaves the order's fate
genuinely unknown — a timeout, a connection reset after the request was written — this
adapter does **not** retry and does **not** assume the order was lost. It raises, the
runtime halts new orders, and reconciliation resolves what actually happened by querying
the venue. Guessing here is what produces the duplicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from tia.core.clock import Clock, utc_from_millis
from tia.core.errors import (
    ExecutionError,
    LiveActivationError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.core.logging import get_logger
from tia.data.providers.binance_signing import BinanceSigner
from tia.domain.enums import OrderState, OrderType, Side, TimeInForce
from tia.domain.orders import Fill, Order, OrderIntent
from tia.domain.portfolio import PortfolioState, Position
from tia.execution.provider import ExecutionCapabilities, ExecutionProvider

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tia.live.gate import LiveActivationToken

_log = get_logger("execution.binance")

#: Documented Binance spot endpoints this adapter uses. Every one is read-or-trade; the
#: list is exhaustive and there is nothing here that moves funds off the exchange.
_ORDER_PATH = "/api/v3/order"
_OPEN_ORDERS_PATH = "/api/v3/openOrders"
_ACCOUNT_PATH = "/api/v3/account"
_MY_TRADES_PATH = "/api/v3/myTrades"
_EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"

#: Our order-type vocabulary to the venue's. REQUIRES VALIDATION.
_ORDER_TYPE_MAP = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP_LIMIT: "STOP_LOSS_LIMIT",
    OrderType.TAKE_PROFIT: "TAKE_PROFIT_LIMIT",
}

_TIF_MAP = {
    TimeInForce.GTC: "GTC",
    TimeInForce.IOC: "IOC",
    TimeInForce.FOK: "FOK",
}

#: Venue order status to ours. An unmapped status is an error, never a default: a status
#: this adapter does not recognise means it does not know what happened to the order.
_STATUS_MAP = {
    "NEW": OrderState.ACKNOWLEDGED,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELLED,
    "PENDING_CANCEL": OrderState.CANCEL_REQUESTED,
    "REJECTED": OrderState.REJECTED,
    "EXPIRED": OrderState.EXPIRED,
    "EXPIRED_IN_MATCH": OrderState.EXPIRED,
}


class BinanceExecutionProvider(ExecutionProvider):
    """Places spot orders on Binance, under an activation token.

    ``is_simulated`` is a constructor argument rather than a hardcoded ``False`` so that
    the same adapter can be pointed at the testnet and exercised without a live token —
    and so that liveness is a decision made by the caller and the gate, never a property
    baked into the class. The boundary test enforces that it stays a parameter.
    """

    def __init__(
        self,
        *,
        signer: BinanceSigner,
        clock: Clock,
        activation: LiveActivationToken | None = None,
        base_url: str = "https://api.binance.com",
        simulated: bool = True,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        quote_asset: str = "USDT",
    ) -> None:
        super().__init__(
            ExecutionCapabilities(
                name="binance-spot" if not simulated else "binance-spot-testnet",
                is_simulated=simulated,
                supports_limit_orders=True,
                supports_stop_orders=True,
                supports_partial_fills=True,
                supports_cancellation=True,
                models_slippage=False,
                models_fees=False,
                models_latency=False,
                notes=(
                    "REQUIRES VALIDATION: endpoints and field names written from "
                    "documentation and never exercised — every Binance host was blocked in "
                    "the build environment. Run scripts/validate_binance.py first. Costs are "
                    "not modelled here because they are real: the venue charges them."
                ),
            ),
            activation=activation,
            clock=clock,
        )
        self._signer = signer
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._quote_asset = quote_asset.upper()
        #: client_order_id -> our Order. The local mirror of venue state; reconciliation
        #: compares it against the venue and the venue wins every disagreement.
        self._orders: dict[str, Order] = {}
        self._by_venue_id: dict[str, str] = {}

    # ------------------------------------------------------------------ transport

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={"User-Agent": "trader-ia/0.2"},
            )
        return self._client

    async def _signed_get(self, path: str, params: dict[str, Any]) -> Any:
        return await self._request("GET", path, params)

    async def _request(self, method: str, path: str, params: dict[str, Any]) -> Any:
        """Send a signed request, mapping failures onto the distinction that matters.

        Two failure classes, treated completely differently:

        * The venue answered and said no — a rejection. The order did not happen and it is
          safe to say so.
        * The venue did not answer — a timeout or a transport error. The order's fate is
          **unknown**, and the only safe response is to say that too. This is why
          ``httpx.TimeoutException`` is not folded in with the rest.
        """
        signed = self._signer.sign(params)
        client = await self._http()
        url = f"{path}?{signed.query_string}"

        try:
            response = await client.request(method, url, headers=signed.headers)
        except httpx.TimeoutException as exc:
            raise ReconciliationError(
                f"{method} {path} timed out; the order state at the venue is UNKNOWN. "
                "Not retrying: a retry after a timeout is how one signal becomes two "
                "positions. Reconcile against the venue before submitting anything else.",
                path=path,
                key=self._signer.key_fingerprint,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"binance transport error on {method} {path}: {exc}",
                provider=self.name,
            ) from exc

        if response.status_code >= 400:
            self._raise_venue_error(response, path)

        try:
            return response.json()
        except ValueError as exc:
            raise ExecutionError(
                f"binance returned a non-JSON body on {method} {path}",
                received=response.text[:300],
            ) from exc

    def _raise_venue_error(self, response: httpx.Response, path: str) -> None:
        """Turn a venue error body into something a human can act on.

        The venue's numeric codes are stable and its messages are not, so both are carried
        through rather than summarised. REQUIRES VALIDATION: the ``{"code","msg"}`` body
        shape is documented but unconfirmed here, so a body that does not match is reported
        raw instead of being parsed into a misleading message.
        """
        try:
            body = response.json()
            code = body.get("code")
            message = body.get("msg", "")
        except ValueError:
            code, message = None, response.text[:300]

        detail = f"binance rejected {path}: HTTP {response.status_code} code={code} {message}"

        if response.status_code == 429 or response.status_code == 418:
            raise ProviderUnavailableError(
                f"{detail} — rate limited. Back off; do not retry immediately.",
                provider=self.name,
            )
        if response.status_code == 401 or response.status_code == 403:
            raise LiveActivationError(
                f"{detail} — the API key was refused. Check that it is active, that its IP "
                "restriction includes this host, and that it has spot trading permission."
            )
        raise OrderRejectedError(detail, code=code, path=path)

    # ------------------------------------------------------------------ symbols

    @staticmethod
    def to_venue_symbol(symbol: str) -> str:
        """``BTC-USD`` -> ``BTCUSDT``."""
        base, _, quote = symbol.partition("-")
        if not quote:
            return symbol.upper()
        quote = "USDT" if quote.upper() == "USD" else quote.upper()
        return f"{base.upper()}{quote}"

    @staticmethod
    def from_venue_symbol(venue_symbol: str, *, quote_asset: str = "USDT") -> str:
        upper = venue_symbol.upper()
        if upper.endswith(quote_asset):
            return f"{upper[: -len(quote_asset)]}-USD" if quote_asset == "USDT" else (
                f"{upper[: -len(quote_asset)]}-{quote_asset}"
            )
        return upper

    # ------------------------------------------------------------------ orders

    async def submit_order(self, intent: OrderIntent) -> Order:
        """Submit an intent to the venue. Idempotent on ``client_order_id``.

        The gate is checked here, immediately before the request, rather than at
        construction — an adapter built an hour ago may hold an expired activation, and the
        order about to be sent is the thing that must be authorised, not the object that
        sends it.
        """
        self.assert_may_trade()

        existing = self._orders.get(intent.client_order_id)
        if existing is not None:
            # Same logical order. Return what we already have rather than sending again.
            return existing

        venue_type = _ORDER_TYPE_MAP.get(intent.order_type)
        if venue_type is None:
            raise ExecutionError(
                f"order type {intent.order_type.value} is not supported by this adapter; "
                "it is not in the documented spot order-type set",
                order_type=intent.order_type.value,
            )

        params: dict[str, Any] = {
            "symbol": self.to_venue_symbol(intent.symbol),
            "side": intent.side.value.upper(),
            "type": venue_type,
            "quantity": _format_decimal(intent.quantity),
            "newClientOrderId": intent.client_order_id,
            "newOrderRespType": "FULL",
        }
        if intent.order_type is not OrderType.MARKET:
            params["timeInForce"] = _TIF_MAP.get(intent.time_in_force, "GTC")
        if intent.limit_price is not None:
            params["price"] = _format_decimal(intent.limit_price)
        if intent.stop_price is not None:
            params["stopPrice"] = _format_decimal(intent.stop_price)

        _log.info(
            "binance_submit",
            client_order_id=intent.client_order_id,
            symbol=intent.symbol,
            side=intent.side.value,
            quantity=intent.quantity,
            key=self._signer.key_fingerprint,
        )

        payload = await self._request("POST", _ORDER_PATH, params)
        order = self._parse_order(payload, intent=intent)
        self._orders[intent.client_order_id] = order
        self._by_venue_id[str(payload.get("orderId"))] = intent.client_order_id
        return order

    async def cancel_order(self, order_id: str) -> Order:
        self.assert_may_trade()
        order = self._orders.get(order_id) or self._orders.get(
            self._by_venue_id.get(order_id, "")
        )
        if order is None:
            raise ExecutionError(f"unknown order {order_id}", order_id=order_id)

        payload = await self._request(
            "DELETE",
            _ORDER_PATH,
            {
                "symbol": self.to_venue_symbol(order.symbol),
                "origClientOrderId": order.client_order_id,
            },
        )
        updated = self._parse_order(payload, existing=order)
        self._orders[order.client_order_id] = updated
        return updated

    async def get_order(self, order_id: str) -> Order | None:
        order = self._orders.get(order_id) or self._orders.get(
            self._by_venue_id.get(order_id, "")
        )
        if order is None:
            return None
        payload = await self._signed_get(
            _ORDER_PATH,
            {
                "symbol": self.to_venue_symbol(order.symbol),
                "origClientOrderId": order.client_order_id,
            },
        )
        refreshed = self._parse_order(payload, existing=order)
        self._orders[order.client_order_id] = refreshed
        return refreshed

    async def get_orders(self, *, open_only: bool = False) -> list[Order]:
        if not open_only:
            return list(self._orders.values())
        payload = await self._signed_get(_OPEN_ORDERS_PATH, {})
        if not isinstance(payload, list):
            raise ExecutionError("expected an array of open orders", received=str(payload)[:200])
        return [self._parse_order(row) for row in payload]

    # ------------------------------------------------------------------ account

    async def get_balance(self) -> float:
        """Free quote-asset balance at the venue.

        The venue is the source of truth. This adapter never caches a balance and never
        computes one from its own fill history: a computed balance that has drifted is
        indistinguishable from a correct one until it sizes a position.
        """
        payload = await self._signed_get(_ACCOUNT_PATH, {})
        for entry in payload.get("balances", []):
            if entry.get("asset") == self._quote_asset:
                return float(entry.get("free", 0.0))
        return 0.0

    async def get_positions(self) -> dict[str, Position]:
        """Spot holdings, expressed as positions.

        Spot has no position concept — it has balances — so a non-zero base-asset balance
        is reported as a long. There is no short: this adapter does not touch margin, and
        the risk engine's sizing assumes it cannot.
        """
        payload = await self._signed_get(_ACCOUNT_PATH, {})
        positions: dict[str, Position] = {}
        for entry in payload.get("balances", []):
            asset = entry.get("asset", "")
            if asset == self._quote_asset:
                continue
            quantity = float(entry.get("free", 0.0)) + float(entry.get("locked", 0.0))
            if quantity <= 0:
                continue
            symbol = f"{asset}-USD" if self._quote_asset == "USDT" else f"{asset}-{self._quote_asset}"
            positions[symbol] = Position(symbol=symbol, quantity=quantity, average_price=0.0)
        return positions

    async def get_trades(self, *, limit: int = 100) -> list[Fill]:
        """Executed trades, read back from the venue rather than remembered.

        REQUIRES VALIDATION: ``myTrades`` requires a symbol, so this returns trades for the
        symbols this adapter has orders for. A symbol traded by something else on the same
        account will not appear, which is stated here rather than discovered during a
        reconciliation mismatch.
        """
        symbols = {order.symbol for order in self._orders.values()}
        fills: list[Fill] = []
        for symbol in sorted(symbols):
            payload = await self._signed_get(
                _MY_TRADES_PATH,
                {"symbol": self.to_venue_symbol(symbol), "limit": min(limit, 1000)},
            )
            if not isinstance(payload, list):
                continue
            fills.extend(self._parse_trade(row, symbol) for row in payload)
        return sorted(fills, key=lambda f: f.filled_at)[:limit]

    async def get_pnl(self) -> dict[str, float]:
        """P&L is computed by the portfolio layer from fills, not asked of the venue.

        Binance reports balances, not attributed P&L, and a balance difference is not a
        return — see :mod:`tia.portfolio.capital`. Returning zeros here rather than a
        plausible-looking number is deliberate.
        """
        return {"realized": 0.0, "unrealized": 0.0}

    async def get_portfolio(self) -> PortfolioState:
        balance = await self.get_balance()
        positions = await self.get_positions()
        state = PortfolioState.initial(max(balance, 1e-9))
        state.cash = balance
        state.positions = positions
        state.updated_at = self._clock.now() if self._clock else None
        return state

    async def get_exchange_info(self, symbol: str) -> dict[str, Any]:
        """Lot size, tick size and minimum notional for a symbol.

        Unsigned and public, but it belongs here rather than in the market-data client: an
        order rounded to the wrong lot size is rejected by the venue, so this is execution's
        concern. REQUIRES VALIDATION for the filter names.
        """
        client = await self._http()
        response = await client.get(
            _EXCHANGE_INFO_PATH, params={"symbol": self.to_venue_symbol(symbol)}
        )
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------ parsing

    def _parse_order(
        self,
        payload: dict[str, Any],
        *,
        intent: OrderIntent | None = None,
        existing: Order | None = None,
    ) -> Order:
        """Build an :class:`Order` from a venue response.

        A status this adapter does not recognise raises. The tempting alternative —
        defaulting to ``ACKNOWLEDGED`` or carrying the previous state forward — would mean
        the system believes an order is live when the venue may have killed it.
        """
        status = str(payload.get("status", "")).upper()
        state = _STATUS_MAP.get(status)
        if state is None:
            raise ExecutionError(
                f"binance returned an order status this adapter does not recognise: "
                f"{status!r}. Refusing to guess what it means — the order's true state is "
                "unknown until someone maps it.",
                status=status,
                order=str(payload.get("clientOrderId")),
            )

        client_order_id = str(payload.get("clientOrderId", ""))
        base = existing or (self._orders.get(client_order_id) if client_order_id else None)
        now = self._clock.now() if self._clock else None
        transact_ms = payload.get("transactTime") or payload.get("updateTime") or payload.get("time")
        updated_at = utc_from_millis(int(transact_ms)) if transact_ms else now

        symbol = (
            intent.symbol
            if intent
            else (base.symbol if base else self.from_venue_symbol(str(payload.get("symbol", ""))))
        )
        side = (
            intent.side
            if intent
            else Side(str(payload.get("side", "BUY")).lower())
        )
        quantity = float(payload.get("origQty", intent.quantity if intent else 0.0) or 0.0)
        filled = float(payload.get("executedQty", 0.0) or 0.0)
        quote_filled = float(payload.get("cummulativeQuoteQty", 0.0) or 0.0)

        order = Order(
            order_id=str(payload.get("orderId", client_order_id)),
            client_order_id=client_order_id,
            intent_id=intent.intent_id if intent else (base.intent_id if base else ""),
            signal_id=intent.signal_id if intent else (base.signal_id if base else ""),
            symbol=symbol,
            side=side,
            order_type=intent.order_type if intent else (base.order_type if base else OrderType.MARKET),
            quantity=quantity or 1e-9,
            limit_price=float(payload["price"]) if _positive(payload.get("price")) else None,
            stop_price=float(payload["stopPrice"]) if _positive(payload.get("stopPrice")) else None,
            state=state,
            filled_quantity=filled,
            average_fill_price=(quote_filled / filled) if filled > 0 else 0.0,
            created_at=(base.created_at if base else updated_at) or updated_at,
            updated_at=updated_at,
            correlation_id=intent.correlation_id if intent else "",
        )

        for index, row in enumerate(payload.get("fills", []) or []):
            order.fills.append(self._parse_embedded_fill(row, order, index))
            order.fees_paid += float(row.get("commission", 0.0) or 0.0)
        return order

    def _parse_embedded_fill(self, row: dict[str, Any], order: Order, index: int) -> Fill:
        return Fill(
            fill_id=str(row.get("tradeId", f"{order.order_id}-{index}")),
            order_id=order.order_id,
            sequence=index,
            symbol=order.symbol,
            side=order.side,
            quantity=float(row["qty"]),
            price=float(row["price"]),
            fee=float(row.get("commission", 0.0) or 0.0),
            liquidity="taker",
            filled_at=order.updated_at,
        )

    def _parse_trade(self, row: dict[str, Any], symbol: str) -> Fill:
        return Fill(
            fill_id=str(row["id"]),
            order_id=str(row.get("orderId", "")),
            sequence=0,
            symbol=symbol,
            side=Side.BUY if row.get("isBuyer") else Side.SELL,
            quantity=float(row["qty"]),
            price=float(row["price"]),
            fee=float(row.get("commission", 0.0) or 0.0),
            liquidity="maker" if row.get("isMaker") else "taker",
            filled_at=utc_from_millis(int(row["time"])),
        )

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


def _format_decimal(value: float) -> str:
    """Render without scientific notation.

    ``1e-05`` in a quantity field is rejected by the venue, and the rejection message does
    not say why. Formatting is a correctness concern here, not a cosmetic one.
    """
    return f"{value:.8f}".rstrip("0").rstrip(".") or "0"


def _positive(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


__all__ = ["BinanceExecutionProvider"]
