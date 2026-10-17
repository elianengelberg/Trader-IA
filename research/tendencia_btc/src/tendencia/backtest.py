"""Backtest diario long/flat en spot: efectivo (USDT) + BTC. Decisión con el cierre del día d; ejecución en la apertura
oficial del día d + 1 + retraso, con coste = |valor negociado| × (comisión + slippage) × multiplicador. Sin
apalancamiento ni posiciones cortas; el efectivo rinde ``tasa_efectivo`` (0 por defecto)."""

from __future__ import annotations

from dataclasses import dataclass, field

from tendencia.datos import Vela

BP = 1e-4


@dataclass(frozen=True)
class Costes:
    comision_bps: float = 10.0
    slippage_bps: float = 5.0
    multiplicador: float = 1.0

    def tasa(self) -> float:
        return (self.comision_bps + self.slippage_bps) * BP * self.multiplicador


@dataclass
class Resultado:
    dias: list[str]
    equity: list[float]          # al cierre de cada día
    exposicion: list[float]      # peso del BTC al cierre de cada día
    capital: float
    operaciones: list[dict] = field(default_factory=list)
    costes: float = 0.0
    negociado: float = 0.0


def simular(velas: list[Vela], objetivo: list[float | None], desde: str, hasta: str, capital: float = 10_000.0,
            costes: Costes = Costes(), retraso: int = 0, banda: float | None = None,  # noqa: B008
            tasa_efectivo: float = 0.0) -> Resultado:
    """``objetivo[i]`` = exposición decidida con el cierre de ``velas[i]``. ``banda=None``: se opera solo cuando cambia
    el objetivo; con banda b se opera cuando |objetivo − peso actual| ≥ b (b = 0: rebalanceo diario)."""
    if len(objetivo) != len(velas):
        raise ValueError("una exposición objetivo por vela")
    idx = [i for i, v in enumerate(velas) if desde <= v.dia < hasta]
    if not idx:
        raise ValueError("ventana vacía")
    caja, q = capital, 0.0
    ultimo_obj: float | None = None
    res = Resultado([], [], [], capital)
    for i in idx:
        v = velas[i]
        j = i - 1 - retraso
        obj = objetivo[j] if j >= 0 and objetivo[j] is not None else 0.0
        caja *= 1 + tasa_efectivo / 365
        e_ap = caja + q * v.o
        peso = q * v.o / e_ap if e_ap > 0 else 0.0
        operar = (obj != ultimo_obj) if banda is None else (abs(obj - peso) >= banda and abs(obj - peso) > 1e-12)
        if operar and e_ap > 0:
            valor = obj * e_ap - q * v.o
            if abs(valor) > 1e-9:
                coste = abs(valor) * costes.tasa()
                caja -= valor + coste
                q += valor / v.o
                res.costes += coste
                res.negociado += abs(valor)
                res.operaciones.append({"dia": v.dia, "valor": valor, "coste": coste, "objetivo": obj})
            ultimo_obj = obj
        e_ci = caja + q * v.c
        res.dias.append(v.dia)
        res.equity.append(e_ci)
        res.exposicion.append(q * v.c / e_ci if e_ci > 0 else 0.0)
    return res
