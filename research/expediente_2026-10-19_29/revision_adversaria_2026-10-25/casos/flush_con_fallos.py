"""¿flush_persistence distingue «todo guardado» de «todo terminado»? Se usan los métodos REALES de LiveRuntime (sin
instanciar la sesión) sobre un objeto mínimo: 3 escrituras, 2 de ellas fallan. Uso: python -I flush_con_fallos.py <árbol>"""
import asyncio, pathlib, sys, types
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve() / "packages/tia/src"))
from tia.runtime.live import LiveRuntime  # noqa: E402

async def main():
    hechas, o = [], types.SimpleNamespace(_persist_tasks=set(), _persist_lock=asyncio.Lock())
    async def persist_coro(kind, payload):
        await asyncio.sleep(0.01)
        if kind != "order":
            raise RuntimeError(f"base caída al guardar {kind}")
        hechas.append(kind)
    o._persist = persist_coro
    o._sequenced = lambda w: LiveRuntime._sequenced(o, w)
    for kind in ("order", "fill", "stop_stamp"):
        LiveRuntime._save(o, kind, {"x": 1})
    ok = await LiveRuntime.flush_persistence(o, timeout_seconds=5.0)
    print(f"escrituras programadas 3 · guardadas {len(hechas)} ({hechas}) · flush_persistence devolvió {ok}")
    print("CONCLUSIÓN:", "persistence_flushed=True con 2 de 3 escrituras PERDIDAS" if ok and len(hechas) < 3 else "distingue fallos")
asyncio.run(main())
