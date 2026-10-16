"""Política UmbralPrima: predicción del funding con la fórmula de Binance a partir de la prima observada, sin
look-ahead, y lectura de premiumIndexKlines."""

from __future__ import annotations

import pytest
from ayudas import INI, P0

from hcarry.conventions import HORA_MS
from hcarry.data.schema import Barra, Panel
from hcarry.estrategias import EstadoVisible, UmbralPrima, Vista, funding_predicho
from hcarry.model.conciliacion import conciliar
from hcarry.model.motor import simular


def test_formula_de_binance() -> None:
    assert funding_predicho(0.0) == pytest.approx(0.0001)          # prima nula: el interés
    assert funding_predicho(0.0004) == pytest.approx(0.0001)       # dentro de la banda de ±0,05 %: el interés
    assert funding_predicho(-0.0004) == pytest.approx(0.0001)
    assert funding_predicho(0.001) == pytest.approx(0.0005)        # prima alta: prima − 0,05 %
    assert funding_predicho(-0.001) == pytest.approx(-0.0005)      # prima muy negativa: prima + 0,05 %
    assert funding_predicho(0.02) == pytest.approx(0.003)          # tope
    assert funding_predicho(0.0, intervalo_h=4) == pytest.approx(0.00005)


def _barra(i: int, prima: float | None) -> Barra:
    F = P0 * (1 + (prima or 0.0))
    return Barra(INI + i * HORA_MS, P0, P0, P0, P0, F, F, F, F, F, F, F, F, prima=prima)


def test_entra_y_sale_segun_la_prima_observada() -> None:
    primas = [0.0] * 30 + [-0.002] * 30 + [0.0] * 30
    p = Panel([_barra(i, x) for i, x in enumerate(primas)], [], "sintetico:prueba")
    pol = UmbralPrima(ventana_h=4, entrada=0.05, salida=0.0, permanencia_h=0)
    r = simular(p, pol)
    tipos = [(o["tipo"], (o["t"] - INI) // HORA_MS) for o in r.operaciones]
    assert tipos[0] == ("apertura", 1)                     # en t=0 no hay barras cerradas: no decide
    salida = next(h for tipo, h in tipos if tipo == "cierre")
    assert 31 <= salida <= 31 + 4                          # la prima negativa se ve en barras CERRADAS
    reentrada = [h for tipo, h in tipos if tipo == "apertura" and h > salida]
    assert reentrada and 61 <= reentrada[0] <= 61 + 4
    conciliar(r, p)


def test_usa_la_prima_oficial_y_si_falta_el_perp_frente_al_spot() -> None:
    barras = [_barra(i, None) for i in range(10)]
    v = Vista(barras, [], [], 10 - 1, EstadoVisible(False, None, 1.0, 0, None))
    assert UmbralPrima(ventana_h=3).prima_media(v) == pytest.approx(0.0)
    oficial = [_barra(i, 0.001) for i in range(10)]
    v = Vista(oficial, [], [], 9, EstadoVisible(False, None, 1.0, 0, None))
    assert UmbralPrima(ventana_h=3).prima_media(v) == pytest.approx(0.001)
