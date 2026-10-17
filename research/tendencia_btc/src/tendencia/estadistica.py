"""Inferencia que respeta la dependencia temporal: bootstrap circular por bloques (reutiliza el de H-CARRY Next) para
medias de diferencias diarias y para diferencias de Sharpe; nulo de timing por desplazamiento circular."""

from __future__ import annotations

import math
import random
import statistics as st

from hcarry.lab.estadistica import bootstrap_media  # noqa: F401  (reutilizado tal cual)


def bootstrap_sharpe(a: list[float], b: list[float], bloque: int = 20, n: int = 2000, semilla: int = 20261017) -> dict:
    """P(Sharpe(a) − Sharpe(b) > 0) remuestreando bloques PAREADOS de días."""
    if len(a) != len(b):
        raise ValueError("series de distinta longitud")
    rng = random.Random(semilla)
    m = len(a)

    def sh(x: list[float]) -> float:
        s = st.pstdev(x)
        return st.fmean(x) / s * math.sqrt(365) if s else 0.0

    difs = []
    for _ in range(n):
        ia: list[int] = []
        while len(ia) < m:
            ini = rng.randrange(m)
            ia += [(ini + j) % m for j in range(bloque)]
        ia = ia[:m]
        difs.append(sh([a[i] for i in ia]) - sh([b[i] for i in ia]))
    return {"dif_sharpe": sh(a) - sh(b), "p_mayor_que_cero": sum(d > 0 for d in difs) / n, "bloque": bloque,
            "remuestreos": n, "semilla": semilla}


def desplazamientos(n_total: int, n: int = 1000, minimo: int = 30, semilla: int = 20261017) -> list[int]:
    rng = random.Random(semilla)
    return [rng.randrange(minimo, n_total - minimo) for _ in range(n)]
