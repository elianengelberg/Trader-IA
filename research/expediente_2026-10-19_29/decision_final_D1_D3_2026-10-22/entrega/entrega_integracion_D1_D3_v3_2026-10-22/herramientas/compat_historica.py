"""Compatibilidad con registros históricos usando el código REAL de cada versión (no una fila simulada).
Levanta la aplicación del árbol dado sobre una base SQLite compartida, inicia sesión, opcionalmente corre un backtest
por la API y lista lo guardado. Uso: python -I compat_historica.py <raiz_arbol> <base.db> <salida.json> [correr]"""
import asyncio, json, os, sys
from pathlib import Path
raiz, db, salida = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
correr = "correr" in sys.argv[4:]
sys.path.insert(0, str(raiz / "packages/tia/src"))
os.chdir(raiz)  # la API lee data/fixtures relativo al árbol
os.environ["TIA_DEMO_USER"] = "compat-operator"; os.environ["TIA_DEMO_PASSWORD"] = "compat-password-not-a-secret"
import httpx
from asgi_lifespan import LifespanManager
from tia.api.app import create_app
from tia.core.config import Environment, settings_for_env

async def main():
    settings = settings_for_env(Environment.TESTING).model_copy(update={"database_url": f"sqlite+aiosqlite:///{db}"})
    app = create_app(settings)
    out = {"arbol": str(raiz)}
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/auth/login", json={"username": "compat-operator", "password": "compat-password-not-a-secret"})
            assert r.status_code == 200, r.text
            if correr:
                r = await c.post("/api/backtests", json={"symbol": "BTC-USD", "timeframe": "1h", "bars": 600, "seed": 20260812})
                out["post_status"] = r.status_code
                out["post_run_id"] = r.json().get("run_id") if r.status_code == 200 else r.text[:300]
            r = await c.get("/api/backtests")
            out["listado"] = r.json()
    json.dump(out, open(salida, "w"), indent=1, default=str)
asyncio.run(main())
