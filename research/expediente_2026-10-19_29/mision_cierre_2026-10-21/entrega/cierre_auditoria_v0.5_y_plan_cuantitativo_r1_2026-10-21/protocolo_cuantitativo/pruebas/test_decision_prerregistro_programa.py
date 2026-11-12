"""Regla de decisión (MEC §7 y §7.1), prerregistro (esquema, semántica, congelamiento), registro del programa,
procesos sintéticos y el bloqueo del script de calibración."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pec import decision as R
from pec import prerregistro as PR
from pec import programa as PG
from pec import sintetico as G

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = json.loads((RAIZ / "plantillas" / "ejemplo_prerregistro_SINTETICO.json").read_text(encoding="utf-8"))


# ---------- decisión ----------
@pytest.mark.parametrize("args,categoria", [
    (dict(valido=False, motivos_invalidez=["V5"], n_operaciones=99, n_min=30, p=0.001, ic90=(0.1, 0.2)), "INVALIDO"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=10, n_min=30, p=0.001, ic90=(0.1, 0.2)),
     "INCONCLUSO_POR_DATOS"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=40, n_min=30, p=0.02, ic90=(0.01, 0.2)), "RESPALDADA"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=40, n_min=30, p=0.9, ic90=(-0.3, -0.01)), "EN_CONTRA"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=40, n_min=30, p=0.6, ic90=(-0.1, 0.03), delta=0.05),
     "EFECTO_RELEVANTE_DESCARTADO"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=40, n_min=30, p=0.6, ic90=(-0.1, 0.03)), "INSUFICIENTE"),
    (dict(valido=True, motivos_invalidez=[], n_operaciones=40, n_min=30, p=0.2, ic90=(-0.02, 0.12), delta=0.05),
     "INSUFICIENTE")])
def test_categorias_historicas(args, categoria):
    assert R.categoria_historica(**args)["categoria"] == categoria


def test_sin_delta_no_hay_efecto_descartado_y_robustez_aparte():
    r = R.categoria_historica(True, [], 40, 30, 0.6, (-0.1, 0.03))
    assert r["categoria"] == "INSUFICIENTE" and any("δ no fijado" in n for n in r["notas"])
    r = R.categoria_historica(True, [], 40, 30, 0.01, (0.01, 0.2), robustez={"costos_x2": True, "retraso": False})
    assert r["categoria"] == "RESPALDADA" and r["robustez"] == "NO_ROBUSTA" and r["nivel"] == 2
    with pytest.raises(ValueError):
        R.categoria_historica(True, [], 40, 30, 0.01, (0.01, 0.2), alfa=0.1)


def test_mirada_prospectiva():
    c = [4.8769, 3.3569, 2.6803, 2.2898, 2.0310]
    assert R.mirada_prospectiva(1, c, 3.0, 0.2, 0.05)["estado"] == "CONTINUAR"
    assert R.mirada_prospectiva(3, c, 2.7, 0.2, 0.05)["estado"] == "CONFIRMADA_PROSPECTIVAMENTE"
    assert R.mirada_prospectiva(2, c, 0.5, 0.04, 0.05)["estado"] == "EFECTO_RELEVANTE_DESCARTADO"
    assert R.mirada_prospectiva(5, c, 1.9, 0.2, 0.05)["estado"] == "NO_CONCLUYENTE"
    with pytest.raises(ValueError):
        R.mirada_prospectiva(1, c, 3.0, 0.2, None)  # sin δ no hay fase prospectiva
    with pytest.raises(ValueError):
        R.mirada_prospectiva(6, c, 3.0, 0.2, 0.05)  # mirada fuera de calendario


# ---------- prerregistro ----------
def test_ejemplo_valido_con_aviso_de_detectabilidad():
    assert PR.validar_esquema(EJEMPLO) == []
    s = PR.validar_semantica(EJEMPLO)
    assert s["errores"] == [] and any("criba de detectabilidad" in a for a in s["avisos"])


def mutado(**cambios):
    d = copy.deepcopy(EJEMPLO)
    for ruta, valor in cambios.items():
        *padres, hoja = ruta.split("__")
        x = d
        for p in padres:
            x = x[p]
        if valor is KeyError:
            del x[hoja]
        else:
            x[hoja] = valor
    return d


@pytest.mark.parametrize("cambios,texto", [
    ({"titulo": KeyError}, "falta «titulo»"),
    ({"extra": 1}, "campo no admitido «extra»"),
    ({"prueba__alfa": 0.05}, "máximo"),
    ({"datos__zona_horaria": "UTC-3"}, "no está en"),
    ({"parada__variantes_permitidas": 3}, "máximo"),
    ({"potencia__n_min": 10}, "mínimo"),
])
def test_errores_de_esquema(cambios, texto):
    assert any(texto in e for e in PR.validar_esquema(mutado(**cambios)))


@pytest.mark.parametrize("cambios,texto", [
    ({"reglas__parametros": {"z_umbral": [-2, -3, -4]}}, "varios valores"),
    ({"ventanas__validacion": ["2031-06-01", "2032-12-31"]}, "se solapan"),
    ({"multiplicidad__familia_confirmatoria": ["H-EJEMPLO-SINTETICO", "H-OTRA"]}, "Bonferroni"),
    ({"familia__reabre_familia_descartada": True}, "D-G5"),
    ({"universo__mercado": "perpetuo"}, "funding"),
    ({"ejecucion__apalancamiento": 3}, "margen de mantenimiento"),
    ({"potencia__acepta_no_concluyente": False}, "no se aceptó de antemano"),
    ({"reproduccion__presentar_todas": False}, "A14"),
    ({"ventanas__prospectiva": {"inicio": "2026-11-01", "miradas": ["2027-11-01"], "n_max_dias": 365}}, "sin δ"),
    ({"ventanas__prospectiva": {"inicio": "2026-01-01", "miradas": ["2027-01-01"], "n_max_dias": 365},
      "potencia__delta_anual": 0.05}, "antes de 2026-10-14"),
])
def test_errores_semanticos(cambios, texto):
    errores = PR.validar_semantica(mutado(**cambios))["errores"]
    assert any(texto in e for e in errores), errores


def test_periodos_contaminados_y_reservado_para_btc():
    d = mutado(universo__activos=["BTCUSDT"], ventanas__desarrollo=["2018-01-01", "2020-12-31"],
               ventanas__validacion=["2021-01-01", "2021-12-31"], ventanas__prueba_final=["2022-01-01", "2026-05-31"])
    s = PR.validar_semantica(d)
    assert s["errores"] == [] and any("NO es evidencia independiente" in a for a in s["avisos"])
    d["ventanas"]["prueba_final"] = ["2022-01-01", "2026-08-31"]
    assert any("período reservado" in e for e in PR.validar_semantica(d)["errores"])


def test_congelar_y_verificar():
    c = PR.congelar(EJEMPLO, "2026-10-21T00:00:00Z")
    assert c["estado"] == "CONGELADO" and PR.verificar_congelado(c)
    reordenado = json.loads(json.dumps(c, sort_keys=False)[::1])
    assert PR.verificar_congelado(dict(reversed(list(reordenado.items()))))  # el orden de las claves no importa
    alterado = copy.deepcopy(c)
    alterado["reglas"]["parametros"]["z_umbral"] = -2.5
    assert not PR.verificar_congelado(alterado)
    with pytest.raises(ValueError):
        PR.congelar(mutado(prueba__alfa=0.05), "2026-10-21T00:00:00Z")


# ---------- programa ----------
def test_registro_del_programa():
    m = PG.multiplicidad_programa()
    assert m["respaldadas"] == 0 and m["registradas"] == 39 and m["intentadas_con_resultado"] == 18
    for h in ("T-MULTI", "H-CARRY", "T", "E2-B", "C10"):
        assert not PG.puede_iniciar(h)["puede"], h
    assert not PG.puede_iniciar("H-REV-SHOCK-v0.2")["puede"]
    assert PG.puede_iniciar("H-REV-SHOCK-v0.2", {"H-REV-SHOCK-v0.2": "D-G1 y D-G5 (ref)"})["puede"]
    assert PG.puede_iniciar("H-NUEVA-X")["puede"]


# ---------- sintéticos y calibración ----------
def test_procesos_sinteticos_deterministas_y_no_centrados():
    for nombre in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert G.proceso(nombre, 400, 1) == G.proceso(nombre, 400, 1)
        medias = [sum(G.proceso(nombre, 400, s)) / 400 for s in range(12)]
        # media POBLACIONAL 0: la muestral varía (si se centrara, la calibración de tamaño no mediría nada)
        assert sum(1 for m in medias if abs(m) > 1e-9) >= 6, (nombre, medias)


def test_calibracion_bloqueada_sin_autorizacion_y_humo():
    script = RAIZ / "calibracion" / "calibracion_mec.py"
    r = subprocess.run([sys.executable, "-B", str(script), "--ejecutar"], capture_output=True, text=True)
    assert r.returncode == 2 and "BLOQUEADO" in r.stderr
    r = subprocess.run([sys.executable, "-B", str(script), "--prueba-humo"], capture_output=True, text=True)
    assert r.returncode == 0 and "no se informa ninguna tasa" in r.stdout
