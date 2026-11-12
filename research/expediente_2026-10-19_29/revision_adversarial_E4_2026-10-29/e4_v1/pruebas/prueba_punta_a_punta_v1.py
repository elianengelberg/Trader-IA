"""E4 v1 · Prueba de punta a punta con fuente LOCAL SINTÉTICA (file://), sin red, en /dev/shm (memoria). Datos SINTÉTICOS en
formato Binance Vision (1d y 1h, marcas en µs, algún encabezado) con fechas ficticias (2030–2031); la carpeta lleva SINTETICO.txt.
El efecto de reversión se planta recién desde el día 60 después de T0: la mirada 1 (60 días de prueba) no debe cortar y la
mirada 2 (120 días) debe detectarlo. Comprueba recolección, manifiestos, errores, rechazos del evaluador y las dos miradas.
Uso: python -I -B prueba_punta_a_punta_v1.py <PROTEGIDOS.tsv> <salida.json>"""
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
COD = os.path.join(os.path.dirname(AQUI), "codigo")
TSV, SAL = sys.argv[1:3]
BASE = tempfile.mkdtemp(prefix="e4v1_", dir="/dev/shm")
FUENTE, DATOS = os.path.join(BASE, "fuente"), os.path.join(BASE, "datos")
os.makedirs(FUENTE)
os.makedirs(DATOS)
open(os.path.join(DATOS, "SINTETICO.txt"), "w").write("Datos SINTÉTICOS de prueba_punta_a_punta_v1.py; no son históricos.\n")
py = sys.executable


def h(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def correr(*a):
    return subprocess.run([py, "-I", "-B", *a], capture_output=True, text=True)


# --- datos sintéticos -------------------------------------------------------------------------------------------------
rng = np.random.default_rng(20261029)
t0 = dt.date(2031, 1, 1)
M1, M2, K = 60, 120, 0.3
inicio = t0 - dt.timedelta(days=31)
ndias = 31 + M2 + 1
simbolos = [f"S{i:02d}USDT" for i in range(36)] + ["PEGUSDUSDT", "WBTCUSDT"]
json.dump(simbolos, open(os.path.join(FUENTE, "LISTADO.json"), "w"))


def us(d, hora=0):
    return int(dt.datetime.combine(d, dt.time(hora), dt.timezone.utc).timestamp() * 1_000_000)


def escribir(s, iv, d, filas, encabezado=False, crudo=None):
    carpeta = os.path.join(FUENTE, s, iv)
    os.makedirs(carpeta, exist_ok=True)
    if crudo is None:
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            txt = ("open_time,open,high,low,close,volume,close_time,quote_volume,count,tbb,tbq,ignore\n" if encabezado else "")
            z.writestr(f"{s}-{iv}-{d}.csv", txt + "".join(",".join(map(str, f)) + "\n" for f in filas))
        crudo = b.getvalue()
    p = os.path.join(carpeta, f"{s}-{iv}-{d}.zip")
    open(p, "wb").write(crudo)
    open(p + ".CHECKSUM", "w").write(f"{hashlib.sha256(crudo).hexdigest()}  {s}-{iv}-{d}.zip\n")


for j, s in enumerate(simbolos):
    hq, gq = rng.standard_normal(ndias) * 0.01, rng.standard_normal(ndias) * 0.04
    cierre, entrada = np.empty(ndias), np.empty(ndias)
    prev, r_prev = 100.0, 0.0
    for i in range(ndias):
        if i >= 31 + M1:  # efecto plantado: el día t (desde las 01:00) revierte el retorno del día t−1
            gq[i] += -K * r_prev
        entrada[i] = prev * np.exp(hq[i])
        cierre[i] = entrada[i] * np.exp(gq[i])
        r_prev = cierre[i] / prev - 1
        prev = cierre[i]
    if s == "PEGUSDUSDT":
        cierre = 1 + rng.standard_normal(ndias) * 0.0005
        entrada = cierre.copy()
    vol = 5e9 if s == "PEGUSDUSDT" else 1e6 * (1 + j)
    for i in range(ndias):
        d = inicio + dt.timedelta(days=i)
        escribir(s, "1d", d.isoformat(), [[us(d), 1, 1, 1, f"{cierre[i]:.10f}", 1, us(d) + 86399999999, vol, 500, 0, 0, 0]])
        horas = [[us(d, hh), 1, 1, 1, f"{(entrada[i] if hh == 0 else cierre[i]):.10f}", 1, us(d, hh) + 3599999999, 1, 1, 0, 0, 0]
                 for hh in range(24)]
        escribir(s, "1h", d.isoformat(), horas, encabezado=(s == "S03USDT"))
# un checksum alterado (no debe guardarse) y un archivo ilegible con checksum correcto (par-día faltante, contado)
d_malo = (t0 + dt.timedelta(days=10)).isoformat()
malo = os.path.join(FUENTE, "S05USDT", "1d", f"S05USDT-1d-{d_malo}.zip.CHECKSUM")
bueno_chk = open(malo).read()
open(malo, "w").write("0" * 64 + "\n")
escribir("S07USDT", "1h", (t0 + dt.timedelta(days=20)).isoformat(), None, crudo=b"esto no es un zip")

res = {"aviso": "DATOS SINTÉTICOS en /dev/shm; fechas ficticias (2030–2031)"}
rec = os.path.join(COD, "recolector.py")
fin = (t0 + dt.timedelta(days=M2)).isoformat()
r = correr(rec, "--fuente", "file://" + FUENTE, "--desde", inicio.isoformat(), "--hasta", fin, "--destino", DATOS, "--protegidos", TSV)
reg = [json.loads(x) for x in open(os.path.join(DATOS, "REGISTRO.jsonl"))]
cadena = all(reg[i + 1]["prev"] == hashlib.sha256(json.dumps(reg[i], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
             for i in range(len(reg) - 1))
res["recoleccion"] = {"rc": r.returncode, "salida": r.stdout.strip()[:200], "cadena_ok": cadena,
                      "dias_registrados": sum(1 for x in reg if x["tipo"] == "RECOLECCION"),
                      "checksum_distinto": sum(x.get("checksum_distinto", 0) for x in reg if x["tipo"] == "RECOLECCION"),
                      "malo_no_guardado": not os.path.exists(os.path.join(DATOS, d_malo, "1d", "S05USDT.zip"))}
r = correr(rec, "--fuente", "file://" + FUENTE, "--desde", inicio.isoformat(), "--hasta", inicio.isoformat(), "--destino", DATOS, "--protegidos", TSV)
res["recoleccion"]["reejecucion_sin_reescritura"] = r.returncode == 0 and json.loads(r.stdout)["guardados"] == 0
serie_real = [l.split("\t")[1].strip() for l in open(TSV) if l.startswith("dir")][0]
r = correr(rec, "--fuente", "file://" + FUENTE, "--desde", inicio.isoformat(), "--hasta", inicio.isoformat(), "--destino", serie_real, "--protegidos", TSV)
res["recoleccion"]["destino_protegido_rechazado"] = r.returncode != 0 and "RutaProtegida" in r.stderr

# --- congelación e inicio de prueba -------------------------------------------------------------------------------------
pre = os.path.join(BASE, "PRERREGISTRO_PRUEBA.md")
open(pre, "w").write("prerregistro de prueba (sintético)\n")
pys = sorted(f for f in os.listdir(COD) if f.endswith(".py"))
cong = os.path.join(BASE, "CONGELACION_PRUEBA.txt")
open(cong, "w").write(f"{h(pre)}  PRERREGISTRO_PRUEBA.md\n" + "".join(f"{h(os.path.join(COD, f))}  codigo/{f}\n" for f in pys))
ini = os.path.join(BASE, "INICIO_PRUEBA.json")
json.dump({"congelacion_sha256": h(cong), "ancla": {"tipo": "prueba", "bloque_utc": "2030-12-31T18:00:00Z"}, "t0": t0.isoformat()}, open(ini, "w"))
ev = os.path.join(COD, "evaluar.py")


def evaluar(mirada, salida, *extra, cong_=cong, ini_=ini, ini_sha=None, sint=True, hoy="2031-12-31"):
    a = [ev, "--datos", DATOS, "--congelacion", cong_, "--inicio", ini_, "--inicio-sha256", ini_sha or h(ini_), "--mirada", str(mirada),
         "--salida", os.path.join(BASE, salida), "--protegidos", TSV, *extra]
    if sint:
        a += ["--sintetico", "--hoy", hoy, "--miradas-prueba", f"{M1},{M2}"]
    return correr(*a)


def rechazo(r, texto):
    return r.returncode != 0 and texto in r.stderr


cong_mala = os.path.join(BASE, "CONGELACION_MALA.txt")
L = open(cong).read().splitlines()
open(cong_mala, "w").write("\n".join([L[0], "0" * 64 + L[1][64:]] + L[2:]) + "\n")
ini2 = os.path.join(BASE, "INICIO_T0_CORRIDO.json")
json.dump({"congelacion_sha256": h(cong), "ancla": {"tipo": "prueba", "bloque_utc": "2030-12-31T18:00:00Z"}, "t0": "2031-01-02"}, open(ini2, "w"))
e = {}
e["congelacion_alterada"] = rechazo(evaluar(1, "x1", cong_=cong_mala), "CONGELACION no coincide")
e["inicio_no_anclado"] = rechazo(evaluar(1, "x2", ini_sha="f" * 64), "no es el anclado")
e["t0_corrido"] = rechazo(evaluar(1, "x3", ini_=ini2), "T0 no es el día UTC siguiente")
e["antes_de_tiempo"] = rechazo(evaluar(1, "x4", hoy="2031-03-01"), "todavía no")
e["modo_real_sobre_sinteticos"] = rechazo(evaluar(1, "x5", sint=False), "SINTETICO")
e["mirada2_antes_que_1"] = rechazo(evaluar(2, "x6"), "exige la mirada 1")
zz = os.path.join(DATOS, (t0 + dt.timedelta(days=5)).isoformat(), "1d", "S01USDT.zip")
orig = open(zz, "rb").read()
open(zz, "wb").write(orig[:-1] + bytes([orig[-1] ^ 1]))
e["zip_alterado"] = rechazo(evaluar(1, "x7"), "cambió después de la recolección")
open(zz, "wb").write(orig)
extra = os.path.join(DATOS, (t0 + dt.timedelta(days=6)).isoformat(), "1d", "INTRUSOUSDT.zip")
shutil.copy(zz, extra)
e["zip_fuera_del_manifiesto"] = rechazo(evaluar(1, "x8"), "fuera del manifiesto")
os.unlink(extra)
# día con error de recolección: el par del checksum alterado, ahora sin .CHECKSUM en la fuente → error → el evaluador lo rechaza
os.unlink(malo)
r = correr(rec, "--fuente", "file://" + FUENTE, "--desde", d_malo, "--hasta", d_malo, "--destino", DATOS, "--protegidos", TSV)
e["recolector_error_codigo_2"] = r.returncode == 2
e["dia_con_errores_rechazado"] = rechazo(evaluar(1, "x9"), "con errores")
open(malo, "w").write(bueno_chk)  # se corrige la fuente y se vuelve a recolectar ese día
r = correr(rec, "--fuente", "file://" + FUENTE, "--desde", d_malo, "--hasta", d_malo, "--destino", DATOS, "--protegidos", TSV)
e["rerecoleccion_ok"] = r.returncode == 0 and json.loads(r.stdout)["guardados"] == 1
v = evaluar(1, "x10", "--solo-validar")
e["solo_validar"] = json.loads(v.stdout) if v.returncode == 0 else v.stderr[-300:]
r1 = evaluar(1, "sal_m1")
e["mirada1"] = json.loads(r1.stdout) if r1.returncode == 0 else r1.stderr[-400:]
e["mirada1_sin_estadisticos"] = isinstance(e["mirada1"], dict) and not ({"ic_medio", "t", "ee_nw"} & set(e["mirada1"]))
e["mirada1_repetida"] = rechazo(evaluar(1, "x11"), "ya se hizo")
r2 = evaluar(2, "sal_m2", hoy="2032-01-01")
m2 = json.loads(r2.stdout) if r2.returncode == 0 else r2.stderr[-400:]
e["mirada2"] = {k: m2[k] for k in ("decision", "clasificacion", "ic_medio", "t", "limite", "n_dias", "salidas_totales", "lectura")} if isinstance(m2, dict) else m2
e["mirada2_repetida"] = rechazo(evaluar(2, "x12", hoy="2032-01-01"), "ya se hizo")
res["evaluador"] = e
reg = [json.loads(x) for x in open(os.path.join(DATOS, "REGISTRO.jsonl"))]
res["registro_evaluaciones"] = [{k: x.get(k) for k in ("mirada", "decision", "clasificacion", "n_evaluables")} for x in reg if x["tipo"] == "EVALUACION"]
R = res["recoleccion"]
res["ok"] = bool(R["rc"] == 0 and R["cadena_ok"] and R["checksum_distinto"] == 1 and R["malo_no_guardado"] and R["reejecucion_sin_reescritura"]
                 and R["destino_protegido_rechazado"] and all(e[k] for k in ("congelacion_alterada", "inicio_no_anclado", "t0_corrido",
                 "antes_de_tiempo", "modo_real_sobre_sinteticos", "mirada2_antes_que_1", "zip_alterado", "zip_fuera_del_manifiesto",
                 "recolector_error_codigo_2", "dia_con_errores_rechazado", "rerecoleccion_ok", "mirada1_sin_estadisticos",
                 "mirada1_repetida", "mirada2_repetida"))
                 and isinstance(e["solo_validar"], dict) and e["solo_validar"]["validacion"] == "OK" and e["solo_validar"]["ilegibles"] == 1
                 and e["mirada1"]["decision"] == "CONTINUAR" and isinstance(m2, dict) and m2["clasificacion"] == "RESPALDADA_INFORMACION")
json.dump(res, open(SAL, "w"), ensure_ascii=False, indent=1, default=str)
shutil.rmtree(BASE)  # datos sintéticos en memoria: se borran; el resultado queda en SAL
print(json.dumps({"ok": res["ok"], "recoleccion": R, "mirada1": e["mirada1"], "mirada2": e["mirada2"]}, ensure_ascii=False, default=str))
