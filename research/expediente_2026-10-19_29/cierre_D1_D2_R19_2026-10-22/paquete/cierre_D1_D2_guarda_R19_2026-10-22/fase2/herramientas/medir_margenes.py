"""Mide (solo mide) los márgenes de la guarda en un árbol: racha máxima sin cobertura, permanencia máxima con stop
temporal, movimientos de stop, cierres rechazados y expirados, etc. Uso: python medir_margenes.py <árbol>"""
import sys, pathlib, json
raiz = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(raiz / "packages/tia/src")); sys.path.insert(0, str(raiz / "tests/integration"))
import pytest
import test_engine_version_contract as g

class MP:
    def __init__(self): self._undo = []
    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name))); setattr(obj, name, value)
    def undo(self):
        for obj, name, value in reversed(self._undo): setattr(obj, name, value)

def racha(record):
    best = streak = 0
    for look in record.looks:
        if look.held != 0.0 and not any(g._protects(look.held, w) for w in look.working): streak += 1; best = max(best, streak)
        else: streak = 0
    return best

def permanencia(record):
    best, opened = 0, None
    for look in record.looks:
        if look.held != 0.0 and opened is None: opened = look.bar
        elif look.held == 0.0: opened = None
        if opened is not None: best = max(best, look.bar - opened)
    return best

ESC = {"rechazo_primer_cierre": dict(reject_first_close=True, max_holding_bars=g.TIME_STOP_BARS),
       "calmo": {}, "parciales": dict(partial=0.9),
       "ioc": dict(closes_are_ioc=True, partial=0.9, max_holding_bars=g.TIME_STOP_BARS),
       "todo_junto": dict(reject_first_close=True, reject=0.3, partial=0.6, entry_order_type="limit", max_holding_bars=g.TIME_STOP_BARS)}
out = {}
for n, kw in ESC.items():
    mp = MP()
    try:
        r = g._run(mp, **kw)
    except BaseException as e:
        out[n] = {"error": type(e).__name__ + ": " + str(e)[:200]}; mp.undo(); continue
    mp.undo()
    moved, wrong = g.stop_moves(r)
    out[n] = {"posiciones": max((f.episode for f in r.fills), default=0), "enviadas": len(r.sent),
              "cierres_enviados": sum(1 for s in r.sent if s.reduce_only and s.order_type is g.OrderType.MARKET),
              "cierres_rechazados": r.closes_rejected, "cierres_expirados_con_posicion": r.closes_expired_with_position,
              "racha_max_sin_cobertura": racha(r), "permanencia_max_barras": permanencia(r), "stops_movidos": moved, "stops_mal": len(wrong),
              "muertas_reenviadas": len(g.dead_orders_sent_again(r)), "crece_tras_cierre": len(g.growth_after_close(r)),
              "entrada_en_posicion_posterior": len(g.entries_filling_a_later_position(r)), "cierres_sin_reduce_only": len(g.closes_without_reduce_only(r))}
print(json.dumps(out, indent=1, ensure_ascii=False))
