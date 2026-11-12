"""Cálculo PREVIO a la ejecución (no usa ninguna réplica de la calibración): probabilidad de que una prueba con tamaño
EXACTO (α real = nominal) incumpla el criterio congelado del MEC §5 solo por error de Monte Carlo.

Con R réplicas, la celda incumple si #{p ≤ 0,025} > ⌊0,032·R⌋ o #{p ≤ 0,05} > ⌊0,0597·R⌋. Bajo tamaño exacto,
(#≤0,025, #(0,025;0,05]) ~ Multinomial(R; 0,025, 0,025). Se calcula de forma exacta y se agrega sobre 24 celdas
(6 procesos × 4 tamaños) suponiendo independencia entre celdas (las semillas son distintas por celda)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def _lbinom(n: int, k: int, p: float) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log1p(-p)


def main(parametros: Path) -> dict:
    par = json.loads(parametros.read_bytes())
    r = par["replicas"]
    celdas = len(par["procesos"]) * len(par["tamanos"])
    hi25, hi5 = par["bandas"]["0.025"][1], par["bandas"]["0.05"][1]
    k25 = max(k for k in range(r + 1) if k / r <= hi25)  # mayor conteo que cumple, con la misma comparación del script
    k5 = max(k for k in range(r + 1) if k / r <= hi5)
    # P(cumple) = Σ_{a ≤ k25} P(A = a) · P(a + C ≤ k5 | A = a), C | A = a ~ Bin(R − a, 0,025/0,975)
    q = 0.025 / 0.975
    cumple = 0.0
    for a in range(k25 + 1):
        pa = math.exp(_lbinom(r, a, 0.025))
        pc = sum(math.exp(_lbinom(r - a, c, q)) for c in range(max(0, k5 - a) + 1))
        cumple += pa * pc
    solo25 = 1 - sum(math.exp(_lbinom(r, a, 0.025)) for a in range(k25 + 1))
    solo5 = 1 - sum(math.exp(_lbinom(r, a, 0.05)) for a in range(k5 + 1))
    out = {"replicas": r, "celdas_por_regla": celdas, "conteo_max_que_cumple_2.5": k25, "conteo_max_que_cumple_5": k5,
           "p_incumple_celda_solo_2.5": solo25, "p_incumple_celda_solo_5": solo5,
           "p_incumple_celda_alguno": 1 - cumple,
           "p_regla_incumple_con_tamano_exacto": 1 - cumple ** celdas,
           "p_ambas_reglas_incumplen_si_independientes": (1 - cumple ** celdas) ** 2}
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), ensure_ascii=False, indent=1))
