"""¿Cuánto tiempo de evaluación en papel hace falta para que el exceso de timing de T sea distinguible del azar?
Usa SOLO desarrollo (2018-02-14 → 2021-12-31): media y error del exceso diario frente a la estática con la misma
exposición, con bootstrap por bloques (la dependencia temporal entra en el error)."""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media
from tendencia.metricas import rendimientos
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
DESDE, HASTA = "2018-02-14", "2022-01-01"
Z = {"90 %": 1.2816, "95 %": 1.6449}


def exceso(sym: str) -> list[float]:
    v, _ = leer(AQUI.parent / "datos" / sym)
    s = simular(v, tsmom([x.c for x in v]), DESDE, HASTA)
    wbar = st.fmean(s.exposicion)
    e = simular(v, [wbar] * len(v), DESDE, HASTA, costes=Costes(0, 0), banda=0.0)
    return [a - b for a, b in zip(rendimientos(s), rendimientos(e), strict=True)]


def main() -> None:
    series = {s: exceso(s) for s in ("BTCUSDT", "ETHUSDT")}
    series["BTC+ETH (media)"] = [(a + b) / 2 for a, b in zip(series["BTCUSDT"], series["ETHUSDT"], strict=True)]
    out = {}
    for k, x in series.items():
        b = bootstrap_media(x, bloque=20, n=2000, semilla=20261017)
        anos = len(x) / 365
        se = (b["intervalo_anual"][1] - b["intervalo_anual"][0]) / (2 * 1.6449)   # error del exceso anual en desarrollo
        sigma1 = se * anos ** 0.5                                                   # error con 1 año de datos
        mu = b["media_anual"]
        out[k] = {"exceso_anual_desarrollo": mu, "error_1_ano": sigma1,
                  "anos_necesarios": {nivel: {"si_efecto_igual_al_desarrollo": (z * sigma1 / mu) ** 2,
                                              "si_efecto_mitad": (z * sigma1 / (mu / 2)) ** 2} for nivel, z in Z.items()},
                  "error_tras_12_meses": sigma1, "error_tras_24_meses": sigma1 / 2 ** 0.5}
    (AQUI / "potencia.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for k, o in out.items():
        n = o["anos_necesarios"]
        print(f"{k:16s} exceso dev {o['exceso_anual_desarrollo']:+.1%}/año · error con 1 año ±{o['error_1_ano']:.1%} · años para "
              f"P≥95 %: {n['95 %']['si_efecto_igual_al_desarrollo']:.1f} (efecto mitad: {n['95 %']['si_efecto_mitad']:.0f}) · "
              f"P≥90 %: {n['90 %']['si_efecto_igual_al_desarrollo']:.1f}")


if __name__ == "__main__":
    main()
