"""Plugin de pytest para R24: corre las pruebas EXISTENTES de trazabilidad del almacén
(tests/integration/test_backtest_provenance.py) contra PostgreSQL en lugar de SQLite, sin tocar el archivo de pruebas.

Reemplaza solo el ayudante ``_store`` del módulo: cada prueba recibe una base de datos PostgreSQL NUEVA (CREATE DATABASE
con nombre único) en la instancia desechable indicada por R24_PG_SOCKET (directorio del socket Unix). Las pruebas que no
usan ``_store`` (la de la API, que arma su propia base SQLite) siguen igual."""
import os
import sys
import uuid

import psycopg2

SOCK = os.environ["R24_PG_SOCKET"]
CREADAS = []


def _nueva_base() -> str:
    nombre = "r24_" + uuid.uuid4().hex[:12]
    con = psycopg2.connect(host=SOCK, user="postgres", dbname="postgres")
    con.autocommit = True
    con.cursor().execute(f'CREATE DATABASE "{nombre}"')
    con.close()
    CREADAS.append(nombre)
    return nombre


def pytest_collection_finish(session):
    from tia.persistence import Database

    mod = sys.modules.get("tests.integration.test_backtest_provenance")
    if mod is None:
        return

    async def _store(tmp_path):
        db = Database(f"postgresql+asyncpg://postgres@/{_nueva_base()}?host={SOCK}")
        await db.create_schema()
        assert db.dialect == "postgresql", db.dialect
        return db

    mod._store = _store
    print(f"\n[r24] _store de test_backtest_provenance redirigido a PostgreSQL (socket {SOCK})")


def pytest_sessionfinish(session, exitstatus):
    print(f"\n[r24] bases PostgreSQL creadas: {len(CREADAS)}")
