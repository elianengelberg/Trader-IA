"""Casos adversarios del gate v4 (scripts/ci_gate.py del parche 12) en un clon DESECHABLE que ya corrió la suite completa
con el plugin (ci_local.sh). Resultado esperado fijado ANTES de correr: "fail" (rc != 0 y, además, la razón esperada entre
los problemas) o "pass" (rc == 0). Los casos marcados SIMULADO alteran session.json para representar una corrida en otro
entorno (no hay un segundo intérprete 3.11 con otras versiones disponible aquí); los marcados REAL corren pytest de nuevo.
Cada caso parte de los artefactos prístinos y restaura los archivos que toca (se verifica al final).
Uso: python -I gate_v4_adversario.py <clon> <dir_artefactos_main> <dir_artefactos_pg> <python_venv> <dir_salida> [casos,...]
Nota (registrada después de la primera corrida): en N04 la sombra en PYTHONPATH NO llega a importarse, porque el
`pythonpath = ["packages/tia/src"]` de pyproject pone el checkout primero en sys.path; el gate registró el motor del
checkout (correcto) y falló por la suite reducida. N04b fuerza la sustitución con un sitecustomize."""
import copy
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

clon, art, art_pg, py, out = (Path(a) for a in sys.argv[1:6])
SOLO = set(sys.argv[6].split(",")) if len(sys.argv) > 6 else None
out.mkdir(parents=True, exist_ok=True)
EV = clon / "ci-evidence"
ENG = clon / "packages/tia/src/tia/backtest/engine.py"
GUARD_FILE = clon / "tests/integration/test_engine_version_contract.py"
GUARD = "tests.integration.test_engine_version_contract"
IGNORADO = "research/hcarry_next/datos/descarga.log"  # versionado aunque .gitignore lo excluye (git ls-files -ci)
PLANTADO = "tests/unit/test_plantado_despues.py"
ORIG = {p: p.read_bytes() for p in (ENG, GUARD_FILE, clon / "constraints/ci-py311.txt", clon / "scripts/ci_gate_policy.json",
                                    clon / "tests/unit/test_walkforward.py", clon / IGNORADO)}
TXT = ENG.read_text()
LINEA = next(line for line in TXT.splitlines() if line.startswith("ENGINE_VERSION = "))
VERSION = LINEA.split('"')[1]
NONCE = json.loads((art / "session.json").read_text())["nonce"]
ENV = {"PATH": f"{py.parent}:/usr/bin:/bin", "CI_RUN_NONCE": NONCE, "HOME": os.environ.get("HOME", "/root")}


def pristino():
    shutil.rmtree(EV, ignore_errors=True)
    EV.mkdir()
    shutil.copy2(art / "junit.xml", EV / "junit.xml")
    shutil.copy2(art / "session.json", EV / "session.json")


def junit(cambiar):
    arbol = ET.parse(EV / "junit.xml")
    for suite in arbol.getroot().iter("testsuite"):
        cambiar(suite)
    arbol.write(EV / "junit.xml", encoding="utf-8", xml_declaration=True)


def recount(s):
    cases = s.findall("testcase")
    s.set("tests", str(len(cases)))
    s.set("failures", str(sum(c.find("failure") is not None for c in cases)))
    s.set("errors", str(sum(c.find("error") is not None for c in cases)))
    s.set("skipped", str(sum(c.find("skipped") is not None for c in cases)))


def session(cambiar):
    d = json.loads((EV / "session.json").read_text())
    cambiar(d)
    (EV / "session.json").write_text(json.dumps(d))


def motor(texto):
    return lambda: ENG.write_text(texto)


def sin_guarda():
    def f(s):
        for c in [c for c in s.findall("testcase") if c.get("classname") == GUARD]:
            s.remove(c)
        recount(s)
    junit(f)


def casi_todo_omitido():
    def f(s):
        for c in s.findall("testcase"):
            if c.get("classname") != GUARD:
                for h in list(c):
                    c.remove(h)
                ET.SubElement(c, "skipped", {"type": "pytest.skip", "message": "sintético"})
        recount(s)
    junit(f)


def subconjunto():
    def f(s):
        otras = 0
        for c in s.findall("testcase"):
            if c.get("classname") != GUARD:
                otras += 1
                if otras > 3:
                    s.remove(c)
        recount(s)
    junit(f)


def guarda_xfail():
    def f(s):
        for c in s.findall("testcase"):
            if c.get("classname") == GUARD:
                ET.SubElement(c, "skipped", {"type": "pytest.xfail", "message": "sintético"})
        recount(s)
    junit(f)


def guarda_duplicada():
    def f(s):
        for c in [c for c in s.findall("testcase") if c.get("classname") == GUARD]:
            s.append(copy.deepcopy(c))
        recount(s)
    junit(f)


def guarda_trivial():
    def f(s):
        for c in [c for c in s.findall("testcase") if c.get("classname") == GUARD]:
            s.remove(c)
        for i in range(7):
            ET.SubElement(s, "testcase", {"classname": GUARD, "name": f"test_trivial_{i}", "time": "0.001"})
        recount(s)
    junit(f)


def nonce_junit():
    def f(s):
        for p in s.iter("property"):
            if p.get("name") == "ci_run_nonce":
                p.set("value", "otra-corrida")
    junit(f)


def omision_no_permitida():
    clave = "tests.unit.test_walkforward::test_"
    def f(s):
        for c in s.findall("testcase"):
            if f"{c.get('classname')}::{c.get('name')}".startswith(clave):
                ET.SubElement(c, "skipped", {"type": "pytest.skip", "message": "sintético"})
                break
        recount(s)
    junit(f)
    def g(d):
        k = next(k for k in sorted(d["outcomes"]) if k.startswith(clave))
        d["outcomes"][k] = "skipped"
    session(g)


def correr_pytest(*args, env_extra=None, pythonpath="packages/tia/src"):
    shutil.rmtree(EV, ignore_errors=True)
    env = {**ENV, "PYTHONPATH": pythonpath, **(env_extra or {})}
    return subprocess.run([str(py), "-m", "pytest", *args, "-q", "-p", "scripts.ci_provenance",
                           "--junitxml=ci-evidence/junit.xml"], cwd=clon, env=env, capture_output=True, text=True,
                          timeout=1800)


def sombra():
    """Un paquete tia completo fuera del clon, con engine.py declarando 1.0.0, PRIMERO en el path de la corrida."""
    s = out / "sombra"
    shutil.rmtree(s, ignore_errors=True)
    shutil.copytree(clon / "packages/tia/src/tia", s / "tia", ignore=shutil.ignore_patterns("__pycache__"))
    e = s / "tia/backtest/engine.py"
    e.write_text(e.read_text().replace(LINEA, 'ENGINE_VERSION = "1.0.0"'))
    correr_pytest("tests/integration/test_engine_version_contract.py", pythonpath=f"{s}:packages/tia/src")
    shutil.rmtree(s, ignore_errors=True)


def sombra_sitecustomize():
    """El mismo paquete sombra (1.0.0), importado por un sitecustomize al arrancar el intérprete: ya está en
    sys.modules cuando pytest agrega su pythonpath, así que las pruebas usan la sombra."""
    s = out / "sombra_sc"
    shutil.rmtree(s, ignore_errors=True)
    shutil.copytree(clon / "packages/tia/src/tia", s / "tia", ignore=shutil.ignore_patterns("__pycache__"))
    e = s / "tia/backtest/engine.py"
    e.write_text(e.read_text().replace(LINEA, 'ENGINE_VERSION = "1.0.0"'))
    (s / "sitecustomize.py").write_text("import tia.backtest.engine  # noqa: F401\n")
    r = correr_pytest("tests/integration/test_engine_version_contract.py", pythonpath=f"{s}:packages/tia/src")
    (out / "N04b_pytest.txt").write_text(r.stdout[-3000:] + r.stderr[-2000:])
    shutil.rmtree(s, ignore_errors=True)


CASOS = [
    # nombre, preparar, esperado, razón esperada (subcadena de un problema), tipo
    ("K0_control_sin_guarda", sin_guarda, "fail", "disagree", "18"),
    ("K1_asignacion_duplicada_primera_1_0_0", lambda: (motor(TXT.replace(LINEA, 'ENGINE_VERSION = "1.0.0"\n' + LINEA))(), sin_guarda()), "fail", "binds ENGINE_VERSION 2 times", "18"),
    ("K2_dentro_de_if", lambda: (motor(TXT.replace(LINEA, "if True:\n    " + LINEA))(), sin_guarda()), "fail", "not a top-level string literal", "18"),
    ("K3_dentro_de_try", lambda: (motor(TXT.replace(LINEA, "try:\n    " + LINEA + "\nexcept Exception:\n    raise"))(), sin_guarda()), "fail", "not a top-level string literal", "18"),
    ("K4_desempaquetado_de_tupla", lambda: (motor(TXT.replace(LINEA, f'ENGINE_VERSION, _NOTE = "{VERSION}", ""'))(), sin_guarda()), "fail", "not a top-level string literal", "18"),
    ("K5_importada_de_otro_modulo", lambda: (motor(TXT.replace(LINEA, "from tia.core.version_adversaria import ENGINE_VERSION  # noqa"))(),
                                             (clon / "packages/tia/src/tia/core/version_adversaria.py").write_text(f'ENGINE_VERSION = "{VERSION}"\n'),
                                             sin_guarda()), "fail", "bound or patched outside the engine module", "18"),
    ("K6_comentario_y_docstring_enganosos", lambda: (motor(TXT.replace(LINEA, '# ENGINE_VERSION = "0.1.0"\n"""ENGINE_VERSION = "0.0.1" in prose"""\n' + LINEA))(), sin_guarda()), "fail", "disagree", "18"),
    ("K7_sintaxis_rota", lambda: (motor(TXT.replace(LINEA, LINEA + "\ndef (:"))(), sin_guarda()), "fail", "cannot be read as Python", "18"),
    ("K8_bytes_no_utf8", lambda: (ENG.write_bytes(ORIG[ENG].replace(LINEA.encode(), LINEA.encode() + b"\n# \xff\xfe")), sin_guarda()), "fail", "cannot be read as Python", "18"),
    ("K9_expresion", lambda: (motor(TXT.replace(LINEA, f'ENGINE_VERSION = "{VERSION[:2]}" + "{VERSION[2:]}"'))(), sin_guarda()), "fail", "not a top-level string literal", "18"),
    ("K10_anotada", lambda: (motor(TXT.replace(LINEA, f'ENGINE_VERSION: str = "{VERSION}"'))(), sin_guarda()), "fail", "disagree", "18"),
    ("J1_casi_todo_omitido", casi_todo_omitido, "fail", "disagree", "18"),
    ("J2_subconjunto_de_4_pruebas", subconjunto, "fail", "disagree", "18"),
    ("J3_guarda_xfail", guarda_xfail, "fail", "disagree", "18"),
    ("J4_guarda_duplicada", guarda_duplicada, "fail", "twice", "18"),
    ("J5_guarda_reemplazada_por_7_triviales", guarda_trivial, "fail", "disagree", "18"),
    ("J6_junit_inexistente", lambda: (EV / "junit.xml").unlink(), "fail", "missing or empty", "18"),
    ("J7_junit_real_con_otro_interprete_del_gate", lambda: None, "pass", "", "18:/usr/bin/python3.11"),
    # nuevos
    ("N01_declaracion_duplicada_mismo_valor", motor(TXT.replace(LINEA, LINEA + "\n" + LINEA)), "fail", "binds ENGINE_VERSION 2 times", "nuevo"),
    ("N02_declaracion_condicional_if_else", motor(TXT.replace(LINEA, f'if __debug__:\n    {LINEA}\nelse:\n    ENGINE_VERSION = "0.0.0"')), "fail", "binds ENGINE_VERSION 2 times", "nuevo"),
    ("N03_parcheada_desde_otro_modulo", lambda: (clon / "packages/tia/src/tia/core/parche_adversario.py").write_text(
        "import tia.backtest.engine as e\ne.ENGINE_VERSION = '1.0.0'\nsetattr(e, 'ENGINE_VERSION', '1.0.0')\n"), "fail", "bound or patched outside the engine module", "nuevo"),
    ("N04_modulo_sustituido_en_el_path_REAL", sombra, "fail", "not this checkout's", "nuevo"),
    ("N04b_modulo_sustituido_por_sitecustomize_REAL", sombra_sitecustomize, "fail", "not this checkout's", "nuevo"),
    ("N05_sintaxis_rota_con_junit_completo", motor(TXT.replace(LINEA, LINEA + "\ndef (:")), "fail", "cannot be read as Python", "nuevo"),
    ("N06_junit_truncado", lambda: (EV / "junit.xml").write_bytes((EV / "junit.xml").read_bytes()[:5000]), "fail", "does not parse", "nuevo"),
    ("N07_junit_vacio", lambda: (EV / "junit.xml").write_bytes(b""), "fail", "missing or empty", "nuevo"),
    ("N08_junit_dice_pasada_la_que_fallo", lambda: session(lambda d: d["outcomes"].update(
        {sorted(d["outcomes"])[100]: "failed"})), "fail", "disagree", "nuevo"),
    ("N09a_junit_de_otra_corrida", nonce_junit, "fail", "JUnit report is from another run", "nuevo"),
    ("N09b_sesion_de_otra_corrida", lambda: session(lambda d: d.update({"nonce": "otra"})), "fail", "session record is from another run", "nuevo"),
    ("N09c_sin_nonce_en_el_entorno", lambda: ENV.pop("CI_RUN_NONCE"), "fail", "CI_RUN_NONCE is not set", "nuevo"),
    ("N10_suite_reducida_con_k_REAL", lambda: correr_pytest("tests", "-k", "engine_version_contract"), "fail", "narrowed (keyword", "nuevo"),
    ("N11_deselect_REAL", lambda: correr_pytest("tests/integration/test_engine_version_contract.py", "--deselect",
                                                f"tests/integration/test_engine_version_contract.py::test_the_stop_in_the_book_follows_the_leg"),
     "fail", "narrowed (deselect", "nuevo"),
    ("N12_guarda_con_nombres_correctos_y_contenido_trivial", lambda: GUARD_FILE.write_text(
        "\n".join(f"def {n}() -> None:\n    pass\n" for n in (
            "test_a_rejected_close_is_sent_again_as_a_new_order_and_closes", "test_the_stop_in_the_book_follows_the_leg",
            "test_partial_fills_never_add_to_a_closing_position_or_reopen_one",
            "test_a_close_that_ends_with_position_left_is_followed_by_another",
            "test_rejections_partials_and_limit_entries_together", "test_the_checks_pass_a_clean_record_and_catch_each_defect",
            "test_the_label_decides_the_promise_and_cannot_escape_the_guard"))), "fail", "is not the policy's", "nuevo"),
    ("N13_resultado_de_la_guarda_no_coincide", lambda: session(lambda d: d["outcomes"].update(
        {next(k for k in sorted(d["outcomes"]) if k.startswith(GUARD)): "failed"})), "fail", "disagree", "nuevo"),
    ("N14_dependencias_distintas_de_las_fijadas_SIMULADO", lambda: session(lambda d: d.update(
        {"distributions": [x if not x.startswith("httpx==") else "httpx==0.27.2" for x in d["distributions"]]})),
     "fail", "differ from the pins", "nuevo"),
    ("N15_otro_python_SIMULADO", lambda: session(lambda d: d["python"].update({"version": "3.12.7"})), "fail", "requires 3.11", "nuevo"),
    ("N16a_artefactos_viejos_de_otra_corrida", lambda: (shutil.copy2(art_pg / "junit.xml", EV / "junit.xml"),
                                                        shutil.copy2(art_pg / "session.json", EV / "session.json")),
     "fail", "from another run", "nuevo"),
    ("N16b_archivo_alterado_despues_de_la_corrida", lambda: (clon / "tests/unit/test_walkforward.py").write_text(
        ORIG[clon / "tests/unit/test_walkforward.py"].decode() + "\n# alterado después\n"), "fail", "working tree changed", "nuevo"),
    ("N17a_sesion_ilegible", lambda: (EV / "session.json").write_text("{no es json"), "fail", "missing or unreadable", "nuevo"),
    ("N17b_politica_ausente_error_interno", lambda: (clon / "scripts/ci_gate_policy.json").unlink(), "fail", "internal error in the gate", "nuevo"),
    ("N17c_atributos_junit_inconsistentes", lambda: junit(lambda s: s.set("tests", "abc")), "fail", "says tests=abc", "nuevo"),
    ("N18_omision_no_permitida", omision_no_permitida, "fail", "outside the allow-list", "nuevo"),
    ("N19_xpass", lambda: session(lambda d: d["outcomes"].update({sorted(d["outcomes"])[5]: "xpassed"})), "fail", "passed unexpectedly", "nuevo"),
    ("N20_control_corrida_honesta", lambda: None, "pass", "", "nuevo"),
    ("N21_job_pg_con_pruebas_pg_omitidas", lambda: ENV.update({"CI_GATE_REQUIRE_POSTGRESQL": "1"}), "fail", "PostgreSQL job passed 0", "nuevo"),
    ("N25_versionado_ignorado_alterado_despues", lambda: (clon / IGNORADO).write_bytes(ORIG[clon / IGNORADO] + b"alterado\n"),
     "fail", "working tree changed", "nuevo"),
    ("N26_archivo_nuevo_plantado_despues", lambda: (clon / PLANTADO).write_text("def test_x() -> None:\n    pass\n"),
     "fail", "working tree changed", "nuevo"),
    ("N24_politica_debilitada_despues_de_la_corrida", lambda: (clon / "scripts/ci_gate_policy.json").write_text(
        ORIG[clon / "scripts/ci_gate_policy.json"].decode().replace('"min_tests": 2031', '"min_tests": 1')), "fail", "working tree changed", "nuevo"),
]

filas = []
for nombre, preparar, esperado, razon, tipo in CASOS:
    if SOLO is not None and nombre not in SOLO:
        continue
    pristino()
    env_guardado = dict(ENV)
    interprete = tipo.split(":", 1)[1] if ":" in tipo else str(py)
    try:
        preparar()
        r = subprocess.run([interprete, "-B", "scripts/ci_gate.py", "ci-evidence", "ci-evidence/junit.xml"], cwd=clon,
                           env=ENV, capture_output=True, text=True, timeout=600)
        prov_path = EV / "provenance.json"
        prov = json.loads(prov_path.read_text()) if prov_path.exists() else None
    finally:
        for p, b in ORIG.items():
            p.write_bytes(b)
        for extra in ("packages/tia/src/tia/core/version_adversaria.py", "packages/tia/src/tia/core/parche_adversario.py", PLANTADO):
            (clon / extra).unlink(missing_ok=True)
        ENV.clear()
        ENV.update(env_guardado)
    problemas = prov["problems"] if prov else []
    razon_ok = (not razon) or any(razon in p for p in problemas)
    if esperado == "pass":
        ok = r.returncode == 0 and prov is not None and prov["verdict"] == "pass"
    else:
        ok = r.returncode != 0 and prov is not None and prov["verdict"] == "fail" and razon_ok
    fila = {"caso": nombre, "tipo": tipo.split(":")[0], "esperado": esperado, "razon_esperada": razon, "rc": r.returncode,
            "veredicto": prov["verdict"] if prov else None, "provenance_json": prov is not None, "problemas": problemas,
            "OK": ok}
    filas.append(fila)
    (out / f"{nombre}.json").write_text(json.dumps({**fila, "provenance": prov, "stderr": r.stderr[-1500:]}, indent=1))
    print(f"{'OK   ' if ok else 'FALLA'} {nombre:52s} esperado={esperado:4s} rc={r.returncode} prov={prov is not None} "
          f"razón={'sí' if razon_ok else 'NO'} · {(problemas[0] if problemas else '')[:110]}")
pristino()
for p, b in ORIG.items():
    assert p.read_bytes() == b, p
json.dump(filas, open(out / ("gate_v4_adversario.json" if SOLO is None else "gate_v4_adversario_parcial.json"), "w"),
          indent=1, ensure_ascii=False)
print(f"RESULTADO: {sum(not f['OK'] for f in filas)} de {len(filas)} casos con un desenlace distinto del esperado "
      f"({sum(f['tipo'] == '18' for f in filas)} originales, {sum(f['tipo'] == 'nuevo' for f in filas)} nuevos)")
