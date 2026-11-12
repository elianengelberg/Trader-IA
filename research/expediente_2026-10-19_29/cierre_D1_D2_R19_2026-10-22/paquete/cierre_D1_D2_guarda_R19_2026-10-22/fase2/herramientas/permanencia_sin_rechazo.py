"""Mide la permanencia máxima vista en la venue con stop por tiempo, con y sin el primer cierre rechazado (solo mide)."""
import sys, pathlib
raiz = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(raiz / "packages/tia/src")); sys.path.insert(0, str(raiz / "tests/integration"))
import test_engine_version_contract as g
class MP:
    def setattr(self, o, n, v): setattr(o, n, v)
def perm(r):
    best, opened = 0, None
    for look in r.looks:
        if look.held != 0.0 and opened is None: opened = look.bar
        elif look.held == 0.0: opened = None
        if opened is not None: best = max(best, look.bar - opened)
    return best
for rech in (False, True):
    r = g._run(MP(), reject_first_close=rech, max_holding_bars=g.TIME_STOP_BARS)
    print(f"primer cierre rechazado={rech}: permanencia máxima en la venue = {perm(r)} barras (TIME_STOP_BARS={g.TIME_STOP_BARS})")
