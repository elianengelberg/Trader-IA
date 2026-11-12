"""E1 — ejecución y análisis prerregistrados (ver prerregistro/PRERREGISTRO_E1.md).

Uso:
  python -B e1.py --salida <dir nuevo>                      # datos reales (una sola ejecución)
  python -B e1.py --salida <dir nuevo> --sintetico 20000    # ensayo funcional con datos SINTÉTICOS
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import e1_comun as C
from tia.backtest.baselines import always_flat, buy_and_hold, sma_cross, volatility_targeted
from tia.core.config import ExecutionSimConfig

PRINCIPALES = {"P1": ("trend_following",), "P2": ("mean_reversion",), "P3": ("breakout",)}
FUSION = C.ESTRATEGIAS
SUBPERIODOS = [("2019-10→2021-12", "2019-10-01", "2022-01-01"), ("2022", "2022-01-01", "2023-01-01"),
               ("2023-01→2026-05", "2023-01-01", "2026-06-01")]
BANDAS = [(0.55, 0.65), (0.65, 0.75), (0.75, 1.0001)]
ALFA = 0.05
VELAS: list = []


def _tareas():
    t = []
    bases = {**PRINCIPALES, "S1": FUSION}
    for k, est in bases.items():
        t.append((k, est, {}, None))
        t.append((f"S2|{k}", est, {"comision_bps": 20.0}, None))
        t.append((f"S3|{k}", est, {"retraso": True}, None))
        t.append((f"S4|{k}", est, {"comision_bps": 0.0, "deslizamiento_base_bps": 0.0, "impacto": 0.0}, None))
        t.append((f"S5|{k}", est, {"cortos": True}, None))
        t.append((f"S6|{k}", est, {"gobernadores_en_vivo": True}, None))
    for k, est in PRINCIPALES.items():
        t.append((f"S7|{k}", est, {"motor_original": True}, None))
    t.append(("VALIDEZ|S1|prefijo70", FUSION, {}, 0.70))
    return t


def _init(sintetico):
    global VELAS
    if sintetico:
        VELAS = C.sinteticas(sintetico, 2026, t0=datetime(2019, 10, 1, tzinfo=timezone.utc))
    else:
        VELAS, _ = C.leer_velas()


def _huella(r, corte):
    d = "\n".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) for x in r.decision_log if x.bar_close_time < corte)
    t = "\n".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) for x in r.trades if x.exit_at < corte)
    return hashlib.sha256(d.encode()).hexdigest(), hashlib.sha256(t.encode()).hexdigest(), d.count("\n") + 1


def _correr(tarea):
    nombre, est, kw, prefijo = tarea
    t0 = time.time()
    velas = VELAS[: int(len(VELAS) * prefijo)] if prefijo else VELAS
    r, d3 = C.correr_con_d3(velas, est, **kw)
    corte = VELAS[int(len(VELAS) * 0.70) - 1].open_time
    rts = C.round_trips(r.trades)
    out = {"nombre": nombre, "estrategias": list(est), "parametros": kw, "barras": len(velas),
           "segundos": round(time.time() - t0, 1), "round_trips": rts,
           "metricas": r.metrics.model_dump(mode="json"), "decisiones": r.decisions.model_dump(mode="json"),
           "advertencias": list(r.warnings), "d3": d3}
    if nombre in ("S1", "VALIDEZ|S1|prefijo70"):
        out["huella_antes_del_corte"] = _huella(r, corte)
    if nombre.startswith("S6|"):
        frenos = [x for x in r.decision_log if (x.stage == "budget" and "emergency" in x.reason.lower())
                  or (x.stage == "risk" and ("halted" in x.reason or "max drawdown" in x.reason))]
        out["gobernadores"] = {"primer_bloqueo": frenos[0].bar_close_time.isoformat() if frenos else None,
                               "decisiones_bloqueadas": len(frenos),
                               "ultima_entrada": rts[-1]["entrada"] if rts else None}
    return out


# ------------------------------------------------------------------------------------------- análisis
def _mes(iso):
    return iso[:7]


def _bloques(etiquetas_periodo, rts, clave):
    suma = {e: 0.0 for e in etiquetas_periodo}
    cuenta = {e: 0 for e in etiquetas_periodo}
    for x in rts:
        b = clave(x["entrada"])
        if b in suma:
            suma[b] += x["neto_pct"]
            cuenta[b] += 1
    return np.array([suma[e] for e in etiquetas_periodo]), np.array([cuenta[e] for e in etiquetas_periodo])


def bootstrap_media(rts, etiquetas, clave, B, semilla):
    S, N = _bloques(etiquetas, rts, clave)
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(etiquetas), size=(B, len(etiquetas)))
    s, n = S[idx].sum(1), N[idx].sum(1)
    medias = s[n > 0] / n[n > 0]
    return {"P_media_mayor_0": float((medias > 0).mean()), "ic90": [float(np.percentile(medias, 5)), float(np.percentile(medias, 95))],
            "replicas_validas": int(medias.size)}


def _trimestre(dt):
    return f"{dt.year}T{(dt.month - 1) // 3 + 1}"


def nulo_emparejado(rts, velas, R, semilla, warmup=120, comision_bps=10.0, base_bps=2.0):
    """Entradas aleatorias estratificadas por trimestre, con las mismas duraciones (barras) sin solapamiento."""
    n = len(velas)
    o = np.array([v.open for v in velas]); h = np.array([v.high for v in velas]); lo = np.array([v.low for v in velas])
    c = np.array([v.close for v in velas])
    rango_bps = (h - lo) / c * 1e4
    slip = (base_bps + np.minimum(rango_bps * 0.05, 25.0)) / 1e4
    f = comision_bps / 1e4
    idx_cierre = {v.close_time.isoformat(): i for i, v in enumerate(velas)}
    trim = [_trimestre(v.open_time) for v in velas]
    rango_q: dict[str, list[int]] = {}
    for i in range(warmup, n - 1):
        rango_q.setdefault(trim[i], [i, i + 1])[1] = i + 1
    por_q: dict[str, list[int]] = {}
    for x in rts:
        e = idx_cierre[x["entrada"]]
        d = max(1, idx_cierre[x["salida"]] - e)
        por_q.setdefault(trim[e], []).append(d)
    rng = np.random.default_rng(semilla)
    netos = []
    apretados = 0
    for q, ds in por_q.items():
        a, b = rango_q[q]
        d = np.array(ds)
        holgura = (b - a) - d.sum()
        if holgura < 0:
            apretados += 1
            holgura = 0
        u = np.sort(rng.integers(0, holgura + 1, size=(R, d.size)), axis=1)
        perm = np.argsort(rng.random((R, d.size)), axis=1)
        dp = d[perm]
        ini = a + u + np.cumsum(dp, axis=1) - dp
        fin = np.minimum(ini + dp, n - 1)
        ini = np.minimum(ini, n - 2)
        pe = np.minimum(h[ini], o[ini] * (1 + slip[ini]))
        ps = np.maximum(lo[fin], o[fin] * (1 - slip[fin]))
        netos.append(((ps - pe) - f * pe - f * ps) / pe * 100.0)
    todos = np.concatenate(netos, axis=1)
    return todos.mean(axis=1), apretados


def holm(pvals: dict[str, float]):
    orden = sorted(pvals, key=pvals.get)
    m, pasa, sigue = len(orden), {}, True
    for k, nombre in enumerate(orden):
        umbral = ALFA / (m - k)
        sigue = sigue and pvals[nombre] <= umbral
        pasa[nombre] = {"p": pvals[nombre], "umbral_holm": umbral, "rechaza_nulo": sigue}
    return pasa


def spearman(x, y):
    rx = np.argsort(np.argsort(x)); ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1]) if len(x) > 2 else float("nan")


def describir(rts):
    if not rts:
        return {"n": 0}
    v = np.array([x["neto_pct"] for x in rts]); g = v[v > 0]; p = v[v <= 0]
    racha = peor = 0
    for x in v:
        racha = racha + 1 if x <= 0 else 0
        peor = max(peor, racha)
    razones: dict[str, list[float]] = {}
    for x in rts:
        razones.setdefault("+".join(x["razon_salida"]), []).append(x["neto_pct"])
    return {"n": int(v.size), "media_neta_pct": float(v.mean()), "mediana_pct": float(np.median(v)), "desvio_pct": float(v.std(ddof=1)) if v.size > 1 else None,
            "cuantiles_pct": {q: float(np.percentile(v, q)) for q in (5, 25, 50, 75, 95)},
            "tasa_acierto": float((v > 0).mean()), "ganancia_media_pct": float(g.mean()) if g.size else None,
            "perdida_media_pct": float(p.mean()) if p.size else None,
            "factor_beneficio": float(g.sum() / -p.sum()) if p.size and p.sum() < 0 else None, "peor_racha_perdedora": peor,
            "media_bruta_pct": float(np.mean([x["bruto_pct"] for x in rts])),
            "comisiones_medias_pct": float(np.mean([x["comisiones_pct"] for x in rts])),
            "barras_medias": float(np.mean([x["barras"] for x in rts])),
            "suma_retornos_pct": float(v.sum()),
            "por_razon_salida": {k: {"n": len(w), "media_pct": float(np.mean(w))} for k, w in sorted(razones.items())}}


def analizar(res, velas, B, R):
    meses = sorted({v.open_time.strftime("%Y-%m") for v in velas})
    trims = sorted({_trimestre(v.open_time) for v in velas})
    cierre = np.array([v.close for v in velas]); idx_cierre = {v.close_time.isoformat(): i for i, v in enumerate(velas)}
    out = {"configuraciones": {}}
    for nombre, r in res.items():
        rts_all = r["round_trips"]
        rts = [x for x in rts_all if "forced liquidation at end of sample" not in x["razon_salida"]]
        largos = [x for x in rts if x["direccion"] == "long"]
        cortos = [x for x in rts if x["direccion"] != "long"]
        d = {"descripcion": describir(rts), "liquidaciones_finales_excluidas": len(rts_all) - len(rts),
             "metricas_curva": {k: r["metricas"].get(k) for k in ("total_return_pct", "annualized_return_pct", "annualized_volatility_pct",
                                                                  "sharpe", "sortino", "max_drawdown_pct", "exposure_pct")},
             "decisiones": {k: r["decisiones"].get(k) for k in ("signals_generated", "intents_submitted", "fills", "orders_rejected",
                                                                 "protective_stops_unplaced", "stops_tightened", "exits_requested", "budget_rejected")},
             "segundos": r["segundos"]}
        if cortos:
            d["solo_largos"] = describir(largos)
            d["solo_cortos_hipoteticos"] = {**describir(cortos), "bootstrap_mensual": bootstrap_media(cortos, meses, _mes, B, 7)}
        if "gobernadores" in r:
            d["gobernadores"] = r["gobernadores"]
        if rts:
            d["bootstrap_mensual"] = bootstrap_media(rts, meses, _mes, B, C.SEMILLA)
            d["bootstrap_trimestral"] = bootstrap_media(rts, trims, lambda iso: _trimestre(datetime.fromisoformat(iso)), B, C.SEMILLA)
            d["por_subperiodo"] = {}
            for et, a, b in SUBPERIODOS:
                w = [x["neto_pct"] for x in rts if a <= x["entrada"][:10] < b]
                d["por_subperiodo"][et] = {"n": len(w), "media_pct": float(np.mean(w)) if w else None}
            reg: dict[str, list[float]] = {}
            for x in rts:
                e = idx_cierre[x["entrada"]]
                if e - 1 - 720 < 0:
                    continue
                ret = cierre[e - 1] / cierre[e - 1 - 720] - 1
                reg.setdefault("alcista" if ret > 0.10 else "bajista" if ret < -0.10 else "lateral", []).append(x["neto_pct"])
            d["por_regimen_ex_ante_30d"] = {k: {"n": len(w), "media_pct": float(np.mean(w))} for k, w in sorted(reg.items())}
            conf = np.array([x["confianza"] for x in rts]); net = np.array([x["neto_pct"] for x in rts])
            rng = np.random.default_rng(3)
            por_mes = {}
            for i, x in enumerate(rts):
                por_mes.setdefault(_mes(x["entrada"]), []).append(i)
            claves = list(por_mes)
            rs = []
            for _ in range(2000):
                ii = [j for k in rng.integers(0, len(claves), len(claves)) for j in por_mes[claves[k]]]
                if len(ii) > 2:
                    rs.append(spearman(conf[ii], net[ii]))
            d["confianza"] = {"spearman": spearman(conf, net), "ic90_bootstrap_mensual": [float(np.nanpercentile(rs, 5)), float(np.nanpercentile(rs, 95))],
                              "bandas": {f"{a:.2f}-{min(b, 1):.2f}": ({"n": int(((conf >= a) & (conf < b)).sum()),
                                                                       "media_pct": float(net[(conf >= a) & (conf < b)].mean())}
                                                                      if ((conf >= a) & (conf < b)).sum() >= 30 else
                                                                      {"n": int(((conf >= a) & (conf < b)).sum()), "media_pct": "menos de 30: no se informa"})
                                         for a, b in BANDAS}}
        if nombre in (*PRINCIPALES, "S1") and rts:
            medias_nulo, apretados = nulo_emparejado(rts, velas, R, C.SEMILLA)
            m = d["descripcion"]["media_neta_pct"]
            d["nulo_entrada_aleatoria"] = {"replicas": R, "media_nulo_pct": float(medias_nulo.mean()),
                                           "banda90_nulo_pct": [float(np.percentile(medias_nulo, 5)), float(np.percentile(medias_nulo, 95))],
                                           "exceso_sobre_nulo_pct": float(m - medias_nulo.mean()),
                                           "p_nulo": float((1 + (medias_nulo >= m).sum()) / (1 + R)),
                                           "trimestres_sin_holgura": apretados}
        out["configuraciones"][nombre] = d
    # decisión prerregistrada
    p_signo = {k: 1 - out["configuraciones"][k]["bootstrap_mensual"]["P_media_mayor_0"] for k in PRINCIPALES
               if "bootstrap_mensual" in out["configuraciones"][k]}
    p_nulo = {k: out["configuraciones"][k]["nulo_entrada_aleatoria"]["p_nulo"] for k in PRINCIPALES
              if "nulo_entrada_aleatoria" in out["configuraciones"][k]}
    hs, hn = holm(p_signo), holm(p_nulo)
    dec = {}
    for k in PRINCIPALES:
        c = out["configuraciones"][k]
        n = c["descripcion"]["n"]
        if n < 30:
            dec[k] = "EVIDENCIA INSUFICIENTE (menos de 30 operaciones)"
            continue
        if c["bootstrap_mensual"]["ic90"][1] < 0:
            dec[k] = "EVIDENCIA EN CONTRA de una ventaja neta (IC90 de la media neta por operación < 0)"
            continue
        sub_ok = all(v["media_pct"] is not None and v["media_pct"] > 0 for v in c["por_subperiodo"].values())
        x2 = out["configuraciones"][f"S2|{k}"]["descripcion"].get("media_neta_pct")
        if hs[k]["rechaza_nulo"] and hn[k]["rechaza_nulo"] and sub_ok and x2 is not None and x2 > 0:
            dec[k] = "VENTAJA RESPALDADA"
        else:
            dec[k] = "EVIDENCIA INSUFICIENTE"
    out["decision"] = {"holm_signo": hs, "holm_nulo": hn, "veredicto": dec}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--sintetico", type=int, default=0)
    ap.add_argument("--B", type=int, default=10_000)
    ap.add_argument("--R", type=int, default=2_000)
    a = ap.parse_args()
    sal = Path(a.salida)
    if (sal / "resultado_e1.json").exists():
        sys.exit(f"{sal}/resultado_e1.json ya existe: una sola ejecución")
    sal.mkdir(parents=True, exist_ok=True)
    _init(a.sintetico)
    velas = VELAS
    meta = {"tipo": "SINTÉTICO (solo ensayo funcional)" if a.sintetico else "HISTÓRICO REAL", "inicio_utc": datetime.now(timezone.utc).isoformat()}
    if not a.sintetico:
        _, meta["datos"] = C.leer_velas()
        (sal / "manifiesto_datos.json").write_text(json.dumps(meta["datos"], indent=1, ensure_ascii=False))
    with Pool(4, initializer=_init, initargs=(a.sintetico,)) as p:
        res = {r["nombre"]: r for r in p.imap_unordered(_correr, _tareas())}
    # validez (§8), antes de cualquier análisis
    val = {}
    val["invariancia_prefijo_real"] = (res["S1"]["huella_antes_del_corte"] == res["VALIDEZ|S1|prefijo70"]["huella_antes_del_corte"]
                                       and res["S1"]["huella_antes_del_corte"][2] > 100)
    val["solo_largos_sin_cortos"] = all(x["direccion"] == "long" for k, r in res.items() if not k.startswith("S5|") for x in r["round_trips"])
    problemas = []
    for k, r in res.items():
        if k.startswith("S7|"):
            continue
        en_mercado = r["metricas"].get("exposure_pct", 0) / 100 * r["barras"]
        if r["decisiones"]["protective_stops_unplaced"] > 0.03 * max(en_mercado, 1):
            problemas.append(f"{k}: stops sin colocar {r['decisiones']['protective_stops_unplaced']} > 3 % de {en_mercado:.0f} barras en mercado")
        if any(x["barras"] > 2000 for x in r["round_trips"]):
            problemas.append(f"{k}: round trip de más de 2000 barras")
        if r.get("d3", {}).get("piernas_sin_stop_huerfanas", 0) > 0:
            problemas.append(f"{k}: {r['d3']['piernas_sin_stop_huerfanas']} barras con una pierna huérfana sin stop")
    val["stops_y_duraciones"] = not problemas
    val["problemas"] = problemas
    val["todo_ok"] = val["invariancia_prefijo_real"] and val["solo_largos_sin_cortos"] and val["stops_y_duraciones"]
    (sal / "operaciones_por_configuracion.json").write_text(json.dumps({k: r["round_trips"] for k, r in res.items()}, ensure_ascii=False))
    (sal / "validez.json").write_text(json.dumps(val, indent=1, ensure_ascii=False))
    print("VALIDEZ:", json.dumps(val, ensure_ascii=False))
    if not val["todo_ok"]:
        (sal / "corridas_sin_analizar.json").write_text(json.dumps({k: {x: y for x, y in r.items() if x != "round_trips"} for k, r in res.items()},
                                                                   ensure_ascii=False, default=str))
        sys.exit("la validez falla: se detiene ANTES de analizar o interpretar")
    ana = analizar({k: r for k, r in res.items() if not k.startswith("VALIDEZ")}, velas, a.B, a.R)
    costos = ExecutionSimConfig(taker_fee_bps=10.0, maker_fee_bps=10.0, base_slippage_bps=2.0)
    refs = {}
    for nombre, fn, kw in (("buy_and_hold", buy_and_hold, {"costs": costos}), ("efectivo", always_flat, {}),
                           ("cruce_medias_20_50_long_flat", sma_cross, {"costs": costos}),
                           ("volatilidad_objetivo_15", volatility_targeted, {"costs": costos})):
        b = fn(velas, periods_per_year=8760.0, **kw)
        refs[nombre] = {"operaciones": b.trades, **{k: b.metrics.model_dump(mode="json").get(k) for k in
                        ("total_return_pct", "annualized_return_pct", "annualized_volatility_pct", "sharpe", "sortino",
                         "max_drawdown_pct", "exposure_pct")}}
    ana["referencias"] = refs
    ana["meta"] = {**meta, "fin_utc": datetime.now(timezone.utc).isoformat(), "B": a.B, "R": a.R, "validez": val,
                   "barras": len(velas), "primera": velas[0].open_time.isoformat(), "ultima": velas[-1].open_time.isoformat()}
    (sal / "resultado_e1.json").write_text(json.dumps(ana, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({"veredicto": ana["decision"]["veredicto"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
