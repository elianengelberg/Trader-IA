"""Esquema de datos de mercado: barras horarias alineadas de spot, perpetuo y mark, y eventos de funding."""

from __future__ import annotations

from dataclasses import dataclass, field

from hcarry.conventions import HORA_MS, iso


@dataclass(frozen=True, slots=True)
class Barra:
    """Una hora [t, t + 1 h). S = spot, F = perpetuo (último precio), M = mark. qv_* = volumen en USDT (o None)."""
    t: int
    S_o: float
    S_h: float
    S_l: float
    S_c: float
    F_o: float
    F_h: float
    F_l: float
    F_c: float
    M_o: float
    M_h: float
    M_l: float
    M_c: float
    qv_spot: float | None = None
    qv_perp: float | None = None
    relleno: bool = False  # hora sin datos rellenada con el último cierre: el motor no decide en ella
    prima: float | None = None  # índice de prima al cierre (fracción); None si no hay dato oficial


@dataclass(frozen=True, slots=True)
class EventoFunding:
    """Liquidación de funding en el instante ``t`` (alineado a la hora). ``tasa`` en fracción por evento.
    ``mark`` es el markPrice publicado con el evento, si existe."""
    t: int
    tasa: float
    mark: float | None = None


@dataclass
class Panel:
    """Serie horaria contigua y eventos de funding dentro de [barras[0].t, barras[-1].t + 1 h).

    ``origen`` describe la procedencia ('sintetico:...' o 'binance_vision:...'); los informes la muestran siempre,
    para que un resultado sintético no se confunda con uno real."""
    barras: list[Barra]
    funding: list[EventoFunding]
    origen: str
    notas: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.barras:
            raise ValueError("panel vacío")
        for a, b in zip(self.barras, self.barras[1:]):
            if b.t - a.t != HORA_MS:
                raise ValueError(f"barras no contiguas: {iso(a.t)} → {iso(b.t)}")
        if self.barras[0].t % HORA_MS:
            raise ValueError("barras no alineadas a la hora")
        ini, fin = self.barras[0].t, self.barras[-1].t + HORA_MS
        marcas = [e.t for e in self.funding]
        if marcas != sorted(set(marcas)):
            raise ValueError("eventos de funding desordenados o repetidos")
        if any(m < ini or m >= fin or m % HORA_MS for m in marcas):
            raise ValueError("evento de funding fuera del panel o no alineado a la hora")

    @property
    def sintetico(self) -> bool:
        return self.origen.startswith("sintetico")

    @property
    def inicio(self) -> int:
        return self.barras[0].t

    @property
    def fin(self) -> int:
        """Exclusivo."""
        return self.barras[-1].t + HORA_MS

    def recortar(self, desde_ms: int, hasta_ms: int) -> Panel:
        """Sub-panel [desde, hasta)."""
        barras = [b for b in self.barras if desde_ms <= b.t < hasta_ms]
        if not barras:
            raise ValueError(f"sin barras en [{iso(desde_ms)}, {iso(hasta_ms)})")
        ini, fin = barras[0].t, barras[-1].t + HORA_MS
        return Panel(barras, [e for e in self.funding if ini <= e.t < fin], self.origen, list(self.notas))
