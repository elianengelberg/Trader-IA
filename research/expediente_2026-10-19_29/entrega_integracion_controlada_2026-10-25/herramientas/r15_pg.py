"""R15 contra PostgreSQL real: escritores concurrentes de BacktestRepository.save con el mismo run_id.

Una sola base («r15_ic»), creada al empezar y borrada al terminar; la tabla se vacía (TRUNCATE) antes de cada intento.
Mide, por escenario, qué le dice save() a cada escritor y qué fila queda. Criterio fijado ANTES de correr:
  - «exito_descartado»: un escritor recibió éxito (sin excepción) con contenido distinto del que quedó guardado
    (procedencia o números distintos) → DEBE ser 0. Es R15.
  - conflictos con contenido distinto: exactamente 1 escritor aceptado; idénticos: todos aceptados y 1 fila.
  - rollback / timeout / desconexión: el escritor afectado NO recibe éxito; la fila final es la de un escritor que sí.
  - reintento tras resultado ambiguo: el reintento no duplica ni cambia procedencia/números.
Uso: python -I r15_pg.py <árbol> <socket_pg> <intentos_por_celda> <salida.json> <semilla>"""
import asyncio
import json
import random
import sys
import time
from pathlib import Path

arbol, sock, n, salida, semilla = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import psycopg2  # noqa: E402
from sqlalchemy import text  # noqa: E402

from tests.integration.test_backtest_provenance import _row, _run  # noqa: E402
from tia.persistence import BacktestRepository, Database  # noqa: E402

BASE = _row(_run())
VARIANTES = {
    "identico": dict(BASE),
    "otros_numeros": {**BASE, "trades": BASE["trades"] + 1, "total_return_pct": BASE["total_return_pct"] + 1.0},
    "otra_version": {**BASE, "conditions": {**BASE["conditions"], "engine_version": "9.9.9"}},
    "otra_version_y_numeros": {**BASE, "trades": BASE["trades"] + 2,
                               "conditions": {**BASE["conditions"], "engine_version": "9.9.9"}},
}
NOMBRE = "r15_ic"


def admin(sql: str) -> None:
    con = psycopg2.connect(host=sock, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(sql)
    con.close()


def huella(fila) -> tuple:
    if fila is None:
        return None
    c = fila["conditions"] if isinstance(fila, dict) else fila.conditions
    trades = fila["trades"] if isinstance(fila, dict) else fila.trades
    ret = fila["total_return_pct"] if isinstance(fila, dict) else fila.total_return_pct
    return (c.get("engine_version"), trades, round(ret, 9))


async def escribir(db, fila, listo, retraso, *, despues=None):
    """Un escritor: abre su sesión, espera la señal, (retraso), save(), y opcionalmente algo antes del commit."""
    try:
        async with db.session() as s:
            await listo.wait()
            if retraso:
                await asyncio.sleep(retraso)
            r = await BacktestRepository(s).save(fila)
            if despues is not None:
                await despues(s)
        return ("aceptado", str(r) if r is not None else "None")
    except ValueError as exc:
        return ("rechazado", type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        return ("error", f"{type(exc).__name__}: {str(exc)[:80]}")


async def fila_final(db):
    async with db.session() as s:
        filas = await BacktestRepository(s).list_recent()
    return filas


async def vaciar(db):
    async with db.engine.begin() as conn:
        await conn.execute(text("TRUNCATE backtests"))


def juzgar(escritores, filas):
    """Cuenta los escritores que recibieron éxito con contenido distinto del guardado."""
    guardada = huella(filas[0]) if len(filas) == 1 else None
    descartado = sum(1 for (fila, (res, _)) in escritores if res == "aceptado" and huella(fila) != guardada)
    return descartado, guardada


async def intento_concurrente(db, filas, retrasos):
    await vaciar(db)
    listo = asyncio.Event()
    tareas = [asyncio.create_task(escribir(db, f, listo, r)) for f, r in zip(filas, retrasos, strict=True)]
    await asyncio.sleep(0.02)
    listo.set()
    res = await asyncio.gather(*tareas)
    finales = await fila_final(db)
    descartado, guardada = juzgar(list(zip(filas, res, strict=True)), finales)
    return {"resultados": res, "filas": len(finales), "guardada": guardada, "exito_descartado": descartado}


async def main():
    rnd = random.Random(semilla)
    admin(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)')
    admin(f'CREATE DATABASE "{NOMBRE}"')
    url = f"postgresql+asyncpg://postgres@/{NOMBRE}?host={sock}"
    db = Database(url)
    await db.create_schema()
    out = {"arbol": str(arbol), "semilla": semilla, "intentos_por_celda": n, "celdas": {}, "fallos": {}}
    t0 = time.monotonic()
    # 1. dos escritores, cada variante contra la base, retrasos y orden alternados
    for nombre, otra in VARIANTES.items():
        for retraso in (0.0, 0.001, 0.005, 0.02, 0.1):
            celda = []
            for i in range(n):
                orden = [BASE, otra] if i % 2 == 0 else [otra, BASE]
                retrasos = [0.0, retraso] if rnd.random() < 0.5 else [retraso, 0.0]
                celda.append(await intento_concurrente(db, orden, retrasos))
            out["celdas"][f"{nombre}@{retraso}"] = {
                "intentos": n,
                "exito_descartado": sum(c["exito_descartado"] for c in celda),
                "ambos_aceptados": sum(1 for c in celda if all(r[0] == "aceptado" for r in c["resultados"])),
                "uno_aceptado": sum(1 for c in celda if sum(r[0] == "aceptado" for r in c["resultados"]) == 1),
                "errores": sorted({r[1] for c in celda for r in c["resultados"] if r[0] == "error"}),
                "rechazos": sorted({r[1] for c in celda for r in c["resultados"] if r[0] == "rechazado"}),
                "filas_finales": sorted({c["filas"] for c in celda}),
            }
    # 2. tres escritores (idéntico, otros números, otra versión) con retrasos aleatorios
    celda = []
    for _ in range(n * 2):
        filas = [BASE, VARIANTES["identico"], VARIANTES["otros_numeros"], VARIANTES["otra_version"]]
        rnd.shuffle(filas)
        celda.append(await intento_concurrente(db, filas, [rnd.choice((0.0, 0.001, 0.003, 0.01)) for _ in filas]))
    out["celdas"]["cuatro_escritores_aleatorio"] = {
        "intentos": n * 2, "exito_descartado": sum(c["exito_descartado"] for c in celda),
        "filas_finales": sorted({c["filas"] for c in celda}),
        "aceptados_por_intento": sorted({sum(r[0] == "aceptado" for r in c["resultados"]) for c in celda}),
    }
    # 3. fallos transaccionales
    async def revienta(_s):
        raise RuntimeError("fallo del escritor antes del commit")

    await vaciar(db)
    listo = asyncio.Event()
    t = [asyncio.create_task(escribir(db, BASE, listo, 0.0, despues=revienta)),
         asyncio.create_task(escribir(db, VARIANTES["otros_numeros"], listo, 0.01))]
    await asyncio.sleep(0.02)
    listo.set()
    res = await asyncio.gather(*t)
    finales = await fila_final(db)
    out["fallos"]["rollback_del_primero"] = {"resultados": res, "guardada": huella(finales[0]) if finales else None,
                                             "esperado": "1º error, 2º aceptado, queda el 2º",
                                             "exito_descartado": juzgar(list(zip([BASE, VARIANTES["otros_numeros"]], res, strict=True)), finales)[0]}

    async def retiene(_s):
        await asyncio.sleep(1.5)  # transacción abierta con la fila reclamada

    async def con_timeout(fila, listo):
        try:
            async with db.session() as s:
                await listo.wait()
                await asyncio.sleep(0.2)
                await s.execute(text("SET LOCAL lock_timeout = '300ms'"))
                r = await BacktestRepository(s).save(fila)
            return ("aceptado", str(r))
        except ValueError as exc:
            return ("rechazado", type(exc).__name__)
        except Exception as exc:  # noqa: BLE001
            return ("error", f"{type(exc).__name__}: {str(exc)[:80]}")

    await vaciar(db)
    listo = asyncio.Event()
    t = [asyncio.create_task(escribir(db, BASE, listo, 0.0, despues=retiene)),
         asyncio.create_task(con_timeout(VARIANTES["otros_numeros"], listo))]
    await asyncio.sleep(0.02)
    listo.set()
    res = await asyncio.gather(*t)
    finales = await fila_final(db)
    out["fallos"]["timeout_de_bloqueo_del_segundo"] = {"resultados": res, "guardada": huella(finales[0]) if finales else None,
                                                       "esperado": "1º aceptado, 2º error (lock timeout), queda el 1º",
                                                       "exito_descartado": juzgar(list(zip([BASE, VARIANTES["otros_numeros"]], res, strict=True)), finales)[0]}

    async def desconecta(s):
        pid = (await s.execute(text("select pg_backend_pid()"))).scalar()
        admin(f"select pg_terminate_backend({pid})")
        await asyncio.sleep(0.1)

    await vaciar(db)
    listo = asyncio.Event()
    r1 = await asyncio.gather(escribir(db, BASE, listo, 0.0, despues=desconecta), _set(listo))
    r2 = await escribir(db, VARIANTES["otros_numeros"], _abierto(), 0.0)
    finales = await fila_final(db)
    out["fallos"]["desconexion_antes_del_commit"] = {"resultados": [r1[0], r2], "guardada": huella(finales[0]) if finales else None,
                                                     "esperado": "1º error (conexión cortada), 2º aceptado, queda el 2º",
                                                     "exito_descartado": juzgar(list(zip([BASE, VARIANTES["otros_numeros"]], [r1[0], r2], strict=True)), finales)[0]}
    # 4. reintento tras resultado ambiguo: el commit ocurrió pero la respuesta "se perdió"; se reintenta lo mismo
    await vaciar(db)
    primero = await escribir(db, BASE, _abierto(), 0.0)
    reintento = await escribir(db, {**BASE}, _abierto(), 0.0)
    finales = await fila_final(db)
    out["fallos"]["reintento_tras_ambiguo_commit_hecho"] = {"resultados": [primero, reintento], "filas": len(finales),
                                                            "guardada": huella(finales[0]) if finales else None,
                                                            "esperado": "ambos aceptados (creado, repetido), 1 fila, sin cambios"}
    out["segundos"] = round(time.monotonic() - t0, 1)
    await db.close()
    admin(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)')
    json.dump(out, open(salida, "w"), indent=1, default=str, ensure_ascii=False)
    for k, v in out["celdas"].items():
        print(f"{k:34s} exito_descartado={v['exito_descartado']:3d}/{v['intentos']} " + " ".join(f"{a}={b}" for a, b in v.items() if a not in ("intentos", "exito_descartado")))
    for k, v in out["fallos"].items():
        print(f"{k:34s} {v}")
    print(f"total exito_descartado: {sum(v['exito_descartado'] for v in out['celdas'].values()) + sum(v.get('exito_descartado', 0) for v in out['fallos'].values())} · {out['segundos']} s")


async def _set(ev):
    await asyncio.sleep(0.02)
    ev.set()


def _abierto():
    ev = asyncio.Event()
    ev.set()
    return ev


asyncio.run(main())
