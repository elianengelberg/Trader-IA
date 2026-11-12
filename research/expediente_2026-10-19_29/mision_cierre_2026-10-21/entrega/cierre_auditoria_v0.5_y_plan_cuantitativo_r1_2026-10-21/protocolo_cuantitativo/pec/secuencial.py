"""Diseño secuencial de grupo para la fase prospectiva (MEC v0.2 §7.1): gasto de α de Lan–DeMets tipo O'Brien–Fleming,
unilateral, con miradas en fracciones de información t₁ < … < t_K = 1.

Modelo canónico: S_k = Z_k·√t_k es un movimiento browniano con deriva θ (θ = 0 bajo H₀) e incrementos independientes.
Las fronteras c_k se obtienen por integración numérica recursiva (Armitage, McPherson y Rowe, 1969) para que la
probabilidad de cruzar por primera vez en la mirada k sea α(t_k) − α(t_{k−1}), con
    α(t) = 2 − 2·Φ(z_{1−α/2} / √t)          (α(1) = α).
También se calcula la potencia de esas fronteras bajo una deriva θ y el factor de inflación del tamaño máximo frente
al diseño de una sola mirada. Supuesto declarado (MEC §7.1): incrementos aproximadamente independientes."""
from __future__ import annotations

import math
from itertools import pairwise
from statistics import NormalDist
from typing import Sequence

_N = NormalDist()
_PASO = 0.02      # paso de la malla en la escala z
_LIMITE = 8.5     # la malla cubre z ∈ [−_LIMITE, c_k]


def gasto_obf(t: float, alfa: float) -> float:
    """α(t) acumulado de Lan–DeMets tipo O'Brien–Fleming (unilateral, nivel total α)."""
    if t <= 0:
        return 0.0
    return 2.0 - 2.0 * _N.cdf(_N.inv_cdf(1.0 - alfa / 2.0) / math.sqrt(t))


def _malla(sup_z: float, t: float) -> tuple[list[float], list[float]]:
    """Nodos en la escala S = z·√t y pesos de Simpson (número impar de nodos)."""
    m = max(2, math.ceil((sup_z + _LIMITE) / _PASO))
    m += m % 2
    h = (sup_z + _LIMITE) / m
    nodos = [(-_LIMITE + i * h) * math.sqrt(t) for i in range(m + 1)]
    hs = h * math.sqrt(t)
    pesos = [hs / 3 * (1 if i in (0, m) else (4 if i % 2 else 2)) for i in range(m + 1)]
    return nodos, pesos


def _recorrer(t: Sequence[float], theta: float, fronteras: Sequence[float] | None, alfa: float | None
              ) -> tuple[list[float], list[float]]:
    """Si ``fronteras`` es None las calcula con el gasto OBF de nivel ``alfa`` (bajo θ = 0); si no, las usa.
    Devuelve (fronteras, probabilidad de cruzar por primera vez en cada mirada bajo θ)."""
    t = [float(v) for v in t]
    if not t or any(b <= a for a, b in pairwise(t)) or t[0] <= 0 or abs(t[-1] - 1.0) > 1e-12:
        raise ValueError("las fracciones de información deben crecer estrictamente y terminar en 1")
    c: list[float] = []
    cruces: list[float] = []
    nodos: list[float] = []
    dens: list[float] = []
    pesos: list[float] = []
    previo = 0.0
    for k, tk in enumerate(t):
        inc = tk - (t[k - 1] if k else 0.0)
        sd = math.sqrt(inc)

        def cruce(ck: float, k: int = k, tk: float = tk, inc: float = inc, sd: float = sd,
                  malla: tuple = (nodos, dens, pesos)) -> float:
            u = ck * math.sqrt(tk)
            if k == 0:
                return 1.0 - _N.cdf((u - theta * tk) / math.sqrt(tk))
            return sum(w * f * (1.0 - _N.cdf((u - s - theta * inc) / sd)) for s, f, w in zip(*malla, strict=True))

        if fronteras is None:
            objetivo = gasto_obf(tk, alfa) - gasto_obf(t[k - 1], alfa) if k else gasto_obf(tk, alfa)
            a, b = 0.0, 12.0
            for _ in range(70):  # bisección: cruce() decrece en c
                mid = (a + b) / 2
                a, b = (mid, b) if cruce(mid) > objetivo else (a, mid)
            ck = (a + b) / 2
        else:
            ck = float(fronteras[k])
        c.append(ck)
        cruces.append(cruce(ck))
        # densidad de S_k en la región de continuación (S_k < c_k·√t_k)
        nuevos, w_nuevos = _malla(ck, tk)
        if k == 0:
            nueva = [_N.pdf((u - theta * tk) / math.sqrt(tk)) / math.sqrt(tk) for u in nuevos]
        else:
            nueva = [sum(w * f * _N.pdf((u - s - theta * inc) / sd) for s, f, w in zip(nodos, dens, pesos, strict=True)) / sd
                     for u in nuevos]
        nodos, dens, pesos = nuevos, nueva, w_nuevos
        previo = tk
    del previo
    return c, cruces


def fronteras_obf(t: Sequence[float], alfa: float = 0.025) -> dict:
    """Fronteras z unilaterales c_1 … c_K y el α gastado en cada mirada (bajo H₀)."""
    c, cruces = _recorrer(t, 0.0, None, alfa)
    return {"t": list(t), "alfa": alfa, "fronteras_z": c, "alfa_por_mirada": cruces,
            "alfa_acumulado": [sum(cruces[: i + 1]) for i in range(len(cruces))],
            "gasto_objetivo": [gasto_obf(v, alfa) for v in t]}


def potencia(t: Sequence[float], fronteras: Sequence[float], theta: float) -> float:
    """P(cruzar alguna frontera) bajo una deriva θ (θ = (μ/σ)·√n_max en la escala de información completa)."""
    return sum(_recorrer(t, theta, fronteras, None)[1])


def inflacion(t: Sequence[float], alfa: float = 0.025, beta: float = 0.20) -> dict:
    """Deriva θ que da potencia 1 − β con las fronteras OBF, y R = (θ / θ_fijo)² con θ_fijo = z_{1−α} + z_{1−β}:
    el tamaño máximo es R veces el de una sola mirada."""
    c = fronteras_obf(t, alfa)["fronteras_z"]
    a, b = 0.0, 10.0
    for _ in range(60):
        mid = (a + b) / 2
        a, b = (mid, b) if potencia(t, c, mid) < 1 - beta else (a, mid)
    theta = (a + b) / 2
    fijo = _N.inv_cdf(1 - alfa) + _N.inv_cdf(1 - beta)
    return {"theta": theta, "theta_una_mirada": fijo, "R": (theta / fijo) ** 2, "fronteras_z": c}
