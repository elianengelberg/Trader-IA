"""MS-2 — Paridad: el BacktestEngine corregido de la plataforma frente a las operaciones registradas por E1.

E1 (2026-10-19) corrió MotorE1 = BacktestEngine original + D1/D2/D3 corregidos en una subclase, con datos
BTCUSDT 1h verificados contra .CHECKSUM. Aquí se corre el BacktestEngine del paquete YA corregido (sin subclase),
con la misma configuración, el mismo universo, los mismos escenarios y los mismos datos, y se compara la lista
completa de round trips con la registrada (igualdad exacta del JSON). No se imprime ningún rendimiento.
Uso: PYTHONPATH=<tia corregido>:<E1/codigo> python -B paridad_e1.py <operaciones_por_configuracion.json> <salida.json> [nombres...]
"""
import hashlib
import json
import sys
import time
from multiprocessing import Pool

import e1_comun as C
import tia.backtest.engine as EM
from tia.backtest.engine import BacktestEngine

E1_PRINCIPALES = {"P1": ("trend_following",), "P2": ("mean_reversion",), "P3": ("breakout",), "S1": C.ESTRATEGIAS}
VARIANTES = {"": {}, "S2|": {"comision_bps": 20.0}, "S3|": {"retraso": True},
             "S4|": {"comision_bps": 0.0, "deslizamiento_base_bps": 0.0, "impacto": 0.0}, "S5|": {"cortos": True},
             "S6|": {"gobernadores_en_vivo": True}}
VELAS = []


def _init():
    global VELAS
    VELAS, _ = C.leer_velas()


def _correr(nombre):
    pref, base = (nombre.split("|")[0] + "|", nombre.split("|")[1]) if "|" in nombre else ("", nombre)
    kw = dict(VARIANTES[pref])
    est = E1_PRINCIPALES[base]
    cortos, retraso, gob = kw.pop("cortos", False), kw.pop("retraso", False), kw.pop("gobernadores_en_vivo", False)
    cfg = C.configuracion(est, cortos=cortos, gobernadores_en_vivo=gob, **kw)
    motor = BacktestEngine(cfg, C.universo(cortos), strategies=est)
    assert type(motor) is EM.BacktestEngine and not isinstance(motor, C.MotorE1)
    t0 = time.time()
    with C.escenario(gobernadores_en_vivo=gob, retraso=retraso):
        r = motor.run(VELAS)
    return nombre, C.round_trips(r.trades), dict(motor.order_hygiene), list(r.warnings), round(time.time() - t0, 1)


def main(registrado, salida, nombres):
    ref = json.load(open(registrado))
    nombres = nombres or ["P1", "P2", "P3", "S1"]
    with Pool(3, initializer=_init) as p:
        res = p.map(_correr, nombres)
    out = {"motor": EM.__file__, "sha256_engine": hashlib.sha256(open(EM.__file__, "rb").read()).hexdigest(),
           "registrado": registrado, "sha256_registrado": hashlib.sha256(open(registrado, "rb").read()).hexdigest(),
           "comparaciones": {}}
    for nombre, rts, hig, adv, seg in res:
        a = json.dumps(rts, sort_keys=True)
        b = json.dumps(ref[nombre], sort_keys=True)
        primera = next((i for i, (x, y) in enumerate(zip(rts, ref[nombre])) if x != y), None)
        out["comparaciones"][nombre] = {"identico": a == b, "n_nuevo": len(rts), "n_registrado": len(ref[nombre]),
                                        "sha256_nuevo": hashlib.sha256(a.encode()).hexdigest(),
                                        "sha256_registrado": hashlib.sha256(b.encode()).hexdigest(),
                                        "primer_indice_distinto": primera, "higiene": hig, "advertencias": adv,
                                        "segundos": seg}
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({k: (v["identico"], v["n_nuevo"], v["n_registrado"], v["primer_indice_distinto"]) for k, v in out["comparaciones"].items()}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
