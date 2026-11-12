"""E3 · inferencia exactamente según la v3 §5 (Newey–West para H1; bootstrap-t por bloques circulares bajo H₀ para H2/H3)."""
import math

import numpy as np

from statistics import NormalDist

_N = NormalDist()


def newey_west(x: np.ndarray, L: int = 4) -> dict:
    """v3 §5.1 / N11: γ̂_h = (1/n) Σ_{t>h} (x_t − x̄)(x_{t−h} − x̄); Bartlett 1 − h/(L+1); sin preblanqueo."""
    x = np.asarray(x, dtype=float)
    n = x.size
    m = x.mean()
    d = x - m
    lrv = d @ d / n
    for h in range(1, L + 1):
        lrv += 2.0 * (1.0 - h / (L + 1)) * (d[h:] @ d[:-h]) / n
    ee = math.sqrt(max(lrv, 0.0) / n)
    z = m / ee if ee > 0 else float("nan")
    return {"n": n, "media": m, "ee": ee, "z": z, "p_unilateral": 1.0 - _N.cdf(z),
            "ic90": (m - 1.6448536269514722 * ee, m + 1.6448536269514722 * ee), "L": L}


def _medias_bloque_circulares(x: np.ndarray, ell: int) -> np.ndarray:
    n = x.size
    ext = np.concatenate([x, x[:ell - 1]])
    c = np.concatenate([[0.0], np.cumsum(ext)])
    return (c[ell:ell + n] - c[:n]) / ell


def bootstrap_t(e: np.ndarray, ell: int = 13, B: int = 9999, semilla: int = 20261020, rng=None, devolver_T=False) -> dict:
    """v3 §5.2: T = √n·ē/σ̂_C; réplicas de ẽ = e − ē con k = ⌈n/ℓ⌉ bloques completos; σ̂*² con divisor k − 1;
    T* = √(kℓ)·ē*/σ̂*; p = (1 + #{T* ≥ T})/(B + 1); IC percentil-t por estadísticos de orden."""
    e = np.asarray(e, dtype=float)
    n = e.size
    k = -(-n // ell)
    nstar = k * ell
    eb = e.mean()
    bm = _medias_bloque_circulares(e, ell)
    sig_c = math.sqrt(ell / n * np.sum((bm - eb) ** 2))
    T = math.sqrt(n) * eb / sig_c
    bm0 = bm - eb                                      # medias de bloque de la serie centrada (centrar desplaza cada media en ē)
    rng = rng if rng is not None else np.random.default_rng(semilla)
    inicios = rng.integers(0, n, size=(B, k))
    M = bm0[inicios]                                   # (B, k): medias de los k bloques remuestreados
    estr = M.mean(axis=1)                              # ē* (bloques de igual tamaño)
    sstr = np.sqrt(ell / (k - 1) * np.sum((M - estr[:, None]) ** 2, axis=1))
    Tstar = math.sqrt(nstar) * estr / sstr
    p = (1 + int(np.sum(Tstar >= T))) / (B + 1)
    srt = np.sort(Tstar)
    se = sig_c / math.sqrt(n)

    def q(orden):  # orden 1-based
        return srt[orden - 1]

    o95, o05, o975, o025 = math.ceil(0.95 * (B + 1)), math.floor(0.05 * (B + 1)), math.ceil(0.975 * (B + 1)), math.floor(0.025 * (B + 1))
    res = {"n": n, "ell": ell, "k": k, "B": B, "media": eb, "sigma_C": sig_c, "T": T, "p_unilateral": p,
           "ic90": (eb - q(o95) * se, eb - q(o05) * se), "ic95": (eb - q(o975) * se, eb - q(o025) * se),
           "ordenes": {"q95": o95, "q05": o05, "q975": o975, "q025": o025}}
    if devolver_T:
        res["Tstar"] = Tstar
    return res


def holm_dos(p1: float, p2: float, alfa: float = 0.05) -> dict:
    """v3 §3.2: Holm m = 2 sobre {H1, H2}."""
    ps = {"H1": p1, "H2": p2}
    orden = sorted(ps, key=lambda h: ps[h])
    rech = {"H1": False, "H2": False}
    if ps[orden[0]] <= alfa / 2:
        rech[orden[0]] = True
        if ps[orden[1]] <= alfa:
            rech[orden[1]] = True
    return {"p": ps, "orden": orden, "umbrales": {orden[0]: alfa / 2, orden[1]: alfa}, "rechaza": rech}
