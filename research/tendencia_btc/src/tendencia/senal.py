"""Señales diarias. La exposición decidida con el cierre del día d solo usa cierres ≤ d (sin look-ahead); el
backtest la aplica desde la apertura de d + 1 + retraso."""

from __future__ import annotations

import math
import statistics as st


def tsmom(cierres: list[float], ventanas: tuple[int, ...] = (30, 90, 180)) -> list[float | None]:
    """Fracción de ventanas con rentabilidad pasada positiva (0, 1/3, 2/3, 1). None sin historia suficiente."""
    out: list[float | None] = []
    for d in range(len(cierres)):
        if d < max(ventanas):
            out.append(None)
            continue
        out.append(sum(cierres[d] / cierres[d - lb] > 1 for lb in ventanas) / len(ventanas))
    return out


def vol_gestionada(cierres: list[float], vol_objetivo: float = 0.50, ventana: int = 30) -> list[float | None]:
    """min(1, vol_objetivo / vol realizada anualizada de los últimos ``ventana`` rendimientos log)."""
    out: list[float | None] = []
    for d in range(len(cierres)):
        if d < ventana:
            out.append(None)
            continue
        r = [math.log(cierres[i] / cierres[i - 1]) for i in range(d - ventana + 1, d + 1)]
        s = st.pstdev(r) * math.sqrt(365)
        out.append(min(1.0, vol_objetivo / s) if s > 0 else 1.0)
    return out
