"""Diseño secuencial (MEC §7.1) y aritmética de potencia (Plan de evidencia §4): valores publicados, simulación
independiente de Monte Carlo y las cifras que ya figuran en los documentos del proyecto."""
import math
import random

import pytest
from pec import potencia as P
from pec import secuencial as S

T5 = [0.2, 0.4, 0.6, 0.8, 1.0]


def test_una_mirada_es_la_prueba_fija():
    assert S.fronteras_obf([1.0], 0.025)["fronteras_z"][0] == pytest.approx(1.959964, abs=1e-5)


def test_fronteras_publicadas_lan_demets_obf_k5():
    # Valores de referencia publicados para Lan–DeMets tipo O'Brien–Fleming, 5 miradas equiespaciadas, α = 0,025 unilateral
    c = S.fronteras_obf(T5, 0.025)["fronteras_z"]
    assert c == pytest.approx([4.8769, 3.3569, 2.6803, 2.2898, 2.0310], abs=5e-4)


def test_alfa_gastado_igual_al_objetivo():
    r = S.fronteras_obf([0.25, 0.5, 0.75, 1.0], 0.025)
    assert r["alfa_acumulado"] == pytest.approx(r["gasto_objetivo"], abs=1e-6)
    assert r["alfa_acumulado"][-1] == pytest.approx(0.025, abs=1e-6)


def test_monte_carlo_independiente_del_cruce_bajo_h0():
    """Simulación directa del browniano: la probabilidad acumulada de cruzar coincide con el gasto (±4 errores de MC)."""
    c = S.fronteras_obf(T5, 0.025)["fronteras_z"]
    rng = random.Random(20261021)
    n, cruces = 40000, [0] * 5
    for _ in range(n):
        s, t_prev = 0.0, 0.0
        for k, t in enumerate(T5):
            s += rng.gauss(0.0, math.sqrt(t - t_prev))
            t_prev = t
            if s / math.sqrt(t) >= c[k]:
                cruces[k] += 1
                break
    acumulado = 0
    objetivo = S.fronteras_obf(T5, 0.025)["gasto_objetivo"]
    for k in range(5):
        acumulado += cruces[k]
        p = acumulado / n
        ee = math.sqrt(max(objetivo[k] * (1 - objetivo[k]), 1e-6) / n)
        assert abs(p - objetivo[k]) <= 4 * ee + 1e-4, (k, p, objetivo[k])


def test_potencia_crece_con_la_deriva_e_inflacion_razonable():
    c = S.fronteras_obf(T5, 0.025)["fronteras_z"]
    assert S.potencia(T5, c, 0.0) == pytest.approx(0.025, abs=1e-5)
    pots = [S.potencia(T5, c, th) for th in (1.0, 2.0, 3.0)]
    assert pots == sorted(pots) and pots[-1] > 0.8
    r = S.inflacion(T5, 0.025, 0.20)
    assert 1.0 < r["R"] < 1.06
    assert S.inflacion([1.0], 0.025, 0.20)["R"] == pytest.approx(1.0, abs=2e-3)


def test_fracciones_invalidas():
    for t in ([0.5, 0.4, 1.0], [0.5, 0.9], [0.0, 1.0]):
        with pytest.raises(ValueError):
            S.fronteras_obf(t)


def test_tabla_general_del_plan_de_evidencia():
    # Plan de evidencia §4.2: años para TE/δ = 0,5 1 1,5 2 3 → 2,0 7,8 17,7 31,4 70,6
    for razon, anos in ((0.5, 2.0), (1, 7.8), (1.5, 17.7), (2, 31.4), (3, 70.6)):
        assert round(P.anos_necesarios(razon, 1.0), 1) == anos
    assert round(P.factor(), 4) == 2.8016


def test_cifras_de_T_y_de_las_propuestas():
    assert 63 < P.anos_necesarios(0.202, 0.0705) < 66          # «≈ 65» (Plan §4.3)
    assert round(P.anos_necesarios(0.202, 0.10)) == 32           # «≈ 32»
    assert 8.0 < P.anos_necesarios(0.202, 0.194) < 9.0           # «≈ 8,6»
    assert round(P.delta_por_operacion(0.126, 30), 3) == 0.064   # H-REV-SHOCK: «≥ 6,4 %»
    assert round(P.delta_por_operacion(0.126, 100), 3) == 0.035  # «≥ 3,5 %»
    assert round(P.delta_por_operacion(0.017, 300), 4) == 0.0027 or round(P.delta_por_operacion(0.017, 300), 4) == 0.0028


def test_criba_de_detectabilidad():
    assert P.criba_detectabilidad(0.5, 3)["veredicto"] == "NO_DETECTABLE_EN_EL_HORIZONTE"
    assert P.criba_detectabilidad(2.0, 3)["veredicto"] == "DETECTABLE"
    assert P.ir_requerido(3) == pytest.approx(2.8016 / math.sqrt(3), rel=1e-4)
    assert P.potencia_una_mirada(1.0, 1.0, 7.849) == pytest.approx(0.80, abs=0.002)
