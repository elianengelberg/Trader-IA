"""Tiempo estimado de la ejecución real con un panel SINTÉTICO del tamaño real (≈ 760 símbolos × 3257 días). Sin datos reales."""
import datetime as dt
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ejecutar_E3R as o  # noqa: E402

universo, motor, inferencia = o.importar_congelados(o.E3_DEFECTO)
rng = np.random.default_rng(1)
S, D = 760, 3257
lr = rng.normal(0, 0.03, D) + rng.normal(0, 0.04, (S, D))
C = 10 * np.exp(np.cumsum(lr, axis=1))
O = np.concatenate([C[:, :1], C[:, :-1]], axis=1)
QV = np.exp(rng.normal(np.log(3e6), 1.2, (S, D)))
act = np.ones((S, D), dtype=bool)
for s in range(S):
    act[s, :int(rng.integers(0, 2800))] = False
C, O, QV = (np.where(act, x, np.nan) for x in (C, O, QV))
t0 = time.time()
P = universo.Panel([f"S{i:03d}USDT" for i in range(S)], O, C, QV, act)
print("panel", round(time.time() - t0, 1), "s")
F = universo.lunes(dt.date(2021, 2, 22), dt.date(2026, 5, 25))
t0 = time.time()
val, cache = o.validez_previa(P, F, universo, motor)
print("validez_previa", round(time.time() - t0, 1), "s", {k: val[k] for k in ("evaluables", "invariancia_ok")})
t0 = time.time()
motor.simular(P, F, motor.Config(), cache)
print("simular base (con cache)", round(time.time() - t0, 2), "s")
t0 = time.time()
for b in range(5):
    x = motor.simular(P, F, motor.Config(objetivo="aleatorio", mult_costo=0.0, semilla_aleatoria=b), cache)
print("réplica R5", round((time.time() - t0) / 5, 3), "s")
t0 = time.time()
e = np.random.default_rng(2).normal(0, 0.05, 270)
o.intervalos(e, inferencia)
print("intervalos H2", round(time.time() - t0, 2), "s")
t0 = time.time()
inferencia.bootstrap_t(e, ell=13, B=999, semilla=o.SEMILLA_DIAG)
print("diag B=999", round(time.time() - t0, 3), "s")
