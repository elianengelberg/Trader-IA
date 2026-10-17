"""Evidencia inicial para elegir familia (regla fijada en FAMILIAS_ESTRATEGIA.md). SOLO desarrollo: 2017-08-17 →
2021-12-31. No elige parámetros.

Uso: PYTHONPATH=src:../hcarry_next/src ../hcarry_next/.venv/bin/python -B experimentos/evidencia_inicial_desarrollo.py"""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

from tendencia.datos import leer

AQUI = Path(__file__).resolve().parent
FIN_DESARROLLO = "2022-01-01"


def autocorr(x: list[float], k: int) -> float:
    m = st.fmean(x)
    num = sum((x[i] - m) * (x[i + k] - m) for i in range(len(x) - k))
    return num / sum((v - m) ** 2 for v in x)


def main() -> None:
    out = {"categoria": "HISTÓRICO, solo desarrollo (2017-08-17 → 2021-12-31)", "simbolos": {}}
    for s in ("BTCUSDT", "ETHUSDT"):
        v, _ = leer(AQUI.parent / "datos" / s)
        c = [x.c for x in v if x.dia < FIN_DESARROLLO]
        r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        sem = [math.log(c[i] / c[i - 7]) for i in range(7, len(c), 7)]
        res = {"dias": len(c), "autocorr_diaria": {k: autocorr(r, k) for k in range(1, 6)},
               "autocorr_semanal": {k: autocorr(sem, k) for k in range(1, 5)}, "momentum": {}}
        fechas = range(180, len(c) - 30, 30)
        for lb in (30, 90, 180):
            pos = [math.log(c[t + 30] / c[t]) for t in fechas if c[t] / c[t - lb] - 1 > 0]
            neg = [math.log(c[t + 30] / c[t]) for t in fechas if c[t] / c[t - lb] - 1 <= 0]
            dif = st.fmean(pos) - st.fmean(neg)
            se = math.sqrt(st.variance(pos) / len(pos) + st.variance(neg) / len(neg))
            res["momentum"][lb] = {"n_pos": len(pos), "n_neg": len(neg), "media_sig30_si_pos": st.fmean(pos),
                                   "media_sig30_si_neg": st.fmean(neg), "diferencia": dif, "t": dif / se}
        votos = sum(m["diferencia"] > 0 for m in res["momentum"].values())
        res["regla"] = ("familia 1 (tendencia)" if votos >= 2 else
                        "estudiar familia 3 (reversión)" if res["autocorr_diaria"][1] < -0.10 else "sin base")
        out["simbolos"][s] = res
    (AQUI / "evidencia_inicial_desarrollo.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for s, res in out["simbolos"].items():
        print(s, "días", res["dias"], "→", res["regla"])
        print("  autocorr diaria", {k: round(x, 3) for k, x in res["autocorr_diaria"].items()},
              "semanal", {k: round(x, 3) for k, x in res["autocorr_semanal"].items()})
        for lb, m in res["momentum"].items():
            print(f"  L={lb}: n+={m['n_pos']} n-={m['n_neg']} sig30|+ {m['media_sig30_si_pos']:+.3f} sig30|- "
                  f"{m['media_sig30_si_neg']:+.3f} dif {m['diferencia']:+.3f} t={m['t']:.2f}")


if __name__ == "__main__":
    main()
