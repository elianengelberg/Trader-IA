"""Contabilidad del MEC v0.2 §2 para una manga long/flat, más funding y margen aislado para perpetuos.

Convenciones (las del MEC):
- ``objetivo[t]`` ∈ {0, 1} es la exposición deseada para la barra t, decidida con información hasta el CIERRE de t−1;
  se ejecuta en la APERTURA de t. La estrategia es responsable de no mirar el futuro (ver ``mirada_futuro.py``).
- Compra con todo el efectivo W: precio O·(1+s); unidades q = W / (O·(1+s)·(1+f)). Venta: q·O·(1−s)·(1−f).
- W_t = efectivo + q·C_t al cierre; R_t = W_t/W_{t−1} − 1 (simple). w_t = q·C_{t−1}/W_{t−1} (tras ejecutar en la apertura).
- ε = media de w_t; benchmark B_t = ε·r_t con r_t = C_t/C_{t−1} − 1; exceso x_t = R_t − B_t.
- Fin de la ventana: la posición abierta se liquida al último cierre con costos de salida (la última barra lo refleja).
Las barras faltantes se tratan ANTES (datos.py): aquí la serie debe ser contigua y válida."""
from __future__ import annotations

from typing import Sequence


def simular_manga(aperturas: Sequence[float], cierres: Sequence[float], objetivo: Sequence[int],
                  comision: float = 0.0010, slippage: float = 0.0005, capital: float = 1.0) -> dict:
    n = len(cierres)
    if not (len(aperturas) == n == len(objetivo)) or n < 2:
        raise ValueError("aperturas, cierres y objetivo deben tener la misma longitud (≥ 2)")
    if any(o not in (0, 1) for o in objetivo):
        raise ValueError("objetivo debe ser 0 o 1 (long/flat)")
    if objetivo[0] != 0:
        raise ValueError("la primera barra no tiene información previa: objetivo[0] debe ser 0")
    f, s = comision, slippage
    efectivo, q = capital, 0.0
    w_prev = capital
    valores, rend, expos, bench_r = [capital], [], [], []
    operaciones: list[dict] = []
    abierta: dict | None = None
    for t in range(1, n):
        o, c, c_prev = aperturas[t], cierres[t], cierres[t - 1]
        if objetivo[t] == 1 and q == 0.0:
            q = efectivo / (o * (1 + s) * (1 + f))
            abierta = {"entrada_barra": t, "costo": efectivo}
            efectivo = 0.0
        elif objetivo[t] == 0 and q > 0.0:
            efectivo = q * o * (1 - s) * (1 - f)
            operaciones.append({**abierta, "salida_barra": t, "cobro": efectivo, "pnl": efectivo - abierta["costo"]})
            q, abierta = 0.0, None
        expos.append(q * c_prev / w_prev)
        if t == n - 1 and q > 0.0:  # liquidación al último cierre válido de la ventana, con costos de salida
            efectivo = q * c * (1 - s) * (1 - f)
            operaciones.append({**abierta, "salida_barra": t, "cobro": efectivo, "pnl": efectivo - abierta["costo"],
                                "liquidada_al_fin_de_ventana": True})
            q, abierta = 0.0, None
        w = efectivo + q * c
        rend.append(w / w_prev - 1.0)
        bench_r.append(c / c_prev - 1.0)
        valores.append(w)
        w_prev = w
    eps = sum(expos) / len(expos)
    bench = [eps * r for r in bench_r]
    exceso = [a - b for a, b in zip(rend, bench, strict=True)]
    return {"valores": valores, "rendimientos": rend, "exposicion": expos, "epsilon": eps, "r_activo": bench_r,
            "benchmark": bench, "exceso": exceso, "operaciones": operaciones,
            "costos": {"comision": f, "slippage": s}}


def funding(unidades: float, precio_marca: float, tasa: float) -> float:
    """Pago de funding para el tenedor: unidades > 0 (largo) PAGA si la tasa es positiva; un corto la cobra."""
    return -unidades * precio_marca * tasa


def precio_liquidacion_aislado(entrada: float, apalancamiento: float, margen_mantenimiento: float, lado: int) -> float:
    """Aproximación de margen aislado lineal (sin comisiones de cierre ni funding acumulado):
    largo P = entrada·(1 − 1/L + mm); corto P = entrada·(1 + 1/L − mm)."""
    if apalancamiento < 1 or not 0 <= margen_mantenimiento < 1 / apalancamiento or lado not in (1, -1):
        raise ValueError("parámetros de margen inválidos")
    return entrada * (1 - lado / apalancamiento + lado * margen_mantenimiento)


def simular_apalancada(entrada: float, maximos: Sequence[float], minimos: Sequence[float], cierres: Sequence[float],
                       apalancamiento: float, margen_mantenimiento: float, lado: int, comision: float = 0.0005) -> dict:
    """Posición aislada abierta a ``entrada``. La liquidación se evalúa con el EXTREMO ADVERSO de cada barra (mínimo
    para un largo, máximo para un corto): es conservador. Si se liquida, se pierde todo el margen; el capital nunca es
    negativo. Devuelve el resultado relativo al margen."""
    liq = precio_liquidacion_aislado(entrada, apalancamiento, margen_mantenimiento, lado)
    for t, (hi, lo) in enumerate(zip(maximos, minimos, strict=True)):
        adverso = lo if lado == 1 else hi
        if (lado == 1 and adverso <= liq) or (lado == -1 and adverso >= liq):
            return {"liquidada": True, "barra": t, "precio_liquidacion": liq, "resultado_sobre_margen": -1.0}
    salida = cierres[-1]
    bruto = lado * (salida / entrada - 1.0) * apalancamiento
    costos = comision * apalancamiento * (1 + salida / entrada)
    return {"liquidada": False, "barra": None, "precio_liquidacion": liq,
            "resultado_sobre_margen": max(bruto - costos, -1.0)}
