"""Regla de validez del instrumento, prerregistrada en registro/B1 (solo lee la salida de la corrida principal):
(i) más del 5 % de las corridas sin JSON de la sonda o terminadas por límite de tiempo;
(ii) alguna falla con «persistence writes still in flight» sin el registro del vaciado de esa prueba;
(iii) alguna traza que mencione la sonda (sonda_r19_v2) en cualquier registro.
Uso: python validez_instrumento_r19.py <salida> <reporte.json>"""
import json
import pathlib
import sys

d = pathlib.Path(sys.argv[1])
filas = [json.loads(x) for x in open(d / "corridas.jsonl")]
sin_json = [f["tag"] for f in filas if not (d / f"{f['tag']}.json").exists()]
limite = [f["tag"] for f in filas if f["rc"] == "limite"]
no_capturadas, trazas_sonda, rc_inesperado = [], [], []
for f in filas:
    log = (d / f"{f['tag']}.log").read_text(errors="replace") if (d / f"{f['tag']}.log").exists() else ""
    if "Traceback" in log and "sonda_r19_v2" in log:
        trazas_sonda.append(f["tag"])
    if f["rc"] not in (0, 1, "limite"):
        rc_inesperado.append((f["tag"], f["rc"]))
    jf = d / f"{f['tag']}.json"
    if not jf.exists():
        continue
    j = json.load(open(jf))
    for prueba, info in j["pruebas"].items():
        texto = " ".join(info.get("mensajes", [])) + " ".join(info.get("informes", []))
        if "persistence writes still in flight" in texto:
            if not any(x.get("prueba") == prueba and x.get("llamador") == "settle" and not x.get("ok") for x in j["flushes"]):
                no_capturadas.append((f["tag"], prueba))
    if j.get("exit") != f["rc"] and f["rc"] != "limite":
        rc_inesperado.append((f["tag"], f"pytest exit {j.get('exit')} frente a rc {f['rc']}"))
n = len(filas)
fraccion = (len(set(sin_json) | set(limite)) / n) if n else 1.0
invalido = fraccion > 0.05 or bool(no_capturadas) or bool(trazas_sonda)
rep = {"corridas": n, "sin_json": sin_json, "por_limite": limite, "fraccion_i": round(fraccion, 4), "ii_fallas_no_capturadas": no_capturadas,
       "iii_trazas_de_la_sonda": trazas_sonda, "codigos_inesperados": rc_inesperado, "INSTRUMENTO_INVALIDO": invalido}
json.dump(rep, open(sys.argv[2], "w"), indent=1)
print(json.dumps(rep, indent=1))
