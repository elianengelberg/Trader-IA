"""Diagnóstico económico del carry BTCUSDT con datos HISTÓRICOS oficiales, SOLO en la división de desarrollo
(2020-01-01 → 2023-01-01). No lee validación, test ni período reservado.

Parte A: el mercado (funding, episodios, persistencia, base, mark, regímenes ex ante, volumen).
Parte B: rev. 5, UmbralFunding (parámetros prerregistrados) y un control de efectivo en desarrollo, con las 8
sensibilidades del prerregistro (análisis complementario: NO son los criterios de aceptación, que se aplican en test).

Uso: PYTHONPATH=src .venv/bin/python -B experimentos/historico/diagnostico_desarrollo.py
Salida: experimentos/historico/desarrollo/{DIAGNOSTICO_DESARROLLO.md, diagnostico.json, registro.jsonl}"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import statistics as st
from pathlib import Path

from hcarry.conventions import DIA_MS, HORA_MS
from hcarry.data.binance_vision import construir_panel
from hcarry.lab import experimento as X
from hcarry.lab import historico as H
from hcarry.lab.estadistica import comparar

RAIZ = Path(__file__).resolve().parents[2]
DATOS_DIR = RAIZ / "datos" / "binance_vision"
SALIDA = Path(__file__).resolve().parent / "desarrollo"
DEV = ("2020-01-01", "2023-01-01")
DATOS = {"fuente": "binance_vision", "directorio": str(DATOS_DIR), "desde": "2020-01-01", "hasta": "2026-06-01"}
APR = 3 * 365  # eventos de 8 h por año


def q(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(p * len(s)) - 1))]


def dia(t: int) -> str:
    return dt.datetime.fromtimestamp(t / 1000, dt.UTC).strftime("%Y-%m-%d")


def corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = st.fmean(x), st.fmean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (sx * sy) if sx and sy else None


def rachas(flags: list[bool]) -> list[int]:
    out, n = [], 0
    for f in flags:
        if f:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


# ------------------------------------------------------------------------------------------------ A. mercado
def mercado(panel) -> dict:  # type: ignore[no-untyped-def]
    ev = panel.funding
    f = [e.tasa for e in ev]
    a: dict = {"eventos": len(f), "desde": dia(ev[0].t), "hasta": dia(ev[-1].t)}
    a["funding_por_evento"] = {"media": st.fmean(f), "mediana": st.median(f), "p01": q(f, .01), "p05": q(f, .05),
                               "p25": q(f, .25), "p75": q(f, .75), "p95": q(f, .95), "p99": q(f, .99),
                               "min": min(f), "max": max(f), "desv": st.pstdev(f)}
    a["apr_medio"] = st.fmean(f) * APR
    a["frac_negativos"] = sum(x < 0 for x in f) / len(f)
    a["frac_en_0_01pct"] = sum(abs(x - 1e-4) < 1e-9 for x in f) / len(f)
    a["frac_mayor_0_01pct"] = sum(x > 1e-4 + 1e-9 for x in f) / len(f)
    trim: dict[str, list[float]] = {}
    for e in ev:
        d = dt.datetime.fromtimestamp(e.t / 1000, dt.UTC)
        trim.setdefault(f"{d.year}T{(d.month - 1) // 3 + 1}", []).append(e.tasa)
    a["por_trimestre"] = {k: {"apr": st.fmean(v) * APR, "frac_neg": sum(x < 0 for x in v) / len(v)}
                          for k, v in trim.items()}
    neg = rachas([x < 0 for x in f])
    a["episodios_negativos"] = {"n": len(neg), "mediana_h": st.median(neg) * 8 if neg else 0,
                                "max_h": max(neg) * 8 if neg else 0, "n_mayor_3d": sum(r * 8 > 72 for r in neg),
                                "frac_tiempo": sum(neg) / len(f)}
    tr = [st.fmean(f[max(0, i - 20):i + 1]) * APR for i in range(len(f))]  # media móvil 7 d (21 eventos), ex post
    bajo = rachas([x < 0.05 for x in tr[20:]])
    a["episodios_carry_bajo_7d_menor_5pct"] = {"n": len(bajo), "frac_tiempo": sum(bajo) / len(tr[20:]),
                                               "mediana_d": st.median(bajo) * 8 / 24 if bajo else 0,
                                               "max_d": max(bajo) * 8 / 24 if bajo else 0}
    a["persistencia_prerregistrada_7d"] = H._persistencia(ev)
    a["persistencia_30d"] = H._persistencia(ev, dias=30)
    a["acf_eventos"] = {lag: corr(f[:-lag], f[lag:]) for lag in (1, 3, 9, 21, 63)}
    pasado = [st.fmean(f[i - 21:i]) for i in range(21, len(f) - 21, 21)]
    futuro = [st.fmean(f[i:i + 21]) for i in range(21, len(f) - 21, 21)]
    a["prediccion_7d_siguiente"] = {"corr": corr(pasado, futuro), "n": len(pasado),
                                    "acierto_signo": sum((x > 0) == (y > 0) for x, y in zip(pasado, futuro,
                                                                                          strict=True)) / len(pasado),
                                    "acierto_umbral_10_3": _acierto_umbral(pasado, futuro)}
    # base y mark (horas reales)
    reales = [b for b in panel.barras if not b.relleno]
    base = [b.F_c / b.S_c - 1 for b in reales]
    mk = [b.M_c / b.S_c - 1 for b in reales]
    a["base_F_sobre_S"] = {"media": st.fmean(base), "mediana": st.median(base), "p01": q(base, .01),
                           "p99": q(base, .99), "min": min(base), "max": max(base),
                           "horas_abs_mayor_0_5pct": sum(abs(x) > 0.005 for x in base),
                           "horas_abs_mayor_1pct": sum(abs(x) > 0.01 for x in base)}
    a["mark_sobre_spot"] = {"mediana": st.median(mk), "p01": q(mk, .01), "p99": q(mk, .99)}
    # diario: base, funding, retorno, volatilidad y volumen
    dias: dict[str, dict] = {}
    for b in reales:
        d = dias.setdefault(dia(b.t), {"S": b.S_c, "base": [], "qv": 0.0})
        d["S"] = b.S_c
        d["base"].append(b.F_c / b.S_c - 1)
        d["qv"] += b.qv_perp or 0.0
    fd: dict[str, list[float]] = {}
    for e in ev:
        fd.setdefault(dia(e.t), []).append(e.tasa)
    claves = [k for k in sorted(dias) if k in fd]
    S = [dias[k]["S"] for k in claves]
    fdia = [st.fmean(fd[k]) * APR for k in claves]
    bdia = [st.fmean(dias[k]["base"]) for k in claves]
    a["corr_base_funding_mismo_dia"] = corr(bdia, fdia)
    a["corr_base_hoy_funding_7d_siguiente"] = corr(bdia[:-7], [st.fmean(fdia[i + 1:i + 8]) for i in range(len(fdia) - 7)])
    # regímenes EX ANTE: información hasta el cierre del día d; resultado: funding medio de d+1 a d+7
    filas = []
    for i in range(30, len(claves) - 7):
        r30 = S[i] / S[i - 30] - 1
        rets = [math.log(S[j] / S[j - 1]) for j in range(i - 29, i + 1)]
        vol = st.pstdev(rets) * math.sqrt(365)
        qv7 = st.fmean([dias[claves[j]]["qv"] for j in range(i - 6, i + 1)])
        filas.append({"r30": r30, "vol": vol, "qv7": qv7, "f_sig7": st.fmean(fdia[i + 1:i + 8]),
                      "f_prev7": st.fmean(fdia[i - 6:i + 1])})
    def grupo(cond) -> dict:  # type: ignore[no-untyped-def]
        g = [x["f_sig7"] for x in filas if cond(x)]
        return {"dias": len(g), "apr_7d_siguiente": st.fmean(g) if g else None,
                "frac_7d_sig_menor_5pct": (sum(x < 0.05 for x in g) / len(g)) if g else None}
    a["regimenes_ex_ante"] = {
        "alcista_r30_mayor_10pct": grupo(lambda x: x["r30"] > 0.10),
        "lateral": grupo(lambda x: -0.10 <= x["r30"] <= 0.10),
        "bajista_r30_menor_m10pct": grupo(lambda x: x["r30"] < -0.10),
        "vol_menor_50pct": grupo(lambda x: x["vol"] < 0.5),
        "vol_50_80pct": grupo(lambda x: 0.5 <= x["vol"] <= 0.8),
        "vol_mayor_80pct": grupo(lambda x: x["vol"] > 0.8),
        "funding_7d_previo_menor_5pct": grupo(lambda x: x["f_prev7"] < 0.05),
        "funding_7d_previo_5_10pct": grupo(lambda x: 0.05 <= x["f_prev7"] < 0.10),
        "funding_7d_previo_mayor_10pct": grupo(lambda x: x["f_prev7"] >= 0.10)}
    a["corr_ex_ante"] = {"r30_vs_f_sig7": corr([x["r30"] for x in filas], [x["f_sig7"] for x in filas]),
                         "vol_vs_f_sig7": corr([x["vol"] for x in filas], [x["f_sig7"] for x in filas]),
                         "log_qv7_vs_f_sig7": corr([math.log(x["qv7"]) for x in filas], [x["f_sig7"] for x in filas]),
                         "f_prev7_vs_f_sig7": corr([x["f_prev7"] for x in filas], [x["f_sig7"] for x in filas])}
    a["volumen_perp_diario_usdt"] = {"mediana": st.median([dias[k]["qv"] for k in claves]),
                                     "p05": q([dias[k]["qv"] for k in claves], .05)}
    return a


def _acierto_umbral(pasado: list[float], futuro: list[float]) -> dict:
    """Con la regla de UmbralFunding simplificada a bloques de 7 d: ¿qué APR tuvo el bloque siguiente cuando el
    anterior estaba por encima de la entrada (10 %) o por debajo de la salida (3 %)?"""
    alto = [y * APR for x, y in zip(pasado, futuro, strict=True) if x * APR >= 0.10]
    bajo = [y * APR for x, y in zip(pasado, futuro, strict=True) if x * APR < 0.03]
    return {"bloques_previo_mayor_10": len(alto), "apr_siguiente_si_previo_mayor_10": st.fmean(alto) if alto else None,
            "bloques_previo_menor_3": len(bajo), "apr_siguiente_si_previo_menor_3": st.fmean(bajo) if bajo else None}


# ------------------------------------------------------------------------------------------------ B. políticas
def diario(r) -> list[tuple[str, float]]:  # type: ignore[no-untyped-def]
    out: dict[str, float] = {}
    for fila in r.serie:
        out[dia(fila[0] - 1)] = fila[1]
    return sorted(out.items())


def extra(r) -> dict:  # type: ignore[no-untyped-def]
    d = diario(r)
    eq = [r.capital] + [e for _, e in d]
    pnl = [b - a for a, b in itertools.pairwise(eq)]
    rets = [b / a - 1 for a, b in itertools.pairwise(eq)]
    neg = [x for x in rets if x < 0]
    sortino = (st.fmean(rets) * 365) / (math.sqrt(sum(x * x for x in neg) / len(rets)) * math.sqrt(365)) if neg else None
    pico, dur, peor_dur = eq[0], 0, 0
    for e in eq:
        if e >= pico:
            pico, dur = e, 0
        else:
            dur += 1
            peor_dur = max(peor_dur, dur)
    tot = sum(pnl)
    top = sorted(pnl, reverse=True)[: max(1, len(pnl) // 10)]
    m30 = [eq[i + 30] / eq[i] - 1 for i in range(len(eq) - 30)]
    return {"sortino": sortino, "caida_dur_max_dias": peor_dur, "peor_dia": min(rets), "peor_30d": min(m30) if m30 else None,
            "frac_pnl_top10pct_dias": (sum(top) / tot) if tot else None, "dias": len(pnl)}


def episodios(r) -> list[dict]:  # type: ignore[no-untyped-def]
    """Periodos con posición (lotes_perp ≠ 0) y su funding, costes y PnL de equity."""
    eps, act = [], None
    serie = r.serie
    for i, fila in enumerate(serie):
        en = fila[5] != 0
        if en and act is None:
            act = {"i0": i, "E0": serie[i - 1][1] if i else r.capital, "t0": fila[0]}
        if not en and act is not None:
            act.update({"i1": i, "E1": fila[1], "t1": fila[0]})
            eps.append(act)
            act = None
    if act is not None:
        act.update({"i1": len(serie) - 1, "E1": serie[-1][1], "t1": serie[-1][0]})
        eps.append(act)
    out = []
    for e in eps:
        fund = sum(x["importe"] for x in r.funding if e["t0"] - HORA_MS <= x["t"] < e["t1"])
        cost = sum(o["coste_spot"] + o["coste_perp"] for o in r.operaciones if e["t0"] - HORA_MS <= o["t"] <= e["t1"])
        out.append({"desde": dia(e["t0"]), "hasta": dia(e["t1"]), "dias": (e["t1"] - e["t0"]) / DIA_MS,
                    "pnl": e["E1"] - e["E0"], "funding": fund, "costes": cost})
    return out


def politicas(registro: Path) -> dict:
    pols = dict(H.PRERREGISTRO["politicas"])
    pols["efectivo"] = {"nombre": "efectivo", "params": {}}
    salida: dict = {}
    res = {}
    for n, p in pols.items():
        escen = {"base": None} if n == "efectivo" else {"base": None, **H.PRERREGISTRO["sensibilidad"]}
        for e, ext in escen.items():
            r, m, _ = X.correr(H._cfg(f"dev_{n}__{e}", DATOS, "desarrollo", p, ext), registro)
            clave = f"{n}__{e}"
            res[clave] = r
            salida[clave] = {k: m.get(k) for k in (
                "estado", "final", "pnl_neto", "cagr_neto", "caida_maxima", "vol_anual", "sharpe", "funding_cobrado",
                "funding_pagado", "funding_neto", "costes", "pnl_precio_patas", "tiempo_en_mercado", "rotacion_anual",
                "n_operaciones", "entradas", "duracion_media_h", "utilizacion_media", "rent_capital_comprometido",
                "liquidaciones", "distancia_min_liquidacion", "por_ano", "descomposicion")}
            if e == "base":
                salida[clave].update(extra(r))
    salida["umbral__episodios"] = episodios(res["umbral__base"])
    salida["bootstrap_dev_umbral_menos_rev5"] = comparar(res["umbral__base"], res["rev5__base"], bloque=30, n=2000,
                                                         semilla=20261016)
    return salida


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    panel, inf = construir_panel(DATOS_DIR, *DEV)
    assert panel.fin <= 1672531200000 + HORA_MS, "el diagnóstico no puede salir de desarrollo"
    out = {"categoria": "HISTÓRICO verificado (data.binance.vision, manifiesto con checksums)", "division": DEV,
           "codigo_sha256": X.huella_codigo(), "prerregistro_sha256": H.hash_prerregistro(),
           "manifiesto_sha256": X.sha((DATOS_DIR / "MANIFIESTO.json").read_bytes()),
           "horas_rellenadas": inf.info["horas_rellenadas"], "mercado": mercado(panel),
           "politicas": politicas(SALIDA / "registro.jsonl")}
    (SALIDA / "diagnostico.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, default=str)[:200])


if __name__ == "__main__":
    main()
