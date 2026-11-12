"""Casos adversarios del gate 06v3 (scripts/ci_gate.py del paquete), en un clon DESECHABLE.

Criterio fijado ANTES de correr, por caso ("esperado"): "fail" = un gate seguro debe dar rc != 0; "pass" = debe aprobar;
"cualquiera" = se registra sin juzgar. K*: el motor promete >= 1.1.0 EN EJECUCIÓN y la guarda falta → "fail".
J1/J2 (criterio de esta revisión): una corrida donde casi toda la suite no corrió no debería aprobar → "fail".
Además se registra si el gate deja provenance.json (evidencia) en cada caso.

Uso: python -I gate_adversario.py <clon_con_A> <ci_gate.py> <junit_real.xml> <python_gate> <dir_salida>"""
import copy
import json
import os
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

clon, gate, junit, py_gate, out = (pathlib.Path(sys.argv[i]) for i in range(1, 6))
out.mkdir(parents=True, exist_ok=True)
ENG = clon / "packages/tia/src/tia/backtest/engine.py"
ORIG = ENG.read_bytes()
TXT = ORIG.decode()
LINEA = 'ENGINE_VERSION = "1.1.0"'
assert TXT.count(LINEA) == 1, "el motor de A debe declarar la versión una sola vez"
GUARD = "tests.integration.test_engine_version_contract"
real = ET.parse(junit)


def jv(nombre, cambiar):
    arbol = copy.deepcopy(real)
    for suite in arbol.getroot().iter("testsuite"):
        cambiar(suite)
    ruta = out / f"junit_{nombre}.xml"
    arbol.write(ruta, encoding="utf-8", xml_declaration=True)
    return ruta


def sin_guarda(s):
    for c in s.findall("testcase"):
        if c.get("classname") == GUARD:
            s.remove(c)


def omitir_casi_todo(s):  # todas las pruebas ajenas a la guarda pasan a «skipped»
    for c in s.findall("testcase"):
        if c.get("classname") != GUARD:
            for h in list(c):
                c.remove(h)
            ET.SubElement(c, "skipped", {"message": "sintético: dependencia ausente", "type": "pytest.skip"})


def solo_subconjunto(s):  # solo la guarda y 3 pruebas más
    otras = 0
    for c in s.findall("testcase"):
        if c.get("classname") != GUARD:
            otras += 1
            if otras > 3:
                s.remove(c)


def guarda_xfail(s):
    for c in s.findall("testcase"):
        if c.get("classname") == GUARD:
            ET.SubElement(c, "skipped", {"type": "pytest.xfail", "message": "sintético"})


def guarda_duplicada(s):
    for c in [c for c in s.findall("testcase") if c.get("classname") == GUARD]:
        s.append(copy.deepcopy(c))


def guarda_trivial(s):  # 7 pruebas cualesquiera bajo el nombre de clase de la guarda
    for c in s.findall("testcase"):
        if c.get("classname") == GUARD:
            s.remove(c)
    for i in range(7):
        ET.SubElement(s, "testcase", {"classname": GUARD, "name": f"test_trivial_{i}", "time": "0.001"})


def motor(texto):
    return lambda: ENG.write_text(texto)


casos = [
    # nombre, preparar motor, junit, esperado, intérprete
    ("K0_control_sin_guarda", motor(TXT), jv("sin_guarda", sin_guarda), "fail", None),
    ("K1_asignacion_duplicada_primera_1_0_0", motor(TXT.replace(LINEA, 'ENGINE_VERSION = "1.0.0"\n' + LINEA)), jv("sin_guarda", sin_guarda), "fail", None),
    ("K2_dentro_de_if", motor(TXT.replace(LINEA, 'if True:\n    ' + LINEA)), jv("sin_guarda", sin_guarda), "fail", None),
    ("K3_dentro_de_try", motor(TXT.replace(LINEA, 'try:\n    ' + LINEA + '\nexcept Exception:\n    raise')), jv("sin_guarda", sin_guarda), "fail", None),
    ("K4_desempaquetado_de_tupla", motor(TXT.replace(LINEA, 'ENGINE_VERSION, _VERSION_NOTE = "1.1.0", ""')), jv("sin_guarda", sin_guarda), "fail", None),
    ("K5_importada_de_otro_modulo", motor(TXT.replace(LINEA, 'from tia.core.version_adversaria import ENGINE_VERSION  # noqa')), jv("sin_guarda", sin_guarda), "fail", None),
    ("K6_comentario_y_docstring_engañosos", motor(TXT.replace(LINEA, '# ENGINE_VERSION = "0.1.0"\n"""ENGINE_VERSION = "0.0.1" in prose"""\n' + LINEA)), jv("sin_guarda", sin_guarda), "fail", None),
    ("K7_sintaxis_rota", motor(TXT.replace(LINEA, LINEA + "\ndef (:")), jv("sin_guarda", sin_guarda), "fail", None),
    ("K8_bytes_no_utf8", lambda: ENG.write_bytes(ORIG.replace(LINEA.encode(), LINEA.encode() + b"\n# \xff\xfe")), jv("sin_guarda", sin_guarda), "fail", None),
    ("K9_expresion", motor(TXT.replace(LINEA, 'ENGINE_VERSION = "1." + "1.0"')), jv("sin_guarda", sin_guarda), "fail", None),
    ("K10_anotada_final", motor(TXT.replace(LINEA, 'ENGINE_VERSION: str = "1.1.0"')), jv("sin_guarda", sin_guarda), "fail", None),
    ("J1_casi_todo_omitido", motor(TXT), jv("omitir_casi_todo", omitir_casi_todo), "fail", None),
    ("J2_subconjunto_de_4_pruebas", motor(TXT), jv("subconjunto", solo_subconjunto), "fail", None),
    ("J3_guarda_xfail", motor(TXT), jv("guarda_xfail", guarda_xfail), "fail", None),
    ("J4_guarda_duplicada", motor(TXT), jv("guarda_duplicada", guarda_duplicada), "cualquiera", None),
    ("J5_guarda_reemplazada_por_7_triviales", motor(TXT), jv("guarda_trivial", guarda_trivial), "fail", None),
    ("J6_junit_inexistente", motor(TXT), out / "no_existe.xml", "fail", None),
    ("J7_junit_real_con_otro_interprete", motor(TXT), junit, "pass", "/usr/bin/python3.11"),
]
if (clon / "packages/tia/src/tia/core").is_dir():
    (clon / "packages/tia/src/tia/core/version_adversaria.py").write_text('ENGINE_VERSION = "1.1.0"\n')
filas = []
for nombre, preparar, j, esperado, interprete in casos:
    preparar()
    ev = out / f"evidencia_{nombre}"
    r = subprocess.run([interprete or str(py_gate), "-B", str(gate), str(ev), str(j)], cwd=clon, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    # Lo que Python evalúa de verdad (con el venv, para K5 importando el módulo nuevo):
    ev_rt = subprocess.run([str(py_gate), "-B", "-c", "import tia.backtest.engine as e; print(e.ENGINE_VERSION)"], cwd=clon,
                           capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "packages/tia/src"})
    prov = json.loads((ev / "provenance.json").read_text()) if (ev / "provenance.json").exists() else None
    veredicto = prov["verdict"] if prov else ("crash" if r.returncode else "?")
    seguro = {"fail": r.returncode != 0, "pass": r.returncode == 0, "cualquiera": True}[esperado]
    filas.append({"caso": nombre, "engine_version_en_ejecucion": ev_rt.stdout.strip() or ev_rt.stderr.strip()[-120:],
                  "engine_version_leida_por_el_gate": prov["engine_version"] if prov else None, "rc": r.returncode,
                  "esperado": esperado, "veredicto": veredicto, "provenance_json": prov is not None, "problemas": prov["problems"] if prov else None,
                  "report": prov["report"] if prov else None, "pip_freeze_sha256": prov["pip_freeze_sha256"][:16] if prov else None,
                  "stderr_final": r.stderr.strip().splitlines()[-1][:160] if r.stderr.strip() else "",
                  "SEGURO": seguro})
    ENG.write_bytes(ORIG)
    print(f"{'OK   ' if seguro else 'FALLA'} {nombre:42s} esperado={esperado:10s} rt={filas[-1]['engine_version_en_ejecucion']!s:8.8} gate_lee={filas[-1]['engine_version_leida_por_el_gate']!s:8} rc={r.returncode} veredicto={veredicto} prov={prov is not None} {filas[-1]['stderr_final'][:70]}")
(clon / "packages/tia/src/tia/core/version_adversaria.py").unlink(missing_ok=True)
assert ENG.read_bytes() == ORIG
json.dump(filas, open(out / "gate_adversario.json", "w"), indent=1, ensure_ascii=False)
print(f"RESULTADO: {sum(not f['SEGURO'] for f in filas)} de {len(filas)} casos con un desenlace distinto del esperado")
