"""Prueba primaria del MEC v0.2 (§4), en Python estándar, escrita desde las fórmulas del documento (no copiada de la
implementación de E3, con la que se contrasta en las pruebas).

- ``bootstrap_t``: T = √n·x̄/σ̂_C, con σ̂²_C = (ℓ/n)·Σᵢ (B̄ᵢ − x̄)² sobre las n medias de bloques circulares de longitud ℓ.
  Réplicas de x̃ = x − x̄ con k = ⌈n/ℓ⌉ bloques completos: ē*, σ̂*² = ℓ/(k−1)·Σⱼ (B̄*ⱼ − ē*)², T* = √(kℓ)·ē*/σ̂*.
  Valor p unilateral p = (1 + #{T* ≥ T}) / (B + 1). Intervalos percentil-t duales por estadísticos de orden.
- ``newey_west``: prueba t con error estándar HAC (núcleo de Bartlett, L retardos, sin preblanqueo).
- ``respaldo``: regla del MEC §4.7, p = máx(p_ℓ20, p_ℓ40, p_NW) e intervalo envolvente. Si un componente es un valor p
  válido, el máximo también lo es (P(máx ≤ u) ≤ u).

Una serie constante no tiene prueba: ``ErrorSerieDegenerada``. La capa de decisión la trata como INVÁLIDA.
Estas funciones no deciden nada; ``decision.py`` aplica los niveles del MEC §7."""
from __future__ import annotations

import math
import random
from fractions import Fraction
from statistics import NormalDist
from typing import Sequence

_N = NormalDist()


class ErrorSerieDegenerada(ValueError):
    """La serie no tiene variabilidad: el estadístico no está definido."""


def medias_bloques_circulares(x: Sequence[float], ell: int) -> list[float]:
    """B̄ᵢ = media de x_i, …, x_{i+ℓ−1} (índices módulo n), para i = 0 … n−1."""
    n = len(x)
    if not 1 <= ell <= n:
        raise ValueError(f"ℓ = {ell} fuera de [1, n = {n}]")
    ext = list(x) + list(x[: ell - 1])
    acum = [0.0]
    for v in ext:
        acum.append(acum[-1] + v)
    return [(acum[i + ell] - acum[i]) / ell for i in range(n)]


def _orden(q: Fraction, b: int, hacia_arriba: bool) -> int:
    """Estadístico de orden (1..B) del cuantil q con la convención (B + 1), en aritmética EXACTA: en coma flotante
    (1 − 0,90)/2 = 0,04999… y el suelo caería un orden más abajo (defecto hallado por el contraste con E3)."""
    o = math.ceil(q * (b + 1)) if hacia_arriba else math.floor(q * (b + 1))
    return min(max(o, 1), b)


def bootstrap_t(x: Sequence[float], ell: int = 20, b: int = 9999, semilla: int = 20261101,
                inicios: Sequence[Sequence[int]] | None = None) -> dict:
    """MEC §4. ``inicios`` (B × k índices de inicio de bloque) permite reproducir exactamente un sorteo externo."""
    x = [float(v) for v in x]
    n = len(x)
    if n < 2 * ell:
        raise ValueError(f"n = {n} < 2ℓ = {2 * ell}: muy pocos datos para bloques de ℓ = {ell}")
    k = -(-n // ell)
    nstar = k * ell
    media = sum(x) / n
    bm = medias_bloques_circulares(x, ell)
    sig_c = math.sqrt(ell / n * sum((m - media) ** 2 for m in bm))
    if sig_c == 0.0:
        raise ErrorSerieDegenerada("σ̂_C = 0: serie constante")
    t_obs = math.sqrt(n) * media / sig_c
    bm0 = [m - media for m in bm]  # medias de bloque de la serie centrada bajo H₀
    if inicios is None:
        rng = random.Random(semilla)
        inicios = [[rng.randrange(n) for _ in range(k)] for _ in range(b)]
    elif len(inicios) != b or any(len(f) != k for f in inicios):
        raise ValueError("inicios debe ser una matriz B × k")
    tstar = []
    for fila in inicios:
        bloques = [bm0[i] for i in fila]
        e = sum(bloques) / k
        s2 = ell / (k - 1) * sum((v - e) ** 2 for v in bloques)
        if s2 > 0:
            tstar.append(math.sqrt(nstar) * e / math.sqrt(s2))
        else:  # todos los bloques iguales: el signo decide (no ocurre con datos continuos y k ≥ 2)
            tstar.append(math.copysign(math.inf, e) if e != 0 else 0.0)
    p = (1 + sum(1 for t in tstar if t >= t_obs)) / (b + 1)
    srt = sorted(tstar)
    se = sig_c / math.sqrt(n)

    def ic(nivel: Fraction) -> tuple[float, float]:
        a = (1 - nivel) / 2
        alto, bajo = srt[_orden(1 - a, b, True) - 1], srt[_orden(a, b, False) - 1]
        return media - alto * se, media - bajo * se

    return {"metodo": "bootstrap-t por bloques circulares (MEC v0.2 §4)", "n": n, "ell": ell, "k": k, "B": b,
            "media": media, "sigma_C": sig_c, "T": t_obs, "p_unilateral": p, "ic90": ic(Fraction(90, 100)),
            "ic95": ic(Fraction(95, 100)),
            "semilla": semilla if inicios is None else None}


def newey_west(x: Sequence[float], retardos: int = 20) -> dict:
    """Prueba t de μ ≤ 0 con varianza de largo plazo de Newey–West (Bartlett 1 − h/(L+1), autocovarianzas con 1/n)."""
    x = [float(v) for v in x]
    n = len(x)
    if n <= retardos + 1:
        raise ValueError(f"n = {n} ≤ L + 1 = {retardos + 1}")
    media = sum(x) / n
    d = [v - media for v in x]
    lrv = sum(v * v for v in d) / n
    for h in range(1, retardos + 1):
        lrv += 2.0 * (1.0 - h / (retardos + 1)) * sum(d[t] * d[t - h] for t in range(h, n)) / n
    if lrv <= 0.0:
        raise ErrorSerieDegenerada("varianza de largo plazo ≤ 0")
    ee = math.sqrt(lrv / n)
    z = media / ee
    z90, z95 = _N.inv_cdf(0.95), _N.inv_cdf(0.975)
    return {"metodo": f"t con error estándar Newey–West (Bartlett, L = {retardos})", "n": n, "media": media, "ee": ee,
            "z": z, "p_unilateral": 1.0 - _N.cdf(z), "ic90": (media - z90 * ee, media + z90 * ee),
            "ic95": (media - z95 * ee, media + z95 * ee), "L": retardos}


def respaldo(x: Sequence[float], b: int = 9999, semilla: int = 20261101) -> dict:
    """MEC §4.7: máx de tres valores p (ℓ = 20, ℓ = 40, Newey–West L = 20) e intervalos envolventes."""
    componentes = {"bootstrap_t_l20": bootstrap_t(x, 20, b, semilla), "bootstrap_t_l40": bootstrap_t(x, 40, b, semilla),
                   "newey_west_L20": newey_west(x, 20)}
    p = max(c["p_unilateral"] for c in componentes.values())

    def envolvente(clave: str) -> tuple[float, float]:
        return (min(c[clave][0] for c in componentes.values()), max(c[clave][1] for c in componentes.values()))

    return {"metodo": "regla de respaldo (MEC v0.2 §4.7)", "p_unilateral": p, "ic90": envolvente("ic90"),
            "ic95": envolvente("ic95"), "media": componentes["newey_west_L20"]["media"], "componentes": componentes}
