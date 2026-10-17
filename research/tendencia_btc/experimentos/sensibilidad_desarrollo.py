"""DESCRIPTIVO, SOLO desarrollo (2018-02-14 → 2021-12-31): sensibilidad y estrés de T (no pasó la puerta; esto NO es un
criterio ni habilita validación o test). ETHUSDT con la misma regla, solo descriptivo."""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
DESDE, HASTA = "2018-02-14", "2022-01-01"
ESCENARIOS = {"base": {}, "costes_x05": {"costes": Costes(multiplicador=0.5)}, "costes_x2": {"costes": Costes(multiplicador=2)},
              "costes_x3": {"costes": Costes(multiplicador=3)}, "slippage_25bps": {"costes": Costes(10, 25)},
              "retraso_1d": {"retraso": 1}, "retraso_3d": {"retraso": 3}}


def exceso(v, obj, **kw) -> dict:  # type: ignore[no-untyped-def]
    s = simular(v, obj, DESDE, HASTA, **kw)
    wbar = st.fmean(s.exposicion)
    est = simular(v, [wbar] * len(v), DESDE, HASTA, costes=Costes(0, 0), banda=0.0)
    d = [a - b for a, b in zip(rendimientos(s), rendimientos(est), strict=True)]
    b = bootstrap_media(d, bloque=20, n=2000, semilla=20261017)
    return {"metricas": calcular(s), "exceso_anual": st.fmean(d) * 365, "p": b["p_mayor_que_cero"], "serie": s}


def main() -> None:
    out: dict = {"categoria": "DESCRIPTIVO, solo desarrollo; T no pasó la puerta prefijada", "BTCUSDT": {}, "ETHUSDT": {}}
    for sym in ("BTCUSDT", "ETHUSDT"):
        v, _ = leer(AQUI.parent / "datos" / sym)
        c = [x.c for x in v]
        obj = tsmom(c)
        bh = simular(v, [1.0] * len(v), DESDE, HASTA)
        res = {}
        for e, kw in (ESCENARIOS.items() if sym == "BTCUSDT" else [("base", {})]):
            x = exceso(v, obj, **kw)
            res[e] = {"exceso_anual": x["exceso_anual"], "p": x["p"],
                      **{k: x["metricas"][k] for k in ("cagr", "sharpe", "caida_maxima", "operaciones", "costes_pp_anual",
                                                       "exposicion_media", "por_ano")}}
            if e == "base":
                base = x["serie"]
        res["buy_and_hold"] = {k: calcular(bh)[k] for k in ("cagr", "sharpe", "caida_maxima", "por_ano")}
        # estrés: los 10 peores días del buy and hold y el resultado de T esos días
        rb, rt = rendimientos(bh), rendimientos(base)
        peores = sorted(range(len(rb)), key=lambda i: rb[i])[:10]
        res["peores_dias_bh"] = [{"dia": bh.dias[i], "bh": rb[i], "T": rt[i], "exposicion_T": base.exposicion[i - 1] if i else 0}
                                 for i in peores]
        # régimen ex ante: rentabilidad del BTC en los 90 días previos (umbrales fijos ±15 %)
        cier = {x.dia: x.c for x in v}
        dias = [x.dia for x in v]
        pos = {d: k for k, d in enumerate(dias)}
        reg: dict[str, list[float]] = {"alcista": [], "lateral": [], "bajista": []}
        regb: dict[str, list[float]] = {"alcista": [], "lateral": [], "bajista": []}
        for i, d in enumerate(base.dias):
            k = pos[d]
            r90 = cier[dias[k - 1]] / cier[dias[k - 91]] - 1
            g = "alcista" if r90 > 0.15 else "bajista" if r90 < -0.15 else "lateral"
            reg[g].append(rt[i])
            regb[g].append(rb[i])
        res["por_regimen_ex_ante"] = {g: {"dias": len(reg[g]), "T_media_anual": st.fmean(reg[g]) * 365,
                                          "bh_media_anual": st.fmean(regb[g]) * 365} for g in reg}
        out[sym] = res
    (AQUI / "sensibilidad_desarrollo.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    for sym in ("BTCUSDT", "ETHUSDT"):
        print("==", sym)
        for e, x in out[sym].items():
            if "exceso_anual" in x:
                print(f"  {e:15s} exceso {x['exceso_anual']:+.1%} P {x['p']:.3f} CAGR {x['cagr']:.1%} Sharpe {x['sharpe']:.2f} "
                      f"caída {x['caida_maxima']:.1%} ops {x['operaciones']} costes {x['costes_pp_anual']:.2f}pp")
        print("  B&H", {k: (round(v, 3) if isinstance(v, float) else {a: round(b, 3) for a, b in v.items()}) for k, v in out[sym]["buy_and_hold"].items()})
        print("  T por año", {a: round(b, 3) for a, b in out[sym]["base"]["por_ano"].items()})
        print("  régimen", {g: (z["dias"], round(z["T_media_anual"], 2), round(z["bh_media_anual"], 2)) for g, z in out[sym]["por_regimen_ex_ante"].items()})
        print("  peores días", [(p["dia"], round(p["bh"], 3), round(p["T"], 3)) for p in out[sym]["peores_dias_bh"][:6]])


if __name__ == "__main__":
    main()
