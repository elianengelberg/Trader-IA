"""Pruebas genéricas contra la mirada al futuro (Plan de evidencia §3, B1 y B2), aplicables a CUALQUIER estrategia.

Contrato de una estrategia: ``estrategia(barras) -> objetivos`` con un objetivo por barra; ``objetivos[i]`` es la exposición
para la barra i y solo puede depender de ``barras[:i]`` (hasta el cierre de i−1).
- B1 truncamiento: los objetivos calculados con ``barras[:t]`` coinciden con los calculados con toda la serie en las
  posiciones < t.
- B2 futuro alterado: alterar ``barras[t:]`` no cambia ningún objetivo en posiciones ≤ t.
Devuelven la lista de violaciones (vacía = pasa). Detectan mirada al futuro en la LÓGICA; no prueban que los datos de
entrada no estén contaminados (eso es la procedencia, datos.py y el prerregistro)."""
from __future__ import annotations

import random
from typing import Callable, Sequence

Estrategia = Callable[[Sequence[dict]], Sequence[float]]


def truncamiento(estrategia: Estrategia, barras: Sequence[dict], cortes: int = 20, semilla: int = 1) -> list[str]:
    completo = list(estrategia(barras))
    rng = random.Random(semilla)
    violaciones = []
    for t in sorted(rng.sample(range(2, len(barras)), min(cortes, len(barras) - 2))):
        parcial = list(estrategia(barras[:t]))
        if parcial[:t] != completo[:t]:
            i = next(j for j in range(t) if parcial[j] != completo[j])
            violaciones.append(f"B1: corte t={t}: el objetivo de la barra {i} cambia ({completo[i]} → {parcial[i]})")
    return violaciones


def futuro_alterado(estrategia: Estrategia, barras: Sequence[dict], cortes: int = 20, semilla: int = 2) -> list[str]:
    """Dos alteraciones del futuro en cada corte, porque cada una deja pasar fugas distintas:
    - ``independiente``: cada barra futura con factores aleatorios distintos para apertura y cierre. Un factor común
      conservaría «cierre > apertura» y dejaría pasar a una estrategia que mira la barra actual;
    - ``nivel``: todo el futuro multiplicado por 3. Las perturbaciones alrededor de 1 casi no mueven una estadística
      global (p. ej. la media de toda la serie) y la dejarían pasar."""
    completo = list(estrategia(barras))
    rng = random.Random(semilla)
    violaciones = []
    for t in sorted(rng.sample(range(1, len(barras)), min(cortes, len(barras) - 1))):
        for modo in ("independiente", "nivel"):
            alteradas = [dict(b) for b in barras]
            for b in alteradas[t:]:
                if modo == "nivel":
                    b.update({k: b[k] * 3.0 for k in ("open", "high", "low", "close", "volume")})
                    continue
                o, c = b["open"] * rng.uniform(0.5, 1.5), b["close"] * rng.uniform(0.5, 1.5)
                b.update(open=o, close=c, high=max(o, c) * (1 + 0.1 * rng.random()),
                         low=min(o, c) * (1 - 0.1 * rng.random()), volume=b["volume"] * rng.uniform(0.5, 1.5))
            nuevo = list(estrategia(alteradas))
            if nuevo[: t + 1] != completo[: t + 1]:
                i = next(j for j in range(t + 1) if nuevo[j] != completo[j])
                violaciones.append(f"B2 ({modo}): alterar desde t={t} cambia el objetivo de la barra {i}")
    return violaciones
