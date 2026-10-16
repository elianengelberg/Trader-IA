"""Validación de datos de mercado. Porta la semántica del catálogo de incidencias de rev. 5 (reimplementado; el código
original se perdió):

  A2   funding: hueco, intervalo no admitido, desalineado o cobertura incompleta (principio/final)
  A2b  funding: el intervalo se ALARGA (indistinguible de omisiones)
  A4   marca, unidad o tasa implausible (|tasa| máx > 5 %, mediana > 0,1 %)
  A6   barra incoherente (OHLC fuera de rango, precio no positivo)
  A7   desorden o duplicados
  A8   liquidación de funding a más de 60 s de una hora
  P2   series incoherentes entre sí (perp o mark a más del 5 % del spot)
  H1   barra rellenada por falta de datos (informativo: el motor no decide en esas horas)

Política estricta (rev. 5): nada se rellena en el funding y no se supone ninguna dirección del sesgo de las omisiones
indetectables (un calendario más corto del real que se publica más espaciado). Ver ADENDA rev. 5 §A."""

from __future__ import annotations

import itertools
import statistics
from dataclasses import dataclass, field

from hcarry.conventions import HORA_MS, iso
from hcarry.data.schema import Barra, EventoFunding

INTERVALOS_ADMITIDOS_H = (1, 2, 4, 8)
TOLERANCIA_MS = 60_000
TASA_ABS_MAX = 0.05
MEDIANA_ABS_MAX = 0.001
COHERENCIA_MAX = 0.05


@dataclass(frozen=True)
class Incidencia:
    clase: str
    detalle: str
    t: int | None = None

    def __str__(self) -> str:
        return f"{self.clase}: {self.detalle}" + (f" ({iso(self.t)})" if self.t is not None else "")


@dataclass
class Informe:
    incidencias: list[Incidencia] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def add(self, clase: str, detalle: str, t: int | None = None) -> None:
        self.incidencias.append(Incidencia(clase, detalle, t))

    def clases(self, excluir: tuple[str, ...] = ("H1",)) -> set[str]:
        return {i.clase for i in self.incidencias if i.clase not in excluir}

    @property
    def bloqueante(self) -> bool:
        return bool(self.clases())


def alinear_funding(crudos: list[tuple[int, float, float | None]], inf: Informe) -> list[EventoFunding]:
    """(marca_ms, tasa, mark) tal como llegan → eventos alineados a la hora (A8 si el desfase supera 60 s)."""
    eventos = []
    for t, tasa, mark in crudos:
        h = round(t / HORA_MS) * HORA_MS
        if abs(t - h) > TOLERANCIA_MS:
            inf.add("A8", f"liquidación a {abs(t - h) / 1000:.0f} s de la hora", t)
            continue
        eventos.append(EventoFunding(h, tasa, mark))
    return eventos


def validar_funding(eventos: list[EventoFunding], ini: int, fin: int, inf: Informe | None = None) -> Informe:
    inf = inf or Informe()
    marcas = [e.t for e in eventos]
    if marcas != sorted(marcas) or len(set(marcas)) != len(marcas):
        inf.add("A7", "liquidaciones desordenadas o repetidas")
        return inf
    info = {"liquidaciones": len(eventos), "intervalos_h": {}, "cambios": []}
    inf.info["funding"] = info
    if len(eventos) < 2:
        inf.add("A2", "menos de dos liquidaciones")
        return inf
    tasas = [abs(e.tasa) for e in eventos]
    if max(tasas) > TASA_ABS_MAX:
        inf.add("A4", "|tasa| máxima > 5 % por liquidación")
    if statistics.median(tasas) > MEDIANA_ABS_MAX:
        inf.add("A4", "mediana de |tasa| > 0,1 %: ¿porcentaje en lugar de fracción?")
    cuentas: dict[float, int] = {}
    for e in eventos:
        cuentas[e.tasa] = cuentas.get(e.tasa, 0) + 1
    modal = min(cuentas, key=lambda v: (-cuentas[v], v))
    info["tasa_modal"] = {"tasa": modal, "fraccion": cuentas[modal] / len(eventos)}
    anterior = None
    for k in range(1, len(marcas)):
        d = marcas[k] - marcas[k - 1]
        horas = d // HORA_MS
        if horas not in INTERVALOS_ADMITIDOS_H:
            inf.add("A2", f"hueco o intervalo no admitido de {d / HORA_MS:g} h", marcas[k])
            anterior = None
            continue
        if marcas[k] % d or (k == 1 and marcas[0] % d):
            inf.add("A2", f"liquidación no alineada con su intervalo de {horas} h", marcas[k])
        info["intervalos_h"][str(horas)] = info["intervalos_h"].get(str(horas), 0) + 1
        if anterior is not None and horas != anterior:
            info["cambios"].append({"t": marcas[k], "de_h": anterior, "a_h": horas})
            if horas > anterior:
                inf.add("A2b", f"el intervalo pasa de {anterior} h a {horas} h: cambio de calendario u omisiones, "
                               "indistinguibles", marcas[k])
        anterior = horas
    if marcas[0] - ini >= marcas[1] - marcas[0]:
        inf.add("A2", "faltan liquidaciones al principio de la ventana", marcas[0])
    if fin - marcas[-1] > marcas[-1] - marcas[-2]:
        inf.add("A2", "faltan liquidaciones al final de la ventana", marcas[-1])
    return inf


def validar_barras(barras: list[Barra], inf: Informe | None = None) -> Informe:
    inf = inf or Informe()
    for a, b in itertools.pairwise(barras):
        if b.t <= a.t:
            inf.add("A7", "barras desordenadas o repetidas", b.t)
    malas = 0
    for b in barras:
        for o, h, l, c in ((b.S_o, b.S_h, b.S_l, b.S_c), (b.F_o, b.F_h, b.F_l, b.F_c), (b.M_o, b.M_h, b.M_l, b.M_c)):
            if min(o, h, l, c) <= 0 or l > min(o, c) + 1e-9 or h < max(o, c) - 1e-9:
                inf.add("A6", "OHLC incoherente o precio no positivo", b.t)
                break
        if abs(b.F_c / b.S_c - 1) > COHERENCIA_MAX or abs(b.M_c / b.S_c - 1) > COHERENCIA_MAX:
            malas += 1
            if malas == 1:
                inf.add("P2", f"perp o mark a más del {COHERENCIA_MAX:.0%} del spot", b.t)
    return inf
