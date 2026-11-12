"""E4 v1 · α real de la prueba con más simulaciones (vectorizado; mismo t de Newey-West que nucleo.newey_west), con los límites
normales (`limites`, como la v0) y con los calibrados (`limites_nw`, v1). Semilla distinta de la de la calibración.
Series de IC SINTÉTICAS bajo el nulo. Uso: python -I -B alfa_preciso.py <salida.json>"""
import json, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "codigo"))
import numpy as np
import nucleo as N
import secuencial as SQ

def nw_t(X, L=N.NW_REZAGOS):
    n = X.shape[1]; mu = X.mean(1); e = X - mu[:, None]
    s = (e * e).sum(1) / n
    for k in range(1, L + 1):
        s += 2 * (1 - k / (L + 1)) * (e[:, k:] * e[:, :-k]).sum(1) / n
    return mu / np.sqrt(s / n)

def series(m, n, phi, colas, g):
    E = g.standard_t(5, (m, n)) / math.sqrt(5 / 3) if colas else g.standard_normal((m, n))
    X = np.empty((m, n)); X[:, 0] = E[:, 0]; c = math.sqrt(1 - phi * phi)
    for i in range(1, n):
        X[:, i] = phi * X[:, i - 1] + c * E[:, i]
    return X

L = {"normales_v0": (SQ.limites(365, 730, 730), SQ.z(0.975)), "calibrados_v1": (SQ.limites_nw(365, 730, 730), SQ.limites_nw(None, 365, 365)[1])}
out = {k: {"b1": v[0][0], "b2": v[0][1], "una_mirada_365": v[1]} for k, v in L.items()}
g = np.random.default_rng(2026)
for nombre, phi, colas in (("normal_iid", 0.0, False), ("t5_ar0.1", 0.1, True), ("t5_ar0.2", 0.2, True)):
    tot = {k: {"sup": 0, "inf": 0, "sup_una_mirada_365": 0} for k in L}; M = 0
    for _ in range(10):
        X = series(10000, 730, phi, colas, g); M += 10000
        t1, t2 = nw_t(X[:, :365]), nw_t(X)
        for k, ((b1, b2), c) in L.items():
            tot[k]["sup"] += int(((t1 >= b1) | ((t1 < b1) & (t1 > -b1) & (t2 >= b2))).sum())
            tot[k]["inf"] += int(((t1 <= -b1) | ((t1 < b1) & (t1 > -b1) & (t2 <= -b2))).sum())
            tot[k]["sup_una_mirada_365"] += int((t1 >= c).sum())
    for k in L:
        out[k][nombre] = {kk: v / M for kk, v in tot[k].items()} | {"sims": M}
        print(k, nombre, out[k][nombre], flush=True)
out["ee_mc"] = math.sqrt(0.025 * 0.975 / M)
json.dump(out, open(sys.argv[1], "w"), indent=1)
