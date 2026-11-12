"""Registro del programa de hipótesis: impide iniciar por descuido una hipótesis cerrada, descartada o no aprobada, y
cuenta la multiplicidad a nivel programa (todas las hipótesis ya intentadas pesan al leer un resultado nuevo)."""
from __future__ import annotations

import json
from pathlib import Path

REGISTRO = Path(__file__).resolve().parent.parent / "registro_programa" / "HIPOTESIS_PROGRAMA.json"
NO_INICIABLES = {"CERRADA", "DESCARTADA", "PROPUESTA_NO_APROBADA", "ORIGINAL_NO_RECUPERADO"}


def cargar(ruta: Path = REGISTRO) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def puede_iniciar(id_: str, aprobaciones: dict[str, str] | None = None, registro: dict | None = None) -> dict:
    """Una hipótesis nueva (fuera del registro) puede iniciarse con su prerregistro. Una del registro solo si su estado
    lo permite o si hay una aprobación explícita registrada para ella (D-G1 / D-G5)."""
    registro = registro or cargar()
    aprobaciones = aprobaciones or {}
    fila = next((h for h in registro["hipotesis"] if h["id"] == id_), None)
    if fila is None:
        return {"puede": True, "motivo": "hipótesis nueva: requiere su prerregistro PEC-1.0 y entra en la multiplicidad"}
    if fila["estado"] in NO_INICIABLES:
        if id_ in aprobaciones:
            return {"puede": True, "motivo": f"{fila['estado']} con aprobación registrada: {aprobaciones[id_]}"}
        return {"puede": False, "motivo": f"{fila['estado']}: {fila.get('reapertura') or 'sin vía de reapertura'}"}
    return {"puede": True, "motivo": fila["estado"]}


def multiplicidad_programa(registro: dict | None = None) -> dict:
    registro = registro or cargar()
    probadas = [h for h in registro["hipotesis"] if h["resultado"] is not None]
    return {"intentadas_con_resultado": len(probadas), "registradas": len(registro["hipotesis"]),
            "respaldadas": registro["respaldadas"]}
