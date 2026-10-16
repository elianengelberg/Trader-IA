"""Convenciones explícitas de H-CARRY Next. Todo el paquete las usa; ninguna se deduce en silencio.

Tiempo
  - Marcas en milisegundos UTC (int). Una barra horaria se identifica por su apertura ``t`` (múltiplo de HORA_MS) y
    cubre [t, t + HORA_MS).
  - Un evento de funding con marca T se liquida en el instante T, sobre la posición mantenida DURANTE [T − 1 h, T),
    es decir, ANTES de las operaciones ejecutadas en la apertura de la barra T (convención de rev. 5: la liquidación
    de la hora de entrada no se cobra; la de la hora de salida sí).

Unidades
  - Precios en USDT por BTC. Cantidades en BTC, guardadas internamente como un número ENTERO de lotes
    (cantidad = lotes · paso) para que no se acumulen errores de redondeo.
  - Importes monetarios en USDT (float). Costes en puntos básicos (1 bp = 1e-4) del nocional a precio de apertura.

Signos
  - La estrategia es larga en spot y corta en el perpetuo por la MISMA cantidad (delta-neutral).
  - Tasa de funding f por evento, en fracción (0.0001 = 1 bp por evento). f > 0: los largos pagan a los cortos;
    el corto COBRA q · m · f, siendo m el markPrice del evento (o la apertura del mark si falta).
  - Base = (F − S) / S. Base adversa de una operación: al abrir/ampliar (comprar spot, vender perp) es (S − F)/S;
    al reducir/cerrar (vender spot, comprar perp) es (F − S)/S. Positiva = adversa.

Capital
  - Dos cuentas: spot (efectivo U, BTC) y futuros (saldo W, corto con precio medio Fb). Equity ejecutable:
    E = U + q_spot·S + W + q_perp·(Fb − F). El margen no se suma aparte.
  - Ratio de la pata de futuros ρ = (W + q_perp·(Fb − F)) / (q_perp · F). Con ρ = 1 el corto está cubierto al 100 %
    de su nocional (estructura 1x de rev. 5); con ρ = 0,5, al 50 % (apalancamiento 2x de la pata corta).
  - Precio de liquidación del corto (margen fijo de mantenimiento mmr): P_liq = (W + q·Fb) / (q·(1 + mmr)).

Períodos
  - PERIODO_RESERVADO: 2026-06-01T00:00Z — 2026-10-13T23:59:59.999Z. Ningún cargador lo acepta (guarda en código).
  - Las divisiones de investigación (desarrollo, validación, test) están en ``hcarry.lab.splits``.
"""

from __future__ import annotations

import datetime as _dt

HORA_MS = 3_600_000
DIA_MS = 24 * HORA_MS
BP = 1e-4


def ms(texto: str) -> int:
    """'2024-02-01' o '2024-02-01T08:00' (UTC) → milisegundos."""
    t = _dt.datetime.fromisoformat(texto)
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.UTC)
    return int(t.timestamp() * 1000)


def iso(marca_ms: int) -> str:
    return _dt.datetime.fromtimestamp(marca_ms / 1000, tz=_dt.UTC).strftime("%Y-%m-%dT%H:%MZ")


RESERVADO_INICIO_MS = ms("2026-06-01")
RESERVADO_FIN_MS = ms("2026-10-14")  # exclusivo


class PeriodoReservadoError(PermissionError):
    """Se intentó cargar o usar datos del período reservado."""


def comprobar_fuera_de_reservado(desde_ms: int, hasta_ms: int) -> None:
    """[desde, hasta) no puede solaparse con el período reservado. No hay ninguna forma de desactivarlo por
    configuración: tocarlo exige cambiar este código, y ese cambio queda en la huella del código del experimento."""
    if desde_ms < RESERVADO_FIN_MS and hasta_ms > RESERVADO_INICIO_MS:
        raise PeriodoReservadoError(f"[{iso(desde_ms)}, {iso(hasta_ms)}) se solapa con el período reservado "
                                    f"[{iso(RESERVADO_INICIO_MS)}, {iso(RESERVADO_FIN_MS)})")
