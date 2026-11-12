"""E3 · pruebas del motor con datos SINTÉTICOS (v3 §10.4–10.5). No lee datos reales.

Uso: python -I pruebas_motor.py <salida.json>
"""
import ast
import datetime as dt
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inferencia import newey_west  # noqa: E402
from motor import Config, costo, ic_semanal, simular  # noqa: E402
from universo import INICIO, Panel, lunes, universo  # noqa: E402

D = (dt.date(2020, 12, 31) - INICIO).days + 1


def panel_sintetico(semilla, S=70, momentum=0.0):
    """Precios con factor común; momentum plantado: deriva diaria ∝ retorno de los 14 días previos (transversal)."""
    rng = np.random.default_rng(semilla)
    f = rng.normal(0, 0.03, D)
    eps = rng.normal(0, 0.04, (S, D))
    lr = np.zeros((S, D))
    for d in range(1, D):
        lr[:, d] = f[d] + eps[:, d]
        if momentum and d > 15:
            pas = lr[:, d - 14:d].sum(axis=1)
            lr[:, d] += momentum * (pas - pas.mean())
    C = 10 * np.exp(np.cumsum(lr, axis=1))
    O = np.empty_like(C)
    O[:, 0] = C[:, 0]
    O[:, 1:] = C[:, :-1]                          # mercado 24/7: apertura ≈ cierre previo
    QV = np.exp(rng.normal(np.log(5e6), 0.8, (S, D)))
    act = np.ones((S, D), dtype=bool)
    for s in range(S):                            # altas escalonadas, algunas bajas, huecos y una suspensión larga
        ini = int(rng.integers(0, 500))
        act[s, :ini] = False
        if s % 9 == 0:
            fin = int(rng.integers(900, D - 60))
            act[s, fin:] = False
        if s % 13 == 0:
            g = int(rng.integers(700, 1000))
            act[s, g:g + 10] = False
        if s == 5:
            act[s, 800:840] = False
    C = np.where(act, C, np.nan)
    O = np.where(act, O, np.nan)
    QV = np.where(act, QV, np.nan)
    syms = [f"C{i:02d}USDT" for i in range(S - 3)] + ["USDCUSDT", "C01UPUSDT", "XUSDT"]
    return Panel(syms, O, C, QV, act)


def formaciones():
    return lunes(dt.date(2018, 9, 3), dt.date(2020, 12, 21))


def prueba_invariancia(P, semilla=20261022, cortes=5):
    rng = np.random.default_rng(semilla)
    F = formaciones()
    base_cache = {}
    base = simular(P, F, Config(), cache_univ=base_cache, registrar_pesos=True)
    resultados = []
    for c in sorted(rng.choice(np.arange(F[20], F[-10]), size=cortes, replace=False)):
        P2 = Panel(P.sym, P.O.copy(), P.C.copy(), P.QV.copy(), P.act.copy())
        P2.O[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.C[:, c:] *= rng.uniform(0.2, 5, (P.S, 1))
        P2.QV[:, c:] = rng.uniform(0, 1e8, P2.QV[:, c:].shape)
        P2.act[:, c:] = rng.random(P2.act[:, c:].shape) < 0.5
        P2.C[:, c:] = np.where(P2.act[:, c:], P2.C[:, c:], np.nan)
        P2._derivados()
        F2 = [t for t in F if t < c - 7]
        r2 = simular(P2, F2 + [F2[-1] + 7], Config(), cache_univ={}, registrar_pesos=True)
        ok_univ = all((a is None and b is None) or (a["U_inv"] == b["U_inv"] and a["U_pred"] == b["U_pred"] and np.allclose(a["S"], b["S"]) and a["rk"] == b["rk"])
                      for a, b in zip(base["univs"][:len(F2)], r2["univs"][:len(F2)]))
        ok_obj = base["objetivos"][:len(r2["objetivos"]) - 1] == r2["objetivos"][:-1]
        ok_pesos = all(set(a[1]) == set(b[1]) and all(abs(a[1][s] - b[1][s]) < 1e-12 for s in a[1]) for a, b in zip(base["pesos"][:len(F2)], r2["pesos"][:len(F2)]))
        resultados.append({"corte": int(c), "universos_y_senal": ok_univ, "objetivos": ok_obj, "pesos": ok_pesos})
    return resultados


def main(salida):
    out = {}
    # 1) costos (v3 §4.9)
    out["costos"] = {"rango1": costo(1, 1), "rango5": costo(5, 1), "rango20": costo(20, 1), "fuera": costo(None, 1), "x2_rango5": costo(5, 2)}
    assert abs(costo(1, 1) - 0.0015) < 1e-12 and abs(costo(5, 1) - 0.0020) < 1e-12 and abs(costo(20, 1) - 0.0030) < 1e-12 and abs(costo(None, 1) - 0.0040) < 1e-12
    # 2) exclusiones estáticas
    P = panel_sintetico(1)
    out["exclusiones"] = {"fijo": [P.sym[i] for i in np.flatnonzero(P.fijo)], "apalancado": [P.sym[i] for i in np.flatnonzero(P.apalancado)]}
    assert "USDCUSDT" in out["exclusiones"]["fijo"] and "C01UPUSDT" in out["exclusiones"]["apalancado"]
    # 3) invariancia al truncar (5 cortes, semilla 20261022)
    out["invariancia"] = prueba_invariancia(P)
    assert all(all(v for k, v in r.items() if k != "corte") for r in out["invariancia"])
    # 4) H1: momentum plantado detectado; nulo ≈ 0
    for nombre, mom in (("nulo", 0.0), ("momentum_plantado", 0.02)):
        Pm = panel_sintetico(2, momentum=mom)
        F = formaciones()
        cache = {}
        ics = ic_semanal(Pm, F, cache)
        x = np.array([v for _, v, _, _ in ics if not math.isnan(v)])
        nw = newey_west(x, 4)
        out[f"H1_{nombre}"] = {"semanas": int(x.size), "IC_media": float(x.mean()), "p": nw["p_unilateral"]}
    assert out["H1_momentum_plantado"]["IC_media"] > 0.02 and out["H1_momentum_plantado"]["p"] < 0.01
    # 5) liquidación contable y ventas diferidas
    Pl = panel_sintetico(3)
    F = formaciones()
    r = simular(Pl, F, Config(objetivo="ew"), cache_univ={})
    out["eventos_ew"] = {"liquidaciones": len(r["eventos"]["liquidaciones"]), "ventas_diferidas": r["eventos"]["ventas_diferidas"],
                         "compras_omitidas": r["eventos"]["compras_omitidas"]}
    for sym, d, v in r["eventos"]["liquidaciones"]:
        s = Pl.sym.index(sym)
        assert Pl.inact_run[s, d - 1] >= 30 and not Pl.act[s, d - 30:d].any()
    # 6) nulo aleatorio frente a EW (bruto): media ≈ 0
    P0 = panel_sintetico(4)
    cache = {}
    ew = simular(P0, F, Config(objetivo="ew", mult_costo=0.0), cache_univ=cache)
    medias = []
    for i in range(40):
        ra = simular(P0, F, Config(objetivo="aleatorio", semilla_aleatoria=1000 + i, mult_costo=0.0), cache_univ=cache)
        e = (ra["r"] - ew["r"])[ra["evaluable"]]
        medias.append(e.mean() * 52)
    out["nulo_aleatorio_vs_ew_bruto"] = {"media_anual_promedio": float(np.mean(medias)), "desvio_entre_replicas": float(np.std(medias)),
                                         "error_estandar_del_promedio": float(np.std(medias) / math.sqrt(len(medias)))}
    assert abs(np.mean(medias)) < 3 * np.std(medias) / math.sqrt(len(medias)) + 0.02
    # 7) separación de etapas (N22): calidad.py no importa motor
    arbol = ast.parse(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calidad.py")).read())
    imps = {n.names[0].name if isinstance(n, ast.Import) else n.module for n in ast.walk(arbol) if isinstance(n, (ast.Import, ast.ImportFrom))}
    out["separacion_etapas"] = {"imports_calidad": sorted(i for i in imps if i), "importa_motor": "motor" in imps}
    assert "motor" not in imps
    # 8) H1 sin mirar al futuro: alterar días t..t+6 cambia y pero no S
    t = F[30]
    U1 = universo(P, t)
    P3 = Panel(P.sym, P.O.copy(), P.C.copy(), P.QV.copy(), P.act.copy())
    P3.C[:, t:t + 7] *= 1.7
    P3._derivados()
    U3 = universo(P3, t)
    out["H1_S_independiente_del_futuro"] = bool(np.allclose(U1["S"], U3["S"]) and U1["U_pred"] == U3["U_pred"])
    assert out["H1_S_independiente_del_futuro"]
    out["todo_ok"] = True
    with open(salida, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
