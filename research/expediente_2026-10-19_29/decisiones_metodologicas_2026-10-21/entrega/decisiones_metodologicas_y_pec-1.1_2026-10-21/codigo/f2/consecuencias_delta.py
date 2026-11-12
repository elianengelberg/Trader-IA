"""Fase 2: consecuencias de cada δ candidato con la aritmética de r1 (pec.potencia, pec.secuencial). Sin datos.
n_max (días) = 365,25 · R · ((z_0,975 + z_0,80) · TE / δ)², con R = inflación de 5 miradas O'Brien–Fleming.
Uso: python3 -B -I consecuencias_delta.py <r1_extraido>"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def _mod(r1: Path, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, r1 / "protocolo_cuantitativo" / "pec" / f"{nombre}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main(r1: Path) -> int:
    pot, sec = _mod(r1, "potencia"), _mod(r1, "secuencial")
    infl = sec.inflacion([0.2, 0.4, 0.6, 0.8, 1.0])["R"]
    filas = []
    for delta in (0.03, 0.05, 0.10, 0.15, 0.20):
        for te in (0.05, 0.10, 0.15, 0.20):
            anos = pot.anos_necesarios(te, delta) * infl
            n = math.ceil(365.25 * anos)
            filas.append({"delta_anual": delta, "te": te, "ir_requerido": round(delta / te, 3),
                          "anos_n_max": round(anos, 2), "n_max_dias": n,
                          "en_rango_calibrado_1096_1826": 1096 <= n <= 1826,
                          "delta_diario": delta / 365.25})
    print(json.dumps({"inflacion_R_5_miradas": infl, "filas": filas}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
