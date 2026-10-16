"""Divisiones temporales de la investigación, fijadas ANTES de ver datos reales.

  desarrollo  2019-10-01 — 2023-01-01   elegir parámetros (incluye la caída de 2020, el auge de 2021 y 2022)
  validacion  2023-01-01 — 2024-02-01   confirmar la elección; si falla, no se promueve a test
  test        2024-02-01 — 2026-06-01   = ventana pre-registrada de rev. 5; se usa UNA vez por configuración
                                        prerregistrada
  (reservado  2026-06-01 — 2026-10-14   inaccesible por código: hcarry.conventions)

El test exige que la configuración (su hash) esté en un archivo de prerregistro escrito antes; el laboratorio anota
cada uso del test en el registro y rechaza repetirlo para la misma configuración y los mismos datos."""

from __future__ import annotations

from hcarry.conventions import comprobar_fuera_de_reservado, ms

DIVISIONES: dict[str, tuple[str, str]] = {
    "desarrollo": ("2019-10-01", "2023-01-01"),
    "validacion": ("2023-01-01", "2024-02-01"),
    "test": ("2024-02-01", "2026-06-01"),
}
for _a, _b in DIVISIONES.values():
    comprobar_fuera_de_reservado(ms(_a), ms(_b))


def rango(division: str) -> tuple[int, int]:
    a, b = DIVISIONES[division]
    return ms(a), ms(b)
