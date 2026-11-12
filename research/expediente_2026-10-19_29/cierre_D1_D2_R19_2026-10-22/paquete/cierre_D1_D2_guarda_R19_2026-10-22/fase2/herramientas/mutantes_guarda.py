"""Mutantes para evaluar la guarda de versión (solo en copias aisladas). Cada mutante parte de un árbol (01+02v3 o 02v3
sin 01) y cambia UNA cosa; se corre solo el archivo de la guarda y se registra el resultado de cada prueba.
Uso: python mutantes_guarda.py <arbol_obligatoria> <arbol_solo02v3> <dir_mutantes> <venv_python> <salida.json>"""
import json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MOTOR = "packages/tia/src/tia/backtest/engine.py"
PAPER = "packages/tia/src/tia/execution/paper.py"
GUARDA = "tests/integration/test_engine_version_contract.py"
OBL, SOLO = "obligatoria", "solo02v3"
# (árbol de partida, [(archivo, antes, después)], qué se espera de la guarda, por qué)
MUTANTES = {
    "N0_obligatoria_sin_cambios": (OBL, [], "pasa", "control positivo"),
    "N1_02v3_sin_01": (SOLO, [], "falla", "la etiqueta 1.1.0 sin D1-D3"),
    "M1_D1_salida_id_sin_barra": (OBL, [(MOTOR, 'signal_id=f"{exit_key}:{candle.close_time.isoformat()}",', "signal_id=exit_key,")], "falla", "D1 cierres"),
    "M2_D1_stop_id_sin_colocacion": (OBL, [(MOTOR, 'signal_id=f"{leg.signal_id}:protective:{self._stop_placements}",', 'signal_id=f"{leg.signal_id}:protective",')], "falla", "D1 stops"),
    "M3_D2_sin_comparar_nivel": (OBL, [(MOTOR, "if same_size and same_level:", "if same_size:")], "falla", "D2"),
    "M4_D3_sin_cancelar_resto_al_salir": (OBL, [(MOTOR, "for order in provider.resting_orders(leg.symbol):", "for order in ():")], "falla", "D3 capa 1"),
    "M5_D3_sin_cancelar_resto_en_plano": (OBL, [(MOTOR, "for order in provider.resting_orders(symbol):", "for order in ():")], "falla", "D3 capa 2"),
    "M6_D3_sin_red_de_seguridad": (OBL, [(MOTOR, "if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")], "falla", "D3 capa 3"),
    "M7_sin_aviso_de_pierna_sin_stop": (OBL, [(MOTOR, "if cfg.use_protective_stops and unprotected:", "if False:")], "fuera de alcance", "es el aviso del informe, no una regla de la venue"),
    "M8_D3_sin_ninguna_capa": (OBL, [(MOTOR, "for order in provider.resting_orders(leg.symbol):", "for order in ():"),
                                     (MOTOR, "for order in provider.resting_orders(symbol):", "for order in ():"),
                                     (MOTOR, "if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")], "falla", "D3 entero"),
    "M9_D2_recoloca_el_stop_en_cada_barra": (OBL, [(MOTOR, "if same_size and same_level:", "if False:")], "falla", "D2 sin recolocaciones de más"),
    "M10_cierre_sin_reduce_only": (OBL, [(MOTOR, "            created_at=candle.close_time,\n            reduce_only=True,", "            created_at=candle.close_time,\n            reduce_only=False,")], "falla", "regla previa que 1.1.0 no debilita"),
    "E1_02v3_sin_01_con_contadores_falsos": (SOLO, [(MOTOR, "        counts = _MutableCounts()\n",
        "        counts = _MutableCounts()\n        self.order_hygiene = {'entry_remainders_cancelled_on_exit': 0, 'stale_entry_remainders_cancelled_flat': 0, 'exits_done_with_position_left': 0, 'bars_with_leg_and_no_stop': 0}\n")],
        "falla", "evasión: la interfaz de 01 (order_hygiene) sin el comportamiento"),
    "E2_02v3_sin_01_con_resting_orders": (SOLO, [(PAPER, "    async def get_positions(self) -> dict[str, Position]:",
        "    def resting_orders(self, symbol):\n        return [o for o in self._orders.values() if o.symbol == symbol and not o.state.is_terminal]\n\n    async def get_positions(self) -> dict[str, Position]:")],
        "falla", "evasión: el método que agrega 01 sin usarlo"),
    "L1_obligatoria_declara_1_0_9": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.0.9"')], "se omite", "no promete D1-D3: nada que exigir"),
    "L2_02v3_sin_01_declara_1_0_9": (SOLO, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.0.9"')], "se omite", "etiqueta veraz: sin D1-D3 y sin prometerlos"),
    "L3_obligatoria_declara_1_2_0": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.2.0"')], "pasa", "una versión posterior conserva la promesa"),
    "L4_02v3_sin_01_declara_1_2_0": (SOLO, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.2.0"')], "falla", "una versión posterior sin D1-D3"),
    "L5_obligatoria_declara_1_1_0_dev": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.1.0-dev"')], "falla", "una etiqueta ilegible no se escapa"),
}


def construir(origen: Path, dest: Path, cambios):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(origen / "pyproject.toml", dest / "pyproject.toml")
    for d in ("packages/tia/src", "tests", "data/fixtures"):
        shutil.copytree(origen / d, dest / d, ignore=shutil.ignore_patterns("__pycache__"))
    for archivo, a, b in cambios:
        p = dest / archivo; s = p.read_text()
        assert s.count(a) == 1, (dest.name, a); p.write_text(s.replace(a, b))


def correr(arbol: Path, py: str):
    env = {**os.environ, "PYTHONPATH": "packages/tia/src", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([py, "-B", "-m", "pytest", GUARDA, "-q", "-p", "no:cacheprovider", "-rA", "--tb=line", "-o", "addopts="],
                       cwd=arbol, env=env, capture_output=True, text=True, timeout=1800)
    res = {}
    for linea in r.stdout.splitlines():
        for estado in ("PASSED", "FAILED", "ERROR", "SKIPPED"):
            if linea.startswith(estado + " "):
                nombre = linea.split("::")[-1].split(" ")[0] if "::" in linea else linea.split(" ", 1)[1]
                res[nombre] = estado
    motivos = [l[:400] for l in r.stdout.splitlines() if l.startswith("E ") or l.startswith("FAILED ") or l.startswith("SKIPPED ")]
    return {"rc": r.returncode, "resultados": res, "motivos": motivos[:30], "resumen": r.stdout.strip().splitlines()[-1:]}


def veredicto(esperado, res):
    est = list(res["resultados"].values())
    conductuales = {k: v for k, v in res["resultados"].items() if not k.startswith("test_the_checks") and not k.startswith("test_a_version")}
    if esperado == "pasa":
        return "OK" if res["rc"] == 0 and all(v == "PASSED" for v in est) else "MAL"
    if esperado == "se omite":
        return "OK" if res["rc"] == 0 and conductuales and all(v == "SKIPPED" for v in conductuales.values()) else "MAL"
    if esperado == "falla":
        return "OK (detectado)" if res["rc"] != 0 and any(v in ("FAILED", "ERROR") for v in conductuales.values()) else "VIVO"
    return "detectado" if res["rc"] != 0 else "no detectado"


def main(obl, solo, dirm, py, salida):
    raiz = {OBL: Path(obl), SOLO: Path(solo)}; dirm = Path(dirm)
    for n, (base, cambios, _, _) in MUTANTES.items():
        construir(raiz[base], dirm / n, cambios)
    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(MUTANTES, ex.map(lambda n: correr(dirm / n, py), MUTANTES)))
    out = {n: {"parte_de": MUTANTES[n][0], "cambios": MUTANTES[n][1], "esperado": MUTANTES[n][2], "por_que": MUTANTES[n][3],
               "veredicto": veredicto(MUTANTES[n][2], res[n]), **res[n]} for n in MUTANTES}
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False)
    for n, r in out.items():
        fallan = [k for k, v in r["resultados"].items() if v in ("FAILED", "ERROR")]
        print(f"{n:42s} esperado={r['esperado']:16s} veredicto={r['veredicto']:15s} fallan={len(fallan)} {r['resumen']}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
