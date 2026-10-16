"""Conciliación INDEPENDIENTE: reconstruye el equity de cada cierre solo a partir de los asientos de la cartera y de los
precios de cierre, con una contabilidad distinta (una única caja y el precio medio del corto recalculado), y
descompone el resultado en precio de las patas, funding y costes. Si no coincide con el motor, hay un error."""

from __future__ import annotations

from dataclasses import dataclass

from hcarry.conventions import HORA_MS
from hcarry.data.schema import Panel
from hcarry.model.motor import Resultado


@dataclass
class Descomposicion:
    pnl_spot: float
    pnl_perp: float
    funding: float
    costes: float
    ajustes: float

    @property
    def neto(self) -> float:
        return self.pnl_spot + self.pnl_perp + self.funding - self.costes + self.ajustes


class ErrorConciliacion(AssertionError):
    pass


def conciliar(r: Resultado, panel: Panel, tolerancia: float = 1e-6) -> Descomposicion:
    """Recorre las barras y aplica, antes de cada cierre, los asientos con marca ≤ apertura de esa barra. Compara el
    equity reconstruido con la serie del motor (tolerancia relativa al capital) y el final con ``r.final``."""
    asientos = r.asientos
    k = 0
    caja = 0.0
    q_spot = 0.0
    q_perp = 0.0
    lotes_spot = lotes_perp = 0  # posiciones en lotes enteros: el cero se comprueba sin redondeo
    paso = None
    precio_medio = 0.0
    funding = costes = ajustes = realizado_perp = flujo_spot = 0.0
    por_cierre = {s[0]: s[1] for s in r.serie}
    tol = tolerancia * r.capital
    for b in panel.barras[: r.n_barras]:
        while k < len(asientos) and asientos[k]["t"] <= b.t:
            a = asientos[k]
            k += 1
            tipo = a["tipo"]
            if tipo == "deposito":
                caja += a["importe"]
            elif tipo == "transferencia":
                pass  # movimiento interno entre cuentas: no cambia la caja total
            elif tipo == "spot":
                importe = a["cantidad"] * a["precio"]
                paso = paso or a["cantidad"] / abs(a["lotes"])
                lotes_spot += a["lotes"]
                q_spot = lotes_spot * paso
                if a["lotes"] > 0:
                    caja -= importe
                else:
                    caja += importe
                    flujo_spot += importe
                caja -= a["coste"]
                costes += a["coste"]
            elif tipo in ("perp", "liquidacion"):
                dq = a["cantidad"]
                paso = paso or dq / abs(a["lotes"])
                if a["lotes"] > 0:
                    precio_medio = (q_perp * precio_medio + dq * a["precio"]) / (q_perp + dq)
                    lotes_perp += a["lotes"]
                    q_perp = lotes_perp * paso
                else:
                    r_indep = dq * (precio_medio - a["precio"])
                    if abs(r_indep - a["realizado"]) > tol:
                        raise ErrorConciliacion(f"realizado del perp distinto en {a['t']}: {r_indep} vs {a['realizado']}")
                    caja += r_indep
                    realizado_perp += r_indep
                    lotes_perp += a["lotes"]
                    q_perp = lotes_perp * paso
                    if lotes_perp == 0:
                        precio_medio = 0.0
                caja -= a["coste"]
                costes += a["coste"]
            elif tipo == "funding":
                caja += a["importe"]
                funding += a["importe"]
            elif tipo == "nota":
                caja += a.get("ajuste", 0.0)
                ajustes += a.get("ajuste", 0.0)
            else:
                raise ErrorConciliacion(f"asiento desconocido: {tipo}")
        t_cierre = b.t + HORA_MS
        if t_cierre in por_cierre:
            E = caja + q_spot * b.S_c + q_perp * (precio_medio - b.F_c)
            if abs(E - por_cierre[t_cierre]) > tol:
                raise ErrorConciliacion(f"equity distinto al cierre {t_cierre}: {E} vs {por_cierre[t_cierre]}")
    if k != len(asientos):
        raise ErrorConciliacion("quedaron asientos sin aplicar")
    if lotes_spot or lotes_perp:
        raise ErrorConciliacion(f"posición abierta al final: {lotes_spot} lotes spot, {lotes_perp} perp")
    if abs(caja - r.final) > tol:
        raise ErrorConciliacion(f"final distinto: {caja} vs {r.final}")
    deposito = sum(a["importe"] for a in asientos if a["tipo"] == "deposito")
    # PnL de precio de la pata spot = ventas − compras (todo cerrado al final)
    compras = sum(a["cantidad"] * a["precio"] for a in asientos if a["tipo"] == "spot" and a["lotes"] > 0)
    pnl_spot = flujo_spot - compras
    d = Descomposicion(pnl_spot, realizado_perp, funding, costes, ajustes)
    if abs(deposito + d.neto - r.final) > tol:
        raise ErrorConciliacion("la descomposición no suma el resultado")
    return d
