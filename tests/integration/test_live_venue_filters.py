"""D21 (mission v3): a live session trades on the venue's grid, read before it starts.

Before: ``AppState`` built the live runtime without ``symbol_filters``, so a live session sized,
priced and protected with the instrument universe's values (BTC-USD: lot 1e-6, tick 0.01) and
a limit price was not put on any tick grid at all (``_limit_price_for`` returns the raw price
when no venue tick is loaded). An order off the venue's grid is refused by its PRICE_FILTER or
LOT_SIZE (developers.binance.com, Spot API "Filters", read 2026-10-26).

Now the venue's ``exchangeInfo`` is read when the live session is built, and a session that
cannot read or understand it is not started. The payloads here follow the documented shape;
REQUIRES VALIDATION against the venue (Testnet, not run here).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from tia.core.errors import LiveActivationError
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.filters import filters_for, venue_filters_from_exchange_info


def exchange_info(**row_overrides: Any) -> dict[str, Any]:
    row = {
        "symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
        "orderTypes": ["LIMIT", "LIMIT_MAKER", "MARKET", "STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"],
        "filters": [
            {"filterType": "PRICE_FILTER", "minPrice": "0.01000000", "maxPrice": "1000000.00000000", "tickSize": "0.01000000"},
            {"filterType": "LOT_SIZE", "minQty": "0.00001000", "maxQty": "9000.00000000", "stepSize": "0.00001000"},
            {"filterType": "NOTIONAL", "minNotional": "5.00000000", "applyMinToMarket": True,
             "maxNotional": "9000000.00000000", "applyMaxToMarket": False, "avgPriceMins": 5},
            {"filterType": "MAX_NUM_ALGO_ORDERS", "maxNumAlgoOrders": 5},
        ],
    }
    row.update(row_overrides)
    return {"timezone": "UTC", "symbols": [row]}


def test_the_venue_grid_is_read_as_the_venue_states_it() -> None:
    out = venue_filters_from_exchange_info(exchange_info(), venue_symbol="BTCUSDT")
    assert out["source"] == "exchange_info"
    filters = filters_for("BTC-USD", DEFAULT_UNIVERSE, out)
    assert filters.step_size == Decimal("0.00001") and filters.tick_size == Decimal("0.01")
    assert filters.min_quantity == Decimal("0.00001") and filters.min_notional == Decimal("5")
    assert "venue filters" in filters.source
    # The universe's own lot (1e-6) is finer than this venue's: a size quantized to it is refused.
    assert filters.quantize(0.0123456) == pytest.approx(0.01234)


@pytest.mark.parametrize("payload,match", [
    ({"symbols": []}, "no symbols"),
    (exchange_info(symbol="ETHUSDT"), "does not describe BTCUSDT"),
    (exchange_info(status="BREAK"), "not trading"),
    (exchange_info(orderTypes=["LIMIT", "MARKET"]), "STOP_LOSS"),
    (exchange_info(filters=[{"filterType": "PRICE_FILTER", "tickSize": "0.01"}]), "LOT_SIZE"),
    (exchange_info(filters=[{"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "LOT_SIZE", "minQty": "0.00001", "stepSize": "0.00001"}]), "notional"),
    (exchange_info(filters=[{"filterType": "PRICE_FILTER", "tickSize": "0"},
                            {"filterType": "LOT_SIZE", "minQty": "0.00001", "stepSize": "0.00001"},
                            {"filterType": "NOTIONAL", "minNotional": "5"}]), "tick_size"),
], ids=["empty", "other_symbol", "halted", "no_stop_loss", "no_lot_size", "no_notional", "zero_tick"])
def test_an_incomplete_description_is_refused(payload: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        venue_filters_from_exchange_info(payload, venue_symbol="BTCUSDT")


class _Execution:
    def __init__(self, answer: Any) -> None:
        self.answer = answer

    @staticmethod
    def to_venue_symbol(symbol: str) -> str:
        return "BTCUSDT"

    async def get_exchange_info(self, symbol: str) -> Any:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.mark.parametrize("answer", [httpx.ConnectError("blocked"), {"symbols": []}, exchange_info(status="HALT")],
                         ids=["unreachable", "empty", "halted"])
async def test_a_live_session_that_cannot_read_the_grid_is_not_started(tmp_path: Path, answer: Any) -> None:
    from tests.integration.test_run_lifecycle import _state

    state = await _state(tmp_path)
    try:
        with pytest.raises(LiveActivationError, match="not started"):
            await state._venue_symbol_filters(_Execution(answer), "BTC-USD")
    finally:
        await state.shutdown()


async def test_the_live_session_is_built_with_the_venue_grid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wiring: ``_build_live_runtime`` hands the venue's filters to the runtime."""
    import tia.data.providers.binance_signing as signing
    import tia.runtime.live as live_module
    from tests.integration.test_run_lifecycle import _state
    from tests.unit.test_binance_live import signer
    from tia.data.providers.binance_live import BinanceExecutionProvider

    state = await _state(tmp_path)
    built: dict[str, Any] = {}

    class _Captured:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            built.update(kwargs)

    async def fake_info(self: Any, symbol: str) -> dict[str, Any]:
        return exchange_info()

    monkeypatch.setattr(signing, "signer_from_live_config", lambda live, clock: signer(clock))
    monkeypatch.setattr(BinanceExecutionProvider, "get_exchange_info", fake_info)
    monkeypatch.setattr(live_module, "LiveRuntime", _Captured)
    state.settings = state.settings.model_copy(update={"live": state.settings.live.model_copy(update={"use_testnet": True})})
    try:
        await state._build_live_runtime(token=None)
        assert built["symbol_filters"]["step_size"] == "0.00001000"
        assert built["symbol_filters"]["tick_size"] == "0.01000000"
    finally:
        await state.shutdown()
