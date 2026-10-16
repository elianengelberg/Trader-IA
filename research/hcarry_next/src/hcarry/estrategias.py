"""Políticas de decisión. Cada política devuelve un ``Objetivo`` a partir de una ``Vista`` que SOLO expone información
disponible en el instante de decisión t (apertura de la barra i):

  - barras CERRADAS (índices < i);
  - precios de APERTURA de la barra i (observables en t; la ejecución se hace a esos precios, con costes);
  - eventos de funding con marca ≤ t (el de t ya se liquidó);
  - el estado de la propia cartera.

La vista no tiene ninguna referencia al panel completo accesible por la política: no hay forma de leer el futuro sin
cambiar este módulo (lo comprueba ``tests/test_sin_lookahead.py``)."""

from __future__ import annotations

import bisect
import itertools
import math
from dataclasses import dataclass, field

from hcarry.conventions import HORA_MS
from hcarry.data.schema import Barra, EventoFunding


@dataclass(frozen=True)
class Objetivo:
    """Qué quiere la política.

    - ``en_mercado``: mantener el carry (True) o estar en efectivo (False).
    - ``rho``: ratio objetivo de la pata de futuros (equity de futuros / nocional del corto). rev. 5: 1.
    - ``banda``: se reequilibra si ρ sale de [lo, hi]. rev. 5: (0,5; 1,5).
    - ``escala``: fracción del equity desplegada (1 = todo; el resto queda como efectivo ocioso en spot).
    - ``tolerancia``: si no es None, también se reequilibra cuando la cantidad objetivo difiere de la actual en más
      de esa fracción (lo usan las políticas que cambian la escala)."""
    en_mercado: bool
    rho: float = 1.0
    banda: tuple[float, float] = (0.5, 1.5)
    escala: float = 1.0
    tolerancia: float | None = None


@dataclass(frozen=True)
class EstadoVisible:
    en_posicion: bool
    rho_apertura: float | None
    equity_apertura: float
    horas_en_posicion: int
    horas_desde_salida: int | None


class Vista:
    """Ventana de información en el instante de decisión. Construida por el motor; las políticas no ven el panel."""

    __slots__ = ("F", "M", "S", "_barras", "_funding", "_i", "_marcas_funding", "estado", "t")

    def __init__(self, barras: list[Barra], funding: list[EventoFunding], marcas_funding: list[int], i: int,
                 estado: EstadoVisible) -> None:
        self._barras, self._funding, self._marcas_funding, self._i = barras, funding, marcas_funding, i
        b = barras[i]
        self.t, self.S, self.F, self.M = b.t, b.S_o, b.F_o, b.M_o
        self.estado = estado

    def cerradas(self, n: int | None = None) -> list[Barra]:
        """Últimas n barras cerradas (todas si n es None)."""
        ini = 0 if n is None else max(0, self._i - n)
        return self._barras[ini:self._i]

    def funding(self, n: int | None = None) -> list[EventoFunding]:
        """Últimos n eventos de funding con marca ≤ t."""
        k = bisect.bisect_right(self._marcas_funding, self.t)
        ini = 0 if n is None else max(0, k - n)
        return self._funding[ini:k]


class Politica:
    nombre = "politica"

    def parametros(self) -> dict:
        return {}

    def decidir(self, v: Vista) -> Objetivo:  # pragma: no cover - interfaz
        raise NotImplementedError


# ====================================================================== referencias
@dataclass
class Siempre(Politica):
    """Referencia H-CARRY rev. 5 (reconstruida): carry permanente desde la primera hora, ρ objetivo 1 y banda
    (0,5; 1,5). Con ``rho`` < 1 se convierte en la variante apalancada de la pata corta."""
    rho: float = 1.0
    banda: tuple[float, float] = (0.5, 1.5)
    nombre: str = "siempre"

    def parametros(self) -> dict:
        return {"rho": self.rho, "banda": list(self.banda)}

    def decidir(self, v: Vista) -> Objetivo:
        return Objetivo(True, self.rho, self.banda)


@dataclass
class Efectivo(Politica):
    """Nunca entra (rentabilidad 0 sin el comparador)."""
    nombre: str = "efectivo"

    def decidir(self, v: Vista) -> Objetivo:
        return Objetivo(False)


# ====================================================================== alternativas
def apr_funding(eventos: list[EventoFunding]) -> float | None:
    """Tasa anualizada (sobre el nocional) implícita en la media de los eventos, usando el intervalo observado entre
    ellos. None si hay menos de 2 eventos."""
    if len(eventos) < 2:
        return None
    media = sum(e.tasa for e in eventos) / len(eventos)
    intervalo_h = (eventos[-1].t - eventos[0].t) / HORA_MS / (len(eventos) - 1)
    if intervalo_h <= 0:
        return None
    return media * (365 * 24 / intervalo_h)


@dataclass
class UmbralFunding(Politica):
    """Entra cuando el funding anualizado reciente (media de los últimos ``ventana`` eventos) supera ``entrada`` y sale
    cuando cae por debajo de ``salida`` (histéresis: salida < entrada), tras al menos ``permanencia_h`` horas dentro.

    Hipótesis: el funding es persistente; estar fuera cuando es bajo o negativo evita pagarlo, y el ahorro supera los
    costes de entrar y salir. Se refuta si, con costes registrados, su resultado neto no supera al de ``Siempre``
    fuera de muestra, o si solo lo supera en un período."""
    ventana: int = 21
    entrada: float = 0.10
    salida: float = 0.03
    permanencia_h: int = 72
    rho: float = 1.0
    banda: tuple[float, float] = (0.5, 1.5)
    base_min_entrada_bps: float | None = None
    nombre: str = "umbral_funding"

    def parametros(self) -> dict:
        return {"ventana": self.ventana, "entrada": self.entrada, "salida": self.salida,
                "permanencia_h": self.permanencia_h, "rho": self.rho, "banda": list(self.banda),
                "base_min_entrada_bps": self.base_min_entrada_bps}

    def decidir(self, v: Vista) -> Objetivo:
        apr = apr_funding(v.funding(self.ventana))
        e = v.estado
        if e.en_posicion:
            salir = apr is not None and apr < self.salida and e.horas_en_posicion >= self.permanencia_h
            return Objetivo(not salir, self.rho, self.banda)
        entrar = apr is not None and apr >= self.entrada
        if entrar and self.base_min_entrada_bps is not None:
            entrar = (v.F - v.S) / v.S * 1e4 >= self.base_min_entrada_bps
        return Objetivo(entrar, self.rho, self.banda)


INTERES_8H = 0.0001


def funding_predicho(prima: float, intervalo_h: int = 8) -> float:
    """Funding del intervalo según la fórmula de Binance para una prima media dada:
    f = P + clamp(I − P, −0,05 %, +0,05 %), con I = 0,01 % por 8 h (escalado al intervalo) y tope ±0,3 %·h/8.
    El tope real depende del contrato (supuesto S1: no verificado)."""
    interes = INTERES_8H * intervalo_h / 8
    f = prima + min(0.0005, max(-0.0005, interes - prima))
    tope = 0.003 * intervalo_h / 8
    return min(tope, max(-tope, f))


@dataclass
class UmbralPrima(Politica):
    """Alternativa a UmbralFunding: predice el PRÓXIMO funding con la fórmula de Binance a partir de la prima media de
    las últimas ``ventana_h`` barras CERRADAS (índice de prima oficial si existe; si no, F/S − 1 como aproximación).

    Hipótesis: el funding es una función mecánica de la prima del intervalo, que ya es observable antes de la
    liquidación; reacciona antes que la media de funding pasados. Se refuta si, frente a su línea base, no mejora
    fuera de muestra o si su ventaja desaparece con el retraso de ejecución."""
    ventana_h: int = 24
    entrada: float = 0.05
    salida: float = 0.0
    permanencia_h: int = 24
    rho: float = 1.0
    banda: tuple[float, float] = (0.5, 1.5)
    intervalo_h: int = 8
    nombre: str = "umbral_prima"

    def parametros(self) -> dict:
        return {"ventana_h": self.ventana_h, "entrada": self.entrada, "salida": self.salida,
                "permanencia_h": self.permanencia_h, "rho": self.rho, "banda": list(self.banda),
                "intervalo_h": self.intervalo_h}

    def prima_media(self, v: Vista) -> float | None:
        barras = v.cerradas(self.ventana_h)
        if not barras:
            return None
        valores = [b.prima if b.prima is not None else (b.F_c - b.S_c) / b.S_c for b in barras]
        return sum(valores) / len(valores)

    def decidir(self, v: Vista) -> Objetivo:
        p = self.prima_media(v)
        apr = None if p is None else funding_predicho(p, self.intervalo_h) * 365 * 24 / self.intervalo_h
        e = v.estado
        if e.en_posicion:
            salir = apr is not None and apr < self.salida and e.horas_en_posicion >= self.permanencia_h
            return Objetivo(not salir, self.rho, self.banda)
        return Objetivo(apr is not None and apr >= self.entrada, self.rho, self.banda)


def vol_anual(barras: list[Barra]) -> float | None:
    """Volatilidad anualizada de los rendimientos logarítmicos horarios del spot (cierres)."""
    if len(barras) < 3:
        return None
    r = [math.log(b.S_c / a.S_c) for a, b in itertools.pairwise(barras)]
    m = sum(r) / len(r)
    var = sum((x - m) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var * 24 * 365)


@dataclass
class RhoPorVolatilidad(Politica):
    """Envuelve otra política y ajusta el ratio de la pata de futuros a la volatilidad reciente: más margen (ρ mayor)
    cuando la volatilidad sube. Hipótesis: reduce el riesgo de liquidación y de reequilibrios forzados sin renunciar
    al carry. ρ = clip(rho_base · vol / vol_ref, rho_min, rho_max); la banda escala con ρ."""
    base: Politica = field(default_factory=Siempre)
    ventana_h: int = 24 * 7
    vol_ref: float = 0.6
    rho_base: float = 0.5
    rho_min: float = 0.4
    rho_max: float = 1.0
    tolerancia: float = 0.2
    nombre: str = "rho_vol"

    def parametros(self) -> dict:
        return {"base": self.base.nombre, "base_param": self.base.parametros(), "ventana_h": self.ventana_h,
                "vol_ref": self.vol_ref, "rho_base": self.rho_base, "rho_min": self.rho_min, "rho_max": self.rho_max,
                "tolerancia": self.tolerancia}

    def decidir(self, v: Vista) -> Objetivo:
        o = self.base.decidir(v)
        vol = vol_anual(v.cerradas(self.ventana_h))
        rho = self.rho_base if vol is None else min(self.rho_max, max(self.rho_min, self.rho_base * vol / self.vol_ref))
        lo, hi = o.banda
        f = rho / o.rho
        return Objetivo(o.en_mercado, rho, (lo * f, hi * f), o.escala, self.tolerancia)


@dataclass
class EscalaPorVolatilidad(Politica):
    """Envuelve otra política y despliega solo una fracción del equity cuando la volatilidad es alta:
    escala = min(1, vol_obj / vol). Hipótesis: reduce caída y coste de reequilibrio en episodios violentos."""
    base: Politica = field(default_factory=Siempre)
    ventana_h: int = 24 * 7
    vol_obj: float = 0.5
    tolerancia: float = 0.25
    nombre: str = "escala_vol"

    def parametros(self) -> dict:
        return {"base": self.base.nombre, "base_param": self.base.parametros(), "ventana_h": self.ventana_h,
                "vol_obj": self.vol_obj, "tolerancia": self.tolerancia}

    def decidir(self, v: Vista) -> Objetivo:
        o = self.base.decidir(v)
        vol = vol_anual(v.cerradas(self.ventana_h))
        escala = 1.0 if not vol else min(1.0, self.vol_obj / vol)
        return Objetivo(o.en_mercado, o.rho, o.banda, escala, self.tolerancia)


def construir(nombre: str, params: dict | None = None) -> Politica:
    """Política a partir de su nombre y parámetros (para configuraciones JSON)."""
    p = dict(params or {})
    if "banda" in p:
        p["banda"] = tuple(p["banda"])
    if nombre == "siempre":
        return Siempre(**p)
    if nombre == "efectivo":
        return Efectivo()
    if nombre == "umbral_funding":
        return UmbralFunding(**p)
    if nombre == "umbral_prima":
        return UmbralPrima(**p)
    if nombre in ("rho_vol", "escala_vol"):
        base = construir(p.pop("base", "siempre"), p.pop("base_param", {}))
        return (RhoPorVolatilidad if nombre == "rho_vol" else EscalaPorVolatilidad)(base=base, **p)
    raise ValueError(f"política desconocida: {nombre}")
