"""E3 · motor de cartera (v3 §4.7–4.13) e IC de H1. Solo se ejecuta sobre datos reales en la ejecución confirmatoria registrada.

Orden diario de eventos (sin mirar al futuro):
  1) si d es día de valuación (formación + demora): W antes de operar = efectivo + Σ unidades·(O_d si d activo, si no P_val(d−1));
  2) liquidaciones contables: posiciones con ≥ 30 días inactivos seguidos hasta d−1 → unidades·P_val·(1−c_liq)·recorte;
  3) ventas pendientes: si d es activo, se ejecutan a O_d con el costo decidido en su formación;
  4) si d es día de ejecución de una formación: ventas, vuelta a pesos iguales o reposición, compras (v3 §4.7–4.9).
"""
import datetime as dt
import math

import numpy as np

from universo import INICIO, spearman, universo

PB = 1e-4


class Config:
    def __init__(self, k=6, N_inv=30, banda=12, horizontes=(7, 14, 21, 28), dia_semana=0, demora=0, mult_costo=1.0,
                 recorte_liq=1.0, excluidos=frozenset(), objetivo="momentum", semilla_aleatoria=None, filtro_absoluto=False):
        self.k, self.N_inv, self.banda, self.horizontes = k, N_inv, banda, tuple(horizontes)
        self.dia_semana, self.demora, self.mult_costo, self.recorte_liq = dia_semana, demora, mult_costo, recorte_liq
        self.excluidos, self.objetivo, self.semilla_aleatoria, self.filtro_absoluto = frozenset(excluidos), objetivo, semilla_aleatoria, filtro_absoluto


def costo(rango_V, mult):
    """v3 §4.9: 10 pb + tramo por posición de liquidez V (1–2: 5; 3–10: 10; 11–30: 20; resto o no elegible: 30)."""
    if rango_V is None or rango_V > 30:
        t = 30
    elif rango_V <= 2:
        t = 5
    elif rango_V <= 10:
        t = 10
    else:
        t = 20
    return (10 + t) * PB * mult


def simular(P, formaciones, cfg: Config, cache_univ=None, registrar_pesos=False):
    """Devuelve valores W en cada día de valuación, retornos semanales, flags de semana evaluable y eventos."""
    rng = np.random.default_rng(cfg.semilla_aleatoria) if cfg.semilla_aleatoria is not None else None
    unidades, efectivo = {}, 1.0
    pendientes = {}                       # s -> costo decidido
    eventos = {"liquidaciones": [], "ventas_diferidas": 0, "compras_omitidas": 0}
    W_hist, evaluable, univs, pesos_semana, objetivos = [], [], [], [], []
    mes_prev = None
    dias_val = [t + cfg.demora for t in formaciones]
    fin = dias_val[-1]
    pos_form = {t + cfg.demora: t for t in formaciones}
    d = dias_val[0]
    while d <= fin:
        # 1) valuación
        if d in pos_form:
            W = efectivo + sum(u * (P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)) for s, u in unidades.items())
            W_hist.append(W)
        # 2) liquidaciones contables por inactividad
        for s in list(unidades):
            if P.inact_run[s, d - 1] >= 30:
                v = unidades[s] * P.pval(s, d - 1) * (1 - costo(None, cfg.mult_costo)) * cfg.recorte_liq
                efectivo += v
                eventos["liquidaciones"].append((P.sym[s], d, v))
                del unidades[s]
                pendientes.pop(s, None)
        # 3) ventas pendientes
        for s in list(pendientes):
            if s in unidades and P.act[s, d]:
                efectivo += unidades[s] * P.O[s, d] * (1 - pendientes[s])
                del unidades[s]
                del pendientes[s]
                eventos["ventas_diferidas"] += 1
        # 4) formación
        if d in pos_form:
            t = pos_form[d]
            U = cache_univ.get((t, cfg.N_inv, cfg.horizontes, cfg.excluidos)) if cache_univ is not None else None
            if U is None:
                U = universo(P, t, cfg.excluidos, N_inv=cfg.N_inv, horizontes=cfg.horizontes)
                if cache_univ is not None:
                    cache_univ[(t, cfg.N_inv, cfg.horizontes, cfg.excluidos)] = U
            ev = U is not None and U["n_elegibles"] >= 30
            evaluable.append(ev)
            univs.append(U)
            if ev:
                W = W_hist[-1]
                rk = U["rk"]
                if cfg.objetivo == "aleatorio":
                    perm = rng.permutation(len(U["U_inv"]))
                    rk = {s: int(perm[i]) + 1 for i, s in enumerate(U["U_inv"])}
                tenidas = [s for s in unidades if s not in pendientes]
                if cfg.objetivo == "ew":
                    T = list(U["U_inv"])
                    kk = len(T)
                else:
                    kk = cfg.k
                    quedan = [s for s in tenidas if s in rk and rk[s] <= cfg.banda]
                    quedan = sorted(quedan, key=lambda s: rk[s])[:kk]
                    entran = [s for s in sorted(rk, key=lambda s: rk[s]) if s not in quedan][: kk - len(quedan)]
                    T = quedan + entran
                if cfg.filtro_absoluto:
                    T = [s for s in T if U["A"][U["pos_pred"][s]] > 0]
                objetivos.append((t, list(T)))
                for s in list(pendientes):                                  # vuelve a ser objetivo: se cancela la venta
                    if s in T:
                        del pendientes[s]
                cost = {s: costo(U["rango_V"].get(s), cfg.mult_costo) for s in set(T) | set(unidades)}
                for s in tenidas:                                           # ventas
                    if s not in T:
                        if P.act[s, d]:
                            efectivo += unidades.pop(s) * P.O[s, d] * (1 - cost[s])
                        else:
                            pendientes[s] = cost[s]
                mes = (INICIO + dt.timedelta(days=t)).month
                precio = {s: (P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)) for s in unidades}
                valor = {s: unidades[s] * precio[s] for s in unidades}
                tope = 2.0 / kk
                reset = (mes != mes_prev) or any(v / W > tope for s, v in valor.items() if W > 0)
                mes_prev = mes
                if reset:
                    obj = W / kk
                    for s in T:                                             # vender sobreponderadas hasta W/k
                        if s in unidades and s not in pendientes and P.act[s, d] and valor.get(s, 0) > obj:
                            q = (valor[s] - obj) / P.O[s, d]
                            unidades[s] -= q
                            efectivo += q * P.O[s, d] * (1 - cost[s])
                    nec = {s: obj - (unidades.get(s, 0) * P.O[s, d]) for s in T if P.act[s, d] and s not in pendientes and obj - unidades.get(s, 0) * P.O[s, d] > 0}
                    tot = sum(nec.values())
                    esc = min(1.0, efectivo / tot) if tot > 0 else 0.0
                    for s, x in nec.items():
                        a = x * esc
                        unidades[s] = unidades.get(s, 0) + a / (P.O[s, d] * (1 + cost[s]))
                        efectivo -= a
                    eventos["compras_omitidas"] += sum(1 for s in T if not P.act[s, d] and s not in unidades)
                else:
                    entran = [s for s in T if s not in unidades]
                    if entran:
                        parte = efectivo / len(entran)
                        for s in entran:
                            if P.act[s, d]:
                                unidades[s] = parte / (P.O[s, d] * (1 + cost[s]))
                                efectivo -= parte
                            else:
                                eventos["compras_omitidas"] += 1
                if registrar_pesos:
                    Wd = efectivo + sum(u * (P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)) for s, u in unidades.items())
                    pesos_semana.append((t, {s: u * (P.O[s, d] if P.act[s, d] else P.pval(s, d - 1)) / Wd for s, u in unidades.items()}))
            elif registrar_pesos:
                pesos_semana.append((t, {}))
        d += 1
    W_hist = np.array(W_hist)
    r = W_hist[1:] / W_hist[:-1] - 1
    return {"W": W_hist, "r": r, "evaluable": np.array(evaluable[:-1]), "univs": univs, "eventos": eventos,
            "pesos": pesos_semana, "objetivos": objetivos, "efectivo_final": efectivo}


def ic_semanal(P, formaciones, cache_univ, horizontes=(7, 14, 21, 28)):
    """H1 (v3 §4.13): IC_t = Spearman(S, y) en U100, y = ln(P_val(s, t+6) / C_{s,t−1}); horizonte calendario fijo."""
    out = []
    for t in formaciones[:-1]:
        U = cache_univ.get((t, 30, horizontes, frozenset())) or universo(P, t, horizontes=horizontes)
        if U is None or U["n_elegibles"] < 30:
            out.append((t, np.nan, 0, 0))
            continue
        up = U["U_pred"]
        y = np.array([math.log(P.pval(s, t + 6) / P.C[s, t - 1]) for s in up])
        obsoletas = sum(1 for s in up if not P.act[s, t + 6])
        out.append((t, spearman(U["S"], y), len(up), obsoletas))
    return out
