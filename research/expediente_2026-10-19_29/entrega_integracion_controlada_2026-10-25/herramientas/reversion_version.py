"""E15 reversión de versión (Fase K): un paso, con el árbol dado, sobre una base SQLite compartida entre pasos.
  escribir  → (árbol candidato) guarda un resultado de backtest (motor actual) y un incidente de kind largo
  leer      → (cualquier árbol) lee resultados e incidentes con sus repositorios y prueba ensure_schema()
  exportar  → copia a JSON los incidentes de kind > 32 (historia preservada) y los borra para permitir la reversión
Uso: python -I reversion_version.py <árbol> <paso> <base.db> <salida.json>"""
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

arbol, paso, base, salida = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from sqlalchemy import text  # noqa: E402

from tia.persistence import BacktestRepository, Database, IncidentRepository  # noqa: E402
from tia.persistence.models import SCHEMA_VERSION  # noqa: E402

if paso == "escribir":  # importa fuera del bucle: el módulo de pruebas corre asyncio.run al importarse
    from tests.integration.test_backtest_provenance import _row, _run  # noqa: E402


async def main():
    db = Database(f"sqlite+aiosqlite:///{base}")
    out = {"arbol": arbol.name, "paso": paso, "SCHEMA_VERSION_del_codigo": SCHEMA_VERSION}
    try:
        if paso == "escribir":
            fila = _row(_run())
            async with db.session() as s:
                out["save"] = str(await BacktestRepository(s).save(fila))
                await IncidentRepository(s).record({"incident_id": "e15-largo", "at": datetime.now(UTC),
                                                    "kind": "entries_blocked:position_unverified", "actor": "system",
                                                    "reason": "e15", "run_id": "r", "detail": {}})
                await IncidentRepository(s).record({"incident_id": "e15-corto", "at": datetime.now(UTC),
                                                    "kind": "halt_new_orders", "actor": "system", "reason": "e15",
                                                    "run_id": "r", "detail": {}})
            out["engine_version_guardada"] = fila["conditions"]["engine_version"]
        elif paso == "leer":
            async with db.session() as s:
                bts = await BacktestRepository(s).list_recent()
                inc = await IncidentRepository(s).recent()
            out["backtests"] = [{"run_id": b.run_id[:12], "engine_version": (b.conditions or {}).get("engine_version"),
                                 "trades": b.trades} for b in bts]
            out["incidentes"] = sorted(i.kind for i in inc)
            try:
                out["ensure_schema"] = await db.ensure_schema()
            except Exception as exc:  # noqa: BLE001 - registrado
                out["ensure_schema"] = f"RECHAZA: {type(exc).__name__}: {str(exc)[:160]}"
        elif paso == "exportar":
            async with db.engine.begin() as conn:
                largos = [dict(r._mapping) for r in await conn.execute(text(
                    "select incident_id, at, kind, actor, reason, run_id, detail from incidents where length(kind) > 32"))]
                Path(str(salida) + ".incidentes_exportados.json").write_text(json.dumps(largos, default=str, indent=1))
                await conn.execute(text("delete from incidents where length(kind) > 32"))
            out["exportados_y_borrados"] = len(largos)
    finally:
        await db.close()
    salida.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    print(json.dumps(out, default=str, ensure_ascii=False))


asyncio.run(main())
