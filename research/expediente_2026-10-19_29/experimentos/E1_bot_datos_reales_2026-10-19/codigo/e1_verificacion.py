"""E1 — verificación del backtester ANTES de tocar datos reales, solo con datos SINTÉTICOS.

V1  D1/D2: motor original frente a MotorE1 (stop activo y al nivel correcto; sin posiciones trabadas).
V2  Look-ahead por invariancia de prefijo: correr con N barras y con un prefijo de K; todo lo decidido antes de K-1
    (decisiones, operaciones cerradas y equity) debe ser idéntico.
V3  Look-ahead por perturbación del futuro: reemplazar todas las barras posteriores a K por otro camino; idem.
V4  Representación: en barras al azar, recalcular la decisión fuera del motor (ventana de 300, mismo filtro de calidad,
    mismas features, mismo régimen y un StrategyEngine nuevo con SOLO esa estrategia) y comparar con lo registrado.
V5  Modo solo largos: ninguna operación corta.
Uso: python -B e1_verificacion.py <salida.json>
"""

from __future__ import annotations

import json
import random
import sys
from multiprocessing import Pool

import e1_comun as C
from tia.backtest import engine as EM
from tia.core.clock import SimulatedClock
from tia.core.config import StrategyConfig
from tia.data.quality import DataQualityEngine
from tia.quant.features import FeatureBuilder
from tia.regime.classifier import RegimeClassifier
from tia.strategy.engine import StrategyEngine
from tia.strategy.library import build_strategies

N, K = 5000, 3500
CONFIGS = [("trend_following",), ("mean_reversion",), ("breakout",), C.ESTRATEGIAS]


def _clave_decision(d):
    x = d.model_dump(mode="json")
    return json.dumps(x, sort_keys=True)


def _resumen(r, corte_t):
    dec = [_clave_decision(d) for d in r.decision_log if d.bar_close_time < corte_t]
    tr = [json.dumps(t.model_dump(mode="json"), sort_keys=True) for t in r.trades if t.exit_at < corte_t]
    return dec, tr


def _correr(args):
    nombre, velas, est, cortos, original, rechazo = args
    import tia.core.config as CC
    cfg_kw = {}
    if rechazo is not None:
        cfg_kw = {}
    if rechazo == "parciales":  # V6: llenados parciales al 90 % para provocar la carrera de D3
        cfg = C.configuracion(est, cortos=cortos)
        cfg.execution = CC.ExecutionSimConfig(**{**cfg.execution.model_dump(), "partial_fill_probability": 0.9})
        motor = (EM.BacktestEngine if original else C.MotorE1)(cfg, C.universo(cortos), strategies=est)
        with C.escenario(gobernadores_en_vivo=False, retraso=False):
            r = motor.run(velas)
        rts = C.round_trips(r.trades)
        ultima = max((x["entrada"] for x in rts), default=None)
        return nombre, {"round_trips": len(rts), "max_barras_round_trip": max((x["barras"] for x in rts), default=0),
                        "ultima_entrada": ultima, "fin_de_datos": velas[-1].open_time.isoformat(),
                        "d3": dict(getattr(motor, "d3", {}))}
    r = C.correr(velas, est, cortos=cortos, motor_original=original) if rechazo is None else None
    if rechazo is not None:  # V1: rechazo explícito
        cfg = C.configuracion(est, cortos=cortos)
        cfg.execution = CC.ExecutionSimConfig(**{**cfg.execution.model_dump(), "reject_probability": rechazo})
        clase = EM.BacktestEngine if original else C.MotorE1
        obs = []
        orig = clase._sync_protective_stop

        def espia(self, provider, leg, current_id, counts):
            nuevo = orig(self, provider, leg, current_id, counts)
            if leg is not None and leg.exit_pending is None and leg.stop_price is not None:
                o = EM._sync(provider.get_order(nuevo)) if nuevo else None
                obs.append((leg.signal_id, float(leg.stop_price), float(o.stop_price) if o is not None and o.stop_price else None))
            return nuevo
        clase._sync_protective_stop = espia
        try:
            with C.escenario(gobernadores_en_vivo=False, retraso=False):
                r = clase(cfg, C.universo(cortos), strategies=est).run(velas)
        finally:
            clase._sync_protective_stop = orig
        racha, max_racha, previo = 0, 0, None
        for sid, a, b in obs:
            racha = (racha + 1 if sid == previo else 1) if b is None else 0
            previo = sid
            max_racha = max(max_racha, racha)
        return nombre, {"operaciones": len(r.trades), "barras_abiertas": len(obs),
                        "barras_sin_stop_activo": sum(1 for s_, a, b in obs if b is None),
                        "max_barras_seguidas_sin_stop_en_una_posicion": max_racha,
                        "barras_stop_activo_a_otro_nivel": sum(1 for s_, a, b in obs if b is not None and abs(a - b) > 1e-9 * a),
                        "max_barras_en_una_operacion": max((t.bars_held for t in r.trades), default=0),
                        "stops_sin_colocar": r.decisions.protective_stops_unplaced,
                        "ordenes_rechazadas": r.decisions.orders_rejected}
    return nombre, r


def main(salida):
    base = C.sinteticas(N, 11)
    otro_futuro = base[:K] + C.sinteticas(N - K, 99, desde=base[K - 1])
    tareas = []
    for orig in (True, False):
        tareas.append((f"V1|{'original' if orig else 'E1'}", base, ("trend_following",), False, orig, 0.01))
    for est in CONFIGS:
        n = "+".join(est)
        tareas += [(f"V2|{n}|completo", base, est, False, False, None), (f"V2|{n}|prefijo", base[:K], est, False, False, None),
                   (f"V3|{n}|otro_futuro", otro_futuro, est, False, False, None)]
    largo = C.sinteticas(8000, 23)
    for orig in (True, False):
        for est in (("trend_following",), C.ESTRATEGIAS):
            tareas.append((f"V6|{'original' if orig else 'E1'}|{'+'.join(est)}", largo, est, False, orig, "parciales"))
    tareas += [("V2|fusion_cortos|completo", base, C.ESTRATEGIAS, True, False, None),
               ("V2|fusion_cortos|prefijo", base[:K], C.ESTRATEGIAS, True, False, None)]
    with Pool(4) as p:
        res = dict(p.map(_correr, tareas))
    out = {"datos": f"SINTÉTICOS ({N} velas 1 h, semillas 11 y 99); no son históricos", "V1": {}, "V2": {}, "V3": {}, "V4": {}, "V5": {}, "V6": {}}
    out["V1"] = {k.split("|")[1]: v for k, v in res.items() if k.startswith("V1")}
    corte = base[K - 1].open_time   # todo lo anterior a la última barra del prefijo
    for est in [*["+".join(e) for e in CONFIGS], "fusion_cortos"]:
        comp = res[f"V2|{est}|completo"]
        for prueba, otro in (("V2", res.get(f"V2|{est}|prefijo")), ("V3", res.get(f"V3|{est}|otro_futuro"))):
            if otro is None:
                continue
            d1, t1 = _resumen(comp, corte)
            d2, t2 = _resumen(otro, corte)
            eq = list(comp.equity_curve[:K - 2]) == list(otro.equity_curve[:K - 2])
            out[prueba][est] = {"decisiones_comparadas": len(d1), "decisiones_identicas": d1 == d2,
                                "operaciones_comparadas": len(t1), "operaciones_identicas": t1 == t2,
                                "equity_identica_hasta_K-2": eq, "ok": d1 == d2 and t1 == t2 and eq and len(d1) > 100}
    # V4 representación: se recorre la serie en orden con un clasificador propio (tiene histéresis), llamando a
    # classify exactamente en las barras en que lo llama el motor (tras el warmup, sin fallo duro de calidad, no la
    # última); en 300 barras al azar se recalcula la señal con un StrategyEngine nuevo de SOLO esa estrategia.
    rnd = random.Random(5)
    for est in CONFIGS[:3]:
        r = res[f"V2|{'+'.join(est)}|completo"]
        por_t = {d.bar_close_time: d for d in r.decision_log}
        cfg = C.configuracion(est, cortos=False)
        muestras = set(rnd.sample(sorted(por_t), 300))
        clasificador, fb, qe = RegimeClassifier(), FeatureBuilder(), DataQualityEngine(cfg.data_quality)
        warmup = max(cfg.warmup_bars, fb.min_bars)
        iguales = comparadas = 0
        for i, vela in enumerate(base[:-1]):
            if i + 1 < warmup:
                continue
            t = vela.close_time
            ventana = base[max(0, i + 1 - cfg.lookback_bars): i + 1]
            q = qe.evaluate(symbol=C.SIMBOLO, timeframe="1h", candles=ventana, now=t, last_feed_message_at=t)
            if q.hard_fail:
                continue
            f = fb.build(C.SIMBOLO, "1h", ventana)
            reg = clasificador.classify(f, now=t)
            if t in muestras:
                se = StrategyEngine(build_strategies(est), StrategyConfig(enabled=est), SimulatedClock(t))
                sig, _ = se.evaluate(features=f, regime=reg, quality=q, correlation_id="rep")
                d = por_t[t]
                comparadas += 1
                iguales += (sig.direction == d.direction and abs(sig.confidence - d.confidence) < 1e-12
                            and reg.regime == d.regime and f.feature_hash == d.feature_hash)
        out["V4"]["+".join(est)] = {"barras_comparadas": comparadas, "decisiones_replicadas_identicas": iguales,
                                     "ok": comparadas == 300 and iguales == comparadas}
    for est in CONFIGS:
        r = res[f"V2|{'+'.join(est)}|completo"]
        cortas = sum(1 for t in r.trades if t.direction.value != "long")
        out["V5"]["+".join(est)] = {"operaciones": len(r.trades), "operaciones_cortas": cortas, "ok": cortas == 0}
    rf = res["V2|fusion_cortos|completo"]
    out["V5"]["fusion_con_cortos_hipoteticos"] = {"operaciones": len(rf.trades),
                                                   "operaciones_cortas": sum(1 for t in rf.trades if t.direction.value != "long")}
    out["V6"] = {k.split("|", 1)[1]: v for k, v in res.items() if k.startswith("V6")}
    for k, v in list(out["V6"].items()):
        if k.startswith("E1"):
            v["ok"] = (v["max_barras_round_trip"] < 500 and v["d3"].get("piernas_sin_stop_huerfanas", 1) == 0
                       and v["ultima_entrada"] is not None and v["ultima_entrada"] >= "2020-10-01")
    v1 = out["V1"]
    # Criterio corregido (el inicial, "0 barras sin stop", ignoraba que el simulador rechaza el 1 % de los stops):
    # ninguna posición pasa más de 1 barra seguida sin stop (un rechazo se reintenta en la barra siguiente) y el stop
    # activo está siempre al nivel vigente de la pierna.
    out["V1"]["criterio"] = "max_barras_seguidas_sin_stop_en_una_posicion <= 1 y barras_stop_activo_a_otro_nivel == 0"
    out["V1"]["ok"] = (v1["E1"]["max_barras_seguidas_sin_stop_en_una_posicion"] <= 1 and v1["E1"]["barras_stop_activo_a_otro_nivel"] == 0)
    out["todo_ok"] = all(v.get("ok", True) for g in ("V2", "V3", "V4", "V5", "V6") for v in out[g].values()) and out["V1"]["ok"]
    json.dump(out, open(salida, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
