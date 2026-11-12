"""R15 en PostgreSQL con intercalados y tipos de conflicto distintos (solo mide; base nueva por intento).
Para cada (conflicto, retraso de la 2.ª sesión) se hacen N intentos de dos BacktestRepository.save simultáneos con el
mismo run_id. Contrato de 02v3:
  - "otros_numeros": misma procedencia, números distintos → la 2.ª debe ser RECHAZADA.
  - "otra_procedencia": otra engine_version → la 2.ª debe ser RECHAZADA.
  - "mismos_numeros": re-corrida idéntica → las dos pueden aceptarse (idempotente).
Se registra qué recibe cada escritor y qué fila queda.
Uso: python -I r15_intercalados.py <árbol_con_A> <socket_pg> <intentos> <salida.json> [conflictos,...] [retrasos_s,...]\nCada base se borra (DROP DATABASE) después de su intento."""
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
VARIANTES = {
    "otros_numeros": {**BASE, "trades": BASE["trades"] + 1, "total_return_pct": BASE["total_return_pct"] + 1.0},
    "otra_procedencia": {**BASE, "conditions": {**BASE["conditions"], "engine_version": "9.9.9"}},
    "mismos_numeros": dict(BASE),
}


def borrar_base(nombre: str) -> None:
    con = psycopg2.connect(host=sock, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
    con.close()


def nueva_base() -> str:
    nombre = "r15i_" + uuid.uuid4().hex[:12]
    con = psycopg2.connect(host=sock, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(f'CREATE DATABASE "{nombre}"')
    con.close()
    return nombre


async def guardar(db, fila, listo, retraso):
    try:
        async with db.session() as s:
            await listo.wait()
            if retraso:
                await asyncio.sleep(retraso)
            await BacktestRepository(s).save(fila)
        return "aceptado"
    except ValueError as exc:
        return "rechazado"
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}"


async def intento(conflicto, retraso):
    nombre = nueva_base()
    db = Database(f"postgresql+asyncpg://postgres@/{nombre}?host={sock}")
    await db.create_schema()
    listo = asyncio.Event()
    otra = VARIANTES[conflicto]
    t = [asyncio.create_task(guardar(db, BASE, listo, 0.0)), asyncio.create_task(guardar(db, otra, listo, retraso))]
    await asyncio.sleep(0.05)
    listo.set()
    a, b = await asyncio.gather(*t)
    async with db.session() as s:
        filas = await BacktestRepository(s).list_recent()
    f = filas[0] if filas else None
    quedo = None if f is None else ("primera" if (f.trades == BASE["trades"] and (f.conditions or {}).get("engine_version") == BASE["conditions"].get("engine_version")) else "segunda")
    await db.close()
    borrar_base(nombre)
    return a, b, quedo, len(filas)


async def main():
    res = {}
    conflictos = sys.argv[5].split(",") if len(sys.argv) > 5 else list(VARIANTES)
    retrasos = [float(x) for x in sys.argv[6].split(",")] if len(sys.argv) > 6 else [0.0, 0.001, 0.005, 0.02, 0.1]
    for conflicto in conflictos:
        for retraso in retrasos:
            out = [await intento(conflicto, retraso) for _ in range(n)]
            ambos = sum(1 for a, b, _, _ in out if a == b == "aceptado")
            uno = sum(1 for a, b, _, _ in out if sorted((a, b)) == ["aceptado", "rechazado"])
            otros = sorted({(a, b) for a, b, _, _ in out if {a, b} - {"aceptado", "rechazado"}})
            quedo = {k: sum(1 for *_, q, _ in out if q == k) for k in ("primera", "segunda", None)}
            res[f"{conflicto}@{retraso}"] = {"intentos": n, "ambos_aceptados": ambos, "uno_rechazado": uno, "otros": otros,
                                             "filas_finales": sorted({x[3] for x in out}), "quedo": {str(k): v for k, v in quedo.items()}}
            print(f"{conflicto:17s} retraso {retraso*1000:6.1f} ms: ambos aceptados {ambos:2d}/{n} · uno rechazado {uno:2d} · otros {otros} · queda {quedo}")
    json.dump(res, open(salida, "w"), indent=1, default=str)


asyncio.run(main())
