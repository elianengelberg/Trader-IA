"""Fase L, lo que es legítimo medir en este entorno: el efecto del motor 1.1.0 → 1.2.0 (R18) sobre los resultados, con
costos y fricciones del simulador (comisiones maker/taker, spread/deslizamiento, latencia, rechazos, parciales), frente a
las referencias pasivas que el propio evaluador calcula. Datos: las fixtures del repositorio (SINTÉTICAS, semillas fijas,
hash registrado): NO sirven para afirmar ventaja y no se usan para elegir parámetros. Reglas fijas: configuración por
defecto del motor; sólo varía la tasa de rechazo (el factor que R18 cambia) y la semilla del simulador.
Uso: python -I fase_l_cuantitativa.py <árbol> <salida.json>"""
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

arbol, salida = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.backtest.engine import ENGINE_VERSION  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.data.providers.csv_replay import CsvReplayProvider  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402

from tia.backtest.experiment import evaluate_experiment  # noqa: E402

FIX = arbol / "data/fixtures"
SERIES = asyncio.run(CsvReplayProvider(FIX).get_candles("BTC-USD", "1h", limit=700))
fx = FIX / "BTC-USD_1h.csv"
out = {"arbol": arbol.name, "engine_version": ENGINE_VERSION, "datos": {"archivo": "data/fixtures/BTC-USD_1h.csv",
       "sha256": hashlib.sha256(fx.read_bytes()).hexdigest(), "barras": len(SERIES), "naturaleza": "sintética (generate_fixtures.py, semilla fija)"},
       "corridas": []}
for reject in (0.0, 0.01, 0.05, 0.2):
    for seed in (1, 2, 3):
        ejec = ExecutionSimConfig(reject_probability=reject)
        eng = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, execution=ejec, seed=seed),
                             DEFAULT_UNIVERSE)
        res = eng.run(SERIES)
        fila = {"reject_probability": reject, "semilla": seed, "run_id": res.conditions.run_id[:16],
                "trades": len(res.trades), "total_return_pct": round(res.metrics.total_return_pct, 4),
                "max_drawdown_pct": round(res.metrics.max_drawdown_pct, 4), "sharpe": None if res.metrics.sharpe != res.metrics.sharpe else round(res.metrics.sharpe, 4),
                "salidas": dict(sorted({t.exit_reason: sum(1 for x in res.trades if x.exit_reason == t.exit_reason) for t in res.trades}.items())),
                "higiene": dict(getattr(eng, "order_hygiene", {})), "advertencias": len(res.warnings)}
        if True:
            rep = evaluate_experiment(res, SERIES, at=datetime(2026, 10, 25, tzinfo=UTC), costs=eng.config.execution)
            fila["veredicto_evaluador"] = rep.verdict.value
            fila["referencias"] = {b.name: round(b.metrics.total_return_pct, 4) for b in rep.baselines}
        out["corridas"].append(fila)
        print(json.dumps(fila, ensure_ascii=False)[:300])
salida.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
