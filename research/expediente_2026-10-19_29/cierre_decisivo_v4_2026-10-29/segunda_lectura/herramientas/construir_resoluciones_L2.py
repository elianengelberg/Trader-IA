"""Segunda lectura (protocolo SL-v1, §5–§6) · convierte la lectura ciega en resoluciones, con reglas fijas, y la compara con
la segunda pasada de la reparación.

Reglas de conversión (SL-v1 §5), aplicadas a cada ítem con su clave de la primera pasada (par, E1) y su categoría cat1:
  - accion_par ∈ {REMUEVE, EXCLUYE_TOKEN} y E_N5 definida:  E_N5 == E1 → «confirmar»;  E_N5 ≠ E1 → «fecha_corregida» con E = E_N5.
    Excepción A3.5 (b): si cat1 == C_no_explicada y el lector documenta reapertura o postergación/cancelación → «C_explicada».
  - accion_par ∈ {AGREGA, CANCELADA}: cat1 == C_no_explicada → «C_explicada»; si no → «descartar».
  - accion_par == CORRIGE_PAR → «descartar».
  - cualquier otro caso (NO_MENCIONA, OTRA, o E_N5 nula con REMUEVE/EXCLUYE_TOKEN) → NO_DETERMINABLE (va a adjudicación).
Comparación: concordante si la acción y, cuando corresponde, la E coinciden con las de la segunda pasada; si no, discrepante.
Adjudicación (opcional, archivo de la §6): {clave: {"eleccion": "X"|"Y"|"NO_DETERMINABLE", ...}} con X/Y según `orden`.
Las secciones sin_fecha, tokens_sin_par, renombres y vs2 se copian sin cambios de la segunda pasada (fuera del alcance).
Uso: python3 -I -B construir_resoluciones_L2.py <eventos_pasada1.json> <resoluciones_pasada2.json> <mapa_items.json>
       <lectura_L2.json> <adjudicacion.json|-> <dir_salida>"""
import json
import sys
from pathlib import Path

EV1, RES2, MAPA, LECT, ADJ, OUT = (Path(a) for a in sys.argv[1:7])
ev1 = {e["clave"]: e for e in json.loads(EV1.read_text())}
res2 = json.loads(RES2.read_text())
mapa = json.loads(MAPA.read_text())
lect = {x["id"]: x for x in json.loads(LECT.read_text())["items"]}
adj = json.loads(ADJ.read_text()) if str(ADJ) != "-" else {}
assert set(lect) == set(mapa), "la lectura no cubre exactamente los 47 ítems"


def convertir(x, E1, cat1):
    acc, E = x.get("accion_par"), x.get("E_N5")
    expl = bool((x.get("reapertura") or {}).get("hay")) or bool((x.get("postergacion_cancelacion_correccion") or {}).get("hay"))
    if acc in ("REMUEVE", "EXCLUYE_TOKEN") and E:
        if cat1 == "C_no_explicada" and expl:
            return {"accion": "C_explicada"}
        return {"accion": "confirmar"} if E == E1 else {"accion": "fecha_corregida", "E": E}
    if acc in ("AGREGA", "CANCELADA"):
        return {"accion": "C_explicada"} if cat1 == "C_no_explicada" else {"accion": "descartar"}
    if acc == "CORRIGE_PAR":
        return {"accion": "descartar"}
    return {"accion": "NO_DETERMINABLE"}


def igual(a, b):
    return a["accion"] == b["accion"] and (a["accion"] != "fecha_corregida" or a.get("E") == b.get("E"))


comparacion, eventos_L2, vs3_L2, pendientes = [], {}, {}, []
for iid, m in sorted(mapa.items()):
    clave, x = m["clave"], lect[iid]
    E1, cat1 = clave.split("|")[1], ev1[clave]["categoria"]
    l2 = convertir(x, E1, cat1)
    p2 = {k: v for k, v in res2["eventos"][clave].items() if k in ("accion", "E")}
    fila = {"id": iid, "clave": clave, "categoria_pasada1": cat1, "L2": l2, "pasada2": p2, "concordante": igual(l2, p2)}
    final = l2
    if not fila["concordante"]:
        a = adj.get(clave)
        if a is None:
            final = None
        else:
            orden = a["orden"]  # {"X": "L2"|"P2", "Y": "L2"|"P2"}
            eleccion = a["eleccion"]
            final = None if eleccion == "NO_DETERMINABLE" else {"L2": l2, "P2": p2}[orden[eleccion]]
            fila["adjudicacion"] = a
    if final is None or final["accion"] == "NO_DETERMINABLE":
        pendientes.append(clave)
        fila["final"] = None
    else:
        fila["final"] = final
        eventos_L2[clave] = {**final, "cita": x.get("cita_E") or x.get("cita_accion"), "fuente_paginas": m["paginas"],
                             "categoria_pasada1": cat1, "lector": "segunda lectura SL-v1", "certeza": x.get("certeza")}
        vs3_L2[clave] = {"muestra_pasada1": res2["vs3"][clave]["muestra_pasada1"], "par_ok": x.get("accion_par") != "CORRIGE_PAR",
                         "categoria_pasada1": cat1, "resultado": final["accion"], "E_texto": x.get("E_N5"), "cita": x.get("cita_E")}
    comparacion.append(fila)

OUT.mkdir(parents=True, exist_ok=True)
res_L2 = {"_nota": "Segunda lectura SL-v1 (lector ciego). Secciones fuera del alcance copiadas de la segunda pasada sin cambios.",
          "eventos": eventos_L2, "sin_fecha": res2["sin_fecha"], "tokens_sin_par": res2["tokens_sin_par"],
          "renombres": res2["renombres"], "vs2": res2["vs2"], "vs3": vs3_L2}
resumen = {"items": len(comparacion), "concordantes": sum(f["concordante"] for f in comparacion),
           "discrepantes": [f["clave"] for f in comparacion if not f["concordante"]], "pendientes_sin_resolver": pendientes}
(OUT / "comparacion_L2.json").write_text(json.dumps({"resumen": resumen, "filas": comparacion}, ensure_ascii=False, indent=1))
if not pendientes:
    (OUT / "resoluciones_L2.json").write_text(json.dumps(res_L2, ensure_ascii=False, indent=1))
print(json.dumps(resumen, ensure_ascii=False, indent=1))
