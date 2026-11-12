"""Aritmética de potencia y detectabilidad (Plan de evidencia §4; MEC v0.2 §11). Solo supuestos, nunca datos.

- años ≈ ((z_{1−α} + z_{1−β})·TE/δ)²; con α = 0,025 unilateral y potencia del 80 %, el factor es 2,8016.
- Por operación: δ_op ≈ factor·s_op/√N.
- Razón de información requerida para confirmar en H años: IR = factor/√H. Es la CRIBA de detectabilidad: una hipótesis
  cuyo IR neto plausible (por su mecanismo, antes de mirar datos) está por debajo de ese valor no puede terminar en
  «confirmada» dentro del horizonte, y se clasifica así ANTES de gastar datos.
- Con miradas repetidas (O'Brien–Fleming) el tamaño máximo se multiplica por R ≥ 1 (``secuencial.inflacion``)."""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()


def factor(alfa: float = 0.025, beta: float = 0.20) -> float:
    return _N.inv_cdf(1 - alfa) + _N.inv_cdf(1 - beta)


def anos_necesarios(te: float, delta: float, alfa: float = 0.025, beta: float = 0.20) -> float:
    """Años de datos (una sola mirada) para detectar un exceso anual δ con desvío anual del exceso TE."""
    if te <= 0 or delta <= 0:
        raise ValueError("TE y δ deben ser positivos")
    return (factor(alfa, beta) * te / delta) ** 2


def delta_minimo(te: float, anos: float, alfa: float = 0.025, beta: float = 0.20) -> float:
    return factor(alfa, beta) * te / math.sqrt(anos)


def delta_por_operacion(s_op: float, n_op: int, alfa: float = 0.025, beta: float = 0.20) -> float:
    return factor(alfa, beta) * s_op / math.sqrt(n_op)


def potencia_una_mirada(te: float, delta: float, anos: float, alfa: float = 0.025) -> float:
    return 1 - _N.cdf(_N.inv_cdf(1 - alfa) - delta * math.sqrt(anos) / te)


def ir_requerido(anos: float, alfa: float = 0.025, beta: float = 0.20) -> float:
    return factor(alfa, beta) / math.sqrt(anos)


def criba_detectabilidad(ir_neto_plausible: float, horizonte_anos: float, inflacion_secuencial: float = 1.0,
                         alfa: float = 0.025, beta: float = 0.20) -> dict:
    """DETECTABLE si el IR neto plausible alcanza para potencia 1 − β en el horizonte (con la inflación del diseño
    secuencial); si no, NO_DETECTABLE_EN_EL_HORIZONTE: el resultado esperable es «no concluyente» y no se inicia."""
    requerido = factor(alfa, beta) * math.sqrt(inflacion_secuencial) / math.sqrt(horizonte_anos)
    anos = (factor(alfa, beta) / ir_neto_plausible) ** 2 * inflacion_secuencial if ir_neto_plausible > 0 else math.inf
    return {"ir_requerido": requerido, "ir_neto_plausible": ir_neto_plausible, "anos_necesarios": anos,
            "veredicto": "DETECTABLE" if ir_neto_plausible >= requerido else "NO_DETECTABLE_EN_EL_HORIZONTE"}
