"""Pruebas del gate de CI (parche 06, scripts/ci_gate.py) con variantes sintéticas del JUnit REAL de la suite del árbol final.
Cada caso fija ANTES de correr el veredicto esperado (pass/fail) y, para los fail, el texto del motivo que debe aparecer.
Uso: python -I pruebas_gate.py <árbol_final> <junit_real.xml> <árbol_base> <python_del_entorno> <dir_salida> [<otro_python_sin_dependencias>]
El intérprete se usa tal como se pasa (un venv es un enlace: resolverlo cambiaría de intérprete)."""
import copy
import os
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

final, junit, base, out = (pathlib.Path(sys.argv[i]).resolve() for i in (1, 2, 3, 5))
py = os.path.abspath(sys.argv[4])
otro = os.path.abspath(sys.argv[6]) if len(sys.argv) > 6 else None
out.mkdir(parents=True, exist_ok=True)
GATE = final / "scripts/ci_gate.py"
GUARD = "tests.integration.test_engine_version_contract"
real = ET.parse(junit)


def variante(nombre, cambiar):
    arbol = copy.deepcopy(real)
    raiz = arbol.getroot()
    for suite in raiz.iter("testsuite"):
        cambiar(suite)
    ruta = out / f"junit_{nombre}.xml"
    arbol.write(ruta, encoding="utf-8", xml_declaration=True)
    return ruta


def omitir_guarda(suite):
    for c in suite.findall("testcase"):
        if c.get("classname") == GUARD:
            for h in list(c):
                c.remove(h)
            ET.SubElement(c, "skipped", {"message": "sintético: guarda omitida"})


def quitar_guarda(suite):
    for c in suite.findall("testcase"):
        if c.get("classname") == GUARD:
            suite.remove(c)


def quitar_una_de_la_guarda(suite):
    for c in suite.findall("testcase"):
        if c.get("classname") == GUARD:
            suite.remove(c)
            return


def fallar_una_ajena(suite):
    for c in suite.findall("testcase"):
        if c.get("classname") != GUARD and not list(c):
            ET.SubElement(c, "failure", {"message": "sintético"})
            return


def fallar_una_de_la_guarda(suite):
    for c in suite.findall("testcase"):
        if c.get("classname") == GUARD:
            ET.SubElement(c, "failure", {"message": "sintético"})
            return


def error_en_una(suite):
    for c in suite.findall("testcase"):
        if not list(c):
            ET.SubElement(c, "error", {"message": "sintético"})
            return


def vaciar(suite):
    for c in suite.findall("testcase"):
        suite.remove(c)


omitida = variante("guarda_omitida", omitir_guarda)
casos = [
    # nombre, árbol (cwd), junit, esperado, texto del motivo[, intérprete]
    ("real_final", final, junit, "pass", None),
    ("guarda_omitida", final, omitida, "fail", "version guard ran 7 and passed 0 of 7"),
    ("guarda_quitada", final, variante("guarda_quitada", quitar_guarda), "fail", "version guard ran 0 and passed 0 of 7"),
    ("guarda_6_de_7", final, variante("guarda_6_de_7", quitar_una_de_la_guarda), "fail", "version guard ran 6 and passed 6 of 7"),
    ("falla_ajena", final, variante("falla_ajena", fallar_una_ajena), "fail", "1 failed and 0 errored"),
    ("falla_en_guarda", final, variante("falla_en_guarda", fallar_una_de_la_guarda), "fail", "passed 6 of 7"),
    ("error", final, variante("error", error_en_una), "fail", "0 failed and 1 errored"),
    ("junit_vacio", final, variante("junit_vacio", vaciar), "fail", "the JUnit report holds no test"),
    # Base 72ffae5: el motor no declara ENGINE_VERSION (no hay 02v3), así que la guarda no se exige; el JUnit sin la guarda pasa.
    ("base_sin_version_sin_guarda", base, variante("base_sin_guarda", quitar_guarda), "pass", None),
]
if otro:
    # Otro intérprete, sin las dependencias del proyecto: no puede importar el motor. El gate no debe aflojar por eso.
    casos += [("otro_interprete_real", final, junit, "pass", None, otro),
              ("otro_interprete_guarda_omitida", final, omitida, "fail", "version guard ran 7 and passed 0 of 7", otro)]
filas = []
for nombre, arbol, j, esperado, motivo, *interprete in casos:
    ev = out / f"evidencia_{nombre}"
    r = subprocess.run([interprete[0] if interprete else py, "-B", str(GATE), str(ev), str(j)], cwd=arbol, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "packages/tia/src", "PYTHONDONTWRITEBYTECODE": "1"})
    prov = json.loads((ev / "provenance.json").read_text()) if (ev / "provenance.json").exists() else {}
    veredicto = prov.get("verdict")
    ok = (veredicto == esperado and r.returncode == (0 if esperado == "pass" else 1)
          and (motivo is None or any(motivo in p for p in prov.get("problems", []))))
    filas.append({"caso": nombre, "interprete": interprete[0] if interprete else py, "esperado": esperado, "veredicto": veredicto, "rc": r.returncode, "motivo_esperado": motivo,
                  "problemas": prov.get("problems"), "engine_version": prov.get("engine_version"), "report": prov.get("report"),
                  "OK": ok, "stderr": r.stderr[-400:]})
    print(f"{'OK ' if ok else 'MAL'} {nombre:28s} esperado={esperado} veredicto={veredicto} rc={r.returncode} problemas={prov.get('problems')}")
json.dump(filas, open(out / "pruebas_gate.json", "w"), indent=1, ensure_ascii=False)
print(f"RESULTADO: {sum(f['OK'] for f in filas)}/{len(filas)} casos con el veredicto y el motivo esperados")
sys.exit(0 if all(f["OK"] for f in filas) else 1)
