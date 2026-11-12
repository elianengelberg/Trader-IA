"""Lectura descriptiva POSTERIOR (escrita después de ver los resultados; no cambia la decisión vinculante):
1. tasas agregadas por regla en todos los procesos salvo C4, para ver si hay un sesgo general;
2. en C4, la tasa entre réplicas NO degeneradas (las degeneradas no tienen eventos y cuentan como no rechazo).
Uso: python3 -B -I descriptivo_posterior.py <salida> <parametros.json>"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

Z = 1.959963984540054


def _wilson(k: int, r: int) -> list[float]:
    f = k / r
    c = (f + Z * Z / (2 * r)) / (1 + Z * Z / r)
    m = Z * math.sqrt(f * (1 - f) / r + Z * Z / (4 * r * r)) / (1 + Z * Z / r)
    return [round(c - m, 5), round(c + m, 5)]


def main(sal: Path, parametros: Path) -> dict:
    par = json.loads(parametros.read_bytes())
    out: dict = {"nota": "POSTERIOR y descriptivo: no cambia la decisión vinculante", "agregado_sin_C4": {},
                 "C4_sin_degeneradas": []}
    for regla, pref in (("bootstrap_t_l20", "primaria"), ("respaldo_max", "respaldo")):
        tot, k = 0, {a: 0 for a in par["bandas"]}
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                rp = json.loads((sal / "celdas" / f"{pref}_{pr}_n{n}.json").read_text(encoding="utf-8"))["replicas"]
                if pr == "C4":
                    validas = [p for p, g in rp if not g]
                    fila = {"regla": regla, "n": n, "no_degeneradas": len(validas)}
                    for a in par["bandas"]:
                        j = sum(1 for p in validas if p <= float(a))
                        fila[a] = {"tasa": round(j / len(validas), 5), "wilson95": _wilson(j, len(validas))}
                    out["C4_sin_degeneradas"].append(fila)
                    continue
                tot += len(rp)
                for a in par["bandas"]:
                    k[a] += sum(1 for p, _ in rp if p <= float(a))
        out["agregado_sin_C4"][regla] = {a: {"rechazos": k[a], "replicas": tot, "tasa": round(k[a] / tot, 5),
                                             "wilson95": _wilson(k[a], tot)} for a in par["bandas"]}
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=1))
