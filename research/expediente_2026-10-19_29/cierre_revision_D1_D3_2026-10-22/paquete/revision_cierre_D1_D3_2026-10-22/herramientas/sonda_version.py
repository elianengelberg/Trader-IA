"""Sonda (solo mide): qué versión y huella registra el motor del árbol dado y qué produce sobre los fixtures con rechazos
y parciales. Uso: python -I sonda_version.py <raiz_arbol>"""
import asyncio, sys
from pathlib import Path
raiz = Path(sys.argv[1]); sys.path.insert(0, str(raiz / "packages/tia/src"))
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
s = asyncio.run(CsvReplayProvider(raiz / "data/fixtures").get_candles("BTC-USD", "1h", limit=400))
e = BacktestEngine(BacktestConfig(dataset="fixtures:BTC-USD:1h", timeframe="1h", warmup_bars=120,
                   execution=ExecutionSimConfig(reject_probability=0.3, partial_fill_probability=0.5)), DEFAULT_UNIVERSE)
r = e.run(s); c = r.conditions
print(f"engine_version={getattr(c, 'engine_version', '(no existe)')} · huella={getattr(c, 'engine_fingerprint', '(no existe)')[:16]} · "
      f"run_id={c.run_id} · operaciones={len(r.trades)} · retorno={r.metrics.total_return_pct:.6f} · "
      f"tiene D1-D3 (order_hygiene)={hasattr(e, 'order_hygiene')}")
