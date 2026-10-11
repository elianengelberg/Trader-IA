"""The integration guard itself (Phase 1.6): every default websocket dialler is refused,
scripted connectors and mock transports are not.

``tests/integration/conftest.py`` replaces the module-level ``_default_connector`` of the
market stream, the user data stream and the market-making stream. Each stream falls back
to that attribute when built without a ``connector``; this file proves the fallback now
raises instead of dialling, that an injected connector is left alone, and that an HTTP
client over ``httpx.MockTransport`` still answers — the guard is about sockets, not seams.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import httpx
import pytest

from tests.integration.conftest import REAL_SOCKET_DIALLERS
from tia.data.providers.binance_stream import BinanceStreamProvider
from tia.data.providers.binance_user_stream import BinanceUserDataStream
from tia.mm.streams import MarketDataStream


@pytest.mark.parametrize(("module_name", "attribute"), REAL_SOCKET_DIALLERS)
def test_every_default_dialler_is_replaced_by_a_refusal(module_name: str, attribute: str) -> None:
    import importlib

    dialler = getattr(importlib.import_module(module_name), attribute)
    with pytest.raises(AssertionError, match="real websocket") as refused:
        dialler("wss://stream.binance.com:9443/ws/btcusdt@bookTicker")
    assert module_name in str(refused.value)


class _Source:
    def user_stream_subscribe_params(self) -> dict[str, object]:
        return {"apiKey": "not-a-key"}


def test_streams_built_without_a_connector_cannot_dial_the_venue() -> None:
    market = BinanceStreamProvider(object(), symbol="BTC-USD")
    user = BinanceUserDataStream(_Source(), now_ms=lambda: 0, on_report=lambda report, at: None)
    maker = MarketDataStream("BTC-USD")
    for stream, url in (
        (market, "wss://stream.binance.com:9443/stream"),
        (user, "wss://ws-api.binance.com:443/ws-api/v3"),
        (maker, "wss://stream.binance.com:9443/stream"),
    ):
        with pytest.raises(AssertionError, match="real websocket"):
            stream._connector(url)


async def test_a_scripted_connector_is_not_touched_by_the_guard() -> None:
    opened: list[str] = []

    @contextlib.asynccontextmanager
    async def scripted(url: str) -> AsyncIterator[AsyncIterator[str]]:
        opened.append(url)

        async def lines() -> AsyncIterator[str]:
            yield '{"stream": "btcusdt@bookTicker", "data": {}}'

        yield lines()

    provider = BinanceStreamProvider(object(), symbol="BTC-USD", connector=scripted)
    assert provider._connector is scripted
    async with provider._connector("wss://scripted") as socket:
        assert [line async for line in socket] == ['{"stream": "btcusdt@bookTicker", "data": {}}']
    assert opened == ["wss://scripted"]


async def test_an_http_client_over_a_mock_transport_still_answers() -> None:
    def venue(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path})

    async with httpx.AsyncClient(transport=httpx.MockTransport(venue), base_url="https://fapi.binance.com") as client:
        response = await client.get("/fapi/v1/premiumIndex", params={"symbol": "BTCUSDT"})
    assert response.status_code == 200 and response.json() == {"path": "/fapi/v1/premiumIndex"}
