"""Sonda (solo mide; base de datos SQLite temporal): ¿puede el guardado del parche 02 sobrescribir en silencio un
resultado con otro de la MISMA procedencia registrada pero números distintos? Se simula «algo que la procedencia no
registra» sustituyendo, en memoria, el proveedor de ejecución por una subclase que rechaza la primera orden (como haría
un cambio de entorno o de una pieza sustituida por quien llama). Uso: python sonda_misma_procedencia.py <raiz_arbol> <tmpdir>"""
import asyncio, sys
from datetime import UTC, datetime
from pathlib import Path
raiz, tmp = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(raiz / "packages/tia/src"))
import tia.backtest.engine as EM
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.paper import PaperExecutionProvider
from tia.persistence import BacktestRepository, Database

serie = asyncio.run(CsvReplayProvider(raiz / "data/fixtures").get_candles("BTC-USD", "1h", limit=400))
cfg = BacktestConfig(dataset="fixtures:BTC-USD:1h", timeframe="1h", warmup_bars=120,
                     execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0))

class RechazaLaPrimera(PaperExecutionProvider):
    vistas = 0
    def _should_reject(self, order):
        RechazaLaPrimera.vistas += 1
        return RechazaLaPrimera.vistas == 1 or super()._should_reject(order)

def fila(r):
    c = r.conditions
    return {"run_id": c.run_id, "created_at": datetime.now(UTC), "dataset": c.dataset, "symbols": list(c.symbols),
            "timeframe": c.timeframe, "bars": c.bars, "seed": c.seed, "total_return_pct": r.metrics.total_return_pct,
            "max_drawdown_pct": r.metrics.max_drawdown_pct, "sharpe": r.metrics.sharpe, "trades": len(r.trades),
            "equity_curve": [round(v, 4) for v in r.equity_curve[::5]], "conditions": c.model_dump(mode="json")}

a = BacktestEngine(cfg, DEFAULT_UNIVERSE).run(serie)
EM.PaperExecutionProvider = RechazaLaPrimera
b = BacktestEngine(cfg, DEFAULT_UNIVERSE).run(serie)
print("run_id A:", a.conditions.run_id, "· operaciones", len(a.trades), "· retorno", round(a.metrics.total_return_pct, 6))
print("run_id B:", b.conditions.run_id, "· operaciones", len(b.trades), "· retorno", round(b.metrics.total_return_pct, 6))
print("misma procedencia registrada:", {k: getattr(a.conditions, k) == getattr(b.conditions, k) for k in ("engine_version", "engine_fingerprint", "data_fingerprint", "universe_digest")})

async def main():
    db = Database(f"sqlite+aiosqlite:///{tmp / 'sonda.db'}"); await db.create_schema()
    async with db.session() as s: await BacktestRepository(s).save(fila(a))
    try:
        async with db.session() as s: await BacktestRepository(s).save(fila(b))
        resultado = "ACEPTADO"
    except ValueError as e:
        resultado = f"RECHAZADO: {e}"
    async with db.session() as s:
        filas = await BacktestRepository(s).list_recent()
    print("segundo guardado:", resultado)
    print("filas:", [(f.run_id, f.trades, round(f.total_return_pct, 6)) for f in filas])
    await db.close()
asyncio.run(main())
