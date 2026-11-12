"""Sonda R4 (solo lectura): corre el motor del árbol actual (PYTHONPATH) sobre los fixtures con una
configuración fija y dice su run_id, el run_id «antiguo» (fórmula de 72ffae5) y los números.
Uso: python sonda_run_id.py <raiz_del_arbol> <salida.json>"""
import asyncio, json, sys
from pathlib import Path
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.core.ids import deterministic_id
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE

raiz = Path(sys.argv[1])
serie = asyncio.run(CsvReplayProvider(raiz / "data" / "fixtures").get_candles("BTC-USD", "1h", limit=400))
out = {}
for nombre, ejec, barras in (
    ("sin_rechazos_400", ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0), serie),
    ("sin_rechazos_350", ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0), serie[:350]),
    ("rechazos_0.3_parciales_0.5", ExecutionSimConfig(reject_probability=0.3, partial_fill_probability=0.5), serie),
):
    cfg = BacktestConfig(dataset="fixtures:BTC-USD:1h", timeframe="1h", warmup_bars=120, execution=ejec)
    r = BacktestEngine(cfg, DEFAULT_UNIVERSE).run(barras)
    c = r.conditions
    out[nombre] = {
        "run_id": c.run_id,
        "run_id_formula_72ffae5": deterministic_id("bt", cfg.dataset, "BTC-USD", cfg.digest()),
        "engine_version": getattr(c, "engine_version", "(campo inexistente)"),
        "bars": c.bars, "trades": len(r.trades),
        "total_return_pct": r.metrics.total_return_pct, "final_equity": r.equity_curve[-1],
        "warnings": len(r.warnings),
    }
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out, indent=1))
