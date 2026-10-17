"""Evidencia inicial de la familia 5 (regla en FAMILIAS_ESTRATEGIA.md). SOLO desarrollo (2017-08-17 → 2021-12-31)."""

from __future__ import annotations

import json
import math
import statistics as st
from pathlib import Path

from tendencia.datos import leer

AQUI = Path(__file__).resolve().parent


def main() -> None:
    out = {"categoria": "HISTÓRICO, solo desarrollo", "simbolos": {}}
    for s in ("BTCUSDT", "ETHUSDT"):
        v, _ = leer(AQUI.parent / "datos" / s)
        c = [x.c for x in v if x.dia < "2022-01-01"]
        r = [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
        bloques = [st.pstdev(r[i:i + 30]) * math.sqrt(365) for i in range(0, len(r) - 29, 30)]
        x, y = bloques[:-1], bloques[1:]
        mx, my = st.fmean(x), st.fmean(y)
        pers = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / math.sqrt(
            sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
        grupos: dict[str, list[float]] = {"baja_lt50": [], "media_50_80": [], "alta_gt80": []}
        for i in range(30, len(r)):
            vol = st.pstdev(r[i - 30:i]) * math.sqrt(365)  # solo información previa al día i
            g = "baja_lt50" if vol < 0.5 else "alta_gt80" if vol > 0.8 else "media_50_80"
            grupos[g].append(r[i])
        res = {"persistencia_vol_30d": pers, "grupos": {
            g: {"dias": len(z), "media_diaria": st.fmean(z), "desv_diaria": st.pstdev(z),
                "cociente": st.fmean(z) / st.pstdev(z)} for g, z in grupos.items()}}
        res["regla"] = ("candidata familia 5" if pers >= 0.5 and res["grupos"]["baja_lt50"]["cociente"]
                        >= res["grupos"]["alta_gt80"]["cociente"] else "sin base")
        out["simbolos"][s] = res
    (AQUI / "evidencia_volatilidad_desarrollo.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for s, res in out["simbolos"].items():
        print(s, f"persistencia {res['persistencia_vol_30d']:.2f} →", res["regla"])
        for g, z in res["grupos"].items():
            print(f"   {g}: días {z['dias']}, media {z['media_diaria']*100:+.3f}%, desv {z['desv_diaria']*100:.2f}%, "
                  f"cociente {z['cociente']:+.4f}")


if __name__ == "__main__":
    main()
