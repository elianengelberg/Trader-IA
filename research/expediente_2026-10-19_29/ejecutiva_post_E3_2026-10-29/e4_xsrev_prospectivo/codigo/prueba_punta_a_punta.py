"""E4 · Prueba de punta a punta con fuente LOCAL SINTÉTICA (file://), sin red. Los datos son sintéticos, en formato de
Binance Vision (CSV de 12 columnas dentro de un ZIP, con .CHECKSUM), y la carpeta de datos lleva la marca SINTETICO.txt.
Comprueba: recolección con verificación de checksum y registro encadenado; rechazo de un checksum alterado; guarda de rutas del
destino; evaluación única en modo sintético con un efecto de reversión plantado; y los rechazos del evaluador (antes de tiempo,
segunda evaluación, prerregistro alterado, modo real sobre datos sintéticos).
Uso: python -I -B prueba_punta_a_punta.py <dir_vacio> <PROTEGIDOS.tsv> <salida.json>"""
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE, TSV, SAL = sys.argv[1:4]
os.makedirs(BASE, exist_ok=False)
FUENTE = os.path.join(BASE, "fuente_sintetica")
DATOS = os.path.join(BASE, "datos")
os.makedirs(FUENTE)
os.makedirs(DATOS)
open(os.path.join(DATOS, "SINTETICO.txt"), "w").write("Datos SINTÉTICOS generados por prueba_punta_a_punta.py; no son históricos.\n")
rng = np.random.default_rng(20261029)
n, dias, t0 = 35, 285, dt.date(2031, 1, 1)  # fechas ficticias, lejos de cualquier dato real
inicio = t0 - dt.timedelta(days=31)
z = rng.standard_normal((n, dias)) * 0.04
r = z.copy()
r[:, 2:] += -0.06 * z[:, :-2]
cierre = 100 * np.cumprod(1 + r, axis=1)
simbolos = [f"S{i:03d}USDT" for i in range(n)]
json.dump(simbolos, open(os.path.join(FUENTE, "LISTADO.json"), "w"))
for i, s in enumerate(simbolos):
    os.makedirs(os.path.join(FUENTE, s))
    for k in range(dias):
        d = (inicio + dt.timedelta(days=k)).isoformat()
        ms = int(dt.datetime.combine(inicio + dt.timedelta(days=k), dt.time(), dt.timezone.utc).timestamp() * 1000)
        fila = f"{ms},1,1,1,{cierre[i, k]:.10f},1,{ms + 86399999},{1e6 * (1 + i)},1000,0,0,0\n"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"{s}-1d-{d}.csv", fila)
        b = buf.getvalue()
        p = os.path.join(FUENTE, s, f"{s}-1d-{d}.zip")
        open(p, "wb").write(b)
        open(p + ".CHECKSUM", "w").write(f"{hashlib.sha256(b).hexdigest()}  {s}-1d-{d}.zip\n")
# checksum alterado en un archivo: el recolector no debe guardarlo
malo = os.path.join(FUENTE, simbolos[5], f"{simbolos[5]}-1d-{inicio.isoformat()}.zip.CHECKSUM")
open(malo, "w").write("0" * 64 + "\n")

py = sys.executable


def correr(*args):
    return subprocess.run([py, "-I", "-B", *args], capture_output=True, text=True)


res = {"aviso": "DATOS SINTÉTICOS; fechas ficticias (2030–2031)"}
for k in range(dias):
    d = (inicio + dt.timedelta(days=k)).isoformat()
    rr = correr(os.path.join(AQUI, "recolector.py"), "--fuente", "file://" + FUENTE, "--dia", d, "--destino", DATOS, "--protegidos", TSV)
    if rr.returncode != 0:
        res["recoleccion_error"] = rr.stderr[-500:]
        break
reg = [json.loads(x) for x in open(os.path.join(DATOS, "REGISTRO.jsonl"))]
cadena_ok = all(reg[i + 1]["prev"] == hashlib.sha256(json.dumps(reg[i], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
                for i in range(len(reg) - 1))
res["recoleccion"] = {"lineas_registro": len(reg), "cadena_ok": cadena_ok,
                      "checksum_distinto_registrado": sum(1 for x in reg if x["tipo"] == "CHECKSUM_DISTINTO"),
                      "archivo_malo_no_guardado": not os.path.exists(os.path.join(DATOS, inicio.isoformat(), simbolos[5] + ".zip"))}
# reejecutar un día no reescribe nada
rr = correr(os.path.join(AQUI, "recolector.py"), "--fuente", "file://" + FUENTE, "--dia", inicio.isoformat(), "--destino", DATOS, "--protegidos", TSV)
res["recoleccion"]["reejecucion"] = json.loads(rr.stdout)
# guarda de rutas del destino
serie_real = [l.split("\t")[1].strip() for l in open(TSV) if l.startswith("dir")][0]
rr = correr(os.path.join(AQUI, "recolector.py"), "--fuente", "file://" + FUENTE, "--dia", inicio.isoformat(), "--destino", serie_real, "--protegidos", TSV)
res["recoleccion"]["destino_protegido_rechazado"] = rr.returncode != 0 and "RutaProtegida" in rr.stderr
# prerregistro de prueba y congelación
pre = os.path.join(BASE, "PRERREGISTRO_PRUEBA.md")
open(pre, "w").write("prerregistro de prueba (sintético)\n")
cong = os.path.join(BASE, "CONGELACION_PRUEBA.txt")
open(cong, "w").write(hashlib.sha256(open(pre, "rb").read()).hexdigest() + "  PRERREGISTRO_PRUEBA.md\n")
ndias = dias - 32
comun = ["--datos", DATOS, "--t0", t0.isoformat(), "--dias", str(ndias), "--prerregistro", pre, "--congelacion", cong, "--protegidos", TSV]
ev = os.path.join(AQUI, "evaluar.py")
temprano = correr(ev, *comun, "--salida", os.path.join(BASE, "sal_temprana"), "--sintetico", "--hoy", t0.isoformat())
real_sobre_sint = correr(ev, *comun, "--salida", os.path.join(BASE, "sal_real"))
ok1 = correr(ev, *comun, "--salida", os.path.join(BASE, "sal_1"), "--sintetico", "--hoy", "2032-01-01")
segunda = correr(ev, *comun, "--salida", os.path.join(BASE, "sal_2"), "--sintetico", "--hoy", "2032-01-01")
open(pre, "a").write("cambio\n")
alterado = correr(ev, *comun, "--salida", os.path.join(BASE, "sal_3"), "--sintetico", "--hoy", "2032-01-01")
res["evaluacion"] = {
    "antes_de_tiempo_rechazada": temprano.returncode != 0 and "todavía no" in temprano.stderr,
    "modo_real_sobre_sinteticos_rechazado": real_sobre_sint.returncode != 0 and "SINTETICO" in real_sobre_sint.stderr,
    "unica_corrida": json.loads(ok1.stdout) if ok1.returncode == 0 else ok1.stderr[-400:],
    "segunda_rechazada": segunda.returncode != 0 and "una sola mirada" in segunda.stderr,
    "prerregistro_alterado_rechazado": alterado.returncode != 0 and "no coincide" in alterado.stderr}
e = res["evaluacion"]
res["ok"] = (res["recoleccion"]["cadena_ok"] and res["recoleccion"]["checksum_distinto_registrado"] == 1 and res["recoleccion"]["archivo_malo_no_guardado"]
             and res["recoleccion"]["reejecucion"]["guardado"] == 0 and res["recoleccion"]["destino_protegido_rechazado"]
             and e["antes_de_tiempo_rechazada"] and e["modo_real_sobre_sinteticos_rechazado"] and isinstance(e["unica_corrida"], dict)
             and e["unica_corrida"]["clasificacion"] == "RESPALDADA_INFORMACION" and e["segunda_rechazada"] and e["prerregistro_alterado_rechazado"])
json.dump(res, open(SAL, "w"), ensure_ascii=False, indent=1, default=str)
import shutil  # noqa: E402
shutil.rmtree(FUENTE)  # datos sintéticos de la prueba: se borran para no ocupar disco; el resultado queda en SAL
shutil.rmtree(DATOS)
print(json.dumps({"ok": res["ok"], "recoleccion": res["recoleccion"], "evaluacion": {k: (v if not isinstance(v, dict) else
      {kk: v[kk] for kk in ("clasificacion", "ic_medio", "t", "n_dias", "descarte_rapido_economico")}) for k, v in e.items()}},
                 ensure_ascii=False, default=str))
