"""Live paper mode: the engine on the market-data feed, persisted and pushed,
resumable — and still without any road to an execution provider."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from tia.mm.costs import MarketMakerCostConfig
from tia.mm.engine import MarketMakerConfig
from tia.mm.latency import LatencyStats
from tia.mm.latency_model import build_latency_profile
from tia.mm.market_data import MarketDataService
from tia.mm.order_book import snapshot_from_levels
from tia.mm.service import MarketMakerService
from tia.mm.spread import SpreadConfig
from tia.mm.streams import MarketDataStream
from tia.risk.engine import RiskState

T0 = 1_789_754_400_000


def _stats(values: list[float]) -> dict:  # type: ignore[type-arg]
    stats = LatencyStats()
    for v in values:
        stats.add(v)
    return stats.as_dict()


PROFILE = build_latency_profile(
    stream={"latency_depth_ms": _stats([40, 50, 60]), "latency_trade_ms": _stats([40, 50, 60])},
    processing_us=_stats([20, 30]),
    measured_at_utc="2026-09-18T00:00:00Z",
    commit="synthetic",
    duration_s=60,
    symbol="BTC-USD",
)


def _depth(U: int, u: int, t: int, bids=(), asks=()) -> str:  # type: ignore[no-untyped-def]
    return json.dumps({"stream": "s@depth@100ms", "data": {"e": "depthUpdate", "E": t - 30, "s": "BTCUSDT", "U": U, "u": u, "b": [[f"{p:.2f}", f"{q:.5f}"] for p, q in bids], "a": [[f"{p:.2f}", f"{q:.5f}"] for p, q in asks]}})


def _trade(tid: int, t: int, price: float, qty: float, *, seller: bool) -> str:
    return json.dumps({"stream": "s@trade", "data": {"e": "trade", "E": t - 2, "s": "BTCUSDT", "t": tid, "p": f"{price:.2f}", "q": f"{qty:.5f}", "T": t - 5, "m": seller, "M": True}})


class Scripted:
    def __init__(self) -> None:
        self.queues: list[asyncio.Queue[str | None]] = []

    def connector(self):  # type: ignore[no-untyped-def]
        @asynccontextmanager
        async def connect(url: str):  # type: ignore[no-untyped-def]
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

    async def send(self, frame: str) -> None:
        await self.queues[-1].put(frame)
        await asyncio.sleep(0.01)


async def _market(clock: dict[str, int]) -> tuple[MarketDataService, Scripted]:
    import tia.mm.streams as module

    module.BACKOFF = (0.01,)
    scripted = Scripted()
    bids = [(round(100_000.0 - i * 0.1, 1), 1.0) for i in range(80)]
    asks = [(round(100_000.2 + i * 0.1, 1), 1.0) for i in range(80)]

    async def fetch_snapshot():  # type: ignore[no-untyped-def]
        return snapshot_from_levels(100, bids, asks)

    stream = MarketDataStream("BTC-USD", connector=scripted.connector(), now_ms=lambda: clock["ms"])
    market = MarketDataService("BTC-USD", stream=stream, fetch_snapshot=fetch_snapshot, resync_cooldown_s=0.01, now_ms=lambda: clock["ms"])
    market.start()
    await asyncio.sleep(0.05)
    return market, scripted


def _config() -> MarketMakerConfig:
    return MarketMakerConfig(costs=MarketMakerCostConfig(maker_fee_bps=0.5), spread=SpreadConfig(min_half_spread_bps=0.5, cost_buffer_bps=0.0, vol_multiplier=0.0), requote_interval_ms=200)


async def test_the_service_quotes_on_the_feed_persists_pushes_and_resumes(tmp_path: Path) -> None:
    clock = {"ms": T0}
    market, scripted = await _market(clock)
    persisted: list[tuple[str, dict]] = []  # type: ignore[type-arg]
    pushed: list[dict] = []  # type: ignore[type-arg]

    async def persist(kind: str, payload: dict) -> None:  # type: ignore[type-arg]
        persisted.append((kind, payload))

    state = RiskState()
    service = MarketMakerService(
        market=market, config=_config(), profile=PROFILE, scenario="optimistic", run_id="run-test",
        risk_state=lambda: state, persist=persist, broadcast=pushed.append, now_ms=lambda: clock["ms"],
        state_push_interval_ms=500, ledger_save_interval_ms=1_000,
    )
    service.start()
    assert service.is_running and market.usable
    uid = 101
    for i in range(30):
        clock["ms"] += 100
        await scripted.send(_depth(uid, uid, clock["ms"], bids=[(99_993.0, 1.0 + (i % 3))]))
        uid += 1
        if i % 2:
            clock["ms"] += 10
            await scripted.send(_trade(500 + i, clock["ms"], 99_995.0, 0.002, seller=True))
    await asyncio.sleep(0.05)
    snap = service.snapshot()
    assert snap["events"] > 0 and snap["quotes"] >= 1 and snap["gate"]["state"] == "safe"
    assert snap["execution_stats"]["fills"] >= 1 and snap["ledger"]["fills"] >= 1
    assert snap["data_quality"]["usable"] is True and snap["profile"]["id"] == PROFILE.profile_id
    assert "real_money" not in snap  # the service adds no such key: nothing in tia/mm reads the flag
    kinds = {k for k, _ in persisted}
    assert {"mm_journal", "mm_fill", "mm_ledger"} <= kinds
    assert any(p["type"] == "mm.state" for p in pushed) and any(p["type"] == "mm.journal" and p["data"]["kind"] == "decision" for p in pushed)
    assert service.journal(limit=5, kind="fill")[-1]["kind"] == "fill"
    metrics = service.metrics()
    assert metrics["edge"]["verdict"] == "NO EDGE DETECTED" and metrics["scenario"]["latency"] == "optimistic"
    # The session's risk engine halting is seen by the gate, read-only.
    from tia.domain.enums import SystemMode

    state.mode = SystemMode.HALTED
    for _ in range(4):
        clock["ms"] += 300
        await scripted.send(_depth(uid, uid, clock["ms"]))
        uid += 1
    assert service.engine.gate_blocks >= 1 and service.snapshot()["gate"]["state"] == "halted"
    assert state.mode is SystemMode.HALTED  # untouched
    inventory_before = service.engine.ledger.state.inventory_btc
    await service.close()
    assert not service.is_running and persisted[-1][0] == "mm_ledger"
    # A new service resumes the ledger from the saved state.
    resumed = MarketMakerService(market=market, config=_config(), profile=PROFILE, scenario="optimistic", run_id="run-test", risk_state=lambda: state, now_ms=lambda: clock["ms"])
    resumed.restore(persisted[-1][1]["state"])
    assert resumed.engine.ledger.state.inventory_btc == inventory_before and resumed.restored_from == "database"
    await market.close()


async def test_an_engine_fault_never_breaks_the_feed(tmp_path: Path) -> None:
    clock = {"ms": T0}
    market, scripted = await _market(clock)
    service = MarketMakerService(market=market, config=_config(), profile=PROFILE, scenario="baseline", run_id="r", risk_state=lambda: None, now_ms=lambda: clock["ms"])
    service.start()

    def boom(kind, event, t):  # type: ignore[no-untyped-def]
        raise RuntimeError("engine bug")

    service.engine.on_event = boom  # type: ignore[method-assign]
    clock["ms"] += 100
    await scripted.send(_depth(101, 101, clock["ms"]))
    assert service.engine_errors == 1 and "engine bug" in service.last_engine_error
    assert market.usable and market.subscriber_errors == 0  # the fault stayed inside the service
    await service.close()
    await market.close()
