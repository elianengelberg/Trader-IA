"""MS-2 — Verificación del BacktestEngine CORREGIDO con datos SINTÉTICOS (generador de E1). No es evidencia económica.

Las mismas pruebas de E1 (e1_verificacion.py), pero sobre el motor del paquete ya corregido, sin la subclase MotorE1:
  V1  rechazos al 1 %: ninguna pierna sin stop activo más de 8 barras seguidas; el stop en el libro al nivel de la pierna.
  V2  invariancia de prefijo: N barras contra un prefijo de K; todo lo decidido antes de K-1 es idéntico.
  V3  perturbación del futuro: las barras posteriores a K se reemplazan por otro camino; ídem.
  V6  parciales al 90 % sobre 8000 barras: ningún round trip de más de 2000 barras y entradas hasta el final de los datos.
  DET determinismo entre procesos: la misma corrida en dos procesos da la misma huella.
Uso: python -B verificacion_motor.py <salida.json>
"""

import hashlib
import json
import sys
from multiprocessing import Pool

import e1_comun as C
import tia.backtest.engine as EM
import tia.core.config as CC
from tia.backtest.engine import BacktestEngine

N, K = 5000, 3500
CONFIGS = [("trend_following",), ("mean_reversion",), ("breakout",), C.ESTRATEGIAS]


def _clave(x):
    return json.dumps(x.model_dump(mode="json"), sort_keys=True)


def _resumen(r, corte_t):
    dec = [_clave(d) for d in r.decision_log if d.bar_close_time < corte_t]
    tr = [_clave(t) for t in r.trades if t.exit_at < corte_t]
    return dec, tr


def _motor(est, **ejec):
    cfg = C.configuracion(est, cortos=False)
    if ejec:
        cfg.execution = CC.ExecutionSimConfig(**{**cfg.execution.model_dump(), **ejec})
    return BacktestEngine(cfg, C.universo(False), strategies=est)


def _correr(args):
    nombre, velas, est, modo = args
    if modo == "rechazos":
        motor = _motor(est, reject_probability=0.01)
        obs = []
        orig = BacktestEngine._sync_protective_stop

        def espia(self, provider, leg, current_id, counts, **kw):
            nuevo = orig(self, provider, leg, current_id, counts, **kw)
            if leg is not None and leg.exit_pending is None and leg.stop_price is not None:
                o = EM._sync(provider.get_order(nuevo)) if nuevo else None
                activo = o is not None and not o.state.is_terminal
                obs.append((leg.signal_id, float(leg.stop_price), float(o.stop_price) if activo and o.stop_price else None))
            return nuevo
        BacktestEngine._sync_protective_stop = espia
        try:
            with C.escenario(gobernadores_en_vivo=False, retraso=False):
                r = motor.run(velas)
        finally:
            BacktestEngine._sync_protective_stop = orig
        racha = max_racha = 0
        previo = None
        for sid, a, b in obs:
            racha = (racha + 1 if sid == previo else 1) if b is None else 0
            previo = sid
            max_racha = max(max_racha, racha)
        otro_nivel = sum(1 for _, a, b in obs if b is not None and abs(a - b) > 1e-9 * a)
        return nombre, {"operaciones": len(r.trades), "barras_abiertas": len(obs), "max_barras_seguidas_sin_stop": max_racha,
                        "barras_stop_a_otro_nivel": otro_nivel, "ordenes_rechazadas": r.decisions.orders_rejected,
                        "higiene": motor.order_hygiene,
                        "ok": len(r.trades) > 0 and max_racha <= 8 and otro_nivel == 0}
    if modo == "parciales":
        motor = _motor(est, partial_fill_probability=0.9)
        with C.escenario(gobernadores_en_vivo=False, retraso=False):
            r = motor.run(velas)
        rts = C.round_trips(r.trades)
        ultima = max((x["entrada"] for x in rts), default="")
        mx = max((x["barras"] for x in rts), default=0)
        return nombre, {"round_trips": len(rts), "max_barras_round_trip": mx, "ultima_entrada": ultima,
                        "fin_de_datos": velas[-1].open_time.isoformat(), "higiene": motor.order_hygiene,
                        "ok": len(rts) > 20 and mx <= 2000 and ultima[:7] >= velas[-1].open_time.isoformat()[:7]}
    motor = _motor(est)
    with C.escenario(gobernadores_en_vivo=False, retraso=False):
        r = motor.run(velas)
    return nombre, r


def main(salida):
    base = C.sinteticas(N, 11)
    otro_futuro = base[:K] + C.sinteticas(N - K, 99, desde=base[K - 1])
    largo = C.sinteticas(8000, 23)
    tareas = [("V1", base, ("trend_following",), "rechazos")]
    for est in CONFIGS:
        n = "+".join(est)
        tareas += [(f"V2|{n}|completo", base, est, None), (f"V2|{n}|prefijo", base[:K], est, None),
                   (f"V3|{n}|otro_futuro", otro_futuro, est, None)]
    tareas += [(f"V6|{'+'.join(est)}", largo, est, "parciales") for est in (("trend_following",), C.ESTRATEGIAS)]
    tareas += [("DET|breakout|b", base, ("breakout",), None)]
    with Pool(int(sys.argv[2]) if len(sys.argv) > 2 else 3) as p:
        res = dict(p.map(_correr, tareas))
    corte = base[K - 1].open_time
    out = {"datos": f"SINTÉTICOS (generador de E1; {N} y 8000 velas 1 h); no son históricos",
           "motor": EM.__file__, "sha256_engine": hashlib.sha256(open(EM.__file__, "rb").read()).hexdigest(),
           "V1": res["V1"], "V2": {}, "V3": {}, "V6": {k.split("|", 1)[1]: v for k, v in res.items() if k.startswith("V6|")}}
    for est in CONFIGS:
        n = "+".join(est)
        comp = _resumen(res[f"V2|{n}|completo"], corte)
        for prueba, otro in (("V2", res[f"V2|{n}|prefijo"]), ("V3", res[f"V3|{n}|otro_futuro"])):
            o = _resumen(otro, corte)
            out[prueba][n] = {"decisiones_antes_del_corte": len(comp[0]), "operaciones_antes_del_corte": len(comp[1]),
                              "identicas": comp == o, "ok": comp == o and len(comp[0]) > 100}
        out["V5_solo_largos_" + n] = all(t.direction.value == "long" for t in res[f"V2|{n}|completo"].trades)
    a = hashlib.sha256("\n".join(_clave(t) for t in res["V2|breakout|completo"].trades).encode()).hexdigest()
    b = hashlib.sha256("\n".join(_clave(t) for t in res["DET|breakout|b"].trades).encode()).hexdigest()
    out["DET"] = {"huella_a": a, "huella_b": b, "ok": a == b}
    out["todo_ok"] = (out["V1"]["ok"] and all(v["ok"] for k in ("V2", "V3") for v in out[k].values())
                      and all(v["ok"] for v in out["V6"].values()) and out["DET"]["ok"]
                      and all(v for k, v in out.items() if k.startswith("V5_")))
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False, default=str)
    print(json.dumps({"todo_ok": out["todo_ok"], "V1": out["V1"]["ok"], "V2": {k: v["ok"] for k, v in out["V2"].items()},
                      "V3": {k: v["ok"] for k, v in out["V3"].items()}, "V6": {k: v["ok"] for k, v in out["V6"].items()},
                      "DET": out["DET"]["ok"]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
