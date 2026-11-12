"""Análisis de R19 con los criterios de PLAN_R19 + enmienda 1, fijados ANTES de correr. Solo lee <salida>.
Uso: python r19_analisis.py <salida> <resultados.json>

Clasificación de cada prueba que falla en una corrida (con la evidencia de la sonda v2):
  trabada                      «persistence writes still in flight» y la cola NO AVANZA: quedan escrituras de la foto y
                               ninguna terminó en la ventana final de EXTRA2 s con el bucle de fondo detenido      -> H-SINC
  error_escritura_no_inyectada una excepción de escritura que no es la que inyecta la prueba                       -> H-SINC
  lenta_con_productor          venció el plazo con el bucle de fondo vivo y girando, y la cola siguió avanzando    -> H-ENT
  lenta_sin_productor          venció el plazo sin bucle de fondo vivo (aparcado o ya detenido), la cola avanzó    -> Inconcluso
  (Una cola que avanza pero no termina todo en EXTRA + EXTRA2 s es lenta, no trabada: se informa el remanente y la
  fracción de escrituras del propio bucle —reconciliaciones— en la foto.)
  otra_falla                   cualquier otra cosa. NO se atribuye a R19
Decisión (sobre las corridas de la prueba sola; las del módulo se informan aparte y sus señales H-SINC también cuentan):
  H-SINC        si hay alguna «trabada», algún error de escritura no inyectado (en cualquier corrida) o un error de FK en
                los registros.
  NO REPRODUCIDO si no hay ninguna falla de las clases lenta_* en la prueba sola.
  H-ENT         si (a) todas las fallas lenta_* son lenta_con_productor y ocurren con el bucle activo; (b) por carga, con el bucle activo y los dos árboles juntos, fallas(K0) <= fallas(K4) <= fallas(K8)
                y fallas(K8) > fallas(K0); (d) con el bucle aparcado, 0 fallas lenta_* en las 3 cargas.
  INCONCLUSO    en cualquier otro caso (por ejemplo, fallas aparcadas que drenan, o una tasa que no crece con K).
Medida continua (descriptiva, no decide): duración del vaciado afirmado por settle() con el bucle vivo, por celda."""
import json
import math
import pathlib
import re
import statistics
import sys

d = pathlib.Path(sys.argv[1])
FK = re.compile(r"FOREIGN KEY|IntegrityError|ForeignKeyViolation", re.I)
MSG = "persistence writes still in flight"
filas = [json.loads(x) for x in open(d / "corridas.jsonl")]


def clasificar(prueba, info, flushes, errores):
    texto = " ".join(info.get("mensajes", [])) + " ".join(info.get("informes", []))
    propias = [f for f in flushes if f.get("prueba") == prueba]
    afirmados = [f for f in propias if f.get("llamador") == "settle" and not f.get("ok")]
    if any(not e["inyectada"] for e in errores if e.get("prueba") == prueba):
        return "error_escritura_no_inyectada", None
    if MSG in texto and afirmados:
        f = afirmados[-1]
        if f.get("no_terminaron_sin_productor", 0) > 0 and f.get("terminaron_sin_productor", 0) == 0:
            return "trabada", f
        if f.get("bucle_vivo") and f.get("ciclos_fondo_durante", 0) > 0:
            return "lenta_con_productor", f
        return "lenta_sin_productor", f
    return "otra_falla", (afirmados[-1] if afirmados else None)


def fisher_dos_colas(a, b, c, e):
    """Prueba exacta de Fisher para [[a, b], [c, e]] (descriptiva)."""
    n, r1, c1 = a + b + c + e, a + b, a + c
    def p(x):
        return math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)
    obs = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, r1 + c1 - n), min(r1, c1) + 1) if p(x) <= obs * (1 + 1e-9)))


corridas, fk_runs, no_iny = [], [], []
for f in filas:
    jf = d / f"{f['tag']}.json"
    log = (d / f"{f['tag']}.log").read_text(errors="replace") if (d / f"{f['tag']}.log").exists() else ""
    j = json.load(open(jf)) if jf.exists() else None
    fallas = []
    if j is not None:
        for prueba, info in j["pruebas"].items():
            if info.get("resultado") in ("failed", "error"):
                clase, fl = clasificar(prueba, info, j["flushes"], j["errores_escritura"])
                foto = (fl or {}).get("foto_por_tipo", {})
                propias_bucle = sum(v for k, v in foto.items() if k in ("reconciliation", "run_heartbeat"))
                fallas.append({"prueba": prueba, "clase": clase, "mensajes": info.get("mensajes", []), "vaciado": fl,
                               "fraccion_foto_del_bucle": round(propias_bucle / sum(foto.values()), 3) if foto else None})
        no_iny += [{**e, "tag": f["tag"]} for e in j["errores_escritura"] if not e["inyectada"]]
    if FK.search(log):
        fk_runs.append(f["tag"])
    afirm_vivo = [x["seg"] for x in (j or {}).get("flushes", []) if x.get("llamador") == "settle" and x.get("bucle_vivo")]
    afirm = [x["seg"] for x in (j or {}).get("flushes", []) if x.get("llamador") == "settle"]
    corridas.append({**f, "sonda": j is not None, "exit_pytest": (j or {}).get("exit"), "fallas": fallas,
                     "ciclos_fondo": (j or {}).get("fondo"), "vaciado_settle_max_s": max(afirm, default=None),
                     "vaciado_settle_bucle_vivo_max_s": max(afirm_vivo, default=None),
                     "pendientes_max": max((x["pendientes"] for x in (j or {}).get("flushes", [])), default=None),
                     "errores_inyectados": sum(1 for e in (j or {}).get("errores_escritura", []) if e["inyectada"])})

R19 = ("lenta_con_productor", "lenta_sin_productor", "trabada")
celdas = {}
for c in corridas:
    key = f"{c['arbol']}|K{c['K']}|park{c['park']}|{c['sel']}"
    z = celdas.setdefault(key, {"corridas": 0, "sin_sonda": 0, "rc_distinto_de_0": 0, "fallas_por_clase": {}, "pruebas_que_fallan": {},
                                "vaciado_settle_s": [], "carga_con_quemadores": [], "ejecutables": [], "fraccion_cpu": []})
    z["corridas"] += 1
    z["sin_sonda"] += not c["sonda"]
    z["rc_distinto_de_0"] += c["rc"] != 0
    z["carga_con_quemadores"].append(c["carga_con_quemadores"][0])
    if c.get("ejecutables_con_quemadores") is not None:
        z["ejecutables"].append(c["ejecutables_con_quemadores"])
    if c.get("fraccion_cpu_pytest") is not None:
        z["fraccion_cpu"].append(c["fraccion_cpu_pytest"])
    if c["vaciado_settle_max_s"] is not None:
        z["vaciado_settle_s"].append(c["vaciado_settle_max_s"])
    for fa in c["fallas"]:
        z["fallas_por_clase"][fa["clase"]] = z["fallas_por_clase"].get(fa["clase"], 0) + 1
        nombre = fa["prueba"].split("::")[-1]
        z["pruebas_que_fallan"][nombre] = z["pruebas_que_fallan"].get(nombre, 0) + 1
for z in celdas.values():
    v = sorted(z.pop("vaciado_settle_s"))
    z["vaciado_settle"] = {"n": len(v), "mediana": statistics.median(v) if v else None, "max": v[-1] if v else None,
                           ">=8s": sum(1 for x in v if x >= 8.0)}
    cq = z.pop("carga_con_quemadores")
    z["carga_con_quemadores_mediana"] = statistics.median(cq) if cq else None
    ej, fc = z.pop("ejecutables"), z.pop("fraccion_cpu")
    z["ejecutables_mediana"] = statistics.median(ej) if ej else None
    z["fraccion_cpu_pytest_mediana"] = statistics.median(fc) if fc else None

sola = [c for c in corridas if c["sel"] == "prueba"]
r19_fallas = [(c, fa) for c in sola for fa in c["fallas"] if fa["clase"] in R19]
trabadas = [(c["tag"], fa["prueba"]) for c in corridas for fa in c["fallas"] if fa["clase"] == "trabada"]
por_k = {k: sum(1 for c, fa in r19_fallas if c["K"] == k and c["park"] == 0) for k in sorted({c["K"] for c in corridas})}
aparcadas = sum(1 for c, fa in r19_fallas if c["park"] == 1)
ks = sorted(por_k)
criterios = {
    "a_todas_con_bucle_activo": all(c["park"] == 0 and fa["clase"] == "lenta_con_productor" for c, fa in r19_fallas),
    "b_tasa_crece_con_K": all(por_k[ks[i]] <= por_k[ks[i + 1]] for i in range(len(ks) - 1)) and por_k[ks[-1]] > por_k[ks[0]],
    "c_ninguna_trabada": not trabadas,
    "d_aparcado_sin_fallas": aparcadas == 0,
}
if trabadas or no_iny or fk_runs:
    decision = "H-SINC"
elif not r19_fallas:
    decision = "NO REPRODUCIDO"
elif all(criterios.values()):
    decision = "H-ENT"
else:
    decision = "INCONCLUSO"

def cuenta(arbol):
    xs = [c for c in sola if c["arbol"] == arbol and c["park"] == 0]
    f = sum(1 for c in xs if any(fa["clase"] in R19 for fa in c["fallas"]))
    return f, len(xs) - f
arboles = sorted({c["arbol"] for c in corridas})
comparacion = None
if len(arboles) == 2:
    (a, b), (c_, e) = cuenta(arboles[0]), cuenta(arboles[1])
    comparacion = {"arboles": arboles, "corridas_con_falla_R19_bucle_activo": [a, c_], "sin_falla": [b, e],
                   "fisher_dos_colas_p": fisher_dos_colas(a, b, c_, e)}

res = {"decision": decision, "criterios_H_ENT": criterios, "fallas_R19_por_K_bucle_activo": por_k,
       "fallas_R19_aparcado": aparcadas, "trabadas": trabadas, "errores_escritura_no_inyectados": no_iny[:50],
       "corridas_con_FK_en_registro": fk_runs, "otras_fallas": [(c["tag"], fa["prueba"], fa["mensajes"][:1]) for c in corridas
                                                                for fa in c["fallas"] if fa["clase"] == "otra_falla"],
       "comparacion_cand_base": comparacion, "celdas": celdas, "corridas": corridas}
json.dump(res, open(sys.argv[2], "w"), indent=1, default=str)
print("decisión:", decision)
print("criterios H-ENT:", criterios)
print("fallas R19 con bucle activo por K:", por_k, "· aparcadas:", aparcadas, "· trabadas:", len(trabadas),
      "· errores no inyectados:", len(no_iny), "· FK:", len(fk_runs))
for k, z in sorted(celdas.items()):
    print(f"{k:40s} n={z['corridas']:3d} rc!=0={z['rc_distinto_de_0']:2d} sin_sonda={z['sin_sonda']} fallas={z['fallas_por_clase']} "
          f"vaciado_med={z['vaciado_settle']['mediana']} max={z['vaciado_settle']['max']} >=8s={z['vaciado_settle']['>=8s']} "
          f"ejecutables_med={z['ejecutables_mediana']} cpu_pytest_med={z['fraccion_cpu_pytest_mediana']}")
if comparacion:
    print("cand vs base (bucle activo, prueba sola):", comparacion)
