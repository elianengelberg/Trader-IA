"""Sonda R15 (solo mide): ¿la carrera «leer y después hacer upsert» de BacktestRepository.save ocurre en PostgreSQL?
En cada intento, dos sesiones guardan A LA VEZ el mismo run_id con la misma procedencia y números distintos. El contrato
de 02v3 dice que la segunda debe ser rechazada. Se cuenta: una rechazada (contrato cumplido), las dos aceptadas (carrera:
gana la última; contrato violado), otros errores. Una base nueva por intento.
Uso: python -I sonda_r15_pg.py <árbol> <socket_pg> <intentos> <salida.json>"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

arbol, sock, n, salida = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import psycopg2  # noqa: E402

from tests.integration.test_backtest_provenance import _row, _run  # noqa: E402
from tia.persistence import BacktestRepository, Database  # noqa: E402

BASE = _row(_run())
OTRA = {**BASE, "trades": BASE["trades"] + 1, "total_return_pct": BASE["total_return_pct"] + 1.0}


def nueva_base() -> str:
    nombre = "r15_" + uuid.uuid4().hex[:12]
    con = psycopg2.connect(host=sock, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(f'CREATE DATABASE "{nombre}"')
    con.close()
    return nombre


async def guardar(db: Database, fila: dict, listo: asyncio.Event) -> str:
    try:
        async with db.session() as s:
            repo = BacktestRepository(s)
            await listo.wait()  # las dos sesiones arrancan juntas
            await repo.save(fila)
        return "aceptado"
    except ValueError as exc:
        return "rechazado" if "same provenance and other results" in str(exc) else f"ValueError: {exc}"[:200]
    except Exception as exc:  # noqa: BLE001 - se registra cualquier otro desenlace
        return f"{type(exc).__name__}: {exc}"[:200]


async def intento() -> dict:
    db = Database(f"postgresql+asyncpg://postgres@/{nueva_base()}?host={sock}")
    await db.create_schema()
    listo = asyncio.Event()
    tareas = [asyncio.create_task(guardar(db, BASE, listo)), asyncio.create_task(guardar(db, OTRA, listo))]
    await asyncio.sleep(0.05)
    listo.set()
    a, b = await asyncio.gather(*tareas)
    async with db.session() as s:
        filas = await BacktestRepository(s).list_recent()
    quedo = "base" if filas and filas[0].trades == BASE["trades"] else ("otra" if filas else "ninguna")
    await db.close()
    return {"a": a, "b": b, "quedo": quedo, "filas": len(filas)}


async def main() -> None:
    res = [await intento() for _ in range(n)]
    resumen = {"intentos": n,
               "una_rechazada": sum(1 for r in res if sorted((r["a"], r["b"])) == ["aceptado", "rechazado"]),
               "dos_aceptadas_carrera": sum(1 for r in res if r["a"] == r["b"] == "aceptado"),
               "otros": [r for r in res if not ({r["a"], r["b"]} <= {"aceptado", "rechazado"})][:5],
               "quedo": {k: sum(1 for r in res if r["quedo"] == k) for k in ("base", "otra", "ninguna")}}
    json.dump({"resumen": resumen, "intentos": res}, open(salida, "w"), indent=1)
    print(json.dumps(resumen, indent=1))


asyncio.run(main())
