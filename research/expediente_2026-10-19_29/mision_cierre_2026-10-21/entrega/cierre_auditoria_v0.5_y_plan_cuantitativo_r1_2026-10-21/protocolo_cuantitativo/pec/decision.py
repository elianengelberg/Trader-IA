"""Regla de decisión del MEC v0.2 §7 (evaluación histórica única) y §7.1 (prospectiva secuencial). Se aplica a los
resultados de la prueba primaria; nunca a métricas descriptivas.

Categorías históricas (se informa una sola, con esta precedencia):
  INVALIDO > INCONCLUSO_POR_DATOS > RESPALDADA > EN_CONTRA > EFECTO_RELEVANTE_DESCARTADO > INSUFICIENTE
- RESPALDADA: p ≤ α (nivel 2). La robustez (nivel 3) se informa aparte y no cambia la categoría.
- EN_CONTRA: extremo superior del IC90 < 0.
- EFECTO_RELEVANTE_DESCARTADO: extremo superior del IC90 < δ. **Sin δ fijado esta categoría no existe**: el resultado cae
  en INSUFICIENTE y se informa que δ falta (decisión A8 / D-S4 del propietario).
- «No respaldada» = INSUFICIENTE (ausencia de evidencia), EN_CONTRA o EFECTO_RELEVANTE_DESCARTADO (evidencia de ausencia).
Ninguna categoría autoriza nada: la autorización es otro estado (P2)."""
from __future__ import annotations

from typing import Sequence


def categoria_historica(valido: bool, motivos_invalidez: Sequence[str], n_operaciones: int, n_min: int,
                        p: float | None, ic90: tuple[float, float] | None, alfa: float = 0.025,
                        delta: float | None = None, robustez: dict[str, bool] | None = None) -> dict:
    if not 0 < alfa <= 0.05:
        raise ValueError("α fuera de (0, 0,05]")
    notas = []
    if delta is None:
        notas.append("δ no fijado (A8/D-S4): EFECTO_RELEVANTE_DESCARTADO no está disponible")
    if not valido:
        return {"categoria": "INVALIDO", "nivel": 0, "motivos": list(motivos_invalidez), "notas": notas}
    if n_operaciones < n_min:
        return {"categoria": "INCONCLUSO_POR_DATOS", "nivel": 0,
                "motivos": [f"{n_operaciones} operaciones < N_min = {n_min}"], "notas": notas}
    if p is None or ic90 is None:
        raise ValueError("una serie válida necesita p e IC90")
    if p <= alfa:
        rob = None
        if robustez is not None:
            rob = "ROBUSTA" if robustez and all(robustez.values()) else "NO_ROBUSTA"
        return {"categoria": "RESPALDADA", "nivel": 3 if rob == "ROBUSTA" else 2,
                "motivos": [f"p = {p:.6f} ≤ α = {alfa}"], "robustez": rob, "robustez_detalle": robustez,
                "notas": notas + ["histórico contaminado: solo la fase prospectiva confirma (nivel 4)"]}
    if ic90[1] < 0:
        return {"categoria": "EN_CONTRA", "nivel": 1, "motivos": [f"IC90 superior {ic90[1]:.6g} < 0"], "notas": notas}
    if delta is not None and ic90[1] < delta:
        return {"categoria": "EFECTO_RELEVANTE_DESCARTADO", "nivel": 1,
                "motivos": [f"IC90 superior {ic90[1]:.6g} < δ = {delta}"], "notas": notas}
    return {"categoria": "INSUFICIENTE", "nivel": 1, "motivos": [f"p = {p:.6f} > α = {alfa}"], "notas": notas}


def mirada_prospectiva(k: int, fronteras_z: Sequence[float], z: float, ic90_superior: float,
                       delta: float | None) -> dict:
    """Mirada k (1-based) de la prueba secuencial: CONFIRMADA si z ≥ c_k; EFECTO_RELEVANTE_DESCARTADO (futilidad no
    vinculante) si el IC90 superior < δ; NO_CONCLUYENTE en la última mirada; si no, CONTINUAR."""
    if not 1 <= k <= len(fronteras_z):
        raise ValueError("mirada fuera del calendario prerregistrado")
    if delta is None:
        raise ValueError("la fase prospectiva exige δ fijado ANTES de empezar (A8/D-S4)")
    if z >= fronteras_z[k - 1]:
        return {"estado": "CONFIRMADA_PROSPECTIVAMENTE", "mirada": k, "frontera": fronteras_z[k - 1]}
    if ic90_superior < delta:
        return {"estado": "EFECTO_RELEVANTE_DESCARTADO", "mirada": k, "frontera": fronteras_z[k - 1]}
    if k == len(fronteras_z):
        return {"estado": "NO_CONCLUYENTE", "mirada": k, "frontera": fronteras_z[k - 1]}
    return {"estado": "CONTINUAR", "mirada": k, "frontera": fronteras_z[k - 1]}
