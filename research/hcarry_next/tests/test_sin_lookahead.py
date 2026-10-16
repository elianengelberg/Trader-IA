"""Ninguna decisión depende de información posterior al instante de decisión: si se altera TODO lo que ocurre después
de la apertura de la barra k (precios de la barra k en adelante salvo su apertura, y funding posterior), las
operaciones hasta t_k y la serie de equity hasta el cierre de k − 1 son idénticas."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from hcarry.data.schema import Panel
from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.estrategias import EscalaPorVolatilidad, RhoPorVolatilidad, Siempre, UmbralFunding, UmbralPrima, Vista
from hcarry.model.motor import simular

BASE = generar(ParamsSintetico(semilla=11, desde="2021-01-01", hasta="2021-04-01"))


def _alterar_despues(panel: Panel, k: int, semilla: int) -> Panel:
    rng = random.Random(semilla)
    barras = list(panel.barras[:k])
    bk = panel.barras[k]
    f = 1 + rng.uniform(-0.2, 0.2)
    barras.append(replace(bk, S_h=bk.S_h * 1.3, S_c=bk.S_c * f, F_h=bk.F_h * 1.3, F_c=bk.F_c * f, M_h=bk.M_h * 1.3,
                          M_c=bk.M_c * f, prima=-0.01))
    for b in panel.barras[k + 1:]:
        g = 1 + rng.uniform(-0.3, 0.3)
        barras.append(replace(b, S_o=b.S_o * g, S_h=b.S_h * g * 1.1, S_l=b.S_l * g * 0.9, S_c=b.S_c * g,
                              F_o=b.F_o * g, F_h=b.F_h * g * 1.1, F_l=b.F_l * g * 0.9, F_c=b.F_c * g,
                              M_o=b.M_o * g, M_h=b.M_h * g * 1.1, M_l=b.M_l * g * 0.9, M_c=b.M_c * g,
                              prima=rng.uniform(-0.01, 0.01)))
    tk = bk.t
    funding = [e if e.t <= tk else replace(e, tasa=-e.tasa * 3) for e in panel.funding]
    return Panel(barras, funding, panel.origen)


@pytest.mark.parametrize("politica", [Siempre(), UmbralFunding(ventana=9, entrada=0.05, salida=0.0, permanencia_h=24),
                                      RhoPorVolatilidad(), EscalaPorVolatilidad(base=UmbralFunding(ventana=9)),
                                      UmbralPrima(ventana_h=8, entrada=0.10, salida=0.03)],
                         ids=["siempre", "umbral", "rho_vol", "escala_vol", "prima"])
@pytest.mark.parametrize("k", [100, 700, 1500])
def test_decisiones_no_dependen_del_futuro(politica, k) -> None:  # type: ignore[no-untyped-def]
    a = simular(BASE, politica)
    b = simular(_alterar_despues(BASE, k, k), politica)
    tk = BASE.barras[k].t
    assert [o for o in a.operaciones if o["t"] <= tk] == [o for o in b.operaciones if o["t"] <= tk]
    assert a.serie[:k] == b.serie[:k]


def test_la_vista_no_expone_barras_futuras() -> None:
    from hcarry.estrategias import EstadoVisible
    v = Vista(BASE.barras, BASE.funding, [e.t for e in BASE.funding], 50, EstadoVisible(False, None, 1.0, 0, None))
    assert len(v.cerradas()) == 50 and v.cerradas()[-1].t < v.t
    assert all(e.t <= v.t for e in v.funding()) and len(v.cerradas(10)) == 10
    assert not hasattr(v, "panel") and not hasattr(v, "barras")
