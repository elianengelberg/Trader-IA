"""Registrador pasivo de la cola de persistencia (plugin de pytest) para la corrida SUPLEMENTARIA de R19. No decide nada.

Cubre lo que la sonda congelada v2 no registra (B.2 de la misión): escrituras programadas, terminadas y pendientes; la
evolución de la cola en el tiempo (una muestra cada RC_INTERVALO s, tomada en los ciclos); la duración de cada vaciado y
de stop(); si stop() dejó la persistencia completa (persistence_flushed); resultado y mensaje de cada prueba.
No espera, no reintenta, no cambia plazos: solo cuenta. Única intervención opcional, la misma que el control del plan
(RC_PARK=1): cancela el bucle de fondo que start() lanza.
Salida: JSON en $RC_OUT."""
import asyncio
import json
import os
import time

import tia.runtime.live as live

OUT = os.environ["RC_OUT"]
PARK = os.environ.get("RC_PARK") == "1"
INTERVALO = float(os.environ.get("RC_INTERVALO", "0.25"))
T0 = time.monotonic()
c = {"programadas": 0, "terminadas": 0, "fallidas": 0, "ciclos_fondo": 0, "ciclos_manuales": 0}
reg = {"park": PARK, "intervalo_s": INTERVALO, "muestras": [], "vaciados": [], "stops": [], "pruebas": {}}
_actual = {"prueba": None, "ultima": -1.0}
_start, _iter, _cycle = live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once
_flush, _seq, _stop = live.LiveRuntime.flush_persistence, live.LiveRuntime._sequenced, live.LiveRuntime.stop


def _ahora():
    return round(time.monotonic() - T0, 3)


def _muestra(motivo):
    reg["muestras"].append([_ahora(), _actual["prueba"], motivo, c["programadas"], c["terminadas"],
                            c["programadas"] - c["terminadas"], c["ciclos_fondo"], c["ciclos_manuales"]])


async def start(self):
    await _start(self)
    t = getattr(self, "_task", None)
    if PARK and t is not None and not t.done():
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


async def loop_iteration(self):
    self._rc_fondo = True
    try:
        await _iter(self)
    finally:
        self._rc_fondo = False


async def cycle_once(self):
    c["ciclos_fondo" if getattr(self, "_rc_fondo", False) else "ciclos_manuales"] += 1
    if time.monotonic() - _actual["ultima"] >= INTERVALO:
        _actual["ultima"] = time.monotonic()
        _muestra("ciclo")
    return await _cycle(self)


def sequenced(self, write):
    c["programadas"] += 1

    async def correr():
        try:
            await _seq(self, write)
        except Exception:
            c["fallidas"] += 1
            raise
        finally:
            c["terminadas"] += 1
    return correr()


async def flush(self, *, timeout_seconds=10.0):
    _muestra("vaciado_inicio")
    t = time.monotonic()
    ok = await _flush(self, timeout_seconds=timeout_seconds)
    reg["vaciados"].append({"prueba": _actual["prueba"], "inicio_s": round(t - T0, 3), "seg": round(time.monotonic() - t, 3),
                            "ok": ok, "plazo_s": timeout_seconds})
    _muestra("vaciado_fin")
    return ok


async def stop(self, *args, **kwargs):
    t = time.monotonic()
    try:
        return await _stop(self, *args, **kwargs)
    finally:
        reg["stops"].append({"prueba": _actual["prueba"], "seg": round(time.monotonic() - t, 3),
                             "persistencia_completa": getattr(self, "persistence_flushed", None)})
        _muestra("stop_fin")


live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once = start, loop_iteration, cycle_once
live.LiveRuntime._sequenced, live.LiveRuntime.flush_persistence, live.LiveRuntime.stop = sequenced, flush, stop


def pytest_runtest_setup(item):
    _actual["prueba"] = item.nodeid


def pytest_runtest_logreport(report):
    d = reg["pruebas"].setdefault(report.nodeid, {"resultado": "passed"})
    if report.when == "call":
        d["seg"] = round(report.duration, 2)
    if report.outcome == "failed":
        d["resultado"] = "failed" if report.when == "call" else "error"
        crash = getattr(report.longrepr, "reprcrash", None)
        d["mensaje"] = (crash.message if crash is not None else str(report.longrepr))[:500]


def pytest_sessionfinish(session, exitstatus):
    _muestra("fin")
    reg["contadores"] = dict(c)
    reg["exit"] = int(exitstatus)
    with open(OUT, "w") as f:
        json.dump(reg, f)
