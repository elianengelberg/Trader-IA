"""E4 · Evaluación ÚNICA (una sola mirada, cero reintentos). Requiere autorización. No corre antes de tiempo ni dos veces.
Guardas:
  - el prerregistro tiene que coincidir byte a byte con el sha256 de CONGELACION_E4.txt;
  - en modo real, hoy ≥ T0 + DIAS + 3 (rezago de publicación) y la carpeta de datos NO tiene la marca SINTETICO.txt;
  - en modo --sintetico (solo pruebas), la carpeta TIENE que tener SINTETICO.txt y el resultado se rotula como sintético;
  - la carpeta de salida no puede existir (se crea con mkdir exclusivo) y el registro de datos no puede tener una EVALUACION previa;
  - guarda de rutas sobre datos y salida.
Uso: python -I -B evaluar.py --datos <dir> --t0 YYYY-MM-DD --dias 365 --prerregistro <md> --congelacion <txt>
       --salida <dir_nuevo> --protegidos <PROTEGIDOS.tsv> [--sintetico --hoy YYYY-MM-DD]"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda_rutas as G  # noqa: E402
import nucleo as N  # noqa: E402
from recolector import anexar  # noqa: E402

REZAGO = 3


def leer_zip(p):
    with zipfile.ZipFile(p) as z:
        fila = next(csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), "ascii")))
    try:
        float(fila[0])
    except ValueError:
        raise SystemExit(f"encabezado inesperado en {p}")
    return float(fila[4]), float(fila[7]), float(fila[8])  # cierre, volumen en USDT, operaciones


def main():
    a = argparse.ArgumentParser()
    for k in ("datos", "t0", "prerregistro", "congelacion", "salida", "protegidos"):
        a.add_argument("--" + k, required=True)
    a.add_argument("--dias", type=int, required=True)
    a.add_argument("--sintetico", action="store_true")
    a.add_argument("--hoy")
    x = a.parse_args()
    prot = G.cargar_protegidos(x.protegidos)
    G.verificar(x.datos, prot)
    G.verificar(os.path.dirname(os.path.abspath(x.salida)), prot)
    congelado = open(x.congelacion).read().split()[0]
    if hashlib.sha256(open(x.prerregistro, "rb").read()).hexdigest() != congelado:
        raise SystemExit("el prerregistro no coincide con su congelación: no se evalúa")
    marca = os.path.exists(os.path.join(x.datos, "SINTETICO.txt"))
    if x.sintetico != marca:
        raise SystemExit("modo y marca SINTETICO.txt no coinciden: no se evalúa")
    if x.hoy and not x.sintetico:
        raise SystemExit("--hoy solo se admite en modo sintético")
    t0 = dt.date.fromisoformat(x.t0)
    hoy = dt.date.fromisoformat(x.hoy) if x.hoy else dt.datetime.now(dt.timezone.utc).date()
    if hoy < t0 + dt.timedelta(days=x.dias + REZAGO):
        raise SystemExit(f"todavía no: la evaluación única es a partir de {t0 + dt.timedelta(days=x.dias + REZAGO)}")
    reg = os.path.join(x.datos, "REGISTRO.jsonl")
    if os.path.exists(reg) and any(json.loads(l).get("tipo") == "EVALUACION" for l in open(reg)):
        raise SystemExit("ya hubo una evaluación: E4 tiene una sola mirada")
    os.mkdir(x.salida)  # falla si existe
    inicio = t0 - dt.timedelta(days=N.VENTANA + 1)
    fechas = [inicio + dt.timedelta(days=i) for i in range((t0 - inicio).days + x.dias + 1)]
    simbolos = sorted({f[:-4] for d in fechas if os.path.isdir(os.path.join(x.datos, d.isoformat()))
                       for f in os.listdir(os.path.join(x.datos, d.isoformat())) if f.endswith(".zip")})
    cierre = {s: np.zeros(len(fechas)) for s in simbolos}
    volq = {s: np.zeros(len(fechas)) for s in simbolos}
    ops = {s: np.zeros(len(fechas)) for s in simbolos}
    for i, d in enumerate(fechas):
        for s in simbolos:
            p = os.path.join(x.datos, d.isoformat(), s + ".zip")
            if os.path.exists(p):
                cierre[s][i], volq[s][i], ops[s][i] = leer_zip(p)
    datos = N.Datos(cierre, volq, ops)
    k0 = (t0 - inicio).days
    dias = [N.dia(datos, t) for t in range(k0, k0 + x.dias) if t + 1 < len(fechas)]
    res = {"experimento": "E4 H-XS-REV-1 prospectivo", "sintetico": x.sintetico, "t0": x.t0, "dias_pedidos": x.dias,
           "prerregistro_sha256": congelado, **N.evaluar(dias)}
    # Sensibilidad de costos declarada en el prerregistro §7 (no cambia la clasificación de información)
    res["sensibilidad_costos"] = {f"medio_spread_{b}bps": {k: N.evaluar(dias, medio_spread_bps=b).get(k) for k in
                                  ("costo_diario_medio", "descarte_rapido_economico", "neto_diario_medio", "t_neto")} for b in (10.0, 20.0)}
    p = os.path.join(x.salida, "RESULTADO_E4.json")
    with open(p, "x") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=float)
        f.flush()
        os.fsync(f.fileno())
    anexar(reg, {"tipo": "EVALUACION", "utc": dt.datetime.now(dt.timezone.utc).isoformat(), "sintetico": x.sintetico,
                 "resultado_sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "clasificacion": res["clasificacion"]})
    print(json.dumps({k: res[k] for k in res if k not in ("nota",)}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
