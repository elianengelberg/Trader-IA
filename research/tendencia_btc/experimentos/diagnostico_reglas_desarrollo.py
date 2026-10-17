"""Diagnóstico con las reglas COMPLETAS, SOLO en desarrollo (2018-02-14 → 2021-12-31). El criterio para pasar a
validación y test está fijado en FAMILIAS_ESTRATEGIA.md antes de ejecutar esto. Parámetros a priori, sin ajuste."""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media, bootstrap_sharpe, desplazamientos
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom, vol_gestionada

AQUI = Path(__file__).resolve().parent
DESDE, HASTA = "2018-02-14", "2022-01-01"


def main() -> None:
    v, inf = leer(AQUI.parent / "datos" / "BTCUSDT")
    c = [x.c for x in v]
    n = len(v)
    obj_t, obj_v = tsmom(c), vol_gestionada(c)
    t = simular(v, obj_t, DESDE, HASTA)
    bh = simular(v, [1.0] * n, DESDE, HASTA)
    wbar = st.fmean(t.exposicion)
    est = simular(v, [wbar] * n, DESDE, HASTA, costes=Costes(0, 0), banda=0.0)
    rt, rest, rbh = rendimientos(t), rendimientos(est), rendimientos(bh)
    exceso = [a - b for a, b in zip(rt, rest, strict=True)]
    boot_t = bootstrap_media(exceso, bloque=20, n=2000, semilla=20261017)
    # nulo: desplazamiento circular de la exposición objetivo dentro de la ventana (misma distribución y persistencia)
    idx = [i for i, x in enumerate(v) if DESDE <= x.dia < HASTA]
    seg = [obj_t[i - 1] for i in idx]  # objetivo aplicado cada día de la ventana
    nulos = []
    for k in desplazamientos(len(seg), n=1000):
        rot = seg[k:] + seg[:k]
        o = [None] * n
        for i, w in zip(idx, rot, strict=True):
            o[i - 1] = w
        rn = rendimientos(simular(v, o, DESDE, HASTA))
        nulos.append(st.fmean(rn) - st.fmean(rest))
    obs = st.fmean(rt) - st.fmean(rest)
    pct = sum(x < obs for x in nulos) / len(nulos)
    vv = simular(v, obj_v, DESDE, HASTA, banda=0.10)
    rv = rendimientos(vv)
    boot_v = bootstrap_sharpe(rv, rbh, bloque=20, n=2000, semilla=20261017)
    m = {k: calcular(r) for k, r in {"T_tendencia": t, "V_volatilidad": vv, "buy_and_hold": bh,
                                     "estatica_misma_exposicion_T": est}.items()}
    pasa_t = boot_t["p_mayor_que_cero"] >= 0.90 and pct >= 0.90 and obs > 0
    pasa_v = (boot_v["p_mayor_que_cero"] >= 0.90 and boot_v["dif_sharpe"] > 0
              and m["V_volatilidad"]["caida_maxima"] < m["buy_and_hold"]["caida_maxima"])
    out = {"categoria": "HISTÓRICO, solo desarrollo (diagnóstico; parámetros a priori)", "ventana": [DESDE, HASTA],
           "manifiesto_sha256": inf["manifiesto_sha256"], "metricas": m, "exposicion_media_T": wbar,
           "T_exceso_vs_estatica": {"media_diaria": obs, "bootstrap": boot_t, "percentil_nulo_circular": pct},
           "V_sharpe_vs_buy_and_hold": boot_v, "pasa_a_validacion": {"T": pasa_t, "V": pasa_v}}
    (AQUI / "diagnostico_reglas_desarrollo.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for k, x in m.items():
        print(f"{k:28s} CAGR {x['cagr']:7.2%} vol {x['vol_anual']:6.1%} Sharpe {x['sharpe']:.2f} caída {x['caida_maxima']:.1%}"
              f" expo {x['exposicion_media']:.2f} ops {x['operaciones']} costes {x['costes_pp_anual']:.2f}pp")
    print("T exceso vs estática:", f"{obs * 365:+.2%}/año", "P", boot_t["p_mayor_que_cero"], "IC90",
          [f"{z:+.1%}" for z in boot_t["intervalo_anual"]], "percentil nulo", pct)
    print("V Sharpe − B&H:", round(boot_v["dif_sharpe"], 3), "P", boot_v["p_mayor_que_cero"])
    print("pasa a validación:", out["pasa_a_validacion"])


if __name__ == "__main__":
    main()
