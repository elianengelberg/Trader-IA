"""Lectura operativa al congelar (rama A autorizada por el usuario el 2026-10-17): historia oficial de la señal, exposición
que la regla congelada fijaría hoy y monitor del carry. NO evalúa rendimiento (la evaluación empieza el 2026-10-18).
Script fuera de src/: no altera la huella congelada del código."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hcarry.data.binance_vision import _bajar_verificado, _escribir_manifiesto, ruta_mensual

from tendencia import papel as P
from tendencia.datos import leer
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent / "datos_papel"


def main(hasta: str) -> None:
    out: dict = {"rama": "A (autorizada por el usuario el 2026-10-17: precios del reservado solo como historia)",
                 "prerregistro_sha256": P.hash_prerregistro(), "codigo_sha256": P.huella_codigo(), "simbolos": {}}
    for s in ("BTCUSDT", "ETHUSDT"):
        man = P.descargar(RAIZ / s, s, "2026-04-20", hasta, permitir_reservado=True)
        velas, inf = leer(RAIZ / s, permitir_reservado=True, permitir_prospectivo=True)
        w = tsmom([v.c for v in velas])
        out["simbolos"][s] = {"archivos": len(man["archivos"]), "no_publicados": man["ausentes"],
                              "dias_ausentes": inf["dias_ausentes"], "apto": inf["apto"], "ultimo_cierre": velas[-1].dia,
                              "exposicion_regla_tras_ultimo_cierre": w[-1]}
    # monitor del carry: meses completos oficiales de fundingRate (jul–sep 2026)
    fdir = RAIZ / "funding_BTCUSDT"
    archivos = []
    for m in (7, 8, 9):
        rel = ruta_mensual("funding", "BTCUSDT", 2026, m)
        r = _bajar_verificado(fdir, rel, P._abrir_http, 4)
        if r:
            archivos.append({"tipo": "funding", "ruta": rel, **r})
    _escribir_manifiesto(fdir, {"procedencia": "historico_oficial", "uso": "monitor del carry (papel, rama A)",
                                "archivos": archivos})
    out["monitor_carry_a_2026_10_01"] = P.monitor_carry(fdir, "2026-10-01", rama="A")
    (AQUI / "estado_inicial.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-17")
