"""Integration tests never open a real venue socket (Phase 1.5, extended in Phase 1.6).

Three modules dial a venue when nothing scripted is handed to them: the market stream
(``BinanceStreamProvider``, kline and bookTicker), the user data stream
(``BinanceUserDataStream``, execution reports and balances) and the market-making stream
(``MarketDataStream``, depth and trades). Each takes an injectable ``connector`` and
falls back to a module-level ``_default_connector`` that imports ``websockets`` and dials
``wss://``. The test settings turn the streams off, but a setting is a convention; this
guard is the contract. A test that reaches any default connector fails here, loudly,
instead of reaching the network — on a machine where the network is open as much as on
one where it is blocked. Scripted connectors, fake clients and ``httpx.MockTransport``
are untouched: the guard replaces the dialler, not the seam tests inject through.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

#: ``(module path, attribute)`` of every default websocket dialler in the package.
REAL_SOCKET_DIALLERS: tuple[tuple[str, str], ...] = (
    ("tia.data.providers.binance_stream", "_default_connector"),
    ("tia.data.providers.binance_user_stream", "_default_connector"),
    ("tia.mm.streams", "_default_connector"),
)


def refuse_real_socket(module: str):  # type: ignore[no-untyped-def]
    def refuse(url: str):  # type: ignore[no-untyped-def]
        raise AssertionError(
            f"an integration test tried to open a real websocket to {url} through "
            f"{module}; give the stream a scripted connector or leave the stream off"
        )

    return refuse


@pytest.fixture(autouse=True)
def _no_real_websockets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    import importlib

    for module_name, attribute in REAL_SOCKET_DIALLERS:
        module = importlib.import_module(module_name)
        assert hasattr(module, attribute), f"{module_name} no longer has {attribute}; move the guard"
        monkeypatch.setattr(module, attribute, refuse_real_socket(module_name))
    yield
