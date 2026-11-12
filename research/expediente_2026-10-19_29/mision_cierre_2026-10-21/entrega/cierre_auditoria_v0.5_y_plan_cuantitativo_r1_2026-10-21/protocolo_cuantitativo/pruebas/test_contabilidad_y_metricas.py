"""Contabilidad del MEC §2 (B5 referencia a mano, B9 suma de operaciones, identidad x̄ = cov(w, r)), costos, funding,
liquidación con margen aislado y métricas descriptivas."""
import random

import pytest
from pec import contabilidad as K
from pec import metricas as M


def test_referencia_a_mano_dos_operaciones():
    o = [100, 101, 102, 104, 103, 105]
    c = [101, 102, 104, 103, 105, 106]
    obj = [0, 1, 1, 0, 1, 0]
    f, s = 0.001, 0.0005
    r = K.simular_manga(o, c, obj, f, s, 1.0)
    q1 = 1.0 / (101 * (1 + s) * (1 + f))
    cobro1 = q1 * 104 * (1 - s) * (1 - f)
    q2 = cobro1 / (103 * (1 + s) * (1 + f))
    cobro2 = q2 * 105 * (1 - s) * (1 - f)
    assert r["valores"][-1] == pytest.approx(cobro2, rel=1e-12)
    assert r["valores"][2] == pytest.approx(q1 * 104, rel=1e-12)          # marcado al cierre de la barra 2
    assert [op["entrada_barra"] for op in r["operaciones"]] == [1, 4]
    assert r["exposicion"][0] == pytest.approx(q1 * 101 / 1.0, rel=1e-12)  # w_1 = q·C_0/W_0


def test_suma_de_operaciones_igual_a_la_variacion_del_capital():
    rng = random.Random(4)
    c = [100.0]
    for _ in range(300):
        c.append(c[-1] * (1 + rng.gauss(0, 0.02)))
    o = [c[0]] + c[:-1]
    obj = [0] + [rng.choice([0, 1]) for _ in range(300)]
    r = K.simular_manga(o, c, obj)
    assert sum(op["pnl"] for op in r["operaciones"]) == pytest.approx(r["valores"][-1] - r["valores"][0], abs=1e-12)


def test_identidad_del_mec_sin_costos():
    """Sin costos y con apertura = cierre anterior: x̄ = (1/n)·Σ(w_t − ε)·r_t = covarianza muestral (1/n) de w y r."""
    rng = random.Random(8)
    c = [100.0]
    for _ in range(500):
        c.append(c[-1] * (1 + rng.gauss(0.0002, 0.015)))
    o = [c[0]] + c[:-1]
    obj = [0] + [1 if rng.random() < 0.4 else 0 for _ in range(500)]
    obj[-1] = 0  # sin liquidación final con costos
    r = K.simular_manga(o, c, obj, comision=0.0, slippage=0.0)
    w, ret, n = r["exposicion"], r["r_activo"], len(r["exceso"])
    wb, rb = sum(w) / n, sum(ret) / n
    cov = sum((a - wb) * (b - rb) for a, b in zip(w, ret, strict=True)) / n
    assert sum(r["exceso"]) / n == pytest.approx(cov, abs=1e-14)


def test_los_costos_reducen_y_la_ventana_liquida():
    c = [100, 101, 103, 102, 104]
    o = [100, 100, 101, 103, 102]
    obj = [0, 1, 1, 1, 1]
    sin = K.simular_manga(o, c, obj, 0.0, 0.0)
    con = K.simular_manga(o, c, obj, 0.001, 0.0005)
    assert con["valores"][-1] < sin["valores"][-1]
    assert con["operaciones"][-1].get("liquidada_al_fin_de_ventana") is True
    with pytest.raises(ValueError):
        K.simular_manga(o, c, [1, 1, 1, 1, 1])  # la primera barra no tiene información previa
    with pytest.raises(ValueError):
        K.simular_manga(o, c, [0, 2, 1, 1, 1])


def test_funding_y_liquidacion():
    assert K.funding(2.0, 100.0, 0.0001) == pytest.approx(-0.02)   # largo paga con tasa positiva
    assert K.funding(-2.0, 100.0, 0.0001) == pytest.approx(0.02)   # corto cobra
    assert K.precio_liquidacion_aislado(100, 10, 0.005, 1) == pytest.approx(90.5)
    assert K.precio_liquidacion_aislado(100, 10, 0.005, -1) == pytest.approx(109.5)
    r = K.simular_apalancada(100, [101, 100, 99], [99, 95, 90], [100, 96, 91], 10, 0.005, 1)
    assert r["liquidada"] and r["barra"] == 2 and r["resultado_sobre_margen"] == -1.0
    ok = K.simular_apalancada(100, [101, 103], [99.5, 100], [100.5, 102], 5, 0.005, 1)
    assert not ok["liquidada"] and ok["resultado_sobre_margen"] > 0
    with pytest.raises(ValueError):
        K.precio_liquidacion_aislado(100, 10, 0.2, 1)  # margen de mantenimiento ≥ 1/L


def test_metricas_descriptivas():
    v = [1.0, 1.1, 0.99, 1.2, 1.08]
    ops = [{"pnl": 0.1}, {"pnl": -0.02}]
    r = M.resumen(v, [1, 1, 0, 1], ops, 252, subperiodos=2, exceso=[0.01, -0.02, 0.03, 0.01])
    assert r["maxima_caida"] == pytest.approx(0.99 / 1.1 - 1)
    assert r["rendimiento_total"] == pytest.approx(0.08)
    assert r["tasa_acierto"] == 0.5 and r["operaciones"] == 2
    assert r["estabilidad"]["subperiodos_con_exceso_positivo"] == 1
    assert r["rotacion_anual"] == pytest.approx(3 / (4 / 252))
