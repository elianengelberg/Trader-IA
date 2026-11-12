"""R19: lo que flush_persistence() dice frente a lo que quedó en la base, por condición. Base vs candidato.

Cada corrida: un LiveRuntime de papel del árbol dado programa N escrituras de incidentes (ids conocidos) hacia una base
SQLite real (tia.persistence, IncidentRepository: el camino de AppState), con la falla de la condición. Se mide el flush
directamente (valor y duración), se cuentan las filas en la base con una conexión nueva, y se juzga con un criterio fijado
antes de correr:
  FALSO_COMPLETO = el flush (o el cierre) dijo True y en la base faltan filas.   Debe ser 0 en el candidato.
  CIERRE_LIMPIO_CON_PENDIENTES = stop() dejó persistence_flushed True con escrituras sin confirmar.  Debe ser 0.
Condiciones: sin_carga, cpu (carga externa), suite_concurrente (carga externa), lentas, errores, interrupcion, reinicio.
Uso: python -I r19_matriz.py <árbol> <condición> <salida.json> <semilla> <n>"""
import asyncio
import json
import random
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

arbol, cond, salida, semilla, n = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from tests.integration.test_live_runtime import build_runtime_paper  # noqa: E402
from tia.persistence import Database, IncidentRepository  # noqa: E402

rnd = random.Random(semilla)


def filas_en_base(path: Path) -> set[str]:
    con = sqlite3.connect(path)  # conexión nueva: lo que lee un proceso reiniciado
    try:
        return {r[0] for r in con.execute("select incident_id from incidents where reason like 'r19m%'")}
    finally:
        con.close()


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="r19m_", dir=str(Path(salida).parent)))
    path = tmp / "r19.db"
    db = Database(f"sqlite+aiosqlite:///{path}")
    await db.create_schema()
    lentas = cond in ("lentas", "interrupcion", "reinicio")
    errores = cond == "errores"

    async def persist(kind, payload):
        if kind != "incident" or not str(payload.get("reason", "")).startswith("r19m"):
            return
        if lentas:
            await asyncio.sleep(rnd.uniform(0.005, 0.05))
        if errores and int(payload["incident_id"].split("-")[1]) % 7 == 3:
            raise OSError("disk I/O error (inyectado)")
        async with db.session() as s:
            await IncidentRepository(s).record(payload)

    runtime, _, _ = build_runtime_paper()
    runtime._persist = persist
    ids = [f"m-{i}" for i in range(n)]
    for i in ids:
        runtime._save(
            "incident", {"incident_id": i, "at": datetime.now(UTC), "kind": "halt_new_orders", "actor": "system",
                         "reason": f"r19m {i}", "run_id": runtime.run_id, "detail": {}})
    timeout = 1.0 if lentas else 10.0
    t0 = time.monotonic()
    interrumpido = False
    if cond == "interrupcion":
        flush = asyncio.ensure_future(runtime.flush_persistence(timeout_seconds=timeout))
        await asyncio.sleep(0.3)
        flush.cancel()  # SIGTERM/cancelación en medio del flush
        try:
            dijo = await flush
        except asyncio.CancelledError:
            dijo, interrumpido = None, True
    else:
        dijo = await runtime.flush_persistence(timeout_seconds=timeout)
    dur = time.monotonic() - t0
    # el cierre de la sesión (stop) con el mismo plazo, como en producción
    runtime._flush_timeout_seconds = timeout
    await runtime.start()
    await runtime.stop()
    cierre = runtime.persistence_flushed
    reporte = runtime.persistence_report() if hasattr(runtime, "persistence_report") else None
    if cond in ("reinicio", "interrupcion"):
        # el proceso "muere": lo que no terminó, no termina (se cancela) y se lee la base desde otro proceso
        for t in list(runtime._persist_tasks):
            t.cancel()
        await asyncio.sleep(0.05)
    await db.close()
    en_base = filas_en_base(path)
    faltan = sorted(set(ids) - en_base)
    out = {
        "arbol": arbol.name, "condicion": cond, "semilla": semilla, "programadas": n,
        "flush_dijo": dijo, "flush_interrumpido": interrumpido, "flush_segundos": round(dur, 3),
        "cierre_persistence_flushed": cierre, "last_error": runtime.last_error[:200],
        "filas_en_base": len(en_base), "faltan": len(faltan),
        "reporte": None if reporte is None else {k: (len(v) if k == "lost" else v) for k, v in reporte.items()},
        "perdidas_identificadas": None if reporte is None else sorted(x["ids"].get("incident_id") for x in reporte["lost"]),
        "FALSO_COMPLETO": bool((dijo is True or cierre is True) and faltan),
        "CIERRE_LIMPIO_CON_PENDIENTES": bool(cierre is True and faltan),
    }
    if reporte is not None and cond == "errores":
        out["perdidas_coinciden_con_faltantes"] = out["perdidas_identificadas"] == faltan
    json.dump(out, open(salida, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k not in ("perdidas_identificadas",)}, default=str))
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()


asyncio.run(main())
