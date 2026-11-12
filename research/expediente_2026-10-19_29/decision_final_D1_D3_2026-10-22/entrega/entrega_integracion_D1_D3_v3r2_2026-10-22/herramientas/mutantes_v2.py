"""Mutantes del motor parcheado (v2, cierre 2026-10-22): cada uno revierte UNA pieza del parche (o tres, M8), o introduce
el defecto que una prueba nueva vigila (M9, M10), para ver qué prueba lo detecta y con qué aserción.
Uso: python mutantes.py <arbol_parcheado> <dir_mutantes> <archivo_de_prueba_relativo> <venv_python> <salida.json>"""
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MOTOR = "packages/tia/src/tia/backtest/engine.py"
MUTANTES = {
    "M1_D1_salida_id_sin_barra": [('signal_id=f"{exit_key}:{candle.close_time.isoformat()}",', "signal_id=exit_key,")],
    "M2_D1_stop_id_sin_colocacion": [('signal_id=f"{leg.signal_id}:protective:{self._stop_placements}",',
                                      'signal_id=f"{leg.signal_id}:protective",')],
    "M3_D2_sin_comparar_nivel": [("if same_size and same_level:", "if same_size:")],
    "M4_D3_sin_cancelar_resto_al_salir": [("for order in provider.resting_orders(leg.symbol):", "for order in ():")],
    "M5_D3_sin_cancelar_resto_en_plano": [("for order in provider.resting_orders(symbol):", "for order in ():")],
    "M6_D3_sin_red_de_seguridad": [("if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")],
    "M7_sin_aviso_de_pierna_sin_stop": [("if cfg.use_protective_stops and unprotected:", "if False:")],
    "M8_D3_sin_ninguna_capa": [("for order in provider.resting_orders(leg.symbol):", "for order in ():"),
                               ("for order in provider.resting_orders(symbol):", "for order in ():"),
                               ("if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")],
    "M9_D2_recoloca_el_stop_en_cada_barra": [("if same_size and same_level:", "if False:")],
    "M10_cierre_sin_reduce_only": [("""            created_at=candle.close_time,
            reduce_only=True,""", """            created_at=candle.close_time,
            reduce_only=False,""")],
}


def construir(origen: Path, dest: Path, cambios):
    if dest.exists():
        shutil.rmtree(dest)
    # solo lo que la prueba necesita: configuración de pytest, el paquete, las pruebas y los fixtures
    dest.mkdir(parents=True)
    shutil.copy2(origen / "pyproject.toml", dest / "pyproject.toml")
    for d in ("packages/tia/src", "tests", "data/fixtures"):
        shutil.copytree(origen / d, dest / d, ignore=shutil.ignore_patterns("__pycache__"))
    p = dest / MOTOR
    s = p.read_text()
    for a, b in cambios:
        assert s.count(a) == 1, (dest.name, a)
        s = s.replace(a, b)
    p.write_text(s)


def correr(arbol: Path, prueba: str, py: str):
    env = {**os.environ, "PYTHONPATH": "packages/tia/src", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([py, "-B", "-m", "pytest", prueba, "-q", "-p", "no:cacheprovider", "-rA", "--tb=line", "-o", "addopts="],
                       cwd=arbol, env=env, capture_output=True, text=True, timeout=1800)
    res = {}
    for linea in r.stdout.splitlines():
        for estado in ("PASSED", "FAILED", "ERROR"):
            if linea.startswith(estado + " "):
                nombre = linea.split("::")[-1].split(" ")[0]
                res[nombre] = estado
    motivos = [l for l in r.stdout.splitlines() if l.startswith("E ") or ("Error" in l and ".py:" in l)
               or l.startswith("FAILED ")]
    return {"rc": r.returncode, "resultados": res, "motivos": motivos[:40], "resumen": r.stdout.strip().splitlines()[-1:]}


def main(arbol, dirm, prueba, py, salida):
    arbol, dirm = Path(arbol), Path(dirm)
    for n, c in MUTANTES.items():
        construir(arbol, dirm / n, c)
    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(MUTANTES, ex.map(lambda n: correr(dirm / n, prueba, py), MUTANTES)))
    json.dump({"prueba": prueba, "mutantes": {n: {"cambios": MUTANTES[n], **res[n]} for n in MUTANTES}},
              open(salida, "w"), indent=1, ensure_ascii=False)
    for n, r in res.items():
        print(n, r["resultados"], r["resumen"])


if __name__ == "__main__":
    main(*sys.argv[1:6])
