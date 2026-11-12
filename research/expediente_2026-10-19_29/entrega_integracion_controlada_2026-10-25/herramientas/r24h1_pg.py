"""R24-H1 contra PostgreSQL real: ¿se pierde un incidente entries_blocked:* largo?
(1) directo: IncidentRepository.record con cada kind que el runtime genera; (2) de punta a punta: un LiveRuntime de papel
cuyo persist escribe incidentes en PostgreSQL como AppState, bloquea entradas por cada causa y espera el flush; se cuenta
lo que quedó en la base y lo que flush_persistence() dijo. Base propia creada y borrada aquí.
Uso: python -I r24h1_pg.py <árbol> <socket_pg> <salida.json>"""
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

arbol, sock, salida = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import psycopg2  # noqa: E402

from tia.persistence import Database, IncidentRepository  # noqa: E402

NOMBRE = "r24h1_ic"
KINDS = ["entries_blocked:account_state", "entries_blocked:orders_unverified", "entries_blocked:position_unverified",
         "entries_blocked:position_unprotected", "protective_stop_failed", "session_deadline_close_unfilled"]


def admin(sql):
    con = psycopg2.connect(host=sock, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(sql)
    con.close()


async def main():
    admin(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)')
    admin(f'CREATE DATABASE "{NOMBRE}"')
    db = Database(f"postgresql+asyncpg://postgres@/{NOMBRE}?host={sock}")
    await db.create_schema()
    out = {"arbol": str(arbol), "directo": {}, "punta_a_punta": {}}
    async with db.engine.connect() as conn:
        from sqlalchemy import text
        out["columna_kind"] = (await conn.execute(text(
            "select character_maximum_length from information_schema.columns where table_name='incidents' and column_name='kind'"))).scalar()
    for i, kind in enumerate(KINDS):
        try:
            async with db.session() as s:
                await IncidentRepository(s).record({"incident_id": f"inc-{i}", "at": datetime.now(UTC), "kind": kind,
                                                    "actor": "system", "reason": "r24h1", "run_id": "r", "detail": {}})
            out["directo"][kind] = "guardado"
        except Exception as exc:  # noqa: BLE001
            out["directo"][kind] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    # punta a punta, como AppState: una sesión por escritura
    from tests.integration.test_live_runtime import build_runtime_paper

    async def persist(kind, payload):
        if kind != "incident":
            return
        async with db.session() as s:
            await IncidentRepository(s).record(payload)

    runtime, _, _ = build_runtime_paper()
    runtime._persist = persist
    for causa in ("account_state", "orders_unverified", "position_unverified", "position_unprotected"):
        runtime._block_entries(causa, f"r24h1: {causa}")
    flushed = await runtime.flush_persistence(timeout_seconds=10.0)
    async with db.session() as s:
        guardados = sorted(r.kind for r in await IncidentRepository(s).recent(limit=100) if r.reason.startswith("r24h1:"))
    out["punta_a_punta"] = {"pedidos": 4, "guardados": guardados, "flush_persistence_devolvio": flushed}
    await db.close()
    admin(f'DROP DATABASE IF EXISTS "{NOMBRE}" WITH (FORCE)')
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out, indent=1, ensure_ascii=False))


asyncio.run(main())
