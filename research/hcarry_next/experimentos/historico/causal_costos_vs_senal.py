"""Diagnóstico causal de H-CARRY: ¿señal, diseño, costes, mercado o asignación de capital?

EXPLORATORIO POSTERIOR AL TEST: el test prerregistrado ya se consumió (cerrojo TEST_CONSUMIDO.json). Nada de esto es
evidencia independiente ni sirve para elegir parámetros; reconstruye y descompone lo que ya ocurrió.

Escenarios (cada uno es una simulación completa con el mismo motor, datos y políticas; solo cambian los costes):
  D  Realista neto: costes base prerregistrados (spot 10 + 5 bps, perpetuo 5 + 5 bps sobre el nocional ejecutado).
  B  Sin comisiones: comisión 0 en ambas patas; se conserva el slippage (5 bps por pata).
  C  Sin costes de ejecución: comisión y slippage 0; se conservan funding y PnL de precio de las patas.
  A  Bruto teórico: SOLO el funding neto devengado en C (la fuente de ingresos de la estrategia), sin patas ni costes.
  E  Capital alternativo: efectivo a 0 % (supuesto del motor), letra del Tesoro a 3 meses (FRED DTB3, no accesible
     directamente para USDT en un exchange) y USDT en Aave v3 (DeFi, accesible con otros riesgos), por separado.
Además, la descomposición contable EXACTA de D (conciliación independiente): PnL spot + PnL perpetuo + funding − costes,
con los costes separados en comisión y slippage por pata (el modelo de costes es lineal: la proporción es exacta).

Uso: PYTHONPATH=src .venv/bin/python -B experimentos/historico/causal_costos_vs_senal.py"""

from __future__ import annotations

import csv
import datetime as dt
import json
import statistics as st
from pathlib import Path

from hcarry.conventions import HORA_MS
from hcarry.data.binance_vision import construir_panel
from hcarry.lab import experimento as X
from hcarry.lab import historico as H

AQUI = Path(__file__).resolve().parent
DIR = AQUI.parents[1] / "datos" / "binance_vision"
SALIDA = AQUI / "causal"
DATOS = {"fuente": "binance_vision", "directorio": str(DIR), "desde": "2020-01-01", "hasta": "2026-06-01"}
DIVS = {"desarrollo": ("2020-01-01", "2023-01-01"), "validacion": ("2023-01-01", "2024-02-01"),
        "test": ("2024-02-01", "2026-06-01"), "completo": ("2020-01-01", "2026-06-01")}
ESCENARIOS = {
    "D_neto": {},
    "B_sin_comisiones": {"costes": {"spot_comision_bps": 0.0, "perp_comision_bps": 0.0}},
    "C_sin_costes_ejecucion": {"costes": {"multiplicador": 0.0}},
    # supuestos alternativos de costes (no prerregistrados): favorables = tarifa con descuento BNB y 1 bp de slippage;
    # adversos = slippage de 15 bps por pata
    "costes_favorables": {"costes": {"spot_comision_bps": 7.5, "spot_slippage_bps": 1.0, "perp_comision_bps": 4.5,
                                     "perp_slippage_bps": 1.0}},
    "costes_adversos": {"costes": {"spot_slippage_bps": 15.0, "perp_slippage_bps": 15.0}},
}
PARTE_COMISION = {"spot": 10 / 15, "perp": 5 / 10}  # proporción de la comisión en el coste base de cada pata
OBJETIVO = 0.05


def dia(t: int) -> str:
    return dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()


def serie_tasas() -> tuple[dict[str, float], dict[str, float]]:
    tb, ultima = {}, None
    filas = list(csv.DictReader((AQUI / "post_test" / "externos" / "DTB3.csv").open(encoding="utf-8")))
    por = {f["observation_date"]: f["DTB3"] for f in filas}
    d, fin = dt.date(2019, 12, 1), dt.date(2026, 6, 1)
    while d <= fin:
        v = por.get(d.isoformat())
        if v not in (None, "", "."):
            ultima = float(v) / 100
        tb[d.isoformat()] = ultima
        d += dt.timedelta(days=1)
    aave = {}
    for x in json.loads((SALIDA / "externos" / "aave_v3_usdt_ethereum.json").read_text(encoding="utf-8"))["data"]:
        v = x.get("apyBase") if x.get("apyBase") is not None else x.get("apy")
        if v is not None:
            aave[x["timestamp"][:10]] = v / 100
    return tb, aave


def benchmark(tasas: dict[str, float], a: str, b: str) -> dict:
    d, fin, f, cubiertos, total = dt.date.fromisoformat(a), dt.date.fromisoformat(b), 1.0, 0, 0
    while d < fin:
        total += 1
        r = tasas.get(d.isoformat())
        if r is not None:
            f *= 1 + r / 365
            cubiertos += 1
        d += dt.timedelta(days=1)
    return {"cagr": f ** (365 / cubiertos) - 1 if cubiertos else None, "cobertura": cubiertos / total}


def uso_capital(r, panel) -> dict:  # type: ignore[no-untyped-def]
    precios = {b.t + HORA_MS: (b.S_c, b.F_c) for b in panel.barras}
    # patrimonio de la cuenta de futuros = saldo W + PnL no realizado del corto = E − U − valor del BTC spot
    acc = {"spot_btc": 0.0, "spot_usdt": 0.0, "patrimonio_futuros": 0.0}
    n = 0
    for t, e, u, _w, ls, _lp, _fb, _c in r.serie:
        if e <= 0 or t not in precios:
            continue
        s, _ = precios[t]
        acc["spot_btc"] += ls * 0.001 * s / e
        acc["spot_usdt"] += u / e
        acc["patrimonio_futuros"] += (e - u - ls * 0.001 * s) / e
        n += 1
    out = {k: v / n for k, v in acc.items()}
    eq = {t: e for t, e, *_ in r.serie}
    noc = [abs(x["importe"] / x["tasa"]) / eq.get(x["t"], r.capital) for x in r.funding if abs(x["tasa"]) > 1e-12]
    out["nocional_sobre_equity"] = st.fmean(noc) if noc else 0.0
    noc0 = [abs(x["importe"] / x["tasa"]) / r.capital for x in r.funding if abs(x["tasa"]) > 1e-12]
    out["nocional_sobre_capital_inicial"] = st.fmean(noc0) if noc0 else 0.0
    out["apr_funding_sobre_nocional"] = (sum(x["tasa"] for x in r.funding) / (r.dias / 365))
    out["fraccion_horas_con_posicion"] = sum(1 for s in r.serie if s[5]) / len(r.serie)
    return out


def flujos(r, m) -> dict:  # type: ignore[no-untyped-def]
    d = m["descomposicion"]
    cs = sum(o["coste_spot"] for o in r.operaciones)
    cp = sum(o["coste_perp"] for o in r.operaciones)
    giro_s = sum(o["cantidad"] * o["S"] for o in r.operaciones if o["coste_spot"])
    giro_p = sum(o["cantidad"] * o["F"] for o in r.operaciones if o["coste_perp"])
    return {"pnl_spot": d["pnl_spot"], "pnl_perp": d["pnl_perp"], "funding_neto": d["funding"],
            "funding_cobrado": m["funding_cobrado"], "funding_pagado": m["funding_pagado"],
            "comision_spot": cs * PARTE_COMISION["spot"], "slippage_spot": cs * (1 - PARTE_COMISION["spot"]),
            "comision_perp": cp * PARTE_COMISION["perp"], "slippage_perp": cp * (1 - PARTE_COMISION["perp"]),
            "costes_total": d["costes"], "ajustes": d["ajustes"], "turnover_spot": giro_s, "turnover_perp": giro_p,
            "costes_pct_turnover": d["costes"] / (giro_s + giro_p) if giro_s + giro_p else None,
            "n_operaciones": m["n_operaciones"],
            "identidad_ok": abs(d["pnl_spot"] + d["pnl_perp"] + d["funding"] - d["costes"] + d["ajustes"]
                                - m["pnl_neto"]) < 1e-6 * r.capital}


def diario(r) -> dict[str, float]:  # type: ignore[no-untyped-def]
    out: dict[str, float] = {}
    for fila in r.serie:
        out[dia(fila[0] - 1)] = fila[1]
    return out


def por_regimen(r, panel) -> dict:  # type: ignore[no-untyped-def]
    """PnL diario agrupado por año y por régimen EX ANTE (rentabilidad del BTC en los 30 días previos al día)."""
    cierres: dict[str, float] = {}
    for b in panel.barras:
        cierres[dia(b.t)] = b.S_c
    dias = sorted(cierres)
    eq = diario(r)
    prev_e = r.capital
    anos: dict[str, float] = {}
    reg: dict[str, float] = {"alcista": 0.0, "lateral": 0.0, "bajista": 0.0, "sin_historia": 0.0}
    for i, d in enumerate(dias):
        if d not in eq:
            continue
        pnl = eq[d] - prev_e
        prev_e = eq[d]
        anos[d[:4]] = anos.get(d[:4], 0.0) + pnl
        if i >= 31:
            r30 = cierres[dias[i - 1]] / cierres[dias[i - 31]] - 1
            reg["alcista" if r30 > 0.10 else "bajista" if r30 < -0.10 else "lateral"] += pnl
        else:
            reg["sin_historia"] += pnl
    return {"pnl_por_ano": anos, "pnl_por_regimen_ex_ante": reg}


def diagnostico_umbral(rev5, umb, panel) -> dict:  # type: ignore[no-untyped-def]
    {fila[0]: fila[5] != 0 for fila in umb.serie}
    tramos, act = [], None
    for fila in umb.serie:
        fuera = fila[5] == 0
        if fuera and act is None:
            act = {"desde": fila[0]}
        if not fuera and act is not None:
            act["hasta"] = fila[0]
            tramos.append(act)
            act = None
    if act is not None:
        act["hasta"] = umb.serie[-1][0] + HORA_MS
        tramos.append(act)
    salidas = []
    for tr in tramos:
        f = [x for x in rev5.funding if tr["desde"] <= x["t"] < tr["hasta"]]
        ult7 = [x["importe"] for x in f if x["t"] >= tr["hasta"] - 7 * 24 * HORA_MS]
        salidas.append({"desde": dia(tr["desde"]), "hasta": dia(tr["hasta"]),
                        "dias": (tr["hasta"] - tr["desde"]) / (24 * HORA_MS),
                        "funding_rev5_positivo": sum(x["importe"] for x in f if x["importe"] > 0),
                        "funding_rev5_negativo": sum(x["importe"] for x in f if x["importe"] < 0),
                        "funding_rev5_ultimos_7d_antes_de_reentrar": sum(ult7)})
    neto_fuera = [s["funding_rev5_positivo"] + s["funding_rev5_negativo"] for s in salidas]
    pagado_dentro = -sum(x["importe"] for x in umb.funding if x["importe"] < 0)
    # capacidad predictiva de la señal dentro de la división: media de 21 eventos previa frente a la siguiente
    f = [e.tasa for e in panel.funding]
    pares = [(st.fmean(f[i - 21:i]) * 1095, st.fmean(f[i:i + 21]) * 1095) for i in range(21, len(f) - 21, 21)]
    corr = None
    if len(pares) > 3:
        xs, ys = zip(*pares, strict=True)
        mx, my = st.fmean(xs), st.fmean(ys)
        sx = sum((a - mx) ** 2 for a in xs) ** .5
        sy = sum((b - my) ** 2 for b in ys) ** .5
        corr = sum((a - mx) * (b - my) for a, b in pares) / (sx * sy) if sx and sy else None
    zona_salida = [y for x, y in pares if x < 0.03]
    zona_entrada = [y for x, y in pares if x >= 0.10]
    orden = sorted(neto_fuera, reverse=True)
    return {"tramos_fuera": salidas, "n_tramos_fuera": len(salidas),
            "funding_perdido_fuera_neto": sum(neto_fuera),
            "funding_positivo_perdido_ultimos_7d_antes_de_reentrar": sum(s["funding_rev5_ultimos_7d_antes_de_reentrar"]
                                                                       for s in salidas),
            "funding_negativo_pagado_por_umbral_estando_dentro": pagado_dentro,
            "tramos_fuera_con_funding_neto_positivo": sum(x > 0 for x in neto_fuera),
            "peso_3_mayores_tramos_en_funding_perdido": (sum(orden[:3]) / sum(neto_fuera)) if sum(neto_fuera) else None,
            "costes_extra": umb.costes_total - rev5.costes_total,
            "prediccion_corr_media21_siguiente21": corr, "bloques": len(pares),
            "apr_siguiente_tras_zona_salida_lt3": st.fmean(zona_salida) if zona_salida else None,
            "n_zona_salida": len(zona_salida),
            "apr_siguiente_tras_zona_entrada_ge10": st.fmean(zona_entrada) if zona_entrada else None,
            "n_zona_entrada": len(zona_entrada)}


def main() -> None:
    assert (AQUI / "resultados" / "historico" / H.CERROJO_TEST).exists(), "solo después de consumir el test"
    SALIDA.mkdir(exist_ok=True)
    tb, aave = serie_tasas()
    ref = json.loads((AQUI / "resultados" / "historico" / "datos_8bdabde706bf" / "resultado.json").read_text())
    out: dict = {"categoria": "EXPLORATORIO posterior al test; no es evidencia independiente",
                 "codigo_sha256": X.huella_codigo(), "manifiesto_sha256": X.sha((DIR / "MANIFIESTO.json").read_bytes()),
                 "divisiones": {}}
    for div, (a, b) in DIVS.items():
        panel, _ = construir_panel(DIR, a, b)
        o: dict = {"benchmarks": {"efectivo_0": 0.0, "tbill_3m": benchmark(tb, a, b),
                                  "aave_v3_usdt": benchmark(aave, a, b), "comparador_prerregistrado": OBJETIVO}}
        runs = {}
        for pol, p in H.PRERREGISTRO["politicas"].items():
            for esc, ext in ESCENARIOS.items():
                r, m, _ = X.correr(H._cfg(f"causal_{div}_{pol}_{esc}", DATOS, {"desde": a, "hasta": b}, p, ext))
                runs[(pol, esc)] = (r, m)
                anos = m["dias"] / 365
                fila = {"cagr": m["cagr_neto"], "pnl": m["pnl_neto"], "pp_anual_simple": m["pnl_neto"] / r.capital / anos * 100,
                        "funding_neto": m["funding_neto"], "costes": m["costes"], "anos": anos}
                if esc == "D_neto":
                    fila["flujos"] = flujos(r, m)
                    fila["uso_capital"] = uso_capital(r, panel)
                    fila.update(por_regimen(r, panel))
                if esc == "C_sin_costes_ejecucion":
                    fila["A_bruto_teorico_funding_pp_anual"] = m["funding_neto"] / r.capital / anos * 100
                o.setdefault(pol, {})[esc] = fila
        o["umbral_diagnostico"] = diagnostico_umbral(runs[("rev5", "D_neto")][0], runs[("umbral", "D_neto")][0], panel)
        if div == "test":  # contraste con el resultado archivado del test
            o["contraste_con_test_archivado"] = {
                pol: {"pnl_archivado": ref["test"][pol]["pnl_neto"], "pnl_recalculado": o[pol]["D_neto"]["pnl"],
                      "coincide": abs(ref["test"][pol]["pnl_neto"] - o[pol]["D_neto"]["pnl"]) < 1e-6}
                for pol in ("rev5", "umbral")}
        out["divisiones"][div] = o
        print(div, "listo", flush=True)
    (SALIDA / "causal.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (SALIDA / "cascada_deficit.json").write_text(json.dumps(cascada(out), ensure_ascii=False, indent=1), encoding="utf-8")


def cascada(out: dict) -> dict:
    """Identidad exacta en pp/año simples sobre el capital inicial: 5 − R = (5 − APR) + APR·(1 − n) + K − P, con
    APR = funding efectivo sobre el nocional y n = nocional medio / capital inicial. Es contabilidad, no causalidad."""
    t = OBJETIVO * 100
    res = {}
    for div, o in out["divisiones"].items():
        for pol in ("rev5", "umbral"):
            d = o[pol]["D_neto"]
            f, anos, cap = d["flujos"], d["anos"], 10_000.0
            r_ = d["pp_anual_simple"]
            fu = f["funding_neto"] / cap / anos * 100
            k = f["costes_total"] / cap / anos * 100
            p = (f["pnl_spot"] + f["pnl_perp"]) / cap / anos * 100
            n0 = d["uso_capital"]["nocional_sobre_capital_inicial"]
            apr = fu / n0
            fila = {"R_neto_pp": r_, "funding_pp": fu, "patas_pp": p, "costes_pp": k,
                    "comisiones_pp": (f["comision_spot"] + f["comision_perp"]) / cap / anos * 100,
                    "nocional_sobre_capital_inicial": n0, "apr_funding_efectivo_sobre_nocional": apr,
                    "deficit": t - r_, "mercado": t - apr, "estructura": apr * (1 - n0), "costes": k, "patas": -p,
                    "apr_necesario_para_objetivo": (t + k - p) / n0}
            fila["error_identidad"] = fila["mercado"] + fila["estructura"] + fila["costes"] + fila["patas"] - fila["deficit"]
            res[f"{div}__{pol}"] = fila
    return res


if __name__ == "__main__":
    main()
