"""Prerregistro PEC-1.1: esquema v1.1 y semántica adicional. ``prerregistro.py`` (PEC-1.0) no cambia: un prerregistro
1.0 se sigue validando con sus propias reglas.

``construir_esquema_v11`` documenta el diff exacto frente a v1, y ``esquemas/prerregistro_v1_1.schema.json`` debe ser
igual a su salida (lo comprueba una prueba):
- ``version_protocolo`` = PEC-1.1;
- la prueba decisiva es la regla de respaldo, con ℓ = 20, B = 9999 y la regla máx;
- un bloque ``calibraciones`` obligatorio con los hashes de A-S1 y SEC-1.0;
- ``potencia.unidad_delta`` obligatoria (exceso aritmético anual neto);
- la prospectiva exige K = 5 miradas y n_max dentro del rango calibrado;
- ``criterios.regla`` = MEC-v0.2-§7 + PEC-1.1.

Semántica adicional (errores):
- la fase prospectiva exige δ;
- n_max debe ser el que da la fórmula con δ y TE: no se elige a mano;
- n_max debe estar dentro del rango calibrado; si no, se declara inalcanzable y no se congela;
- las fechas de las miradas deben ser exactamente las del calendario."""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from pec import prerregistro as v1
from pec import prospectiva as pro

RUTA_ESQUEMA = Path(__file__).resolve().parent.parent / "esquemas" / "prerregistro_v1_1.schema.json"


def construir_esquema_v11(e1: dict) -> dict:
    e = copy.deepcopy(e1)
    e["$id"] = "PEC-1.1/prerregistro_v1_1"
    e["title"] = "Prerregistro de una hipótesis cuantitativa (Protocolo de Evaluación Cuantitativa PEC-1.1)"
    e["required"] = [*e["required"], "calibraciones"]
    p = e["properties"]
    p["version_protocolo"] = {"type": "string", "enum": [pro.VERSION]}
    p["prueba"]["properties"].update({
        "metodo": {"type": "string", "enum": ["regla_respaldo_max_l20_l40_nw"]},
        "ell": {"type": "integer", "enum": [20]},
        "B": {"type": "integer", "enum": [pro.B]},
        "regla_respaldo": {"type": "string", "enum": ["max_l20_l40_nw"]},
    })
    p["calibraciones"] = {"type": "object", "additionalProperties": False, "required": sorted(pro.CALIBRACIONES),
                          "properties": {k: {"type": "string", "enum": [v]} for k, v in pro.CALIBRACIONES.items()}}
    p["potencia"]["required"] = [*p["potencia"]["required"], "unidad_delta"]
    p["potencia"]["properties"]["unidad_delta"] = {"type": "string", "enum": ["exceso_aritmetico_anual_neto"]}
    pr = p["ventanas"]["properties"]["prospectiva"]
    pr["required"] = [*pr["required"], "K"]
    pr["properties"]["K"] = {"type": "integer", "enum": [pro.K]}
    pr["properties"]["miradas"] = {"type": "array", "minItems": pro.K, "maxItems": pro.K, "items": {"type": "string"}}
    pr["properties"]["n_max_dias"] = {"type": "integer", "minimum": pro.N_MAX_CALIBRADO[0],
                                      "maximum": pro.N_MAX_CALIBRADO[1]}
    p["criterios"]["properties"]["regla"] = {"type": "string", "enum": ["MEC-v0.2-§7+PEC-1.1"]}
    return e


def esquema_v11() -> dict:
    return json.loads(RUTA_ESQUEMA.read_text(encoding="utf-8"))


def validar(doc: dict) -> dict:
    errores = v1.validar_esquema(doc, esquema_v11())
    if errores:  # la semántica supone la forma del esquema
        return {"errores": errores, "avisos": []}
    sem = v1.validar_semantica(doc)
    errores, avisos = list(sem["errores"]), list(sem["avisos"])
    pot, prosp = doc["potencia"], doc["ventanas"]["prospectiva"]
    if prosp:
        delta = pot["delta_anual"]
        if delta is not None and delta > 0:
            via = pro.viabilidad(delta, pot["te_supuesto"])
            if via["estado"] != "DENTRO_DEL_RANGO_CALIBRADO":
                errores.append(f"prospectiva {via['estado']} (n_max = {via['n_max_dias']} días): {via['nota']}")
            elif prosp["n_max_dias"] != via["n_max_dias"]:
                errores.append(f"n_max_dias = {prosp['n_max_dias']} no es el de la fórmula con δ y TE "
                               f"({via['n_max_dias']}): n_max no se elige a mano")
            else:
                esperadas = [d.isoformat() for d in pro.calendario(date.fromisoformat(prosp["inicio"]),
                                                                   prosp["n_max_dias"])]
                if prosp["miradas"] != esperadas:
                    errores.append(f"las miradas deben ser exactamente {esperadas}")
                avisos.append(via["nota"])
        elif delta is not None:
            errores.append("δ debe ser positivo")
    return {"errores": errores, "avisos": avisos}


def congelar(doc: dict, fecha_utc: str) -> dict:
    errores = validar(doc)["errores"]
    if errores:
        raise ValueError("no se puede congelar un prerregistro PEC-1.1 con errores: " + "; ".join(errores))
    nuevo = {**doc, "estado": "CONGELADO"}
    nuevo["congelado"] = {"fecha_utc": fecha_utc, "sha256_contenido": v1.huella(nuevo)}
    return nuevo


verificar_congelado = v1.verificar_congelado
