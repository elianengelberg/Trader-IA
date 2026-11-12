"""Métricas DESCRIPTIVAS de una manga o cartera. Ninguna decide: la decisión es la prueba primaria (inferencia.py) y la
regla de decision.py. Se informan siempre todas, incluidas las desfavorables."""
from __future__ import annotations

import math
from itertools import pairwise
from typing import Sequence


def resumen(valores: Sequence[float], exposicion: Sequence[float], operaciones: Sequence[dict],
            periodos_por_ano: float, subperiodos: int = 4, exceso: Sequence[float] | None = None) -> dict:
    if len(valores) < 2:
        raise ValueError("hacen falta al menos dos valores")
    r = [b / a - 1.0 for a, b in pairwise(valores)]
    n = len(r)
    anos = n / periodos_por_ano
    total = valores[-1] / valores[0] - 1.0
    media = sum(r) / n
    var = sum((v - media) ** 2 for v in r) / (n - 1) if n > 1 else 0.0
    vol = math.sqrt(var * periodos_por_ano)
    pico, mdd = valores[0], 0.0
    for v in valores:
        pico = max(pico, v)
        mdd = min(mdd, v / pico - 1.0)
    rotacion = sum(abs(b - a) for a, b in pairwise([0.0, *exposicion])) / anos if anos > 0 else math.nan
    ganadoras = sum(1 for o in operaciones if o["pnl"] > 0)
    out = {"periodos": n, "anos": anos, "rendimiento_total": total,
           "rendimiento_anual_compuesto": (1 + total) ** (1 / anos) - 1 if anos > 0 and total > -1 else math.nan,
           "volatilidad_anual": vol, "sharpe_descriptivo_rf0": (media * periodos_por_ano) / vol if vol > 0 else math.nan,
           "maxima_caida": mdd, "exposicion_media": sum(exposicion) / len(exposicion) if exposicion else 0.0,
           "rotacion_anual": rotacion, "operaciones": len(operaciones),
           "tasa_acierto": ganadoras / len(operaciones) if operaciones else math.nan}
    if exceso is not None and subperiodos > 0 and len(exceso) >= subperiodos:
        tam = len(exceso) // subperiodos
        medias = [sum(exceso[i * tam:(i + 1) * tam]) / tam for i in range(subperiodos)]
        out["estabilidad"] = {"medias_exceso_por_subperiodo": medias,
                              "subperiodos_con_exceso_positivo": sum(1 for m in medias if m > 0),
                              "subperiodos": subperiodos}
    return out
