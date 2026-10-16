"""Paneles pequeños construidos a mano para las pruebas (SINTÉTICOS)."""

from __future__ import annotations

from hcarry.conventions import HORA_MS, ms
from hcarry.data.schema import Barra, EventoFunding, Panel

INI = ms("2024-03-01")
P0 = 60_000.0


def barra(t: int, S: float, F: float | None = None, M: float | None = None, *, S_c: float | None = None,
          F_c: float | None = None, M_c: float | None = None, M_h: float | None = None, F_h: float | None = None,
          F_l: float | None = None, qv: float | None = None) -> Barra:
    F = S if F is None else F
    M = F if M is None else M
    S_c = S if S_c is None else S_c
    F_c = F if F_c is None else F_c
    M_c = M if M_c is None else M_c
    M_h = max(M, M_c) if M_h is None else M_h
    F_h = max(F, F_c) if F_h is None else F_h
    F_l = min(F, F_c) if F_l is None else F_l
    return Barra(t, S, max(S, S_c), min(S, S_c), S_c, F, F_h, F_l, F_c, M, M_h, min(M, M_c), M_c, qv, qv)


def panel(precios: list[float], tasas: dict[int, float] | None = None, *, intervalo_h: int = 8, tasa: float = 0.0,
          ini: int = INI, origen: str = "sintetico:prueba") -> Panel:
    """Barras con apertura = precios[i] y cierre = precios[i+1] (el último cierre repite). Funding: ``tasas`` por
    índice de hora o, si no se da, ``tasa`` constante cada ``intervalo_h`` horas desde la hora 0."""
    n = len(precios)
    barras = [barra(ini + i * HORA_MS, precios[i], S_c=precios[min(i + 1, n - 1)]) for i in range(n)]
    if tasas is None:
        tasas = {i: tasa for i in range(0, n, intervalo_h)}
    eventos = [EventoFunding(ini + i * HORA_MS, f) for i, f in sorted(tasas.items()) if i < n]
    return Panel(barras, eventos, origen)


def constante(n: int = 72, tasa: float = 0.0, intervalo_h: int = 8) -> Panel:
    return panel([P0] * n, tasa=tasa, intervalo_h=intervalo_h)
