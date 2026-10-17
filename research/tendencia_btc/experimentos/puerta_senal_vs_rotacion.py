"""Última puerta (FAMILIAS_ESTRATEGIA.md): exceso de timing BRUTO de T en desarrollo y, solo si pasa, T2 semanal neto."""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
from pathlib import Path

from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media, desplazamientos
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
DESDE, HASTA = "2018-02-14", "2022-01-01"


def semanal(v, obj):  # type: ignore[no-untyped-def]
    """Solo cambia la decisión con el cierre del domingo (UTC); el resto de días repite la última decisión."""
    out, ultima = [], None
    for x, w in zip(v, obj, strict=True):
        if dt.date.fromisoformat(x.dia).weekday() == 6 and w is not None:
            ultima = w
        out.append(ultima)
    return out


def evaluar(v, obj, costes: Costes) -> dict:  # type: ignore[no-untyped-def]
    n = len(v)
    s = simular(v, obj, DESDE, HASTA, costes=costes)
    wbar = st.fmean(s.exposicion)
    est = simular(v, [wbar] * n, DESDE, HASTA, costes=Costes(0, 0), banda=0.0)
    rs, re = rendimientos(s), rendimientos(est)
    obs = st.fmean(rs) - st.fmean(re)
    idx = [i for i, x in enumerate(v) if DESDE <= x.dia < HASTA]
    seg = [obj[i - 1] for i in idx]
    nulos = []
    for k in desplazamientos(len(seg), n=1000):
        rot = seg[k:] + seg[:k]
        o = [None] * n
        for i, w in zip(idx, rot, strict=True):
            o[i - 1] = w
        nulos.append(st.fmean(rendimientos(simular(v, o, DESDE, HASTA, costes=costes))) - st.fmean(re))
    boot = bootstrap_media([a - b for a, b in zip(rs, re, strict=True)], bloque=20, n=2000, semilla=20261017)
    return {"metricas": calcular(s), "exposicion_media": wbar, "exceso_anual": obs * 365, "bootstrap": boot,
            "percentil_nulo": sum(x < obs for x in nulos) / len(nulos),
            "pasa": boot["p_mayor_que_cero"] >= 0.90 and sum(x < obs for x in nulos) / len(nulos) >= 0.90 and obs > 0}


def main() -> None:
    v, inf = leer(AQUI.parent / "datos" / "BTCUSDT")
    obj = tsmom([x.c for x in v])
    out = {"categoria": "HISTÓRICO, solo desarrollo", "manifiesto_sha256": inf["manifiesto_sha256"],
           "T_bruto": evaluar(v, obj, Costes(0, 0))}
    if out["T_bruto"]["pasa"]:
        out["T2_semanal_neto"] = evaluar(v, semanal(v, obj), Costes())
        out["T2_semanal_bruto"] = evaluar(v, semanal(v, obj), Costes(0, 0))
    (AQUI / "puerta_senal_vs_rotacion.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for k, x in out.items():
        if isinstance(x, dict) and "metricas" in x:
            m = x["metricas"]
            print(f"{k:18s} exceso {x['exceso_anual']:+.1%}/año P {x['bootstrap']['p_mayor_que_cero']:.3f} IC90 "
                  f"{[round(z, 3) for z in x['bootstrap']['intervalo_anual']]} nulo {x['percentil_nulo']:.3f} "
                  f"CAGR {m['cagr']:.1%} Sharpe {m['sharpe']:.2f} caída {m['caida_maxima']:.1%} ops {m['operaciones']} "
                  f"costes {m['costes_pp_anual']:.2f}pp expo {x['exposicion_media']:.2f} → pasa {x['pasa']}")


if __name__ == "__main__":
    main()
