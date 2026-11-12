"""DESCRIPTIVO (posterior, no cambia ninguna clasificación): IC90 por bootstrap de bloques de 60 fechas para ΔR²_OOS,
a partir de los pronósticos guardados. Uso: python -B descriptivo_ic.py <pronosticos_y_exposiciones.json> <salida.json>"""
import json, sys
import numpy as np
d = json.load(open(sys.argv[1]))
def ic(pares, B=2000, bloque=60, semilla=20261019):
    por = {}
    for k, (y, ya, yb_or) in pares.items():
        pass
    return None
out = {}
rng = np.random.default_rng(20261019)
def boot(pares):
    # pares: "fecha|activo" -> [y, yb, ya]
    fechas = sorted({k.split("|")[0] for k in pares})
    pos = {f: i for i, f in enumerate(fechas)}
    eb = np.zeros(len(fechas)); ea = np.zeros(len(fechas))
    for k, (y, yb, ya) in pares.items():
        i = pos[k.split("|")[0]]
        eb[i] += (y - yb) ** 2; ea[i] += (y - ya) ** 2
    n = len(fechas); k = int(np.ceil(n / 60)); res = []
    for _ in range(2000):
        ini = rng.integers(0, n, k)
        idx = ((ini[:, None] + np.arange(60)[None, :]).ravel()[:n]) % n
        res.append(1 - ea[idx].sum() / eb[idx].sum())
    return {"delta_R2_oos": float(1 - ea.sum() / eb.sum()), "ic90_bootstrap_bloques60": [float(np.percentile(res, 5)), float(np.percentile(res, 95))]}
for k, pares in d["A"].items():
    out[f"E2-A {k}"] = boot(pares)
out["E2-C"] = boot(d["C"])
json.dump(out, open(sys.argv[2], "w"), indent=1)
for k, v in out.items():
    print(f"{k:24s} ΔR²={v['delta_R2_oos']:+.4f}  IC90 [{v['ic90_bootstrap_bloques60'][0]:+.4f}, {v['ic90_bootstrap_bloques60'][1]:+.4f}]")
