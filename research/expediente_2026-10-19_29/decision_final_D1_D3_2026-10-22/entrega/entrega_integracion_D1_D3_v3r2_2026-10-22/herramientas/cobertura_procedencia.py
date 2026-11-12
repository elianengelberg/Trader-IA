"""Comprobaciones de cobertura de la procedencia (solo leen y corren un backtest sintético en memoria):
1) todos los módulos tia.* que se cargan al correr un backtest están en los subpaquetes que hashea la huella del motor;
2) cambiar cualquier campo escalar de BacktestConfig cambia el digest (y los 3 restantes entran explícitos en el run_id).
Uso: python -I cobertura_procedencia.py <raiz_arbol>"""
import asyncio, dataclasses, sys
from pathlib import Path
raiz = Path(sys.argv[1]); sys.path.insert(0, str(raiz / "packages/tia/src"))
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
import tia.backtest.engine as E
s = asyncio.run(CsvReplayProvider(raiz / "data/fixtures").get_candles("BTC-USD", "1h", limit=400))
for ent in ("market", "limit"):
    BacktestEngine(BacktestConfig(dataset="x", timeframe="1h", warmup_bars=120, entry_order_type=ent, max_holding_bars=6,
                   execution=ExecutionSimConfig(reject_probability=0.2, partial_fill_probability=0.4)), DEFAULT_UNIVERSE).run(s)
mods = sorted(m for m, x in sys.modules.items() if m.startswith("tia.") and getattr(x, "__file__", None))
fuera = [m for m in mods if m.split(".")[1] not in E._ENGINE_PACKAGES]
print(f"1) módulos tia.* cargados: {len(mods)} · subpaquetes: {sorted({m.split('.')[1] for m in mods})}")
print(f"   hasheados por la huella: {sorted(E._ENGINE_PACKAGES)} · fuera de la huella: {fuera or 'ninguno'}")
base = BacktestConfig(); sin, n = [], 0
explicitos = {"dataset", "liquidate_at_end", "is_out_of_sample"}
alt = {"timeframe": "1h", "risk_profile": "moderate", "entry_order_type": "limit"}
for f in dataclasses.fields(BacktestConfig):
    v = getattr(base, f.name)
    if f.name in explicitos or not isinstance(v, (bool, int, float, str)): continue
    nv = (not v) if isinstance(v, bool) else v + 1 if isinstance(v, int) else v * 1.5 + 0.1 if isinstance(v, float) else alt.get(f.name, v + "x")
    n += 1
    if dataclasses.replace(base, **{f.name: nv}).digest() == base.digest(): sin.append(f.name)
comp = [f.name for f in dataclasses.fields(BacktestConfig) if not isinstance(getattr(base, f.name), (bool, int, float, str))]
print(f"2) campos de BacktestConfig: {len(dataclasses.fields(BacktestConfig))} · escalares probados: {n} · que NO cambian el digest: {sin or 'ninguno'}")
print(f"   compuestos (volcados enteros en el digest): {comp} · explícitos en el run_id: {sorted(explicitos)}")
