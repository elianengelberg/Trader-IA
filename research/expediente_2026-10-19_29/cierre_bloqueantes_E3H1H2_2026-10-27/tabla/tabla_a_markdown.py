"""Genera TABLA_RENOMBRES_COMPLETA.md a partir de TABLA_RENOMBRES_COMPLETA.json (sin leer nada más).
Uso: python -I tabla_a_markdown.py <TABLA_RENOMBRES_COMPLETA.json> <clasificacion_barrido.json> <salida.md>"""
import collections
import datetime as dt
import json
import sys
from pathlib import Path

T, CL, SAL = (Path(a) for a in sys.argv[1:4])
tabla = json.loads(T.read_text())["tabla"]
clas = json.loads(CL.read_text())
A = dt.date(2023, 5, 15)
TIT = {"regla_1": "Regla 1 · renombre con cambio de símbolo (se mapea)",
       "regla_1_reutilizacion": "Regla 1, última oración · ticker reutilizado (el tramo nuevo es otro listado)",
       "regla_2": "Regla 2 · redenominación con el mismo símbolo (se mapea)",
       "D1_sin_continuidad_lectura_literal": "Decisión D-1 · la regla 1 no resuelve el caso (NO se mapea con la lectura literal)",
       "bifurcacion_un_X_dos_Y": "Anunciado, fuera de la regla 1 · bifurcación",
       "fusion_en_par_existente": "Anunciado, fuera de la regla 1 · fusión en un par que ya cotizaba",
       "conversion_con_solapamiento": "Anunciado, fuera de la regla 1 · conversión con solapamiento",
       "regla_3_sin_anuncio_archivado": "Regla 3 · cambio de símbolo SIN anuncio archivado (limitación)",
       "regla_3_corte_sin_anuncio": "Regla 3 · corte con reanudación SIN anuncio de canje (mismo listado)"}


def num(r):
    if r is None:
        return "—"
    return f"{r:g}" if r >= 1e-3 else f"1/{round(1 / r):,}".replace(",", ".")


def efecto(t):
    c = t.get("chequeo_actividad") or {}
    if t["tratamiento"] == "regla_1" and c.get("nuevo_con_menos_de_180_dias_en_A"):
        return "**Dentro de A** (edad del nuevo)" if t["origen"] != "tabla_22_reparacion" else "Dentro de A (ya en la tabla de 22)"
    if t["viejo_usdt"] == "GTOUSDT":
        return "**Dentro de A** solo con la opción (b)"
    if any(t["viejo_usdt"].endswith(s + "USDT") for s in ("UP", "DOWN", "BULL", "BEAR")):
        return "Ninguno (apalancado, §4.5)"
    return "Ninguno en A"


def act(t):
    c = t.get("chequeo_actividad") or {}
    if "ultimo_activo_viejo" in c:
        return f"{c['ultimo_activo_viejo']} → {c['primer_activo_nuevo']} (hueco {c['hueco_dias']} d)"
    if c.get("corte"):
        return f"corte {c['corte'][0]} → {c['corte'][1]}"
    if t.get("corte"):
        return f"corte {t['corte'][0]} → {t['corte'][1]}"
    return "—"


grupos = collections.OrderedDict((k, []) for k in TIT)
for t in sorted(tabla, key=lambda t: t["id"]):
    grupos[t["tratamiento"]].append(t)
L = ["# Tabla completa de renombres y redenominaciones (Adenda 1)", "",
     "Generada por `tabla_a_markdown.py` desde `TABLA_RENOMBRES_COMPLETA.json`, que generó y verificó `construir_tabla.py`:",
     "- cada cita es una subcadena del texto archivado del archivo citado;",
     "- la actividad sale de episodios y cortes, sin ningún precio ni volumen.",
     "",
     "**Convenciones:**",
     "- r = unidades nuevas por unidad vieja;",
     "- E = día UTC en que cesa la negociación spot del par viejo, según el texto (N5);",
     "- la apertura es la que dice el texto; la actividad es la de Vision.",
     "",
     f"**Resumen:** {len(tabla)} entradas.",
     "- se aplican **50** mapeos (23 de regla 1, 1 de regla 1R y 26 de regla 2);",
     "- 3 quedan para la decisión D-1;",
     "- 4 son anuncios fuera de la regla;",
     "- 19 son casos de la regla 3;",
     "- los 117 pares del barrido por cuerpo están clasificados en `clasificacion_barrido.json`.", ""]
for k, filas in grupos.items():
    if not filas:
        continue
    L += [f"## {TIT[k]} ({len(filas)})", "",
          "| Id | Viejo → nuevo | r | E | Apertura (texto) | Actividad (último viejo → primer nuevo) | Evidencia archivada (cita verificada) | Certeza | Efecto en A |",
          "|---|---|---|---|---|---|---|---|---|"]
    for t in filas:
        ev = t["evidencia"][0] if t["evidencia"] else None
        cita = (f"`{ev['archivo'][:46]}…` ({ev['captura'][:8]}): «{ev['cita'][:150]}{'…' if len(ev['cita']) > 150 else ''}»"
                + (f" (+{len(t['evidencia']) - 1} citas)" if len(t["evidencia"]) > 1 else "")) if ev else "— (sin cuerpo archivado)"
        ok = "" if all(e["cita_en_pagina"] for e in t["evidencia"]) else " **CITA NO VERIFICADA**"
        L.append(f"| {t['id']} | {t['viejo_usdt']} → {t['nuevo_usdt'] or '(listado nuevo)'} | {num(t['r'])} | {t.get('E') or t.get('reutilizacion_desde') or '—'} "
                 f"| {t.get('apertura_texto') or '—'} | {act(t)} | {cita}{ok} | {t.get('certeza') or '—'} | {efecto(t)} |")
    notas = [t for t in filas if t.get("nota") and not t["viejo_usdt"].endswith(("UPUSDT", "DOWNUSDT"))]
    if notas:
        L += ["", "**Notas:**"] + [f"- **{t['id']} {t['viejo_usdt']} → {t['nuevo_usdt'] or '—'}:** {t['nota']}" for t in notas]
    L.append("")
cuenta = collections.Counter(c["clase"].split(":")[0] for c in clas)
L += ["## Clasificación de los 117 pares del barrido por cuerpo", "", "| Clase | Pares |", "|---|---|"]
L += [f"| {k} | {v} |" for k, v in cuenta.most_common()]
SAL.write_text("\n".join(L) + "\n")
print("filas:", len(tabla), "· escrito", SAL)
