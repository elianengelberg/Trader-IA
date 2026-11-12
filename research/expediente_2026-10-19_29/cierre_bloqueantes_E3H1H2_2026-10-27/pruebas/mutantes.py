"""Pruebas de mutación del v3: cada mutante quita UNA defensa (reemplazos exactos, que tienen que aparecer una sola vez)
y corre la suite completa contra él (variable V3_RUTA). Un mutante «sobrevive» si ninguna prueba falla.
Uso: python -I mutantes.py <ejecutar_E3_v3.py> <python> <dir_salida>"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

V3, PY, OUT = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
SUITE = Path(__file__).resolve().parent / "test_orquestador_v3.py"
MUTANTES = {
    "C7_ventana_no_fijada": [
        ('        if obs != h:\n            malos[nombre]', '        if obs != h and nombre != "ventana_A":\n            malos[nombre]'),
        ('if vd.get("veredicto") != "VALIDO" or vd.get("inicio_H") != INICIO_H_A:', 'if vd.get("veredicto") != "VALIDO":')],
    "C8_manifiesto_vacio_o_incompleto": [
        ("if not isinstance(entradas, list) or not entradas:", "if not isinstance(entradas, list):"),
        ("    if faltan or sobran:", "    if sobran:")],
    "C8_mapeos_desde_el_manifiesto": [
        ('mapeos = json.loads(datos["mapeos_adenda1_completa"])["mapeos"]',
         'mapeos = json.loads((CIERRE / (json.loads(man_bytes).get("mapeos") or "tabla/mapeos_adenda1_completa.json")).read_text())["mapeos"]')],
    "C9_relectura_de_disco": [
        ("P, registro_mapeos = panel_real(datos, universo, mapeos)",
         'P, registro_mapeos = panel_real({**datos, "series_calidad_757": _leer_conjunto(e3 / "resultados/calidad/series")}, universo, mapeos)')],
    "C9_acepta_enlaces": [
        ("            if Path(raiz, n).is_symlink():\n                raise ValueError", "            if False:\n                raise ValueError")],
    "C10_import_desde_disco": [
        ("mods = cargar_modulos(fuentes)                                                  # C10",
         'sys.path.insert(0, str(e3 / "codigo")); import universo, motor, inferencia; '
         'mods = {"universo": universo, "motor": motor, "inferencia": inferencia}')],
    "C11_sin_estado_ERROR": [
        ("except BaseException as exc:  # incluye SystemExit", "except ZeroDivisionError as exc:  # incluye SystemExit")],
    "C11_sin_registro_de_intentos": [
        ("previo = permitir_intento(intentos, sha_aut, texto)", "previo = None")],
    "C11_sin_bloqueo": [
        ("            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)", "            pass")],
    "C12_acepta_duplicados": [("        if clave in vistos:", "        if False:")],
    "C12_acepta_huecos_largos": [("        if k - int(activos_x[-1]) - 1 >= 30:", "        if False:")],
    "C12_sin_control_de_marcas": [
        ('    if malos:\n        raise Rechazo(f"los mapeos cambian marcas', '    if False:\n        raise Rechazo(f"los mapeos cambian marcas')],
    "C12_1R_sin_dividir": [
        ("            O[i, :k], C[i, :k], QV[i, :k], act[i, :k] = np.nan, np.nan, np.nan, False", "            pass")],
    "C12_mapeos_despues_de_crear_la_salida": [
        ("        syms2, _, _, _, _, reg_previo, origen = aplicar_mapeos(syms, ceros, ceros, ceros, act, mapeos, universo.INICIO)\n"
         "        comprobar_marcas(syms, syms2, origen, universo)\n",
         "        reg_previo = []\n")],
    "C13_sin_frases_de_decision": [
        ('**{f"decision_{k}": f in texto for k, f in FRASES_DECISION.items()}}', "}")],
}
OUT.mkdir(parents=True, exist_ok=True)
fuente = V3.read_text()
resumen = {}
for nombre, reemplazos in MUTANTES.items():
    t = fuente
    for viejo, nuevo in reemplazos:
        assert t.count(viejo) == 1, (nombre, viejo[:60], t.count(viejo))
        t = t.replace(viejo, nuevo)
    m = OUT / f"mutante_{nombre}.py"
    m.write_text(t)
    env = {**os.environ, "V3_RUTA": str(m)}
    r = subprocess.run([PY, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "-rf", "-W", "ignore", "--rootdir", str(SUITE.parent),
                        "--basetemp", str(OUT / f"tmp_{nombre}"), str(SUITE)], capture_output=True, text=True, env=env, timeout=1200)
    fallas = sorted(set(re.findall(r"^FAILED \S+::(\S+)", r.stdout, re.M)))
    final = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
    resumen[nombre] = {"sobrevive": not fallas, "pruebas_que_lo_detectan": fallas, "resumen_pytest": final}
    print(f"{nombre:<42} {'SOBREVIVE' if not fallas else 'detectado'} · {final} · {fallas[:4]}", flush=True)
(OUT / "resultado_mutantes.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
print("mutantes:", len(resumen), "· sobreviven:", sum(v["sobrevive"] for v in resumen.values()))
