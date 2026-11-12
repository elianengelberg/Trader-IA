"""Mutantes del revisor (distintos de los 15 del autor). Cada uno cambia UNA defensa del v3; se corre la suite del autor
contra el mutante (variable V3_RUTA), con el plugin guarda_revisor (sin cálculo). «Sobrevive» = ninguna prueba falla.
Uso: PYTHONPATH=<arnes> python -B mutantes_revisor.py <v3.py> <suite.py> <python> <dir_salida>"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

V3, SUITE, PY, OUT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
MUTANTES = {
    "R1_validez_previa_cuenta_como_con_estadisticos": [
        ('ETAPAS_SIN_ESTADISTICOS = ("panel", "validez_previa")', 'ETAPAS_SIN_ESTADISTICOS = ("panel",)')],
    "R2_acepta_autorizacion_repetida_tras_ERROR": [
        ('    if any(e.get("sha_autorizacion") == sha_aut for e in ev):\n        raise Rechazo', '    if False:\n        raise Rechazo')],
    "R3_resultado_no_atomico": [
        ("    os.replace(tmp, p)\n", "    os.replace(tmp, p)\n    p.write_text(texto)\n")],
    "R4_registro_EVALUADO_antes_de_escribir_el_resultado": [
        ('            h = escribir_atomico(salida / "RESULTADO_E3.json", res)\n            intentos.anotar(evento="EVALUADO", id_intento=id_intento, sha_resultado=h)',
         '            intentos.anotar(evento="EVALUADO", id_intento=id_intento, sha_resultado="sin_hash")\n            h = escribir_atomico(salida / "RESULTADO_E3.json", res)')],
    "R5_ERROR_sobrescribe_aunque_ya_haya_resultado": [  # control: es el comportamiento actual; el mutante NO cambia nada
        ("def resultado_error(", "def resultado_error(")],
    "R6_ignora_sha_del_manifiesto_en_la_autorizacion": [
        ('"entradas_congeladas": bool(man_bytes) and sha_man in texto,', '"entradas_congeladas": True,')],
    "R7_sin_comprobar_salida_existente": [
        ('    if salida.exists():\n        raise Rechazo(f"{salida} ya existe', '    if False:\n        raise Rechazo(f"{salida} ya existe')],
    "R8_reintento_sin_citar_el_ERROR": [
        ('    if f"REINTENTO TRAS ERROR {u[\'sha_resultado\']}" not in texto:', '    if False:')],
}
OUT.mkdir(parents=True, exist_ok=True)
fuente = V3.read_text()
res = {}
for nombre, cambios in MUTANTES.items():
    t = fuente
    for viejo, nuevo in cambios:
        assert t.count(viejo) == 1, (nombre, viejo[:50], t.count(viejo))
        t = t.replace(viejo, nuevo)
    m = OUT / f"mutante_{nombre}.py"
    m.write_text(t)
    env = {**os.environ, "V3_RUTA": str(m)}
    r = subprocess.run([PY, "-B", "-m", "pytest", "-p", "guarda_revisor", "-p", "no:cacheprovider", "-q", "-rf", "-W", "ignore",
                        "--rootdir", str(SUITE.parent), "--basetemp", str(OUT / f"bt_{nombre}"), str(SUITE)],
                       capture_output=True, text=True, env=env, timeout=900)
    fallas = sorted(set(re.findall(r"^FAILED \S+::(\S+)", r.stdout, re.M)))
    # las 4 pruebas que fallan siempre por el bloqueo del cálculo no cuentan como detección
    base = {"test_INVALIDO_explicito_y_no_reescrito_como_ERROR", "test_EVALUADO_de_punta_a_punta_y_sin_segunda_ejecucion",
            "test_ejecutar_del_v3_identico_al_del_v2[20261026-0.02]", "test_ejecutar_del_v3_identico_al_del_v2[37-0.0]"}
    detect = [f for f in fallas if f not in base]
    res[nombre] = {"sobrevive": not detect, "detectado_por": detect, "resumen": r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]}
    print(f"{nombre:<52} {'SOBREVIVE' if not detect else 'detectado'} · {res[nombre]['resumen']} · {detect[:3]}", flush=True)
(OUT / "resultado_mutantes_revisor.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
