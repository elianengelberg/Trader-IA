"""Paridad del árbol final con E1 (P1, P2, P3, S1) — solo comparación con lo registrado; no es un experimento.

Corre el BacktestEngine del árbol indicado, SIN subclases, con la configuración, el universo y el escenario de E1
(e1_comun.py de la corrida evaluada) sobre las velas de E1 (leídas y verificadas contra .CHECKSUM por e1_comun).
No calcula ninguna métrica de decisión nueva ni escribe nada fuera de <salida.json>.
Uso: python -I -B paridad_e1_v2.py <src_del_arbol> <dir_codigo_E1> <salida.json> [P1 P2 P3 S1]"""
import hashlib
import json
import sys
from importlib import metadata
from multiprocessing import Pool

SRC, E1COD, SALIDA = sys.argv[1:4]
sys.path[:0] = [SRC, E1COD]

import e1_comun as C  # noqa: E402
import tia.backtest.engine as EM  # noqa: E402
from tia.backtest.engine import BacktestEngine  # noqa: E402

CONFIGS = {"P1": ("trend_following",), "P2": ("mean_reversion",), "P3": ("breakout",), "S1": C.ESTRATEGIAS}
VELAS, META = [], {}


def _init():
    global VELAS, META
    VELAS, META = C.leer_velas()


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _correr(nombre):
    est = CONFIGS[nombre]
    cfg = C.configuracion(est, cortos=False)
    motor = BacktestEngine(cfg, C.universo(False), strategies=est)
    with C.escenario(gobernadores_en_vivo=False, retraso=False):
        r = motor.run(VELAS)
    c = r.conditions
    return nombre, {
        "rt": C.round_trips(r.trades),
        "metricas": r.metrics.model_dump(mode="json"),
        "decisiones": r.decisions.model_dump(mode="json"),
        "h_operaciones_completas": _h([t.model_dump(mode="json") for t in r.trades]),
        "h_equity": hashlib.sha256("\n".join(repr(x) for x in r.equity_curve).encode()).hexdigest(),
        "h_metricas": _h(r.metrics.model_dump(mode="json")),
        "h_decisiones": _h(r.decisions.model_dump(mode="json")),
        "h_registro_de_decisiones": _h([d.model_dump(mode="json") for d in r.decision_log]),
        "higiene": dict(getattr(motor, "order_hygiene", {})), "advertencias": list(r.warnings),
        "n_operaciones": len(r.trades), "equity_final": r.equity_curve[-1] if r.equity_curve else None,
        "condiciones": {k: getattr(c, k, None) for k in ("run_id", "engine_version", "engine_fingerprint",
                                                        "data_fingerprint", "universe_digest", "risk_limits_digest",
                                                        "feature_version", "strategy_versions", "seed", "bars")},
        "digest_config": cfg.digest(),
        "barras_meta": len(VELAS), "datos_meta": {k: v for k, v in META.items() if k != "archivos"},
    }


if __name__ == "__main__":
    nombres = sys.argv[4:] or list(CONFIGS)
    with Pool(len(nombres), initializer=_init) as p:
        res = dict(p.map(_correr, nombres))
    versiones = {d: metadata.version(d) for d in ("pydantic", "pydantic_core", "numpy", "structlog")}
    out = {"motor": EM.__file__, "sha256_engine": hashlib.sha256(open(EM.__file__, "rb").read()).hexdigest(),
           "sha256_e1_comun": hashlib.sha256(open(C.__file__, "rb").read()).hexdigest(),
           "python": sys.version.split()[0], "versiones": versiones, "configuraciones": res}
    json.dump(out, open(SALIDA, "w"), indent=1, ensure_ascii=False, default=str)
    for n, v in res.items():
        print(n, len(v["rt"]), v["h_operaciones_completas"][:12], v["h_equity"][:12], v["h_metricas"][:12], v["condiciones"]["run_id"])
