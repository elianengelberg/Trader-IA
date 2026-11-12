"""E3 · calibración COMPLEMENTARIA de la regla prerregistrada p = máx(p_boot13, p_boot26, p_NW13) (v3 §5.3).

Solo datos sintéticos (procesos G1–G5 de la v3 §5.3 y N10). Los tres valores p se calculan sobre la MISMA serie, para medir
el tamaño de la regla del máximo. No usa datos reales ni cambia ninguna decisión ya registrada.
Semilla 20261028 (distinta de la calibración original, que se conserva intacta). 2000 simulaciones por proceso.

Uso: python -I calibracion_max.py <salida.json>
"""
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibracion import g1, g2, g3, g4, g5  # noqa: E402
from inferencia import bootstrap_t, newey_west  # noqa: E402

SIMS, BCAL = 2000, 1999
MU30 = 0.30 / 52


def tres_p(x, rng):
    p13 = bootstrap_t(x, ell=13, B=BCAL, rng=rng)["p_unilateral"]
    p26 = bootstrap_t(x, ell=26, B=BCAL, rng=rng)["p_unilateral"]
    pnw = newey_west(x, 13)["p_unilateral"]
    return p13, p26, pnw


def main(salida):
    rng = np.random.default_rng(20261028)
    res = {"simulaciones": SIMS, "B": BCAL, "semilla": 20261028, "ee_monte_carlo_005": math.sqrt(0.05 * 0.95 / SIMS),
           "ee_monte_carlo_0025": math.sqrt(0.025 * 0.975 / SIMS), "procesos": {}}
    t0 = time.time()
    for nombre, g in (("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4), ("G5", g5)):
        nulo, alt = [], []
        for _ in range(SIMS):
            x = g(rng)
            nulo.append(tres_p(x, rng))
            alt.append(tres_p(x + MU30, rng))
        nulo, alt = np.array(nulo), np.array(alt)
        pmax_n, pmax_a = nulo.max(axis=1), alt.max(axis=1)
        fila = {}
        for etiqueta, col in (("boot13", 0), ("boot26", 1), ("NW13", 2)):
            fila[etiqueta] = {"rechazo_005": float(np.mean(nulo[:, col] <= 0.05)), "rechazo_0025": float(np.mean(nulo[:, col] <= 0.025)),
                              "potencia_mu30_005": float(np.mean(alt[:, col] <= 0.05)), "potencia_mu30_0025": float(np.mean(alt[:, col] <= 0.025))}
        fila["maximo"] = {"rechazo_005": float(np.mean(pmax_n <= 0.05)), "rechazo_0025": float(np.mean(pmax_n <= 0.025)),
                          "potencia_mu30_005": float(np.mean(pmax_a <= 0.05)), "potencia_mu30_0025": float(np.mean(pmax_a <= 0.025))}
        res["procesos"][nombre] = fila
        print(nombre, json.dumps(fila), f"{time.time() - t0:.0f}s", flush=True)
    res["segundos"] = round(time.time() - t0, 1)
    with open(salida, "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
