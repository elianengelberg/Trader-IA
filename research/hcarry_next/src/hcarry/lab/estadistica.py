"""Comparación estadística de estrategias sobre los MISMOS datos: bootstrap circular por bloques de las diferencias
diarias de rendimiento (estrategia − referencia). Bloques largos porque el funding y la base son persistentes."""

from __future__ import annotations

import random

from hcarry.metricas import percentil_rango_cercano, rendimientos_diarios
from hcarry.model.motor import Resultado


def diferencias_diarias(a: Resultado, b: Resultado) -> list[float]:
    ra, rb = dict(rendimientos_diarios(a)), dict(rendimientos_diarios(b))
    comunes = sorted(set(ra) & set(rb))
    if len(comunes) < max(len(ra), len(rb)) * 0.95:
        raise ValueError("las dos series no cubren los mismos días")
    return [ra[d] - rb[d] for d in comunes]


def bootstrap_media(x: list[float], bloque: int = 30, n: int = 2000, semilla: int = 20261016,
                    nivel: float = 0.90) -> dict:
    """Intervalo de la media diaria por bootstrap circular de bloques; P(media > 0) = fracción de remuestreos > 0."""
    if len(x) < 2 * bloque:
        return {"aplicable": False, "motivo": f"{len(x)} días < 2 bloques de {bloque}"}
    rng = random.Random(semilla)
    m = len(x)
    medias = []
    for _ in range(n):
        tot, k = 0.0, 0
        while k < m:
            ini = rng.randrange(m)
            for j in range(min(bloque, m - k)):
                tot += x[(ini + j) % m]
            k += bloque
        medias.append(tot / m)
    a = (1 - nivel) / 2
    return {"aplicable": True, "dias": m, "media_diaria": sum(x) / m, "media_anual": sum(x) / m * 365,
            "intervalo_anual": [percentil_rango_cercano(medias, a) * 365, percentil_rango_cercano(medias, 1 - a) * 365],
            "p_mayor_que_cero": sum(1 for v in medias if v > 0) / n, "bloque": bloque, "remuestreos": n,
            "semilla": semilla, "nivel": nivel}


def comparar(estrategia: Resultado, referencia: Resultado, **kw) -> dict:
    return bootstrap_media(diferencias_diarias(estrategia, referencia), **kw)
