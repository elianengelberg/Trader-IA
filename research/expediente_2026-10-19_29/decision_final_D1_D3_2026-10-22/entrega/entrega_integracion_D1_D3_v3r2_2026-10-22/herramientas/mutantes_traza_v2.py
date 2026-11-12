"""Mutantes de la trazabilidad (v2, con el control de números del parche 02 corregido): cada uno quita UNA pieza (en uno o más archivos) para ver qué prueba la detecta.
Uso: python mutantes_traza.py <arbol_final> <dir_mutantes> <archivo_de_prueba_relativo> <venv_python> <salida.json>"""
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ENG = "packages/tia/src/tia/backtest/engine.py"
REPO = "packages/tia/src/tia/persistence/repositories.py"
API = "packages/tia/src/tia/api/state.py"
MUTANTES = {
    "T1_run_id_con_la_formula_de_72ffae5": [(ENG, '''            run_id=deterministic_id(
                "bt", cfg.dataset, resolved, cfg.digest(),
                {
                    **provenance,
                    "strategies": strategy_versions,
                    "liquidate_at_end": cfg.liquidate_at_end,
                    "out_of_sample": cfg.is_out_of_sample,
                },
            ),''', '''            run_id=deterministic_id("bt", cfg.dataset, resolved, cfg.digest()),''')],
    "T2_guardar_sin_guarda_upsert_ciego": [(REPO, 'if stored is not None and stored != _provenance(values.get("conditions")):', "if False:")],
    "T3_datos_fuera_del_id": [(ENG, '"data_fingerprint": data_fingerprint(bars),', '"data_fingerprint": cfg.dataset,')],
    "T4_huella_sin_execution": [(ENG, '''    "backtest", "core", "data", "domain", "economics", "execution", "quant", "regime", "risk",''',
                                 '''    "backtest", "core", "data", "domain", "economics", "quant", "regime", "risk",''')],
    "T5_api_sin_version": [(API, '''                    "engine_version": (row.conditions or {}).get("engine_version") or None,\n''', "")],
    "T6_version_fija_no_la_constante": [(ENG, '"engine_version": ENGINE_VERSION,', '"engine_version": "1.1.0",')],
    "T7_estrategias_fuera_del_id": [(ENG, '"strategies": strategy_versions,', '"strategies": {},')],
    "T8_huella_inventada_sin_fuente": [(ENG, 'return digest.hexdigest()[:32] if files else "unavailable"', "return digest.hexdigest()[:32]")],
    "T9_huella_del_motor_fuera_del_id": [(ENG, '"engine_fingerprint": engine_fingerprint(),', '"engine_fingerprint": "",')],
    "T10_legado_rellenado_con_version": [(REPO, 'return tuple(str((conditions or {}).get(key) or "") for key in _BACKTEST_PROVENANCE)',
                                          'return tuple(str((conditions or {}).get(key) or ("1.1.0" if key == "engine_version" else "")) for key in _BACKTEST_PROVENANCE)')],
    "T11_legado_como_comodin": [(REPO, 'if stored is not None and stored != _provenance(values.get("conditions")):',
                                 'if stored is not None and any(stored) and stored != _provenance(values.get("conditions")):')],
    "T12_api_rellena_la_version_del_legado": [(API, '(row.conditions or {}).get("engine_version") or None,',
                                               '(row.conditions or {}).get("engine_version") or "1.1.0",')],
    "T13_sin_control_de_numeros_misma_procedencia": [(REPO, "            if differ:\n", "            if False:\n")],
    "T14_nan_no_se_normaliza": [(REPO, "    if isinstance(value, float) and math.isnan(value):\n        return None\n", "")],
}
#: Mutantes equivalentes: ninguna entrada alcanzable los distingue del original. Se informan, no cuentan como vivos.
EQUIVALENTES = {
    "T10_legado_rellenado_con_version": (
        "_provenance se aplica a ambos lados y compara las cuatro huellas: rellenar solo la versión de una fila "
        "antigua da ('1.1.0','','','') frente a un resultado nuevo con las cuatro llenas (siguen distintas) o frente "
        "a otra fila antigua rellenada igual (siguen iguales). El riesgo real —lo desconocido como comodín— es T11."),
}


def construir(origen: Path, dest: Path, cambios):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(origen / "pyproject.toml", dest / "pyproject.toml")
    for d in ("packages/tia/src", "tests", "data/fixtures"):
        shutil.copytree(origen / d, dest / d, ignore=shutil.ignore_patterns("__pycache__"))
    for archivo, a, b in cambios:
        p = dest / archivo
        s = p.read_text()
        assert s.count(a) == 1, (dest.name, a)
        p.write_text(s.replace(a, b))


def correr(arbol: Path, prueba: str, py: str):
    env = {**os.environ, "PYTHONPATH": "packages/tia/src", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([py, "-B", "-m", "pytest", prueba, "-q", "-p", "no:cacheprovider", "-rA", "--tb=line", "-o", "addopts="],
                       cwd=arbol, env=env, capture_output=True, text=True, timeout=1800)
    res = {}
    for linea in r.stdout.splitlines():
        for estado in ("PASSED", "FAILED", "ERROR"):
            if linea.startswith(estado + " "):
                res[linea.split("::")[-1].split(" ")[0]] = estado
    motivos = [l for l in r.stdout.splitlines() if l.startswith("E ") or ("Error" in l and ".py:" in l)]
    return {"rc": r.returncode, "resultados": res, "motivos": motivos[:12], "resumen": r.stdout.strip().splitlines()[-1:]}


def main(arbol, dirm, prueba, py, salida):
    arbol, dirm = Path(arbol), Path(dirm)
    for n, c in MUTANTES.items():
        construir(arbol, dirm / n, c)
    base = correr(arbol, prueba, py)
    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(MUTANTES, ex.map(lambda n: correr(dirm / n, prueba, py), MUTANTES)))
    vivos = [n for n, r in res.items() if n not in EQUIVALENTES
             and (not r["resultados"] or all(v == "PASSED" for v in r["resultados"].values()))]
    json.dump({"prueba": prueba, "arbol_sin_mutar": base, "vivos": vivos, "equivalentes": EQUIVALENTES,
               "mutantes": {n: {"cambios": [list(c) for c in MUTANTES[n]], **res[n]} for n in MUTANTES}},
              open(salida, "w"), indent=1, ensure_ascii=False)
    print("sin mutar:", base["resumen"])
    for n, r in res.items():
        print(n, "detectado por:", sorted(k for k, v in r["resultados"].items() if v != "PASSED"), r["resumen"])
    print("equivalentes (informados, no cuentan):", list(EQUIVALENTES))
    print("vivos:", vivos or "ninguno")
    return 1 if vivos else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
