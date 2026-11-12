"""Valor informativo de cada camino bajo priors escépticos explícitos. Sin datos: solo potencias documentadas.
- π: probabilidad previa de que el mecanismo exista con el tamaño que la prueba detecta (0,10 y 0,25).
- P(respaldo) = π·potencia + (1 − π)·α; VPP = π·potencia / P(respaldo).
- E3-H1: potencias de PROTOCOLO_E3_v3 §7.2 (IC 0,02: 0,56–0,79; IC 0,03: 0,88–0,99, umbral 0,025). Refutación según
  E3 («IC90 superior < 0,01») con EE de IC̄ entre 0,007 y 0,0095 (v3 §7.1): P(refutar | IC = 0) = Φ(0,01/EE − 1,645).
- Económicas prospectivas: potencia de la prueba z con 5 miradas en 5 años (H1_potencia_y_delta.json), menos 5 puntos
  (lo peor medido por SEC-1.0)."""
import json
from statistics import NormalDist

N = NormalDist()
ALFA = 0.025
caminos = {
    "E3-H1 información, IC real 0,02 (histórico)": (0.56, 0.79),
    "E3-H1 información, IC real 0,03 (histórico)": (0.88, 0.99),
    "Económica prospectiva 5 años, IR 0,35": (0.12 - 0.05, 0.12),
    "Económica prospectiva 5 años, IR 0,5": (0.20 - 0.05, 0.20),
    "Económica prospectiva 5 años, IR 1,0": (0.60 - 0.05, 0.60),
}
out = {"filas": [], "refutacion_E3_H1_si_IC_0": {}}
for nombre, (lo, hi) in caminos.items():
    for pi in (0.10, 0.25):
        for pw in (lo, hi):
            p = pi * pw + (1 - pi) * ALFA
            out["filas"].append({"camino": nombre, "pi": pi, "potencia": round(pw, 3), "P_respaldo": round(p, 3),
                                 "VPP": round(pi * pw / p, 3)})
for ee in (0.007, 0.0095):
    out["refutacion_E3_H1_si_IC_0"][str(ee)] = round(N.cdf(0.01 / ee - 1.645), 3)
print(json.dumps(out, ensure_ascii=False, indent=1))
