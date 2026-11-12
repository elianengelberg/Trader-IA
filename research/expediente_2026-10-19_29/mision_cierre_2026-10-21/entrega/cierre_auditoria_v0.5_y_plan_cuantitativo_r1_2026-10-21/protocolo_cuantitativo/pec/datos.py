"""Validador de velas OHLCV para la fase cuantitativa. Se aplica ANTES de calcular nada y su veredicto es una compuerta:
una serie INVÁLIDA no se evalúa (MEC v0.2 §7: categoría INVÁLIDO). No repara ni rellena nada.

Comprobaciones (cada una con su código):
- V1 campos y tipos: t (entero, ms UTC), open/high/low/close/volume numéricos y finitos.
- V2 orden: t estrictamente creciente.
- V3 duplicados: misma t con valores iguales (DUPLICADO) o distintos (CONFLICTO).
- V4 alineación: t múltiplo del intervalo.
- V5 faltantes: velas esperadas en la ventana [inicio, fin) que no están; INVÁLIDO si superan ``umbral_faltantes``.
- V6 coherencia OHLC: precios > 0, low ≤ min(open, close), high ≥ max(open, close).
- V7 volumen ≥ 0.
- V8 vela incompleta: t + intervalo > ``ahora`` (todavía abierta) o > fin de la ventana.
- V9 fuera de la ventana: filas con t < inicio o t ≥ fin (se informan; no se usan)."""
from __future__ import annotations

import math
from itertools import pairwise
from typing import Iterable

CAMPOS = ("t", "open", "high", "low", "close", "volume")


def validar(filas: Iterable[dict], intervalo_ms: int, inicio_ms: int, fin_ms: int, ahora_ms: int,
            umbral_faltantes: float = 0.005, max_listado: int = 20) -> dict:
    filas = list(filas)
    errores: dict[str, list] = {f"V{i}": [] for i in range(1, 10)}
    validas = []
    for i, f in enumerate(filas):
        if not isinstance(f, dict) or set(CAMPOS) - set(f):
            errores["V1"].append((i, "faltan campos"))
            continue
        if not isinstance(f["t"], int) or isinstance(f["t"], bool):
            errores["V1"].append((i, "t no es entero"))
            continue
        if any(not isinstance(f[k], (int, float)) or isinstance(f[k], bool) or not math.isfinite(f[k])
               for k in CAMPOS[1:]):
            errores["V1"].append((i, "valor no numérico o no finito"))
            continue
        validas.append(f)
    for a, b in pairwise(validas):
        if b["t"] < a["t"]:
            errores["V2"].append((a["t"], b["t"]))
    vistos: dict[int, dict] = {}
    for f in validas:
        if f["t"] in vistos:
            errores["V3"].append((f["t"], "DUPLICADO" if vistos[f["t"]] == f else "CONFLICTO"))
        else:
            vistos[f["t"]] = f
        if f["t"] % intervalo_ms:
            errores["V4"].append(f["t"])
        if min(f["open"], f["high"], f["low"], f["close"]) <= 0 or f["low"] > min(f["open"], f["close"]) \
                or f["high"] < max(f["open"], f["close"]):
            errores["V6"].append(f["t"])
        if f["volume"] < 0:
            errores["V7"].append(f["t"])
        if f["t"] + intervalo_ms > ahora_ms or (inicio_ms <= f["t"] < fin_ms and f["t"] + intervalo_ms > fin_ms):
            errores["V8"].append(f["t"])
        if not inicio_ms <= f["t"] < fin_ms:
            errores["V9"].append(f["t"])
    primera = -(-inicio_ms // intervalo_ms) * intervalo_ms
    esperadas = list(range(primera, fin_ms, intervalo_ms))
    presentes = set(vistos)
    faltantes = [t for t in esperadas if t not in presentes]
    errores["V5"] = faltantes
    frac = len(faltantes) / len(esperadas) if esperadas else 1.0
    motivos = []
    for codigo, texto in (("V1", "filas mal formadas"), ("V2", "orden no creciente"), ("V4", "t fuera de la grilla"),
                          ("V6", "OHLC incoherente"), ("V7", "volumen negativo"), ("V8", "vela incompleta")):
        if errores[codigo]:
            motivos.append(f"{codigo}: {texto} ({len(errores[codigo])})")
    conflictos = [e for e in errores["V3"] if e[1] == "CONFLICTO"]
    if conflictos:
        motivos.append(f"V3: conflictos ({len(conflictos)})")
    if frac > umbral_faltantes:
        motivos.append(f"V5: faltantes {len(faltantes)} de {len(esperadas)} ({frac:.4%} > {umbral_faltantes:.4%})")
    avisos = []
    if len(errores["V3"]) > len(conflictos):
        avisos.append(f"V3: duplicados idénticos ({len(errores['V3']) - len(conflictos)}); se usa una copia")
    if faltantes and frac <= umbral_faltantes:
        avisos.append(f"V5: faltantes {len(faltantes)} ({frac:.4%}), dentro del umbral; siguen las reglas de faltantes")
    if errores["V9"]:
        avisos.append(f"V9: filas fuera de la ventana ({len(errores['V9'])}); no se usan")
    return {"veredicto": "INVALIDO" if motivos else "VALIDO", "motivos": motivos, "avisos": avisos,
            "esperadas": len(esperadas), "presentes_en_ventana": sum(1 for t in presentes if inicio_ms <= t < fin_ms),
            "fraccion_faltante": frac,
            "detalle": {k: v[:max_listado] for k, v in errores.items()}}
