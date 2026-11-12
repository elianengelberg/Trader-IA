"""PEC-1.1: regla decisiva, δ en la escala correcta, plan de miradas, política de faltantes e inválidos, esquema v1.1 y
congelamiento. Ninguna prueba usa datos de mercado; las series son sintéticas."""
import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from pec import decision as D
from pec import inferencia as I
from pec import prerregistro as V1
from pec import prerregistro_v11 as V11
from pec import prospectiva as P
from pec import sintetico as G

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = json.loads((RAIZ / "plantillas" / "ejemplo_prerregistro_SINTETICO_v1_1.json").read_text(encoding="utf-8"))


# ---------- el código calibrado es el que usa PEC-1.1 ----------
def test_codigo_calibrado_sin_cambios():
    for ruta, h in P.CODIGO_CALIBRADO_SHA256.items():
        assert hashlib.sha256((RAIZ / ruta).read_bytes()).hexdigest() == h, ruta


# ---------- δ ----------
def test_delta_diario_y_errores():
    assert P.delta_diario(0.10) == pytest.approx(0.10 / 365.25)
    for malo in (None, 0, -0.05):
        with pytest.raises(ValueError):
            P.delta_diario(malo)


def test_defecto_de_unidades_de_pec10_corregido():
    """PEC-1.0 comparaba δ anual con un IC90 diario sin convertir; PEC-1.1 convierte."""
    plan = P.plan_de_miradas(1461)
    res_11pct = {"p": 0.4, "ic90": (-0.001, 0.0003), "degenerada": False}   # IC90 sup ≈ 11 %/año
    res_7pct = {"p": 0.4, "ic90": (-0.001, 0.0002), "degenerada": False}    # IC90 sup ≈ 7,3 %/año
    assert P.evaluar_mirada(3, plan, 877, True, res_11pct, 0.10)["estado"] == "CONTINUAR"
    assert P.evaluar_mirada(3, plan, 877, True, res_7pct, 0.10)["estado"] == "EFECTO_RELEVANTE_DESCARTADO"
    # con la función de PEC-1.0 y δ anual sin convertir, ambos se declararían descartados (el defecto)
    assert D.mirada_prospectiva(3, plan["c_k"], 0.0, 0.0003, 0.10)["estado"] == "EFECTO_RELEVANTE_DESCARTADO"


# ---------- n_max, viabilidad y plan ----------
def test_inflacion_fijada_coincide_con_el_calculo():
    from pec import secuencial as S
    assert abs(S.inflacion([0.2, 0.4, 0.6, 0.8, 1.0], 0.025)["R"] - P.INFLACION_5_MIRADAS) < 1e-12


def test_plan_igual_al_de_sec_1_0():
    """Los umbrales de PEC-1.1 son los mismos que almacenó la calibración secuencial (n_max = 1096, 1461, 1826)."""
    esperados = {1096: [219, 438, 658, 877, 1096], 1461: [292, 584, 877, 1169, 1461], 1826: [365, 730, 1096, 1461, 1826]}
    for n, nk in esperados.items():
        assert P.plan_de_miradas(n)["n_k"] == nk


@pytest.mark.parametrize("delta,te,n,estado", [
    (0.15, 0.10, 1306, "DENTRO_DEL_RANGO_CALIBRADO"),
    (0.20, 0.15, 1653, "DENTRO_DEL_RANGO_CALIBRADO"),
    (0.10, 0.10, 2938, "NO_ALCANZABLE_EN_EL_RANGO_CALIBRADO"),
    (0.10, 0.05, 735, "FUERA_DEL_RANGO_CALIBRADO_CORTO")])
def test_n_max_y_viabilidad(delta, te, n, estado):
    v = P.viabilidad(delta, te)
    assert (v["n_max_dias"], v["estado"]) == (n, estado)


def test_plan_de_miradas_y_mirada_1_imposible():
    plan = P.plan_de_miradas(1826)
    assert plan["n_k"] == [365, 730, 1096, 1461, 1826]
    publicadas = [4.8769, 3.3569, 2.6803, 2.2898, 2.0310]
    assert all(abs(c - v) < 5e-3 for c, v in zip(plan["c_k"], publicadas, strict=True))
    assert plan["a_k"][0] < 1 / (P.B + 1) < plan["a_k"][1]  # el menor p posible no alcanza la mirada 1
    with pytest.raises(ValueError):
        P.plan_de_miradas(1095)
    with pytest.raises(ValueError):
        P.plan_de_miradas(1827)


def test_calendario():
    assert P.calendario(date(2027, 1, 1), 1096) == [date(2027, 1, 1).fromordinal(date(2027, 1, 1).toordinal() + v)
                                                    for v in (219, 438, 658, 877, 1096)]


# ---------- regla decisiva ----------
def test_inferencia_decisiva_es_la_regla_de_respaldo():
    x = G.proceso("C2", 200, 4242)
    r = P.inferencia_decisiva(x, 7)
    ref = I.respaldo(x, P.B, 7)
    assert r["p"] == ref["p_unilateral"] and r["ic90"] == ref["ic90"] and not r["degenerada"]
    assert r["p"] == max(r["descriptivas"].values())
    assert P.inferencia_decisiva([0.0] * 200, 7) == {"p": 1.0, "ic90": None, "degenerada": True, "descriptivas": {}}


# ---------- política de cada mirada ----------
def _res(p, sup):
    return {"p": p, "ic90": (-1.0, sup), "degenerada": False}


@pytest.mark.parametrize("k,dias,validos,res,estado", [
    (2, 730, False, None, "MIRADA_OMITIDA"),
    (5, 1826, False, None, "INCONCLUSO_POR_DATOS"),
    (3, 900, True, _res(1e-9, 1.0), "MIRADA_OMITIDA"),             # < 90 % de 1096
    (3, 1000, True, _res(1e-9, 1.0), "CONFIRMADA_PROSPECTIVAMENTE"),  # ≥ 90 %: se evalúa
    (5, 1600, True, _res(1e-9, 1.0), "INCONCLUSO_POR_DATOS"),       # < 90 % de n_max
    (1, 365, True, _res(1 / (P.B + 1), 1.0), "CONTINUAR"),         # la mirada 1 no puede confirmar
    (2, 730, True, _res(3e-4, 1.0), "CONFIRMADA_PROSPECTIVAMENTE"),
    (4, 1461, True, _res(0.5, -1e-5), "EN_CONTRA"),
    (4, 1461, True, _res(0.5, 0.0001), "EFECTO_RELEVANTE_DESCARTADO"),
    (4, 1461, True, _res(0.5, 0.01), "CONTINUAR"),
    (5, 1826, True, _res(0.5, 0.01), "NO_CONCLUYENTE"),
    (5, 1826, True, _res(0.02, 0.01), "CONFIRMADA_PROSPECTIVAMENTE"),
    (2, 730, True, {"p": 1.0, "ic90": None, "degenerada": True}, "CONTINUAR"),
    (5, 1826, True, {"p": 1.0, "ic90": None, "degenerada": True}, "INCONCLUSO_POR_DATOS")])
def test_politica_de_miradas(k, dias, validos, res, estado):
    plan = P.plan_de_miradas(1826)
    assert P.evaluar_mirada(k, plan, dias, validos, res, 0.10)["estado"] == estado


def test_ventana_y_errores_de_mirada():
    plan = P.plan_de_miradas(1826)
    assert P.dias_a_usar(2, plan, 800) == 730 and P.dias_a_usar(2, plan, 700) == 700
    with pytest.raises(ValueError):
        P.evaluar_mirada(6, plan, 1826, True, _res(0.5, 0.01), 0.10)
    with pytest.raises(ValueError):
        P.evaluar_mirada(2, plan, 730, True, _res(0.5, 0.01), None)  # sin δ no hay fase prospectiva


def test_categoria_historica_v11_convierte_delta():
    res = {"p": 0.4, "ic90": (-0.001, 0.0002), "degenerada": False}
    assert P.categoria_historica(True, [], 40, 30, res, 0.10)["categoria"] == "EFECTO_RELEVANTE_DESCARTADO"
    assert P.categoria_historica(True, [], 40, 30, res, 0.05)["categoria"] == "INSUFICIENTE"
    assert P.categoria_historica(True, [], 40, 30, res, None)["categoria"] == "INSUFICIENTE"
    assert P.categoria_historica(True, [], 40, 30, {"p": 1.0, "ic90": None, "degenerada": True},
                                 0.10)["categoria"] == "INVALIDO"


# ---------- prerregistro v1.1 ----------
def test_esquema_v11_es_el_diff_documentado_de_v1():
    assert V11.esquema_v11() == V11.construir_esquema_v11(V1.ESQUEMA)


def test_ejemplo_v11_valido_y_v10_rechazado_por_v11():
    r = V11.validar(EJEMPLO)
    assert r["errores"] == [] and any("criba" in a for a in r["avisos"])
    viejo = json.loads((RAIZ / "plantillas" / "ejemplo_prerregistro_SINTETICO.json").read_text(encoding="utf-8"))
    assert V11.validar(viejo)["errores"]                       # un 1.0 no pasa como 1.1
    assert V1.validar_esquema(viejo) == []                     # y sigue siendo un 1.0 válido (sin cambios retroactivos)


def _prospectivo(delta=0.15, te=0.10, inicio="2027-01-01"):
    d = copy.deepcopy(EJEMPLO)
    d["ventanas"] = {"desarrollo": None, "validacion": None, "prueba_final": None, "prospectiva": None}
    d["potencia"].update(delta_anual=delta, te_supuesto=te, ir_neto_plausible=1.6, horizonte_anos=4)
    if delta:
        n = P.n_max_dias(delta, te)
        n_ok = min(max(n, P.N_MAX_CALIBRADO[0]), P.N_MAX_CALIBRADO[1])
    else:
        n_ok = 1306
    d["ventanas"]["prospectiva"] = {"inicio": inicio, "K": 5, "n_max_dias": n_ok,
                                    "miradas": [x.isoformat() for x in P.calendario(date.fromisoformat(inicio), n_ok)]}
    return d


def test_prospectivo_valido_y_congelable():
    d = _prospectivo()
    assert V11.validar(d)["errores"] == []
    c = V11.congelar(d, "2026-12-01T00:00:00Z")
    assert V11.verificar_congelado(c)
    c["potencia"]["delta_anual"] = 0.14
    assert not V11.verificar_congelado(c)


@pytest.mark.parametrize("cambio,texto", [
    (lambda d: d["potencia"].update(delta_anual=None), "sin δ"),
    (lambda d: d["ventanas"]["prospectiva"].update(n_max_dias=1400), "no es el de la fórmula"),
    (lambda d: d["ventanas"]["prospectiva"]["miradas"].__setitem__(2, "2028-01-01"), "exactamente"),
    (lambda d: d["potencia"].update(delta_anual=0.10), "NO_ALCANZABLE"),
    (lambda d: d["potencia"].update(delta_anual=0.25), "FUERA_DEL_RANGO_CALIBRADO_CORTO"),
    (lambda d: d["ventanas"]["prospectiva"].update(inicio="2026-10-01"), "antes de 2026-10-14")])
def test_errores_prospectivos(cambio, texto):
    d = _prospectivo()
    cambio(d)
    errores = V11.validar(d)["errores"]
    assert any(texto in e for e in errores), errores
    with pytest.raises(ValueError):
        V11.congelar(d, "2026-12-01T00:00:00Z")


@pytest.mark.parametrize("ruta,valor", [
    (("prueba", "metodo"), "bootstrap_t_bloques_circulares"),
    (("prueba", "B"), 1999),
    (("calibraciones", "a_s1_zip_sha256"), "0" * 64),
    (("ventanas", "prospectiva", "K"), 4),
    (("potencia", "unidad_delta"), "porcentaje_diario"),
    (("version_protocolo",), "PEC-1.0")])
def test_errores_de_esquema_v11(ruta, valor):
    d = _prospectivo()
    obj = d
    for r in ruta[:-1]:
        obj = obj[r]
    obj[ruta[-1]] = valor
    assert V11.validar(d)["errores"]
