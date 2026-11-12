"""Plugin de pytest (medición): cuenta los ciclos que corre el bucle de fondo creado por start()
frente a los ciclos manuales de la prueba. Escribe JSON en $SONDA_CICLOS."""
import json, os
import tia.runtime.live as live

_n = {"fondo": 0, "manual": 0}
_orig_iter = live.LiveRuntime._loop_iteration
_orig_cycle = live.LiveRuntime._cycle_once

async def _iter(self):
    self._sonda_en_fondo = True
    try:
        await _orig_iter(self)
    finally:
        self._sonda_en_fondo = False

async def _cycle(self):
    _n["fondo" if getattr(self, "_sonda_en_fondo", False) else "manual"] += 1
    return await _orig_cycle(self)

live.LiveRuntime._loop_iteration = _iter
live.LiveRuntime._cycle_once = _cycle

def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["SONDA_CICLOS"], "w") as f:
        json.dump({"exit": int(exitstatus), **_n}, f)
