"""SIM-1 — ejecución y análisis prerregistrados (prerregistro/PRERREGISTRO_SIM1.md).

Uso:
  python -B sim1.py dev   <dir_salida_nuevo>                    # DEV-BTC y DEV-ETH; validez; M1
  python -B sim1.py final <dir_salida_nuevo> <m1_promocion.json> # OOS-ETH, UNA vez (candado)

Motor: el ``BacktestEngine`` del paquete en PYTHONPATH (corregido), sin subclases. Estadística: las funciones de E1
(``e1.describir``, ``bootstrap_media``, ``nulo_emparejado``, ``holm``, ``spearman``) importadas sin cambios.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import e1 as E1A
import e1_comun as C
import sim1_comun as S
import tia.backtest.engine as EM
from tia.backtest.baselines import always_flat, buy_and_hold, sma_cross, volatility_targeted
from tia.backtest.engine import BacktestEngine
from tia.core.config import ExecutionSimConfig, RiskLimits

RAIZ_NUEVA = Path(__file__).resolve().parents[1] / "datos" / "vision"
RAIZ_E1 = C.DATOS
CANDADO = Path(__file__).resolve().parents[1] / "registro" / "CANDADO_OOS_ETH.txt"
CORTE = "2023-01-01T00:00:00+00:00"
ALFA = 0.05
B, R = 10_000, 2_000
CONFIGS = {"P1": ("trend_following",), "P2": ("mean_reversion",), "P3": ("breakout",), "S1": C.ESTRATEGIAS}
VARIANTES = {"": {}, "S2|": {"comision_bps": 20.0}, "S3|": {"retraso": True},
             "S4|": {"comision_bps": 0.0, "deslizamiento_base_bps": 0.0, "impacto": 0.0},
             "S6|": {"gobernadores_en_vivo": True}}
SUBPERIODOS = {
    "DEV-BTC": [("2017-08→2019-09", "2017-08-01", "2019-10-01"), ("2019-10→2021-12", "2019-10-01", "2022-01-01"),
                ("2022", "2022-01-01", "2023-01-01"), ("2023→2026-05", "2023-01-01", "2026-06-01")],
    "DEV-ETH": [("2017-08→2019-12", "2017-08-01", "2020-01-01"), ("2020→2021", "2020-01-01", "2022-01-01"),
                ("2022", "2022-01-01", "2023-01-01")],
    "OOS-ETH": [("2023", "2023-01-01", "2024-01-01"), ("2024", "2024-01-01", "2025-01-01"),
                ("2025-01→2026-05", "2025-01-01", "2026-06-01")],
}
PROCESOS = int(os.environ.get("SIM1_PROCESOS", "4"))
SIMBOLO = {"DEV-BTC": "BTCUSDT", "DEV-ETH": "ETHUSDT", "OOS-ETH": "ETHUSDT"}
VELAS: dict[str, list] = {}
INICIO: dict[str, int] = {}  # índice de la primera vela con decisión


def _cargar(conjuntos):
    btc = eth = None
    for c in conjuntos:
        if SIMBOLO[c] == "BTCUSDT" and btc is None:
            btc, _ = S.leer_velas([RAIZ_NUEVA, RAIZ_E1], "BTCUSDT")
        if SIMBOLO[c] == "ETHUSDT" and eth is None:
            eth, _ = S.leer_velas([RAIZ_NUEVA], "ETHUSDT")
    corte = datetime.fromisoformat(CORTE)
    for c in conjuntos:
        if c == "DEV-BTC":
            VELAS[c], INICIO[c] = btc, 119
        elif c == "DEV-ETH":
            VELAS[c], INICIO[c] = [v for v in eth if v.open_time < corte], 119
        else:
            k = next(i for i, v in enumerate(eth) if v.open_time >= corte)
            VELAS[c], INICIO[c] = eth[k - 299:], 299


def _costo(tarea):
    """Orden de despacho: las corridas largas primero (no cambia ningún resultado)."""
    return (tarea[0] == "DEV-BTC", "S1" in tarea[1])


def _init(conjuntos):
    _cargar(conjuntos)


def _cfg(est, conjunto, kw, q):
    kw = dict(kw)
    retraso, gob = kw.pop("retraso", False), kw.pop("gobernadores_en_vivo", False)
    cfg = C.configuracion(est, cortos=False, gobernadores_en_vivo=gob, dataset=f"{SIMBOLO[conjunto]}-1h-{conjunto}", **kw)
    cfg.warmup_bars = INICIO[conjunto] + 1
    if q is not None:
        cfg.risk = RiskLimits(min_confidence=q) if gob else RiskLimits(max_drawdown_pct=90.0, min_confidence=q)
    return cfg, retraso, gob


def _huella(r, corte_t):
    d = "\n".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) for x in r.decision_log if x.bar_close_time < corte_t)
    t = "\n".join(json.dumps(x.model_dump(mode="json"), sort_keys=True) for x in r.trades if x.exit_at < corte_t)
    return hashlib.sha256(d.encode()).hexdigest(), hashlib.sha256(t.encode()).hexdigest(), d.count("\n") + 1


def _curva(r, desde):
    """Equity al cierre de cada día UTC, desde ``desde`` (la primera vela con decisión)."""
    dias: dict[str, float] = {}
    for t, e in zip(r.equity_timestamps, r.equity_curve):
        if t >= desde:
            dias[t.strftime("%Y-%m-%d")] = e
    return dias


def _correr(tarea):
    conjunto, nombre, q, prefijo = tarea
    pref, base = (nombre.split("|")[0] + "|", nombre.split("|")[1]) if "|" in nombre else ("", nombre)
    if base == "M1":
        est = CONFIGS["P3"]
    else:
        est = CONFIGS[base.split("#")[0]]
    velas = VELAS[conjunto]
    if prefijo:
        velas = velas[: int(len(velas) * prefijo)]
    cfg, retraso, gob = _cfg(est, conjunto, VARIANTES[pref], q)
    motor = BacktestEngine(cfg, S.universo(SIMBOLO[conjunto]), strategies=est)
    assert type(motor) is EM.BacktestEngine
    t0 = time.time()
    with C.escenario(gobernadores_en_vivo=gob, retraso=retraso):
        r = motor.run(velas)
    rts = C.round_trips(r.trades)
    desde = velas[INICIO[conjunto]].open_time
    corte70 = VELAS[conjunto][int(len(VELAS[conjunto]) * 0.70) - 1].open_time
    out = {"conjunto": conjunto, "nombre": nombre + (f"@prefijo{prefijo}" if prefijo else ""), "estrategias": list(est),
           "q_min_confianza": q, "barras": len(velas), "primera_decision": desde.isoformat(),
           "segundos": round(time.time() - t0, 1), "round_trips": rts,
           "metricas_motor": r.metrics.model_dump(mode="json"), "decisiones": r.decisions.model_dump(mode="json"),
           "advertencias": list(r.warnings), "higiene": dict(motor.order_hygiene),
           "comisiones_usdt": float(sum(t.fees for t in r.trades)),
           "nocional_entradas_usdt": float(sum(x["nocional"] for x in rts)),
           "equity_diaria": _curva(r, desde), "capital_inicial": cfg.initial_capital,
           "huella_operaciones": hashlib.sha256(json.dumps(rts, sort_keys=True).encode()).hexdigest(),
           "huella_antes_del_corte70": _huella(r, corte70)}
    return out


# ------------------------------------------------------------------------------------------------ análisis
def _mes(iso):
    return iso[:7]


def _capital(r):
    eq = np.array(list(r["equity_diaria"].values()))
    ini, fin = float(r["capital_inicial"]), float(eq[-1])
    ret = np.diff(np.concatenate([[ini], eq])) / np.concatenate([[ini], eq[:-1]])
    anios = len(ret) / 365.0
    pico = np.maximum.accumulate(np.concatenate([[ini], eq]))
    dd = float(((np.concatenate([[ini], eq]) - pico) / pico).min() * -100)
    sd = float(ret.std(ddof=1)) if len(ret) > 1 else float("nan")
    abajo = ret[ret < 0]
    sharpe = float(ret.mean() / sd * math.sqrt(365)) if sd and sd > 0 else None
    sortino = float(ret.mean() / math.sqrt((abajo ** 2).mean()) * math.sqrt(365)) if abajo.size else None
    # IC90 del Sharpe: bootstrap de bloques de mes calendario sobre los retornos diarios
    meses = [d[:7] for d in r["equity_diaria"]]
    grupos: dict[str, list[int]] = {}
    for i, m in enumerate(meses):
        grupos.setdefault(m, []).append(i)
    claves = list(grupos)
    rng = np.random.default_rng(C.SEMILLA)
    sh = []
    for _ in range(2000):
        ii = [j for k in rng.integers(0, len(claves), len(claves)) for j in grupos[claves[k]]]
        x = ret[ii]
        s = x.std(ddof=1)
        if s > 0:
            sh.append(x.mean() / s * math.sqrt(365))
    return {"capital_inicial": ini, "capital_final": fin, "retorno_neto_total_pct": (fin / ini - 1) * 100,
            "retorno_anualizado_pct": ((fin / ini) ** (1 / anios) - 1) * 100 if anios > 0 else None,
            "volatilidad_anualizada_pct": sd * math.sqrt(365) * 100 if sd == sd else None,
            "sharpe_diario_anualizado": sharpe,
            "sharpe_ic90_bootstrap_mensual": [float(np.percentile(sh, 5)), float(np.percentile(sh, 95))] if sh else None,
            "sortino": sortino, "max_caida_pct": dd, "dias": len(ret),
            "nota_sharpe": "con posiciones de ≈1 % del capital, el Sharpe de la cuenta es casi todo efectivo; la medida "
                           "relevante de la regla es la media neta por operación"}


def _exposicion(r):
    """Velas en mercado sobre las velas con decisión (sin el calentamiento); la del motor incluye el calentamiento."""
    en_mercado = sum(x["barras"] for x in r["round_trips"])
    return {"pct_velas_en_mercado_aprox": 100.0 * en_mercado / max(1, r["barras"] - _inicio_de(r)),
            "exposure_pct_motor": r["metricas_motor"].get("exposure_pct"), "barras_con_decision": r["barras"] - _inicio_de(r)}


def _inicio_de(r):
    return 299 if r["conjunto"] == "OOS-ETH" else 119


def analizar(res, conjunto, velas_conj):
    ini = _inicio_de({"conjunto": conjunto})
    ventana = velas_conj[ini:]
    meses = sorted({v.open_time.strftime("%Y-%m") for v in ventana})
    cierre = np.array([v.close for v in velas_conj])
    idx_cierre = {v.close_time.isoformat(): i for i, v in enumerate(velas_conj)}
    out = {}
    for nombre, r in res.items():
        rts_all = r["round_trips"]
        rts = [x for x in rts_all if "forced liquidation at end of sample" not in x["razon_salida"]]
        d = {"q_min_confianza": r["q_min_confianza"], "descripcion": E1A.describir(rts),
             "liquidaciones_finales_excluidas": len(rts_all) - len(rts), "capital": _capital(r),
             "exposicion": _exposicion(r), "comisiones_usdt": r["comisiones_usdt"],
             "comisiones_pct_del_nocional_operado": (100 * r["comisiones_usdt"] / r["nocional_entradas_usdt"]
                                                      if r["nocional_entradas_usdt"] else None),
             "decisiones": {k: r["decisiones"].get(k) for k in ("signals_generated", "intents_submitted", "fills", "orders_rejected",
                                                                 "protective_stops_unplaced", "stops_tightened", "exits_requested",
                                                                 "budget_rejected", "risk_rejected")},
             "higiene": r["higiene"], "advertencias": r["advertencias"], "segundos": r["segundos"]}
        if rts:
            d["bootstrap_mensual"] = E1A.bootstrap_media(rts, meses, _mes, B, C.SEMILLA)
            d["p_unilateral"] = 1 - d["bootstrap_mensual"]["P_media_mayor_0"]
            d["por_subperiodo"] = {}
            for et, a, b in SUBPERIODOS[conjunto]:
                w = [x["neto_pct"] for x in rts if a <= x["entrada"][:10] < b]
                d["por_subperiodo"][et] = {"n": len(w), "media_pct": float(np.mean(w)) if w else None}
            reg: dict[str, list[float]] = {}
            for x in rts:
                e = idx_cierre.get(x["entrada"])
                if e is None or e - 1 - 720 < 0:
                    continue
                ret = cierre[e - 1] / cierre[e - 1 - 720] - 1
                reg.setdefault("alcista" if ret > 0.10 else "bajista" if ret < -0.10 else "lateral", []).append(x["neto_pct"])
            d["por_regimen_ex_ante_30d"] = {k: {"n": len(w), "media_pct": float(np.mean(w))} for k, w in sorted(reg.items())}
            conf = np.array([x["confianza"] for x in rts]); net = np.array([x["neto_pct"] for x in rts])
            d["confianza"] = {"spearman": E1A.spearman(conf, net), "min": float(conf.min()), "max": float(conf.max()),
                              "p66_67": float(np.percentile(conf, 100 * 2 / 3))}
        if "|" not in nombre and rts:
            medias_nulo, apretados = E1A.nulo_emparejado(rts, velas_conj, R, C.SEMILLA, warmup=ini)
            m = d["descripcion"]["media_neta_pct"]
            d["nulo_entrada_aleatoria"] = {"replicas": R, "media_nulo_pct": float(medias_nulo.mean()),
                                           "banda90_nulo_pct": [float(np.percentile(medias_nulo, 5)), float(np.percentile(medias_nulo, 95))],
                                           "exceso_sobre_nulo_pct": float(m - medias_nulo.mean()),
                                           "p_nulo": float((1 + (medias_nulo >= m).sum()) / (1 + R)),
                                           "trimestres_sin_holgura": apretados}
        out[nombre] = d
    # costo total implícito por operación (media S4 − media base) y sensibilidades
    for k in list(CONFIGS) + ["M1"]:
        if k in out and f"S4|{k}" in out and out[k]["descripcion"].get("n"):
            out[k]["costo_total_implicito_por_operacion_pct"] = (out[f"S4|{k}"]["descripcion"]["media_neta_pct"]
                                                                 - out[k]["descripcion"]["media_neta_pct"])
            out[k]["sensibilidad"] = {v: out[f"{v}|{k}"]["descripcion"].get("media_neta_pct")
                                      for v in ("S2", "S3", "S4", "S6") if f"{v}|{k}" in out}
    return out


def referencias(velas_conj, ini):
    costos = ExecutionSimConfig(taker_fee_bps=10.0, maker_fee_bps=10.0, base_slippage_bps=2.0)
    v = velas_conj[ini:]
    refs = {}
    for nombre, fn, kw in (("buy_and_hold", buy_and_hold, {"costs": costos}), ("efectivo", always_flat, {}),
                           ("cruce_medias_20_50_long_flat", sma_cross, {"costs": costos}),
                           ("volatilidad_objetivo_15", volatility_targeted, {"costs": costos})):
        b = fn(v, periods_per_year=8760.0, **kw)
        refs[nombre] = {"operaciones": b.trades, **{k: b.metrics.model_dump(mode="json").get(k) for k in
                        ("total_return_pct", "annualized_return_pct", "annualized_volatility_pct", "sharpe", "sortino",
                         "max_drawdown_pct", "exposure_pct")}}
    return refs


def validez(res, extra):
    problemas, avisos = [], []
    for k, r in res.items():
        en_mercado = sum(x["barras"] for x in r["round_trips"])
        if r["decisiones"]["protective_stops_unplaced"] > 0.03 * max(en_mercado, 1):
            problemas.append(f"{k}: stops sin colocar {r['decisiones']['protective_stops_unplaced']} > 3 % de {en_mercado} barras en mercado")
        if any(x["barras"] > 2000 for x in r["round_trips"]):
            problemas.append(f"{k}: round trip de más de 2000 barras")
        if any(x["direccion"] != "long" for x in r["round_trips"]):
            problemas.append(f"{k}: operación corta")
        if r["higiene"].get("exits_done_with_position_left", 0):
            avisos.append(f"{k}: {r['higiene']['exits_done_with_position_left']} salidas terminadas con posición restante (red de seguridad D3)")
    return {**extra, "problemas": problemas, "avisos_higiene": avisos,
            "todo_ok": not problemas and all(v for v in extra.values() if isinstance(v, bool))}


def _escribir(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _huellas_codigo():
    aqui = Path(__file__).resolve().parent
    return {"sim1.py": _sha(aqui / "sim1.py"), "sim1_comun.py": _sha(aqui / "sim1_comun.py"),
            "e1.py": _sha(Path(E1A.__file__)), "e1_comun.py": _sha(Path(C.__file__)),
            "tia/backtest/engine.py": _sha(Path(EM.__file__)),
            "tia/execution/paper.py": _sha(Path(EM.__file__).parents[1] / "execution" / "paper.py")}


def main_dev(sal):
    conjuntos = ["DEV-BTC", "DEV-ETH"]
    _cargar(conjuntos)
    # DEV-BTC: base, S2 y S4 (E1 ya tiene S3 y S6 para BTC 2019-10+); DEV-ETH: todas las variantes
    tareas = [(c, f"{v}{k}", None, None) for c in conjuntos for k in CONFIGS for v in VARIANTES
              if c == "DEV-ETH" or v in ("", "S2|", "S4|")]
    tareas += [("DEV-ETH", "S1", None, 0.70), ("DEV-ETH", "P3#repeticion", None, None)]
    with Pool(PROCESOS, initializer=_init, initargs=(conjuntos,)) as p:
        res = {(r["conjunto"], r["nombre"]): r for r in p.imap_unordered(_correr, sorted(tareas, key=_costo, reverse=True))}
    # M1: q del percentil 66,67 de la confianza de P3 base en DEV del mismo activo
    q = {}
    for c in conjuntos:
        conf = [x["confianza"] for x in res[(c, "P3")]["round_trips"] if "forced liquidation at end of sample" not in x["razon_salida"]]
        q[c] = round(float(np.percentile(conf, 100 * 2 / 3)), 3)
    tareas_m1 = [(c, "M1", q[c], None) for c in conjuntos] + [("DEV-ETH", f"{v}M1", q["DEV-ETH"], None) for v in ("S2|", "S4|")]
    with Pool(PROCESOS, initializer=_init, initargs=(conjuntos,)) as p:
        for r in p.imap_unordered(_correr, tareas_m1):
            res[(r["conjunto"], r["nombre"])] = r
    pref = res[("DEV-ETH", "S1@prefijo0.7")]["huella_antes_del_corte70"]
    comp = res[("DEV-ETH", "S1")]["huella_antes_del_corte70"]
    extra = {"invariancia_prefijo_DEV_ETH": pref == comp and comp[2] > 100,
             "determinismo_P3_DEV_ETH": res[("DEV-ETH", "P3")]["huella_operaciones"] == res[("DEV-ETH", "P3#repeticion")]["huella_operaciones"],
             "m1_respeta_q": all(x["confianza"] >= q[c] - 1e-12 for c in conjuntos for x in res[(c, "M1")]["round_trips"])}
    val = validez({f"{c}|{n}": r for (c, n), r in res.items()}, extra)
    _escribir(sal / "operaciones_dev.json", {f"{c}|{n}": r["round_trips"] for (c, n), r in res.items()})
    _escribir(sal / "validez_dev.json", val)
    print("VALIDEZ DEV:", json.dumps(val, ensure_ascii=False)[:1500])
    if not val["todo_ok"]:
        _escribir(sal / "corridas_dev_sin_analizar.json", {f"{c}|{n}": {x: y for x, y in r.items() if x != "round_trips"} for (c, n), r in res.items()})
        sys.exit("la validez de DEV falla: se detiene antes de analizar")
    ana = {}
    for c in conjuntos:
        sub = {n: r for (cc, n), r in res.items() if cc == c and "@" not in n and "#" not in n}
        ana[c] = {"configuraciones": analizar(sub, c, VELAS[c]), "referencias": referencias(VELAS[c], INICIO[c]),
                  "barras": len(VELAS[c]), "primera": VELAS[c][0].open_time.isoformat(), "ultima": VELAS[c][-1].open_time.isoformat()}
    # regla de promoción de M1 (§6)
    m1 = {c: [x for x in res[(c, "M1")]["round_trips"] if "forced liquidation at end of sample" not in x["razon_salida"]] for c in conjuntos}
    medias = {c: (float(np.mean([x["neto_pct"] for x in m1[c]])) if m1[c] else None) for c in conjuntos}
    meses = sorted({v.open_time.strftime("%Y-%m") for c in conjuntos for v in VELAS[c][INICIO[c]:]})
    comb = [x for c in conjuntos for x in m1[c]]
    bs = E1A.bootstrap_media(comb, meses, _mes, B, C.SEMILLA) if comb else None
    promovida = (all(m is not None and m > 0 for m in medias.values()) and all(len(m1[c]) >= 30 for c in conjuntos)
                 and bs is not None and bs["ic90"][0] > 0)
    prom = {"q": q, "medias_netas_M1_pct": medias, "n": {c: len(m1[c]) for c in conjuntos}, "bootstrap_combinado": bs,
            "promovida": promovida, "q_para_OOS_ETH": q["DEV-ETH"] if promovida else None}
    _escribir(sal / "m1_promocion.json", prom)
    _escribir(sal / "resultado_dev.json", {"conjuntos": ana, "m1": prom, "validez": val, "huellas_codigo": _huellas_codigo(),
                                           "fin_utc": datetime.now(timezone.utc).isoformat()})
    print(json.dumps({"m1": prom}, ensure_ascii=False, default=str)[:800])


def main_final(sal, m1_path):
    fd = os.open(CANDADO, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # falla si ya se corrió: una sola lectura
    os.write(fd, json.dumps({"inicio_utc": datetime.now(timezone.utc).isoformat(), "huellas_codigo": _huellas_codigo(),
                             "m1_promocion_sha256": _sha(m1_path)}, indent=1).encode())
    os.close(fd)
    prom = json.loads(Path(m1_path).read_text())
    _cargar(["OOS-ETH"])
    tareas = [("OOS-ETH", f"{v}{k}", None, None) for k in CONFIGS for v in VARIANTES]
    if prom["promovida"]:
        tareas += [("OOS-ETH", f"{v}M1", prom["q_para_OOS_ETH"], None) for v in ("", "S2|", "S4|")]
    with Pool(PROCESOS, initializer=_init, initargs=(["OOS-ETH"],)) as p:
        res = {r["nombre"]: r for r in p.imap_unordered(_correr, tareas)}
    val = validez({f"OOS-ETH|{n}": r for n, r in res.items()}, {})
    _escribir(sal / "operaciones_oos.json", {n: r["round_trips"] for n, r in res.items()})
    _escribir(sal / "validez_oos.json", val)
    print("VALIDEZ OOS:", json.dumps(val, ensure_ascii=False)[:1500])
    if not val["todo_ok"]:
        _escribir(sal / "corridas_oos_sin_analizar.json", {n: {x: y for x, y in r.items() if x != "round_trips"} for n, r in res.items()})
        sys.exit("la validez de OOS falla: se detiene antes de interpretar")
    ana = analizar(res, "OOS-ETH", VELAS["OOS-ETH"])
    # decisión (§8): P3 primaria a α; secundarias con Holm
    secundarias = [k for k in ("P1", "P2", "S1") if k in ana] + (["M1"] if prom["promovida"] else [])
    hs = E1A.holm({k: ana[k]["p_unilateral"] for k in secundarias if "p_unilateral" in ana[k]})
    dec = {}
    for k in ["P3", *secundarias]:
        c = ana[k]
        n = c["descripcion"].get("n", 0)
        if n < 30:
            dec[k] = "INSUFICIENTE (muestra)"
            continue
        if c["bootstrap_mensual"]["ic90"][1] < 0:
            dec[k] = "EN CONTRA"
            continue
        p_ok = c["p_unilateral"] <= ALFA if k == "P3" else hs.get(k, {}).get("rechaza_nulo", False)
        nulo_ok = c.get("nulo_entrada_aleatoria", {}).get("p_nulo", 1.0) <= 0.05
        sub_ok = all(v["media_pct"] is not None and v["media_pct"] > 0 for v in c["por_subperiodo"].values())
        x2 = ana.get(f"S2|{k}", {}).get("descripcion", {}).get("media_neta_pct")
        dec[k] = "VENTAJA RESPALDADA (histórica)" if (p_ok and nulo_ok and sub_ok and x2 is not None and x2 > 0) else "NO CONCLUYENTE"
    out = {"configuraciones": ana, "referencias": referencias(VELAS["OOS-ETH"], INICIO["OOS-ETH"]),
           "decision": {"primaria": "P3", "alfa": ALFA, "holm_secundarias": hs, "veredicto": dec,
                        "consecuencia": "ningún resultado cambia validada_para_operar ni habilita capital"},
           "m1": prom, "validez": val, "huellas_codigo": _huellas_codigo(), "barras": len(VELAS["OOS-ETH"]),
           "primera_decision": VELAS["OOS-ETH"][299].open_time.isoformat(), "ultima": VELAS["OOS-ETH"][-1].open_time.isoformat(),
           "fin_utc": datetime.now(timezone.utc).isoformat()}
    _escribir(sal / "resultado_oos.json", out)
    print(json.dumps(dec, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    modo, salida = sys.argv[1], Path(sys.argv[2])
    if salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} no está vacío")
    salida.mkdir(parents=True, exist_ok=True)
    if modo == "dev":
        main_dev(salida)
    elif modo == "final":
        main_final(salida, Path(sys.argv[3]))
    else:
        sys.exit("modo: dev | final")
