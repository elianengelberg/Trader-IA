"""Sonda R19 v2 (plugin de pytest). Mide; no cambia el resultado de ninguna prueba.

Cambios frente a v1 (enmienda 1 de PLAN_R19, registrada antes de correr):
  - nombra la prueba de cada medición y guarda, para cada prueba que falla, el mensaje de la excepción y el informe;
  - en cada vaciado (flush_persistence): quién lo pidió, plazo, escrituras pendientes por tipo, si el bucle de fondo
    estaba vivo, carga del sistema y ciclos de fondo durante la espera;
  - la espera extra para distinguir «lenta» de «trabada» se hace SOLO cuando el vaciado lo pidió `settle()` de la prueba,
    cuyo resultado se afirma de inmediato: la prueba ya falló y esperar no cambia nada de lo que sigue. Los vaciados que
    pide `stop()` se registran sin esperar más, porque esperar ahí sí cambiaría lo que la prueba ve después;
  - si en la espera extra quedan escrituras sin terminar, se detiene el bucle de fondo y se espera otro plazo. Lo que se
    mide ahí es PROGRESO: cuántas escrituras de la foto terminan en cada ventana y cuál es la cabeza de la cola (la más
    antigua sin terminar, con su tipo y su pila). Una cola que sigue drenando es lenta; una que no completa ninguna
    escritura en la ventana final, sin productor, está trabada. (Validación previa: con el bucle activo la foto puede
    tener miles de reconciliaciones del propio bucle que drenan bien; «no terminó todo en 120 s» no prueba nada.);
  - clasifica cada excepción de escritura como inyectada por la prueba (el `persister` de las pruebas lanza
    `RuntimeError("database unavailable during <tipo>")`) o no inyectada.

Única intervención, opcional y solo como CONTROL (R19_PARK=1): cancela el bucle de fondo que start() lanza, como hace
_drive_by_hand en el parche 03, para comparar con y sin productor concurrente."""
import asyncio
import collections
import json
import os
import sys
import time

import tia.runtime.live as live

OUT = os.environ["R19_OUT"]
PARK = os.environ.get("R19_PARK") == "1"
EXTRA = float(os.environ.get("R19_EXTRA", "120"))
EXTRA2 = float(os.environ.get("R19_EXTRA2", "60"))
INYECTADA = "database unavailable during "

reg = {"version_sonda": 2, "park": PARK, "cpus": os.cpu_count(), "carga_inicio": os.getloadavg(), "fondo": 0,
       "manual": 0, "flushes": [], "errores_escritura": [], "pruebas": {}, "por_prueba": {}}
_actual = {"prueba": None}
_orden = {"n": 0}

_start, _iter, _cycle = live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once
_flush, _seq = live.LiveRuntime.flush_persistence, live.LiveRuntime._sequenced


def _cuenta(clave):
    reg[clave] += 1
    p = _actual["prueba"]
    if p is not None:
        reg["por_prueba"].setdefault(p, {"fondo": 0, "manual": 0})[clave] += 1


def _bucle_vivo(runtime):
    t = getattr(runtime, "_task", None)
    return t is not None and not t.done()


def _tipos(tareas):
    return dict(collections.Counter(getattr(t, "_r19_tipo", "sin_empezar") for t in tareas))


def _cabeza(tareas):
    """La escritura más antigua sin terminar (las escrituras corren de a una, en orden: si esta no avanza, nada avanza)."""
    empezadas = [t for t in tareas if hasattr(t, "_r19_n")]
    if not empezadas:
        return None
    t = min(empezadas, key=lambda x: x._r19_n)
    pila, c = [], t.get_coro()
    while c is not None and len(pila) < 12:  # la cadena de await: dónde está parada de verdad
        f = getattr(c, "cr_frame", None) or getattr(c, "gi_frame", None)
        if f is not None:
            pila.append(f"{f.f_code.co_filename.rsplit('/', 1)[-1]}:{f.f_lineno} {f.f_code.co_name}")
        c = getattr(c, "cr_await", None) or getattr(c, "gi_yieldfrom", None)
    return {"n": t._r19_n, "tipo": t._r19_tipo, "pila": pila}


async def start(self):
    await _start(self)
    if PARK and _bucle_vivo(self):
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
    _cuenta("fondo" if getattr(self, "_r19_fondo", False) else "manual")
    return await _cycle(self)


async def flush(self, *, timeout_seconds=10.0):
    llamador = sys._getframe(1).f_code.co_name
    pend = [t for t in self._persist_tasks if not t.done()]
    rec = {"prueba": _actual["prueba"], "llamador": llamador, "plazo_s": timeout_seconds, "pendientes": len(pend),
           "pendientes_por_tipo": _tipos(pend), "bucle_vivo": _bucle_vivo(self), "carga1": round(os.getloadavg()[0], 2)}
    t0, c0 = time.monotonic(), reg["fondo"]
    ok = await _flush(self, timeout_seconds=timeout_seconds)
    rec.update({"seg": round(time.monotonic() - t0, 3), "ok": ok, "ciclos_fondo_durante": reg["fondo"] - c0})
    if not ok:
        foto = [t for t in self._persist_tasks if not t.done()]
        rec.update({"foto_al_vencer": len(foto), "foto_por_tipo": _tipos(foto), "bucle_vivo_al_vencer": _bucle_vivo(self),
                    "carga1_al_vencer": round(os.getloadavg()[0], 2)})
        if llamador == "settle":
            t1, c1 = time.monotonic(), reg["fondo"]
            hechas, no = await asyncio.wait(foto, timeout=EXTRA) if foto else (set(), set())
            rec.update({"terminaron_despues": len(hechas), "no_terminaron": len(no),
                        "seg_hasta_terminar": round(time.monotonic() - t1, 3), "ciclos_fondo_en_espera": reg["fondo"] - c1,
                        "cabeza_tras_espera": _cabeza(no)})
            if no:
                detenido = False
                if _bucle_vivo(self):
                    self._task.cancel()
                    try:
                        await self._task
                    except BaseException:
                        pass
                    detenido = True
                h2, n2 = await asyncio.wait(no, timeout=EXTRA2)
                rec.update({"productor_detenido": detenido, "terminaron_sin_productor": len(h2),
                            "no_terminaron_sin_productor": len(n2), "tipos_sin_terminar": _tipos(n2),
                            "cabeza_final": _cabeza(n2)})
        else:
            rec["espera_extra"] = "omitida: no la pidió settle(); esperar cambiaría lo que la prueba ve después"
    reg["flushes"].append(rec)
    return ok


async def sequenced(self, write):
    tarea = asyncio.current_task()
    frame = getattr(write, "cr_frame", None)
    tipo = frame.f_locals.get("kind") if frame is not None else None
    if tarea is not None:
        _orden["n"] += 1
        tarea._r19_tipo, tarea._r19_n = tipo or "?", _orden["n"]
    try:
        await _seq(self, write)
    except Exception as exc:
        texto = str(exc)
        reg["errores_escritura"].append({"prueba": _actual["prueba"], "tipo": tipo, "excepcion": type(exc).__name__,
                                         "mensaje": texto[:200],
                                         "inyectada": isinstance(exc, RuntimeError) and texto.startswith(INYECTADA)})
        raise


live.LiveRuntime.start, live.LiveRuntime._loop_iteration, live.LiveRuntime._cycle_once = start, loop_iteration, cycle_once
live.LiveRuntime.flush_persistence, live.LiveRuntime._sequenced = flush, sequenced


def pytest_runtest_setup(item):
    _actual["prueba"] = item.nodeid


def pytest_runtest_logreport(report):
    d = reg["pruebas"].setdefault(report.nodeid, {"resultado": "passed", "fases": {}})
    d["fases"][report.when] = report.outcome
    if report.when == "call":
        d["seg"] = round(report.duration, 2)
    if report.outcome == "failed":
        d["resultado"] = "failed" if report.when == "call" else "error"
        crash = getattr(report.longrepr, "reprcrash", None)
        d.setdefault("mensajes", []).append(f"{report.when}: " + (crash.message if crash is not None else str(report.longrepr))[:1000])
        d.setdefault("informes", []).append(report.longreprtext[-4000:])
    elif report.outcome == "skipped" and d["resultado"] == "passed":
        d["resultado"] = "skipped"


def pytest_sessionfinish(session, exitstatus):
    reg["carga_fin"] = os.getloadavg()
    reg["exit"] = int(exitstatus)
    with open(OUT, "w") as f:
        json.dump(reg, f, indent=1, default=str)
