"""Métricas de una serie diaria de equity (cierre a cierre; el primer día, desde el capital inicial)."""

from __future__ import annotations

import itertools
import math
import statistics as st

from tendencia.backtest import Resultado


def rendimientos(r: Resultado) -> list[float]:
    e = [r.capital, *r.equity]
    return [b / a - 1 for a, b in itertools.pairwise(e)]


def caida(eq: list[float]) -> tuple[float, int]:
    pico, peor, dur, peor_dur = eq[0], 0.0, 0, 0
    for x in eq:
        if x >= pico:
            pico, dur = x, 0
        else:
            dur += 1
            peor = max(peor, 1 - x / pico)
            peor_dur = max(peor_dur, dur)
    return peor, peor_dur


def calcular(r: Resultado) -> dict:
    rd = rendimientos(r)
    n = len(rd)
    anos = n / 365
    final = r.equity[-1]
    m, s = st.fmean(rd), st.stdev(rd)
    neg = [x for x in rd if x < 0]
    dd, dd_dur = caida([r.capital, *r.equity])
    cagr = (final / r.capital) ** (1 / anos) - 1
    eq_medio = st.fmean(r.equity)
    por_ano: dict[str, list[float]] = {}
    for d, x in zip(r.dias, rd, strict=True):
        por_ano.setdefault(d[:4], []).append(x)
    return {"dias": n, "final": final, "rendimiento_total": final / r.capital - 1, "cagr": cagr,
            "vol_anual": s * math.sqrt(365), "sharpe": m / s * math.sqrt(365) if s else None,
            "sortino": (m * 365) / (math.sqrt(sum(x * x for x in neg) / n) * math.sqrt(365)) if neg else None,
            "caida_maxima": dd, "caida_duracion_dias": dd_dur, "calmar": cagr / dd if dd else None,
            "exposicion_media": st.fmean(r.exposicion), "tiempo_en_mercado": sum(x > 1e-9 for x in r.exposicion) / n,
            "operaciones": len(r.operaciones), "costes": r.costes, "costes_pp_anual": r.costes / r.capital / anos * 100,
            "rotacion_anual": r.negociado / eq_medio / anos, "peor_dia": min(rd),
            "por_ano": {a: math.prod(1 + x for x in v) - 1 for a, v in por_ano.items()}}
