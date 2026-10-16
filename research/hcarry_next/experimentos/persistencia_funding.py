"""Diagnóstico de la hipótesis de UmbralFunding: ¿predice el funding medio de los últimos k días el de los k días
siguientes? Correlación entre medias de bloques consecutivos no solapados y tabla de transición del signo.

Con datos reales solo debe correrse sobre el período de DESARROLLO (nunca sobre test). Uso:
  python -B experimentos/persistencia_funding.py                  (mundos sintéticos 101–106 y sus nulos)
  python -B experimentos/persistencia_funding.py DIR_BINANCE      (desarrollo con datos reales)"""

from __future__ import annotations

import math
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "src"))

import itertools

from hcarry.conventions import DIA_MS
from hcarry.lab import experimento as X
from hcarry.lab.divisiones import rango


def medias_por_bloque(eventos, dias: int) -> list[float]:  # type: ignore[no-untyped-def]
    if not eventos:
        return []
    ini = eventos[0].t
    bloques: dict[int, list[float]] = {}
    for e in eventos:
        bloques.setdefault((e.t - ini) // (dias * DIA_MS), []).append(e.tasa)
    return [sum(v) / len(v) for _, v in sorted(bloques.items())][:-1]  # el último bloque puede estar incompleto


def correlacion(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / (sx * sy) if sx and sy else None


def diagnostico(eventos, etiqueta: str) -> str:  # type: ignore[no-untyped-def]
    partes = [etiqueta]
    for dias in (3, 7, 30):
        m = medias_por_bloque(eventos, dias)
        c = correlacion(m[:-1], m[1:])
        neg = [(a < 0, b < 0) for a, b in itertools.pairwise(m)]
        p_neg = (sum(1 for a, b in neg if a and b) / max(1, sum(1 for a, _ in neg if a)))
        partes.append(f"{dias} d: corr={c:+.2f} P(neg|neg)={p_neg:.2f} n={len(m)}" if c is not None else f"{dias} d: —")
    return " | ".join(partes)


def main() -> None:
    lineas = []
    if len(sys.argv) > 1:
        datos = {"fuente": "binance_vision", "directorio": sys.argv[1]}
        panel, _ = X.cargar_datos(datos)
        a, b = rango("desarrollo")
        lineas.append(diagnostico(panel.recortar(a, b).funding, "REAL desarrollo"))
    else:
        for s in range(101, 107):
            for nulo in (False, True):
                datos = {"fuente": "sintetico", "semilla": s, **({"nulo_semilla": s} if nulo else {})}
                panel, _ = X.cargar_datos(datos)
                a, b = rango("desarrollo")
                lineas.append(diagnostico(panel.recortar(a, b).funding, f"sintético {s}{' NULO' if nulo else ''}"))
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
