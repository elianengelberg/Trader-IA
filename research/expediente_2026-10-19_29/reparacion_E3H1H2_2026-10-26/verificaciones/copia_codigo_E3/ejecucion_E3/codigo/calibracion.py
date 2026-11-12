"""E3 · calibración sintética (v3 §5.3; N9–N10). No usa datos reales.

Uso: python -I calibracion.py <salida.json>
"""
import json
import sys
import time

import numpy as np

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from inferencia import bootstrap_t, newey_west

N, SIMS, BCAL, SD = 340, 1000, 1999, 0.05
BANDA05, BANDA025 = (0.036, 0.064), (0.015, 0.035)


def t_est(rng, gl, size):
    return rng.standard_t(gl, size=size) / np.sqrt(gl / (gl - 2))


def g1(rng):
    return SD * t_est(rng, 3, N)


def g2(rng, phi=0.2, burn=500):
    u = SD * np.sqrt(1 - phi ** 2) * t_est(rng, 3, N + burn)
    x = np.empty(N + burn)
    x[0] = u[0]
    for i in range(1, N + burn):
        x[i] = phi * x[i - 1] + u[i]
    return x[burn:]


def g3(rng, a=0.10, b=0.85, burn=500):
    w = SD ** 2 * (1 - a - b)
    z = t_est(rng, 4, N + burn)
    x = np.empty(N + burn)
    s2 = SD ** 2
    for i in range(N + burn):
        x[i] = np.sqrt(s2) * z[i]
        s2 = w + a * x[i] ** 2 + b * s2
    return x[burn:]


def g4(rng):
    m = rng.random(N) < 0.9
    return np.where(m, rng.normal(-0.006, 0.035, N), rng.normal(0.054, 0.10, N))


def g5(rng):
    return -g4(rng)


def h1_proceso(rng, phi=0.1, sd=0.14, burn=500):
    u = rng.normal(0, sd * np.sqrt(1 - phi ** 2), N + burn)
    x = np.empty(N + burn)
    x[0] = u[0]
    for i in range(1, N + burn):
        x[i] = phi * x[i - 1] + u[i]
    return x[burn:]


def main(salida):
    rng = np.random.default_rng(20261023)
    t0 = time.time()
    res = {"n": N, "simulaciones": SIMS, "B": BCAL, "semilla": 20261023, "bandas": {"0.05": BANDA05, "0.025": BANDA025}, "H2_H3": {}, "H1": {}}
    mu30 = 0.30 / 52
    for nombre, g in (("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4), ("G5", g5)):
        for ell in (13,):
            p_nulo, p_alt = [], []
            for _ in range(SIMS):
                x = g(rng)
                p_nulo.append(bootstrap_t(x, ell=ell, B=BCAL, rng=rng)["p_unilateral"])
                p_alt.append(bootstrap_t(x + mu30, ell=ell, B=BCAL, rng=rng)["p_unilateral"])
            p_nulo, p_alt = np.array(p_nulo), np.array(p_alt)
            r05, r025 = float(np.mean(p_nulo <= 0.05)), float(np.mean(p_nulo <= 0.025))
            res["H2_H3"][f"{nombre}_ell{ell}"] = {
                "rechazo_005": r05, "rechazo_0025": r025,
                "dentro_banda_005": BANDA05[0] <= r05 <= BANDA05[1], "dentro_banda_0025": BANDA025[0] <= r025 <= BANDA025[1],
                "sobre_rechaza": r05 > BANDA05[1] or r025 > BANDA025[1],
                "potencia_mu30_005": float(np.mean(p_alt <= 0.05)), "potencia_mu30_0025": float(np.mean(p_alt <= 0.025))}
            print(nombre, ell, res["H2_H3"][f"{nombre}_ell{ell}"], f"{time.time() - t0:.0f}s", flush=True)
    for L in (4,):
        p = np.array([newey_west(h1_proceso(rng), L)["p_unilateral"] for _ in range(SIMS)])
        r05, r025 = float(np.mean(p <= 0.05)), float(np.mean(p <= 0.025))
        res["H1"][f"L{L}"] = {"rechazo_005": r05, "rechazo_0025": r025, "dentro_banda_005": BANDA05[0] <= r05 <= BANDA05[1],
                              "dentro_banda_0025": BANDA025[0] <= r025 <= BANDA025[1], "sobre_rechaza": r05 > BANDA05[1] or r025 > BANDA025[1]}
        print("H1", L, res["H1"][f"L{L}"], flush=True)
    sobre = [k for k, v in res["H2_H3"].items() if v["sobre_rechaza"]]
    res["decision"] = {"H2_H3": "ell=13 aceptado" if not sobre else f"sobre-rechazo en {sobre}: corresponde repetir con ell=26 (v3 §5.3)",
                       "H1": "L=4 aceptado" if not res["H1"]["L4"]["sobre_rechaza"] else "sobre-rechazo: corresponde L=8 (v3 §5.3)"}
    if sobre:  # v3 §5.3: repetir con ℓ = 26 solo si hay sobre-rechazo
        for nombre, g in (("G1", g1), ("G2", g2), ("G3", g3), ("G4", g4), ("G5", g5)):
            p_nulo = np.array([bootstrap_t(g(rng), ell=26, B=BCAL, rng=rng)["p_unilateral"] for _ in range(SIMS)])
            r05, r025 = float(np.mean(p_nulo <= 0.05)), float(np.mean(p_nulo <= 0.025))
            res["H2_H3"][f"{nombre}_ell26"] = {"rechazo_005": r05, "rechazo_0025": r025, "sobre_rechaza": r05 > BANDA05[1] or r025 > BANDA025[1]}
            print(nombre, 26, res["H2_H3"][f"{nombre}_ell26"], flush=True)
    if res["H1"]["L4"]["sobre_rechaza"]:
        p = np.array([newey_west(h1_proceso(rng), 8)["p_unilateral"] for _ in range(SIMS)])
        res["H1"]["L8"] = {"rechazo_005": float(np.mean(p <= 0.05)), "rechazo_0025": float(np.mean(p <= 0.025))}
    res["segundos"] = round(time.time() - t0, 1)
    with open(salida, "w") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
