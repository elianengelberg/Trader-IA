"""Sonda: ¿en qué escenario aparece D3 con el motor original? Solo cantidades mecánicas."""
import asyncio, math, random, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle

def sinteticas(n, semilla, symbol="BTC-USD"):
    rng = random.Random(semilla); t = datetime(2020, 1, 1, tzinfo=timezone.utc); p = 30000.0; out = []
    for i in range(n):
        o = p; path = [o]
        for _ in range(4):
            path.append(path[-1] * math.exp(rng.gauss(0.0003 * math.sin((i + semilla) / 250), 0.004)))
        c = path[-1]
        out.append(Candle(symbol=symbol, timeframe="1h", open_time=t, close_time=t + timedelta(hours=1), open=o,
                          high=max(path) * 1.0005, low=min(path) * 0.9995, close=c, volume=rng.lognormvariate(7, 0.5),
                          provider="SINTETICO"))
        p, t = c, t + timedelta(hours=1)
    return out

class Spy(BacktestEngine):
    def __init__(s, *a, **k):
        super().__init__(*a, **k); s.mismatch = 0; s.first = None; s.bar = 0
    def _sync_protective_stop(s, provider, leg, current_id, counts, **kw):
        s.bar += 1
        r = super()._sync_protective_stop(provider, leg, current_id, counts, **kw)
        pos = provider.portfolio.positions.get(leg.symbol if leg else "BTC-USD")
        held = 0.0 if pos is None or pos.is_flat else abs(pos.quantity)
        exp = 0.0 if leg is None else leg.quantity
        if abs(held - exp) > max(exp * 1e-6, 1e-9):
            s.mismatch += 1; s.first = s.first or s.bar
        return r

fx = Path(sys.argv[1])
for nombre, serie in (("fixtures700", asyncio.run(CsvReplayProvider(fx).get_candles("BTC-USD", "1h", limit=700))),
                      ("sint3000", sinteticas(3000, 23))):
    for partial in (0.5, 0.9):
        t0 = time.time()
        e = Spy(BacktestConfig(dataset="x", timeframe="1h", warmup_bars=120,
                               execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=partial)), DEFAULT_UNIVERSE)
        r = e.run(serie)
        print(nombre, partial, "trades", len(r.trades), "max_bars", max((t.bars_held for t in r.trades), default=0),
              "mismatch", e.mismatch, "first", e.first, "hyg", getattr(e, "order_hygiene", None), f"{time.time()-t0:.1f}s", flush=True)
