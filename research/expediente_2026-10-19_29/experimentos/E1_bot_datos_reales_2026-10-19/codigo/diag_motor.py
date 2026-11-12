"""Diagnóstico del motor con datos SINTÉTICOS (no históricos): ¿quedan posiciones sin stop o sin salida, y el stop
resting sigue al stop ajustado (break-even / trailing)? Solo observa; no cambia el motor."""
import logging, math, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
import numpy as np
from tia.backtest import engine as EM
from tia.backtest.engine import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig, StrategyConfig
from tia.domain.enums import AssetClass
from tia.domain.instruments import Instrument, InstrumentUniverse
from tia.domain.market import Candle
import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

def sinteticas(n, semilla):
    rng = np.random.default_rng(semilla); t0 = datetime(2020, 1, 1, tzinfo=timezone.utc); p = 30000.0; out = []
    for i in range(n):
        o = p; path = o * np.exp(np.cumsum(rng.normal(0.0003 * math.sin(i / 250), 0.004, 4))); c = float(path[-1])
        out.append(Candle(symbol="BTCUSDT", timeframe="1h", open_time=t0 + timedelta(hours=i), close_time=t0 + timedelta(hours=i + 1),
                          open=o, high=float(max(o, path.max())) * 1.0005, low=float(min(o, path.min())) * 0.9995, close=c,
                          volume=float(rng.lognormal(7, 0.5))))
        p = c
    return out

# instrumentación por observación: registrar el stop de la pierna y el precio de la orden stop activa en cada barra
obs = []
orig_sync = BacktestEngine._sync_protective_stop
def espia(self, provider, leg, current_id, counts):
    nuevo = orig_sync(self, provider, leg, current_id, counts)
    if leg is not None and leg.exit_pending is None and leg.stop_price is not None:
        orden = EM._sync(provider.get_order(nuevo)) if nuevo else None
        obs.append((leg.signal_id, leg.stop_kind, float(leg.stop_price),
                    float(orden.stop_price) if orden is not None and orden.stop_price else None,
                    orden.state.value if orden is not None else None))
    return nuevo
BacktestEngine._sync_protective_stop = espia

u = InstrumentUniverse(instruments=(Instrument(symbol="BTCUSDT", asset_class=AssetClass.CRYPTO, tick_size=0.01, lot_size=1e-5,
                                               min_notional=5.0, shortable=False),))
for rechazo in (0.01, 0.0):
    obs.clear()
    cfg = BacktestConfig(dataset="sintetico", timeframe="1h", strategy=StrategyConfig(enabled=("trend_following",)),
                         execution=ExecutionSimConfig(allow_shorting=False, reject_probability=rechazo))
    r = BacktestEngine(cfg, u, strategies=("trend_following",)).run(sinteticas(6000, 7))
    d = r.decisions
    sin_stop = sum(1 for o in obs if o[3] is None)
    desfasado = [o for o in obs if o[3] is not None and abs(o[3] - o[2]) > 1e-6 * o[2]]
    print(f"\n== reject_probability={rechazo}: trades {len(r.trades)}, stops sin colocar {d.protective_stops_unplaced}, "
          f"órdenes rechazadas {d.orders_rejected}, ajustes de stop {d.stops_tightened}, salidas pedidas {dict(d.exits_requested)}")
    print(f"barras con pierna abierta observadas: {len(obs)} | sin orden stop activa: {sin_stop} | "
          f"orden stop con precio distinto del stop de la pierna: {len(desfasado)}")
    if desfasado:
        print("  ejemplos (tipo, stop de la pierna, stop de la orden activa):", [(o[1], round(o[2], 2), round(o[3], 2)) for o in desfasado[:4]])
    print("razones de salida:", Counter(t.exit_reason for t in r.trades).most_common())
    print("barras mantenidas: máx", max((t.bars_held for t in r.trades), default=0), "| mediana", sorted(t.bars_held for t in r.trades)[len(r.trades)//2] if r.trades else 0)
