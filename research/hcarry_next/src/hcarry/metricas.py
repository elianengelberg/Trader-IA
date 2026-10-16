"""Métricas de rendimiento y riesgo, y el clasificador D1–D4 de H-CARRY rev. 5 (criterios congelados).

Definiciones (todas sobre el capital TOTAL salvo que se diga lo contrario):
  - dias: fijos, (n − 1)/24 (rev. 5). CAGR = (final/capital)^(365/dias) − 1.
  - caída máxima: sobre [capital, equity de cada cierre horario, equity final tras salir] (D4 de rev. 5).
  - rendimientos diarios: equity a las 00:00 UTC de cada día (y el final); volatilidad y Sharpe anualizados con 365.
  - capital comprometido: equity desplegado en las dos patas (spot + equity de futuros) cuando hay posición.
    Rentabilidad sobre capital comprometido = PnL neto / (capital comprometido · años), una medida de eficiencia que
    NO sustituye a la rentabilidad sobre el capital total.
  - rotación: nocional negociado (ambas patas) / equity medio / años."""

from __future__ import annotations

import itertools
import math

from hcarry.conventions import DIA_MS, HORA_MS
from hcarry.model.motor import Resultado

UMBRALES_REV5 = {"D1_cagr_max_descarte": 0.06, "D1_banda_no_concluyente": 0.07, "D3_bps": 50.0, "D4_caida": 0.10}
COMPARADOR_ANUAL = 0.05


def percentil_rango_cercano(valores: list[float], p: float) -> float | None:
    """Percentil por rango más cercano (rev. 5): el valor de orden ceil(p·n)."""
    if not valores:
        return None
    v = sorted(valores)
    return v[max(1, math.ceil(p * len(v))) - 1]


def caida_maxima(serie: list[float]) -> float:
    pico, peor = -math.inf, 0.0
    for e in serie:
        pico = max(pico, e)
        if pico > 0:
            peor = max(peor, 1 - e / pico)
    return peor


def diarios(r: Resultado) -> list[tuple[int, float]]:
    """(día, equity a las 00:00 UTC) de la serie, con el capital al inicio y el final al cierre."""
    puntos = [(r.inicio, r.capital)] + [(t, e) for t, e, *_ in r.serie if t % DIA_MS == 0]
    fin_t = r.inicio + (r.n_barras - 1) * HORA_MS
    if puntos[-1][0] != fin_t:
        puntos.append((fin_t, r.final))
    else:
        puntos[-1] = (fin_t, r.final)
    return puntos


def rendimientos_diarios(r: Resultado) -> list[tuple[int, float]]:
    p = diarios(r)
    return [(b[0], b[1] / a[1] - 1) for a, b in itertools.pairwise(p) if a[1] > 0]


def calcular(r: Resultado) -> dict:
    dias = r.dias
    anos = dias / 365 if dias > 0 else float("nan")
    neto = r.final - r.capital
    cagr = (r.final / r.capital) ** (365 / dias) - 1 if dias > 0 and r.final > 0 else float("nan")
    serie_e = [r.capital] + [s[1] for s in r.serie] + [r.final]
    dd = caida_maxima(serie_e)
    rd = [x for _, x in rendimientos_diarios(r)]
    vol = sharpe = None
    if len(rd) > 2:
        m = sum(rd) / len(rd)
        sd = math.sqrt(sum((x - m) ** 2 for x in rd) / (len(rd) - 1))
        vol = sd * math.sqrt(365)
        sharpe = (m / sd * math.sqrt(365)) if sd > 0 else None
    horas = len(r.serie)
    en_pos = [s for s in r.serie if s[5] > 0]
    comprometido_h = sum(s[7] for s in r.serie)
    utilizacion = (sum(s[7] / s[1] for s in r.serie if s[1] > 0) / horas) if horas else 0.0
    capital_anos = comprometido_h / (24 * 365)
    nocional = sum(o["cantidad"] * (o["S"] + o["F"]) for o in r.operaciones if o["tipo"] != "venta_spot_descubierto")
    equity_medio = sum(s[1] for s in r.serie) / horas if horas else r.capital
    ops = [o for o in r.operaciones if o.get("base_adversa") is not None]
    bases = [o["base_adversa"] * 1e4 for o in ops]
    p95 = percentil_rango_cercano(bases, 0.95)
    tipos: dict[str, int] = {}
    for o in r.operaciones:
        tipos[o["tipo"]] = tipos.get(o["tipo"], 0) + 1
    duraciones = _duraciones(r)
    comp = r.capital * (1 + COMPARADOR_ANUAL) ** (dias / 365) if dias > 0 else r.capital
    cobrado = sum(f["importe"] for f in r.funding if f["importe"] > 0)
    pagado = -sum(f["importe"] for f in r.funding if f["importe"] < 0)
    m = {
        "origen": r.origen, "sintetico": r.origen.startswith("sintetico"), "estado": r.estado,
        "politica": r.politica, "parametros_politica": r.parametros_politica,
        "dias": dias, "capital": r.capital, "final": r.final, "pnl_neto": neto,
        "rendimiento_neto": neto / r.capital, "cagr_neto": cagr,
        "pnl_bruto": neto + r.costes_total, "costes": r.costes_total,
        "funding_neto": r.funding_total, "funding_cobrado": cobrado, "funding_pagado": pagado,
        "pnl_precio_patas": neto - r.funding_total + r.costes_total,
        "caida_maxima": dd, "vol_anual": vol, "sharpe": sharpe,
        "calmar": (cagr / dd) if dd > 0 and not math.isnan(cagr) else None,
        "tiempo_en_mercado": len(en_pos) / horas if horas else 0.0,
        "utilizacion_media": utilizacion,
        "rent_capital_comprometido": (neto / capital_anos) if capital_anos > 0 else None,
        "rotacion_anual": (nocional / equity_medio / anos) if anos and anos > 0 else None,
        "operaciones": tipos, "n_operaciones": len(r.operaciones),
        "entradas": tipos.get("apertura", 0), "duracion_media_h": (sum(duraciones) / len(duraciones)) if duraciones else None,
        "rechazos": len(r.rechazos), "liquidaciones": len(r.liquidaciones),
        "distancia_min_liquidacion": r.distancia_min_liquidacion[0] if r.distancia_min_liquidacion else None,
        "base_adversa_p95_bps": p95, "base_adversa_max_bps": max(bases) if bases else None,
        "comparador_5": {"final": comp, "exceso_final": r.final - comp},
        "por_ano": _por_ano(r),
    }
    m["rev5"] = clasificar_rev5(m)
    return m


def _duraciones(r: Resultado) -> list[int]:
    dur, inicio = [], None
    for o in r.operaciones:
        if o["tipo"] == "apertura":
            inicio = o["t"]
        elif inicio is not None and o["lotes_despues"] == 0:
            dur.append((o["t"] - inicio) // HORA_MS)
            inicio = None
    for liq in r.liquidaciones:
        if inicio is not None and liq["t"] >= inicio:
            dur.append((liq["t"] - inicio) // HORA_MS)
            inicio = None
    return dur


def _por_ano(r: Resultado) -> dict[str, float]:
    """Rendimiento por año natural UTC (el primero y el último pueden ser parciales). Un punto de las 00:00 del 1 de
    enero cierra el año anterior."""
    import datetime as dt
    p = diarios(r)
    fin: dict[int, float] = {}
    for t, e in p[1:]:
        fin[dt.datetime.fromtimestamp((t - 1) / 1000, tz=dt.UTC).year] = e
    salida, base = {}, r.capital
    for ano in sorted(fin):
        salida[str(ano)] = fin[ano] / base - 1 if base > 0 else float("nan")
        base = fin[ano]
    return salida


def clasificar_rev5(m: dict) -> dict:
    """Criterios D1–D4 de rev. 5 (umbrales congelados) y su precedencia. Solo informa: no es una decisión nueva."""
    u = UMBRALES_REV5
    d1 = math.isnan(m["cagr_neto"]) or m["cagr_neto"] <= u["D1_cagr_max_descarte"]
    d2 = m["liquidaciones"] > 0
    d3 = m["base_adversa_p95_bps"] is not None and m["base_adversa_p95_bps"] > u["D3_bps"]
    d4 = m["caida_maxima"] > u["D4_caida"]
    activos = [k for k, v in (("D1", d1), ("D2", d2), ("D3", d3), ("D4", d4)) if v]
    if m["estado"] == "detenida_E1":
        res = "DESCARTADA" if d4 else "SIN VEREDICTO"
    elif m["entradas"] == 0:
        res = "SIN VEREDICTO"  # E3: no hubo entrada
    elif d2 or d1 or d3 or d4:
        res = "DESCARTADA"
    else:
        res = "NO DESCARTADA"
    banda = None
    if res == "NO DESCARTADA":
        banda = "no concluyente (6–7 %)" if m["cagr_neto"] <= u["D1_banda_no_concluyente"] else "> 7 %: solo habilita prospectiva"
    return {"resultado": res, "criterios_activos": activos, "banda": banda}
