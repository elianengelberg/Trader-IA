"""¿El D2 re-coloca el stop solo cuando cambia su nivel o tamaño, o en cada barra (churn por redondeo)?"""
import asyncio
from pathlib import Path
import tia.backtest.engine as em
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE

serie = asyncio.run(CsvReplayProvider(Path("data/fixtures")).get_candles("BTC-USD", "1h", limit=700))
class Cuenta(BacktestEngine):
    def __init__(s, *a, **k):
        super().__init__(*a, **k); s.cambios = 0; s.prev = None
    def _sync_protective_stop(s, provider, leg, current_id, counts, **kw):
        clave = (leg.signal_id, leg.quantity, leg.stop_price) if leg is not None and leg.stop_price and leg.exit_pending is None else None
        if clave is not None and clave != s.prev:
            s.cambios += 1
        s.prev = clave
        return super()._sync_protective_stop(provider, leg, current_id, counts, **kw)
for rej, par in ((0.0, 0.0), (0.2, 0.0), (0.0, 0.9)):
    e = Cuenta(BacktestConfig(dataset="fx", timeframe="1h", warmup_bars=120,
                              execution=ExecutionSimConfig(reject_probability=rej, partial_fill_probability=par)), DEFAULT_UNIVERSE)
    r = e.run(serie)
    print(f"rechazo={rej} parcial={par}: colocaciones de stop={e._stop_placements} · cambios de (pierna, tamaño, nivel)={e.cambios} · "
          f"stops ajustados={r.decisions.stops_tightened} · operaciones={len(r.trades)} · rechazadas={r.decisions.orders_rejected}")
