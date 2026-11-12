"""Plugin de pytest (solo medición, no cambia comportamiento): registra por cada flush_persistence
el número de escrituras pendientes al entrar, la duración y el resultado; y por cada escritura
secuenciada, su espera en la cola y su duración propia. Escribe JSON en $SONDA_SALIDA."""
import json, os, time, asyncio
import tia.runtime.live as live

_reg = {"flush": [], "writes": []}
_orig_flush = live.LiveRuntime.flush_persistence
_orig_seq = live.LiveRuntime._sequenced
_orig_save = live.LiveRuntime._save

def _save(self, kind, payload):
    self._sonda_kind = kind
    return _orig_save(self, kind, payload)

def _sequenced(self, write):
    # se llama de forma síncrona dentro de _save: el tipo se captura en ese momento
    return _medido(self, write, getattr(self, "_sonda_kind", "?"))

async def _medido(self, write, kind):
    t0 = time.perf_counter()
    async with self._persist_lock:
        t1 = time.perf_counter()
        await write
        t2 = time.perf_counter()
    _reg["writes"].append((kind, t1 - t0, t2 - t1))

async def flush(self, *, timeout_seconds=10.0):
    pend = sum(1 for t in self._persist_tasks if not t.done())
    t0 = time.perf_counter()
    ok = await _orig_flush(self, timeout_seconds=timeout_seconds)
    _reg["flush"].append({"pendientes": pend, "seg": round(time.perf_counter() - t0, 3), "ok": ok,
                          "quedan": sum(1 for t in self._persist_tasks if not t.done())})
    return ok

live.LiveRuntime.flush_persistence = flush
live.LiveRuntime._sequenced = _sequenced
live.LiveRuntime._save = _save

def pytest_sessionfinish(session, exitstatus):
    w = _reg["writes"]
    por_tipo = {}
    for k, _q, d in w:
        e = por_tipo.setdefault(k, [0, 0.0]); e[0] += 1; e[1] += d
    res = {"exit": int(exitstatus), "flushes": _reg["flush"], "escrituras": len(w),
           "seg_escritura_total": round(sum(d for _k, _q, d in w), 3),
           "por_tipo": {k: {"n": n, "seg": round(s, 3), "ms_media": round(1000 * s / n, 2)} for k, (n, s) in sorted(por_tipo.items())}}
    with open(os.environ["SONDA_SALIDA"], "w") as f:
        json.dump(res, f, indent=1)
