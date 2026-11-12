"""PEC-1.1: regla inferencial decisiva y fase prospectiva secuencial, tal como las calibraron A-S1 y SEC-1.0.

Solo rige para prerregistros PEC-1.1. Las funciones de PEC-1.0 (``decision.py``) no cambian ni se aplican de nuevo a
nada evaluado antes.

- **Regla decisiva:** p = máx(p_ℓ20, p_ℓ40, p_NW con L = 20) de ``inferencia.respaldo``, con B = 9999 y la semilla
  congelada del prerregistro (la misma en todas las miradas). IC90 = envolvente de los tres. El bootstrap-t ℓ = 20 solo
  es DESCRIPTIVO: A-S1 no lo validó.
- **Diseño:** K = 5 miradas en n_k = round(k·n_max/5) días válidos desde el inicio, con fronteras Lan–DeMets tipo
  O'Brien–Fleming (α = 0,025). Se confirma si p_k ≤ a_k = 1 − Φ(c_k). Con B = 9999, la mirada 1 no puede confirmar.
- **Calibrado** (SEC-1.0) para n_max ∈ [1096, 1826] en los procesos C1–C6. Fuera de ese rango no hay calibración.
- **δ** se fija en exceso aritmético ANUAL. Se compara con intervalos de la media DIARIA mediante
  δ_d = δ / 365,25. PEC-1.0 no hacía esta conversión (defecto corregido aquí).
- **Ventana de cada mirada:** los PRIMEROS n_k días válidos desde el inicio (``dias_a_usar``). Si hay más, no se usan.
- **Faltantes e inválidos:** una mirada con datos inválidos, o con menos del 90 % de los n_k días previstos, se OMITE.
  No se prueba ni se reprograma, lo que es conservador. La mirada final exige datos válidos y al menos el 90 % de n_max;
  si no, el resultado es INCONCLUSO_POR_DATOS. Usar entre el 90 % y el 100 % de la información prevista es una
  aproximación declarada que SEC-1.0 no calibró.
- **Futilidad (no vinculante):** si IC90 superior < 0, EN_CONTRA; si IC90 superior < δ_d, EFECTO_RELEVANTE_DESCARTADO.
  Nunca confirma, así que no aumenta el error de tipo I.
Nada de esto es evidencia de rentabilidad: la calibración es sintética."""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from functools import lru_cache
from statistics import NormalDist
from typing import Sequence

from pec import decision, inferencia, potencia, secuencial

_N = NormalDist()
VERSION = "PEC-1.1"
B = 9999
K = 5
ALFA = 0.025
DIAS_POR_ANO = 365.25
N_MAX_CALIBRADO = (1096, 1826)
TOLERANCIA_INFORMACION = 0.10
FRACCION_MINIMA_FINAL = 0.90
CALIBRACIONES = {
    "a_s1_zip_sha256": "37af592c865dd0379d71fad2f6b52033c019e13b20920557867c6d93548f64e6",
    "sec_1_0_especificacion_sha256": "b4064e8c1f272cf9c126190a1439d35160819b5dcc8176de70b03ffa885fd1c5",
    "sec_1_0_resultado_sha256": "1de0399422bca48fdaa401051fd4aeae0ccca5181e3312f6cc21780118fb91da",
}
# Código calibrado: PEC-1.1 lo usa sin cambios (lo comprueba pruebas/test_pec_1_1.py).
CODIGO_CALIBRADO_SHA256 = {
    "pec/inferencia.py": "99d0d3e6eb4b2faaf2ad17320887dac181a3f412ee544d979cf2753302811469",
    "pec/sintetico.py": "7b15c67722ce8c95bbe14b4290bb06baf4ec8dc8f45c0101940cb9661eee7f51",
    "pec/secuencial.py": "90f3a4c2392bf8bfb247e0a5b153c3e9a1e40e5d74b394aab3db2c5cacf3cbc9",
}


def delta_diario(delta_anual: float) -> float:
    """δ anual (fracción, exceso aritmético neto) → escala de la media diaria."""
    if delta_anual is None or not delta_anual > 0:
        raise ValueError("δ debe ser un número positivo (A8/D-S4, decisión del propietario)")
    return delta_anual / DIAS_POR_ANO


# R = secuencial.inflacion([0,2; 0,4; 0,6; 0,8; 1], 0,025)["R"]; tarda ≈ 30 s, así que se fija el valor y una prueba
# comprueba que coincide con el cálculo.
INFLACION_5_MIRADAS = 1.024719881114111


def inflacion_5_miradas() -> float:
    return INFLACION_5_MIRADAS


def n_max_dias(delta_anual: float, te_anual: float) -> int:
    """n_max = ⌈365,25 · R · ((z_0,975 + z_0,80) · TE / δ)²⌉ (MEC §7.1 con la inflación de 5 miradas)."""
    return math.ceil(DIAS_POR_ANO * inflacion_5_miradas() * potencia.anos_necesarios(te_anual, delta_anual, ALFA))


def viabilidad(delta_anual: float, te_anual: float) -> dict:
    n = n_max_dias(delta_anual, te_anual)
    if n > N_MAX_CALIBRADO[1]:
        estado = "NO_ALCANZABLE_EN_EL_RANGO_CALIBRADO"
        nota = ("se declara de antemano que la confirmación prospectiva no es alcanzable en un horizonte calibrado "
                "(MEC §7.1); no se relaja α ni se cambia δ para entrar")
    elif n < N_MAX_CALIBRADO[0]:
        estado = "FUERA_DEL_RANGO_CALIBRADO_CORTO"
        nota = "n_max más corto que lo calibrado: exige una calibración nueva antes de congelar"
    else:
        estado = "DENTRO_DEL_RANGO_CALIBRADO"
        nota = "potencia real esperada ≈ 75–80 % (SEC-1.0 §4), no el 80 % de la prueba z"
    return {"n_max_dias": n, "estado": estado, "nota": nota, "ir_de_diseno": delta_anual / te_anual}


@lru_cache(maxsize=None)
def _plan(n_max: int) -> str:
    nk = [round(k * n_max / K) for k in range(1, K + 1)]
    fr = secuencial.fronteras_obf([v / n_max for v in nk], ALFA)
    return json.dumps({"n_max": n_max, "n_k": nk, "t_k": fr["t"], "c_k": fr["fronteras_z"],
                       "a_k": [1.0 - _N.cdf(c) for c in fr["fronteras_z"]]})


def plan_de_miradas(n_max: int) -> dict:
    """Tamaños, fracciones, fronteras z y umbrales en p de las 5 miradas (los mismos que usó SEC-1.0)."""
    if not N_MAX_CALIBRADO[0] <= n_max <= N_MAX_CALIBRADO[1]:
        raise ValueError(f"n_max = {n_max} fuera del rango calibrado {N_MAX_CALIBRADO} (SEC-1.0)")
    return json.loads(_plan(n_max))


def calendario(inicio: date, n_max: int) -> list[date]:
    """Fechas de las miradas: el día en que se completan n_k días desde el inicio (el mercado opera todos los días)."""
    return [inicio + timedelta(days=v) for v in plan_de_miradas(n_max)["n_k"]]


def inferencia_decisiva(x: Sequence[float], semilla: int) -> dict:
    """Regla decisiva con B = 9999. Una serie degenerada no decide."""
    try:
        r = inferencia.respaldo(x, B, semilla)
    except inferencia.ErrorSerieDegenerada:
        return {"p": 1.0, "ic90": None, "degenerada": True, "descriptivas": {}}
    return {"p": r["p_unilateral"], "ic90": r["ic90"], "degenerada": False,
            "descriptivas": {k: c["p_unilateral"] for k, c in r["componentes"].items()}}


def dias_a_usar(k: int, plan: dict, dias_validos: int) -> int:
    """La mirada k usa los primeros min(días válidos, n_k) días válidos."""
    return min(dias_validos, plan["n_k"][k - 1])


def evaluar_mirada(k: int, plan: dict, dias_validos: int, datos_validos: bool, resultado: dict | None,
                   delta_anual: float) -> dict:
    """Estado tras la mirada k (1…5). ``resultado`` es la salida de ``inferencia_decisiva`` sobre los
    ``dias_a_usar(k, plan, dias_validos)`` primeros días válidos."""
    if not 1 <= k <= K:
        raise ValueError("mirada fuera del calendario prerregistrado")
    d = delta_diario(delta_anual)
    final = k == K
    nk = plan["n_k"][k - 1]
    base = {"mirada": k, "frontera_z": plan["c_k"][k - 1], "umbral_p": plan["a_k"][k - 1], "n_k_planeado": nk,
            "dias_validos": dias_validos}
    if not datos_validos:
        return {**base, "estado": "INCONCLUSO_POR_DATOS" if final else "MIRADA_OMITIDA",
                "motivo": "datos inválidos (validador V1–V9)"}
    if final and dias_validos < FRACCION_MINIMA_FINAL * plan["n_max"]:
        return {**base, "estado": "INCONCLUSO_POR_DATOS",
                "motivo": f"información final {dias_validos} < {FRACCION_MINIMA_FINAL:.0%} de n_max"}
    if not final and dias_validos < (1 - TOLERANCIA_INFORMACION) * nk:
        return {**base, "estado": "MIRADA_OMITIDA", "motivo": "menos del 90 % de la información prevista"}
    if resultado is None or resultado["degenerada"]:
        estado = "INCONCLUSO_POR_DATOS" if final else "CONTINUAR"
        return {**base, "estado": estado, "motivo": "serie sin variabilidad: la mirada no decide"}
    if resultado["p"] <= plan["a_k"][k - 1]:
        return {**base, "estado": "CONFIRMADA_PROSPECTIVAMENTE", "p": resultado["p"]}
    sup = resultado["ic90"][1]
    if sup < 0:
        return {**base, "estado": "EN_CONTRA", "p": resultado["p"], "ic90_superior": sup}
    if sup < d:
        return {**base, "estado": "EFECTO_RELEVANTE_DESCARTADO", "p": resultado["p"], "ic90_superior": sup,
                "delta_diario": d}
    return {**base, "estado": "NO_CONCLUYENTE" if final else "CONTINUAR", "p": resultado["p"]}


def categoria_historica(valido: bool, motivos_invalidez: Sequence[str], n_operaciones: int, n_min: int,
                        resultado: dict | None, delta_anual: float | None, alfa: float = ALFA,
                        robustez: dict[str, bool] | None = None) -> dict:
    """MEC §7 con la regla decisiva de PEC-1.1 y δ convertido a la escala diaria (``decision.categoria_historica``
    sin cambios por debajo)."""
    d = delta_diario(delta_anual) if delta_anual is not None else None
    if resultado is not None and resultado["degenerada"]:
        return {"categoria": "INVALIDO", "nivel": 0, "motivos": ["serie degenerada"], "notas": []}
    p = resultado["p"] if resultado else None
    ic = resultado["ic90"] if resultado else None
    return decision.categoria_historica(valido, motivos_invalidez, n_operaciones, n_min, p, ic, alfa, d, robustez)
