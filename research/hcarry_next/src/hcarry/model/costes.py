"""Modelo de costes por pata y filtros de cantidad. Los valores por defecto son los de rev. 5 (costes por pata) y los
filtros recordados de Binance para BTCUSDT; estos últimos NO están verificados (supuestos S1/S8 de rev. 5)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from hcarry.conventions import BP


@dataclass(frozen=True)
class Costes:
    """Coste de ejecutar un nocional en una pata, en USDT: nocional · (comisión + slippage + impacto) · multiplicador.

    - El nocional se valora al precio de apertura de la barra de ejecución (convención S12 de rev. 5); el precio de
      la operación es la apertura y el slippage se cobra como coste explícito (equivalente a primer orden a
      ejecutar a un precio peor, y conciliable sin ambigüedad).
    - ``impacto_bps_raiz``: impacto adicional en bps · sqrt(nocional / volumen en USDT de la hora). 0 por defecto.
      Sirve para el análisis de capacidad y de liquidez reducida."""
    spot_comision_bps: float = 10.0
    spot_slippage_bps: float = 5.0
    perp_comision_bps: float = 5.0
    perp_slippage_bps: float = 5.0
    impacto_bps_raiz: float = 0.0
    multiplicador: float = 1.0

    def bps(self, pata: str) -> float:
        if pata == "spot":
            return self.spot_comision_bps + self.spot_slippage_bps
        if pata == "perp":
            return self.perp_comision_bps + self.perp_slippage_bps
        raise ValueError(pata)

    def coste(self, pata: str, nocional: float, volumen: float | None = None) -> float:
        if nocional < 0:
            raise ValueError("nocional negativo")
        extra = 0.0
        if self.impacto_bps_raiz and volumen:
            extra = self.impacto_bps_raiz * math.sqrt(nocional / volumen)
        return nocional * (self.bps(pata) + extra) * BP * self.multiplicador

    def escalados(self, factor: float) -> Costes:
        return replace(self, multiplicador=self.multiplicador * factor)


@dataclass(frozen=True)
class Filtros:
    """Filtros de cantidad comunes a las dos patas, en lotes enteros.

    - ``paso``: paso común (mcm de los stepSize de spot y perpetuo; rev. 5: 0,001 BTC).
    - Nocional mínimo por pata (spot 5 USDT; perpetuo 100 USDT: valores recordados, NO verificados).
    - ``max_lotes``: si una orden supera el máximo se divide en varias (S7 de rev. 5); el coste no cambia.
    - El cierre total se permite siempre aunque quede por debajo de los mínimos (supuesto declarado)."""
    paso: float = 0.001
    min_lotes: int = 1
    nocional_min_spot: float = 5.0
    nocional_min_perp: float = 100.0
    max_lotes: int | None = None

    def lotes(self, cantidad: float) -> int:
        """Cantidad → lotes enteros, redondeando HACIA ABAJO (nunca se gasta más de lo disponible)."""
        if cantidad <= 0:
            return 0
        return math.floor(cantidad / self.paso + 1e-9)

    def cantidad(self, lotes: int) -> float:
        return lotes * self.paso

    def motivo_rechazo(self, delta_lotes: int, S: float, F: float, cierre_total: bool) -> str | None:
        """None si la orden es ejecutable; si no, el motivo."""
        if delta_lotes == 0:
            return "cantidad nula"
        if cierre_total:
            return None
        n = abs(delta_lotes)
        if n < self.min_lotes:
            return f"{n} lotes < mínimo {self.min_lotes}"
        q = self.cantidad(n)
        if q * S < self.nocional_min_spot:
            return f"nocional spot {q * S:.2f} < {self.nocional_min_spot}"
        if q * F < self.nocional_min_perp:
            return f"nocional perp {q * F:.2f} < {self.nocional_min_perp}"
        return None

    def ordenes(self, delta_lotes: int) -> int:
        if self.max_lotes is None or delta_lotes == 0:
            return 1 if delta_lotes else 0
        return math.ceil(abs(delta_lotes) / self.max_lotes)
