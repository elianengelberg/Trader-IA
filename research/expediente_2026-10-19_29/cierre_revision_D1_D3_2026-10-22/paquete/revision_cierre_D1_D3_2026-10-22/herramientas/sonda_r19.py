"""Sonda R19 (plugin de pytest). Mide; no cambia el resultado de ninguna prueba.
Única intervención, opcional y solo como CONTROL del experimento (R19_PARK=1): cancela el bucle de fondo que start() lanza,
como hace _drive_by_hand en el parche 03, para comparar con y sin productor concurrente.

Registra en $R19_OUT (JSON):
  - ciclos del bucle de fondo frente a ciclos manuales;
  - por cada flush_persistence: escrituras pendientes al entrar, duración y resultado; si vence el plazo, toma la foto de
    las escrituras pendientes en ese instante y espera hasta $R19_EXTRA s (120 por defecto) para ver si TERMINAN (lentas)
    o NO terminan (trabadas). La prueba recibe el mismo False que habría recibido;
  - excepciones de escrituras (tipo y mensaje);
  - resultado y duración de cada prueba; carga del sistema al empezar y al terminar."""
import asyncio, json, os, time
import tia.runtime.live as live

OUT, PARK, EXTRA = os.environ["R19_OUT"], os.environ.get("R19_PARK") == "1", float(os.environ.get("R19_EXTRA", "120"))
reg = {"park": PARK, "carga_inicio": os.getloadavg(), "fondo": 0, "manual": 0, "flushes": [], "errores_escritura": [], "pruebas": {}}

_start, _iter, _cycle = live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once
_flush, _seq = live.LiveRuntime.flush_persistence, live.LiveRuntime._sequenced


async def start(self):
    await _start(self)
    if PARK and self._task is not None and not self._task.done():
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass


async def loop_iteration(self):
    self._r19_fondo = True
    try:
        await _iter(self)
    finally:
        self._r19_fondo = False


async def cycle_once(self):
    reg["fondo" if getattr(self, "_r19_fondo", False) else "manual"] += 1
    return await _cycle(self)


async def flush(self, *, timeout_seconds=10.0):
    pendientes = sum(1 for t in self._persist_tasks if not t.done())
    t0 = time.monotonic()
    ok = await _flush(self, timeout_seconds=timeout_seconds)
    rec = {"pendientes": pendientes, "seg": round(time.monotonic() - t0, 3), "ok": ok}
    if not ok:
        foto = [t for t in self._persist_tasks if not t.done()]
        t1 = time.monotonic()
        hechas, no = await asyncio.wait(foto, timeout=EXTRA) if foto else (set(), set())
        rec.update({"foto_al_vencer": len(foto), "terminaron_despues": len(hechas), "no_terminaron": len(no),
                    "seg_hasta_terminar": round(time.monotonic() - t1, 3)})
    reg["flushes"].append(rec)
    return ok


async def sequenced(self, write):
    try:
        await _seq(self, write)
    except Exception as exc:
        reg["errores_escritura"].append(f"{type(exc).__name__}: {str(exc)[:120]}")
        raise


live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once = start, loop_iteration, cycle_once
live.LiveRuntime.flush_persistence, live.LiveRuntime._sequenced = flush, sequenced


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        reg["pruebas"][report.nodeid.split("::")[-1]] = {"resultado": report.outcome, "seg": round(report.duration, 2)}


def pytest_sessionfinish(session, exitstatus):
    reg["carga_fin"] = os.getloadavg()
    reg["exit"] = int(exitstatus)
    with open(OUT, "w") as f:
        json.dump(reg, f, indent=1)
