"""Matriz de mutantes de la guarda de versión (v2 de la herramienta; solo copias aisladas). Corre UN archivo de guarda
contra cada caso y verifica que cada mutante falle POR LA RAZÓN prevista (subcadena esperada en las aserciones).
Uso: python mutantes_guarda_v2.py <guarda.py> <obligatoria> <solo02v3> <base> <solo01> <dir_mutantes> <python> <salida.json>"""
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MOTOR = "packages/tia/src/tia/backtest/engine.py"
PAPER = "packages/tia/src/tia/execution/paper.py"
GUARDA = "tests/integration/test_engine_version_contract.py"
OBL, SOLO, BASE, SOLO01 = "obligatoria", "solo02v3", "base", "solo01"
D1C, D2, D3P, D3R, TJ = ("test_a_rejected_close_is_sent_again_as_a_new_order_and_closes", "test_the_stop_in_the_book_follows_the_leg",
                         "test_partial_fills_never_add_to_a_closing_position_or_reopen_one",
                         "test_a_close_that_ends_with_position_left_is_followed_by_another",
                         "test_rejections_partials_and_limit_entries_together")
LIMITE = ("            order_type=OrderType.MARKET,\n            time_in_force=TimeInForce.GTC,\n            created_at=candle.close_time,\n            reduce_only=True,",
          "            order_type=OrderType.LIMIT,\n            limit_price=candle.close * (0.98 if side is Side.SELL else 1.02),\n"
          "            time_in_force=TimeInForce.GTC,\n            created_at=candle.close_time,\n            reduce_only=True,")
# nombre: (árbol, cambios, esperado, {prueba: subcadena que debe aparecer en sus aserciones}, por qué)
CASOS = {
    "N0_obligatoria": (OBL, [], "pasa", {}, "control positivo: 01+02v3"),
    "N1_02v3_sin_01": (SOLO, [], "falla", {D1C: "sent again after it was dead", D2: "no stop in the book ever moved"}, "etiqueta 1.1.0 sin D1-D3"),
    "N2_base_con_guarda_B_sin_A": (BASE, [], "falla", {D1C: "no engine_version"}, "B sin A: la guarda sin 01+02v3"),
    "N3_01_sin_02v3_reversion_parcial": (SOLO01, [], "falla", {D1C: "no engine_version"}, "A revertida a medias: 02v3 revertido solo (R4)"),
    "M1_D1_salida_id_sin_barra": (OBL, [(MOTOR, 'signal_id=f"{exit_key}:{candle.close_time.isoformat()}",', "signal_id=exit_key,")], "falla",
                                  {D1C: "market"}, "D1 cierres: el reintento reusa el id del cierre rechazado"),
    "M2_D1_stop_id_sin_colocacion": (OBL, [(MOTOR, 'signal_id=f"{leg.signal_id}:protective:{self._stop_placements}",', 'signal_id=f"{leg.signal_id}:protective",')],
                                     "falla", {D1C: "stop"}, "D1 stops: la recolocación reusa el id del stop cancelado"),
    "M3_D2_sin_comparar_nivel": (OBL, [(MOTOR, "if same_size and same_level:", "if same_size:")], "falla", {D2: "no stop in the book ever moved"}, "D2"),
    "M4_D3_sin_cancelar_resto_al_salir": (OBL, [(MOTOR, "for order in provider.resting_orders(leg.symbol):", "for order in ():")], "falla",
                                          {D3P: "growth_after_close"}, "D3 capa 1"),
    "M5_D3_sin_cancelar_resto_en_plano": (OBL, [(MOTOR, "for order in provider.resting_orders(symbol):", "for order in ():")], "falla",
                                          {D3P: "entries_filling_a_later_position"}, "D3 capa 2"),
    "M6_D3_sin_red_de_seguridad": (OBL, [(MOTOR, "if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")], "falla",
                                   {D3R: "uncovered_streaks"}, "D3 capa 3"),
    "M7_sin_aviso_de_pierna_sin_stop": (OBL, [(MOTOR, "if cfg.use_protective_stops and unprotected:", "if False:")], "fuera de alcance", {},
                                        "aviso del informe, no regla de venue (lo cubre 01)"),
    "M8_D3_sin_ninguna_capa": (OBL, [(MOTOR, "for order in provider.resting_orders(leg.symbol):", "for order in ():"),
                                     (MOTOR, "for order in provider.resting_orders(symbol):", "for order in ():"),
                                     (MOTOR, "if exit_order is not None and exit_order.state.is_terminal and leg.quantity > 0:", "if False:")],
                               "falla", {D3P: "growth_after_close"}, "D3 entero"),
    "M9_D2_recoloca_el_stop_en_cada_barra": (OBL, [(MOTOR, "if same_size and same_level:", "if False:")], "falla",
                                             {D2: "replaced at the same size and level"}, "D2 sin recolocaciones de más"),
    "M10_cierre_sin_reduce_only": (OBL, [(MOTOR, "            created_at=candle.close_time,\n            reduce_only=True,",
                                          "            created_at=candle.close_time,\n            reduce_only=False,")], "falla",
                                   {D3P: "without reduce_only"}, "regla previa que 1.1.0 no debilita"),
    "E1_02v3_sin_01_con_contadores_falsos": (SOLO, [(MOTOR, "        counts = _MutableCounts()\n",
        "        counts = _MutableCounts()\n        self.order_hygiene = {'entry_remainders_cancelled_on_exit': 0, 'stale_entry_remainders_cancelled_flat': 0, 'exits_done_with_position_left': 0, 'bars_with_leg_and_no_stop': 0}\n")],
        "falla", {D1C: "sent again after it was dead"}, "evasión: interfaz de 01 sin comportamiento"),
    "E2_02v3_sin_01_con_resting_orders": (SOLO, [(PAPER, "    async def get_positions(self) -> dict[str, Position]:",
        "    def resting_orders(self, symbol):\n        return [o for o in self._orders.values() if o.symbol == symbol and not o.state.is_terminal]\n\n    async def get_positions(self) -> dict[str, Position]:")],
        "falla", {D1C: "sent again after it was dead"}, "evasión: método de 01 sin usarlo"),
    "C1_cierre_limite_reduce_only": (OBL, [(MOTOR, *LIMITE)], "pasa", {}, "otra implementación válida del cierre: límite agresiva reduce-only"),
    "C2_02v3_sin_01_cierre_limite": (SOLO, [(MOTOR, *LIMITE)], "falla", {D2: "no stop in the book ever moved"}, "otra forma de cierre sin D1-D3"),
    "L1_obligatoria_1_0_9": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.0.9"')], "se omite", {}, "no promete D1-D3"),
    "L2_02v3_sin_01_1_0_9": (SOLO, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.0.9"')], "se omite", {}, "etiqueta veraz"),
    "L3_obligatoria_1_2_0": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.2.0"')], "pasa", {}, "versión posterior"),
    "L4_02v3_sin_01_1_2_0": (SOLO, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.2.0"')], "falla", {D1C: "sent again after it was dead"}, "posterior sin D1-D3"),
    "L5_obligatoria_1_1_0_dev": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.1.0-dev"')], "falla", {D1C: "not a dotted number"}, "ilegible: falla cerrado"),
    "L6_02v3_sin_01_1_1": (SOLO, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.1"')], "falla", {D1C: "sent again after it was dead"}, "forma corta = 1.1.0"),
    "L7_obligatoria_1_1": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "1.1"')], "pasa", {}, "forma corta = 1.1.0"),
    "L8_obligatoria_v1_1_0": (OBL, [(MOTOR, 'ENGINE_VERSION = "1.1.0"', 'ENGINE_VERSION = "v1.1.0"')], "falla", {D1C: "not a dotted number"}, "prefijo v: ilegible"),
}


def construir(origen: Path, dest: Path, cambios, guarda: Path):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copy2(origen / "pyproject.toml", dest / "pyproject.toml")
    for d in ("packages/tia/src", "tests", "data/fixtures"):
        shutil.copytree(origen / d, dest / d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(guarda, dest / GUARDA)
    for archivo, a, b in cambios:
        p = dest / archivo
        s = p.read_text()
        assert s.count(a) == 1, (dest.name, a)
        p.write_text(s.replace(a, b))


def correr(arbol: Path, py: str):
    env = {**os.environ, "PYTHONPATH": "packages/tia/src", "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([py, "-B", "-m", "pytest", GUARDA, "-q", "-p", "no:cacheprovider", "-rA", "--tb=short", "-o", "addopts="],
                       cwd=arbol, env=env, capture_output=True, text=True, timeout=1800)
    res, actual, texto = {}, None, {}
    for linea in r.stdout.splitlines():
        if linea.startswith("____") and " test_" in linea:
            actual = linea.strip("_ ").strip()
            texto[actual] = []
        elif actual and (linea.startswith("E ") or linea.startswith(">")):
            texto[actual].append(linea)
        for estado in ("PASSED", "FAILED", "ERROR"):
            if linea.startswith(estado + " ") and "::" in linea:
                res[linea.split("::")[-1].split(" ")[0]] = estado
    omitidas = sum(int(x.split("]")[0].strip("[")) for x in [l.split(" ", 1)[1] for l in r.stdout.splitlines() if l.startswith("SKIPPED [")])
    return {"rc": r.returncode, "resultados": res, "omitidas": omitidas, "aserciones": {k: "\n".join(v)[:1500] for k, v in texto.items()},
            "resumen": r.stdout.strip().splitlines()[-1:]}


def veredicto(esperado, razones, res):
    fallan = {k for k, v in res["resultados"].items() if v in ("FAILED", "ERROR")}
    pasan = {k for k, v in res["resultados"].items() if v == "PASSED"}
    if esperado == "pasa":
        return "OK" if res["rc"] == 0 and not fallan and not res["omitidas"] and len(pasan) == 7 else "MAL"
    if esperado == "se omite":
        return "OK" if res["rc"] == 0 and not fallan and res["omitidas"] == 5 else "MAL"
    if esperado == "falla":
        if res["rc"] == 0 or not fallan:
            return "VIVO"
        malas = [p for p, sub in razones.items() if p not in fallan or sub not in res["aserciones"].get(p, "")]
        return "OK (detectado, razón correcta)" if not malas else f"DETECTADO, razón no verificada en {malas}"
    return "detectado" if res["rc"] != 0 else "no detectado"


def main(guarda, obl, solo, base, solo01, dirm, py, salida):
    raiz = {OBL: Path(obl), SOLO: Path(solo), BASE: Path(base), SOLO01: Path(solo01)}
    dirm, guarda = Path(dirm), Path(guarda)
    for n, (b, cambios, *_rest) in CASOS.items():
        construir(raiz[b], dirm / n, cambios, guarda)
    with ThreadPoolExecutor(3) as ex:
        res = dict(zip(CASOS, ex.map(lambda n: correr(dirm / n, py), CASOS)))
    out = {n: {"parte_de": CASOS[n][0], "cambios": CASOS[n][1], "esperado": CASOS[n][2], "razon_esperada": CASOS[n][3], "por_que": CASOS[n][4],
               "veredicto": veredicto(CASOS[n][2], CASOS[n][3], res[n]), **res[n]} for n in CASOS}
    json.dump({"guarda": str(guarda), "casos": out}, open(salida, "w"), indent=1, ensure_ascii=False)
    for n, r in out.items():
        fallan = sorted(k for k, v in r["resultados"].items() if v in ("FAILED", "ERROR"))
        print(f"{n:38s} esperado={r['esperado']:16s} {r['veredicto']:32s} fallan={len(fallan)} omitidas={r['omitidas']} {r['resumen']}")


if __name__ == "__main__":
    main(*sys.argv[1:9])
