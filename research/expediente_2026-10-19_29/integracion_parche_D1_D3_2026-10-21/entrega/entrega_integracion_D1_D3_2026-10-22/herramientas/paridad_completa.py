"""Paridad con E1 y huellas de la salida COMPLETA del motor (no solo de la lista de operaciones).

Datos: BTCUSDT 1h de E1 (2019-10 → 2026-05, ya consumidos por E1; no es un experimento confirmatorio: no se calcula
ninguna métrica de decisión, solo se compara con lo registrado). Motor: el BacktestEngine del PYTHONPATH, sin subclases.

Por configuración se informa:
  rt_identicos_a_E1  la lista agregada de round trips (C.round_trips) es idéntica, como JSON, a la registrada por E1.
                     Campos comparados: entrada, salida, direccion, nocional, neto_pct, bruto_pct, comisiones_pct,
                     barras, razon_salida, confianza, regimen_bot, piezas.
  h_*                huellas SHA-256 de: operaciones completas (ClosedTrade.model_dump), curva de equity (repr de
                     cada float), métricas, contadores de decisiones, higiene y advertencias. E1 no registró estas
                     salidas: sirven para comparar ENTORNOS entre sí, no con E1.
Uso: python -B paridad_completa.py <operaciones_por_configuracion.json de E1> <salida.json> [P1 P2 P3 S1]
"""
import hashlib
import json
import sys
from multiprocessing import Pool

import e1_comun as C
import tia.backtest.engine as EM
from tia.backtest.engine import BacktestEngine

CONFIGS = {"P1": ("trend_following",), "P2": ("mean_reversion",), "P3": ("breakout",), "S1": C.ESTRATEGIAS}
VELAS = []


def _init():
    global VELAS
    VELAS, _ = C.leer_velas()


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _correr(nombre):
    est = CONFIGS[nombre]
    cfg = C.configuracion(est, cortos=False)
    motor = BacktestEngine(cfg, C.universo(False), strategies=est)
    with C.escenario(gobernadores_en_vivo=False, retraso=False):
        r = motor.run(VELAS)
    return nombre, {
        "rt": C.round_trips(r.trades),
        "h_operaciones_completas": _h([t.model_dump(mode="json") for t in r.trades]),
        "h_equity": hashlib.sha256("\n".join(repr(x) for x in r.equity_curve).encode()).hexdigest(),
        "h_metricas": _h(r.metrics.model_dump(mode="json")),
        "h_decisiones": _h(r.decisions.model_dump(mode="json")),
        "higiene": dict(motor.order_hygiene), "advertencias": list(r.warnings),
        "n_operaciones": len(r.trades), "equity_final": r.equity_curve[-1] if r.equity_curve else None,
    }


def main(registrado, salida, nombres):
    ref = json.load(open(registrado))
    with Pool(len(nombres), initializer=_init) as p:
        res = dict(p.map(_correr, nombres))
    out = {"motor": EM.__file__, "sha256_engine": hashlib.sha256(open(EM.__file__, "rb").read()).hexdigest(),
           "sha256_registro_E1": hashlib.sha256(open(registrado, "rb").read()).hexdigest(), "configuraciones": {}}
    for n, v in res.items():
        rt = v.pop("rt")
        out["configuraciones"][n] = {"rt_identicos_a_E1": json.dumps(rt, sort_keys=True) == json.dumps(ref[n], sort_keys=True),
                                     "n_rt": len(rt), "n_rt_E1": len(ref[n]), "h_rt": _h(rt), **v}
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False)
    for n, v in out["configuraciones"].items():
        print(n, v["rt_identicos_a_E1"], v["n_rt"], v["n_rt_E1"], v["h_operaciones_completas"][:12], v["h_equity"][:12], v["h_metricas"][:12])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] or list(CONFIGS))
