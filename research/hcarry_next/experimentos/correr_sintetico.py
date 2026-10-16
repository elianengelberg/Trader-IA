"""Ensayo del protocolo en mundos SINTÉTICOS (y sus versiones nulas con el funding barajado). No es evidencia económica:
mide el comportamiento de la maquinaria y del protocolo (qué elige, qué promueve, cuántas mejoras falsas declara).

Uso: python -B experimentos/correr_sintetico.py SEMILLA_INICIAL N_MUNDOS [VARIANTE]
     Cada mundo escribe una línea JSON en la salida estándar (redirigirla a experimentos/correr_sintetico_*.log)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "src"))

from hcarry.lab import protocolo as P


def main() -> None:
    ini = int(sys.argv[1]) if len(sys.argv) > 1 else 101
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    variante = sys.argv[3] if len(sys.argv) > 3 else "base"
    base = AQUI / "sintetico"
    for s in range(ini, ini + n):
        for nulo in (False, True):
            datos = {"fuente": "sintetico", "semilla": s, "variante": variante}
            if nulo:
                datos = P.nulo(datos, s)
            etiqueta = f"{variante}_semilla{s}" + ("_nulo" if nulo else "")
            t0 = time.time()
            out = P.ejecutar(datos, base / etiqueta, etiqueta)
            fila = {"mundo": etiqueta, "variante": variante, "nulo": nulo, "segundos": round(time.time() - t0, 1),
                    "seleccionados": out["seleccionados"],
                    "promovidos": [k for k, v in out["validacion"].items() if isinstance(v, dict) and v.get("promovido")],
                    "test": {k: {"componente": v["componente"], "base": v["base"], "cagr": v.get("cagr_neto"),
                                 "p_vs_base": v["bootstrap_vs_base"].get("p_mayor_que_cero"),
                                 "vs_ref": v["vs_referencia_rev5"], "liq": v["liquidaciones"],
                                 "dd": v["caida_maxima"]}
                             for k, v in out["test"].items() if isinstance(v, dict) and "componente" in v},
                    "test_bases": {k: out["test"][k]["cagr_neto"] for k in ("referencia", "siempre_rho05")},
                    "ref": {f: out[f]["referencia"]["cagr_neto"] for f in ("desarrollo", "validacion", "test")},
                    "ref_dd_test": out["test"]["referencia"]["caida_maxima"]}
            print(json.dumps(fila, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
