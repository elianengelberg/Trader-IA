"""The suite-wide no-network guard, by behaviour (Phase 1.8).

``tests/conftest.py`` replaces every real HTTP transport and the websocket dialler for
each test, in every suite. These tests prove the seams: a real client fails loudly with
the URL it tried; the venue connectors' default diallers fail without the integration
guard; a mock transport, an ASGI transport and a scripted connector are untouched.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx
import pytest
import websockets

from tia.core.clock import SimulatedClock
from tia.data.funding import FundingMonitor
from tia.data.providers import binance_stream, binance_user_stream
from tia.mm import streams


async def test_a_real_async_http_request_is_refused_with_its_url() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(AssertionError, match=re.escape("real HTTP request to https://example.invalid/klines")):
            await client.get("https://example.invalid/klines")


def test_a_real_sync_http_request_is_refused_too() -> None:
    with httpx.Client() as client, pytest.raises(AssertionError, match=re.escape("real HTTP request")):
        client.get("https://example.invalid/time")


async def test_a_mock_transport_still_answers() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))) as client:
        assert (await client.get("https://fapi.binance.com/fapi/v1/premiumIndex")).json() == {"ok": True}


async def test_an_asgi_transport_still_answers() -> None:
    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://app") as client:
        assert (await client.get("/health")).status_code == 204


def test_the_websocket_dialler_is_refused_with_its_url() -> None:
    with pytest.raises(AssertionError, match=re.escape("real websocket to wss://stream.binance.com")):
        websockets.connect("wss://stream.binance.com:9443/ws/btcusdt@bookTicker")


@pytest.mark.parametrize("module", [binance_stream, binance_user_stream, streams])
def test_every_default_connector_is_stopped_at_the_dialler_without_the_integration_guard(module) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(AssertionError, match=re.escape("real websocket")):
        module._default_connector("wss://ws-api.binance.com:443/ws-api/v3")


async def test_a_monitor_on_a_default_client_reports_the_refusal_instead_of_reaching_the_venue() -> None:
    monitor = FundingMonitor(clock=SimulatedClock(start=datetime(2026, 10, 11, tzinfo=UTC)), client=httpx.AsyncClient())
    try:
        assert await monitor.poll() is None
        health = monitor.report()["health"]
        assert health["ok"] is False and "real HTTP request" in health["detail"]
    finally:
        await monitor.close()
