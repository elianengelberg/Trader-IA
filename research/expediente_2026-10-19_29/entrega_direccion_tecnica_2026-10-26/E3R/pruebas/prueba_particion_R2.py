"""Prueba de la partición de la Adenda R2 (ejecutar_E3R.particionar) con arreglos sintéticos. Sin datos reales."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
import ejecutar_E3R as o  # noqa: E402

universo, motor, inferencia = o.importar_congelados(o.E3_DEFECTO)
D = 400
syms = ["AAAUSDT", "BBBUSDT", "AAAUPUSDT", "CCCUSDT"]
O = np.full((4, D), 10.0)
O[0, 200:] = 0.01          # AAA: corte en 195..199 y reanuda en 200 a ×0,001
O[2, 200:] = 1000.0        # AAAUP: apalancado con salto: no se parte
O[3, 200:] = 50.0          # CCC: salto ×5: no se parte
C, QV = O.copy(), np.full((4, D), 2e6)
act = np.ones((4, D), dtype=bool)
act[:, 195:200] = False
reanuda = (universo.INICIO + dt.timedelta(days=200)).isoformat()
saltos = [{"simbolo": s, "reanuda": reanuda, "ratio_precio": r} for s, r in
          (("AAAUSDT", 0.001), ("AAAUPUSDT", 100.0), ("CCCUSDT", 5.0), ("ZZZUSDT", 100.0))]
P, part = o.particionar(syms, O, C, QV, act, saltos, universo)
assert [p["simbolo"] for p in part] == ["AAAUSDT"], part
nuevo = P.sym.index(part[0]["nuevo"])
assert P.S == 5 and part[0]["nuevo"] == "R2X0AAAUSDT"
assert not P.act[0, 200:].any() and P.act[0, :195].all()                 # tramo viejo termina en el último día activo
assert not P.act[nuevo, :200].any() and P.act[nuevo, 200:].all()         # tramo nuevo empieza en la reanudación
assert np.isnan(P.C[0, 200:]).all() and np.isnan(P.C[nuevo, :200]).all()
assert P.ep_ini[nuevo, 250] == 200                                       # edad desde cero
assert P.ep_ini[0, 194] == 0 and P.inact_run[0, 230] == 36               # viejo: inactividad crece → liquidación a los 30
assert P.pval(0, 260) == 10.0                                            # valuación al último precio del activo viejo
assert P.act[2, 200:].all() and P.act[3, 200:].all()                     # no partidos
assert not P.apalancado[nuevo] and P.apalancado[2]                       # el prefijo no crea apalancados
assert np.allclose(O[0, 200:], 0.01) and act[0, 200:].all()              # los arreglos de entrada no se modifican
print("particion R2: OK", part)
