"""Validación, huella y congelamiento de un prerregistro PEC-1.0.

1. ``validar_esquema``: un validador MÍNIMO del subconjunto de JSON Schema que usa ``esquemas/prerregistro_v1.schema.json``
   (type, required, properties, additionalProperties: false, enum, minimum, maximum, minLength, minItems, maxItems,
   pattern, items). Sin dependencias externas.
2. ``validar_semantica``: lo que un esquema no expresa. ERRORES (impiden congelar) y AVISOS (se informan).
3. ``congelar`` / ``verificar_congelado``: SHA-256 de la forma canónica del contenido (sin el bloque ``congelado``).
   Congelar no publica nada: la huella solo es verificable desde fuera si se ancla fuera (03_CADENA_DE_CONFIANZA.md)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from itertools import pairwise
from pathlib import Path

ESQUEMA = json.loads((Path(__file__).resolve().parent.parent / "esquemas" / "prerregistro_v1.schema.json").read_text(
    encoding="utf-8"))
# Registro de riesgos de sesgo §4: ningún hash vuelve independiente un período ya visto.
PERIODOS_CONTAMINADOS = [
    ({"BTC", "ETH"}, "2017-08-01", "2026-05-31", "desarrollo y fuera de muestra de T, E2, H-CARRY, E1"),
    ({"*"}, "2017-01-01", "2026-05-31", "E3 vio la calidad de todos los pares USDT 1d (contaminación baja)"),
]
PERIODO_RESERVADO = ({"BTC", "ETH"}, "2026-06-01", "2026-10-13", "período reservado de H-CARRY: no se lee")
INICIO_INDEPENDIENTE = "2026-10-14"
_TIPOS = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _tipo_ok(v: object, t: str) -> bool:
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TIPOS[t])


def validar_esquema(doc: object, esquema: dict = ESQUEMA, ruta: str = "$") -> list[str]:
    errores: list[str] = []
    tipos = esquema.get("type")
    if tipos is not None:
        tipos = [tipos] if isinstance(tipos, str) else tipos
        if not any(_tipo_ok(doc, t) for t in tipos):
            return [f"{ruta}: tipo {type(doc).__name__}, se esperaba {tipos}"]
    if doc is None:
        return errores
    if "enum" in esquema and doc not in esquema["enum"]:
        errores.append(f"{ruta}: {doc!r} no está en {esquema['enum']}")
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        if "minimum" in esquema and doc < esquema["minimum"]:
            errores.append(f"{ruta}: {doc} < mínimo {esquema['minimum']}")
        if "maximum" in esquema and doc > esquema["maximum"]:
            errores.append(f"{ruta}: {doc} > máximo {esquema['maximum']}")
    if isinstance(doc, str):
        if len(doc) < esquema.get("minLength", 0):
            errores.append(f"{ruta}: texto demasiado corto")
        if "pattern" in esquema and not re.search(esquema["pattern"], doc):
            errores.append(f"{ruta}: {doc!r} no cumple {esquema['pattern']}")
    if isinstance(doc, list):
        if len(doc) < esquema.get("minItems", 0) or len(doc) > esquema.get("maxItems", 10 ** 9):
            errores.append(f"{ruta}: {len(doc)} elementos fuera de [{esquema.get('minItems', 0)}, "
                           f"{esquema.get('maxItems', '∞')}]")
        if "items" in esquema:
            for i, v in enumerate(doc):
                errores += validar_esquema(v, esquema["items"], f"{ruta}[{i}]")
    if isinstance(doc, dict):
        for k in esquema.get("required", []):
            if k not in doc:
                errores.append(f"{ruta}: falta «{k}»")
        props = esquema.get("properties", {})
        for k, v in doc.items():
            if k in props:
                errores += validar_esquema(v, props[k], f"{ruta}.{k}")
            elif esquema.get("additionalProperties") is False:
                errores.append(f"{ruta}: campo no admitido «{k}»")
    return errores


def _se_solapan(a: list[str] | None, b: tuple[str, str]) -> bool:
    return bool(a) and date.fromisoformat(a[0]) <= date.fromisoformat(b[1]) and date.fromisoformat(b[0]) <= \
        date.fromisoformat(a[1])


def _activos_afectados(universo: list[str], conjunto: set[str]) -> bool:
    return "*" in conjunto or any(any(base in a.upper() for base in conjunto) for a in universo)


def validar_semantica(doc: dict) -> dict:
    errores, avisos = [], []
    v = doc["ventanas"]
    orden = [(n, v[n]) for n in ("desarrollo", "validacion", "prueba_final") if v.get(n)]
    for n, w in orden:
        try:
            if date.fromisoformat(w[0]) > date.fromisoformat(w[1]):
                errores.append(f"ventana {n}: inicio posterior al fin")
        except ValueError:
            errores.append(f"ventana {n}: fechas no ISO")
            return {"errores": errores, "avisos": avisos}
    for (n1, w1), (n2, w2) in pairwise(orden):
        if date.fromisoformat(w1[1]) >= date.fromisoformat(w2[0]):
            errores.append(f"ventanas {n1} y {n2} se solapan o no están en orden temporal")
    if not v.get("prueba_final") and not v.get("prospectiva"):
        errores.append("no hay prueba final ni fase prospectiva: nada puede decidir")
    activos = doc["universo"]["activos"]
    conj, ini, fin, motivo = PERIODO_RESERVADO
    for n, w in orden:
        if _activos_afectados(activos, conj) and _se_solapan(w, (ini, fin)):
            errores.append(f"ventana {n} lee el {motivo} ({ini} → {fin})")
    for n in ("validacion", "prueba_final"):
        for conj, ini, fin, motivo in PERIODOS_CONTAMINADOS:
            if _activos_afectados(activos, conj) and _se_solapan(v.get(n), (ini, fin)):
                avisos.append(f"ventana {n} solapa un período ya visto ({ini} → {fin}: {motivo}): NO es evidencia "
                              "independiente; como máximo nivel 2 «contaminado» (MEC §7)")
    pro = v.get("prospectiva")
    if pro:
        if date.fromisoformat(pro["inicio"]) < date.fromisoformat(INICIO_INDEPENDIENTE):
            errores.append(f"la fase prospectiva empieza antes de {INICIO_INDEPENDIENTE}")
        miradas = [date.fromisoformat(m) for m in pro["miradas"]]
        if miradas != sorted(set(miradas)) or miradas[0] <= date.fromisoformat(pro["inicio"]):
            errores.append("miradas prospectivas: deben ser fechas estrictamente crecientes y posteriores al inicio")
        if doc["potencia"]["delta_anual"] is None:
            errores.append("fase prospectiva sin δ: n_max y la futilidad no están definidos (A8/D-S4)")
    p, m = doc["prueba"], doc["multiplicidad"]
    k = len(m["familia_confirmatoria"])
    if doc["id"] not in m["familia_confirmatoria"]:
        errores.append("la hipótesis no figura en su propia familia confirmatoria")
    if p["alfa"] > m["alfa_familia"] / k + 1e-12:
        errores.append(f"α = {p['alfa']} > α_familia/m = {m['alfa_familia']}/{k} (Bonferroni)")
    for nombre, valor in doc["reglas"]["parametros"].items():
        if isinstance(valor, (list, dict)):
            errores.append(f"parámetro «{nombre}» con varios valores: un prerregistro fija UNA configuración")
    f = doc["familia"]
    if f["reabre_familia_descartada"] and not f["aprobacion_reapertura"]:
        errores.append("reabre una familia descartada sin la aprobación explícita del propietario (D-G5)")
    e = doc["ejecucion"]
    if e["apalancamiento"] > 1 and e["margen_mantenimiento"] is None:
        errores.append("apalancamiento > 1 sin margen de mantenimiento declarado (liquidación indefinida)")
    if doc["universo"]["mercado"] == "perpetuo" and not e["funding"]:
        errores.append("mercado perpetuo sin funding en la contabilidad")
    pot = doc["potencia"]
    requerido = 2.8016 / pot["horizonte_anos"] ** 0.5
    if pot["ir_neto_plausible"] < requerido:
        texto = (f"criba de detectabilidad: IR neto plausible {pot['ir_neto_plausible']} < requerido {requerido:.2f} "
                 f"en {pot['horizonte_anos']} años: el resultado esperable es «no concluyente»")
        (avisos if pot["acepta_no_concluyente"] else errores).append(
            texto + ("" if pot["acepta_no_concluyente"] else " (y no se aceptó de antemano)"))
    r = doc["reproduccion"]
    if not r["determinista"] or not r["presentar_todas"]:
        errores.append("A14: la reproducción exige código determinista y presentar todas las reproducciones")
    return {"errores": errores, "avisos": avisos}


def huella(doc: dict) -> str:
    contenido = {k: v for k, v in doc.items() if k != "congelado"}
    canon = json.dumps(contenido, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def congelar(doc: dict, fecha_utc: str) -> dict:
    errores = validar_esquema(doc)
    if not errores:  # la semántica supone un documento con la forma del esquema
        errores = validar_semantica(doc)["errores"]
    if errores:
        raise ValueError("no se puede congelar un prerregistro con errores: " + "; ".join(errores))
    nuevo = {**doc, "estado": "CONGELADO"}
    nuevo["congelado"] = {"fecha_utc": fecha_utc, "sha256_contenido": huella(nuevo)}
    return nuevo


def verificar_congelado(doc: dict) -> bool:
    c = doc.get("congelado")
    return bool(c) and doc.get("estado") == "CONGELADO" and huella(doc) == c["sha256_contenido"]
