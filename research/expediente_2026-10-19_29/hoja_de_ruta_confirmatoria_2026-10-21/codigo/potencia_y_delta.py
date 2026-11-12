"""Hoja de ruta confirmatoria: aritmética de potencia y de δ con el diseño calibrado de PEC-1.1. Sin datos de mercado.

1. Potencia de la prueba económica (5 miradas OBF, α = 0,025) por IR neto y horizonte, con la aproximación de la prueba
   z de `pec.secuencial.potencia`. SEC-1.0 midió que la regla decisiva real rinde entre 0 y 5 puntos menos en los puntos
   de diseño.
2. IR necesario y n_max por δ y TE (pec.prospectiva).
3. δ = (F/K + π)/(1 − d) para combinaciones de capital, costo fijo y deterioro.
Uso: python3 -B -I potencia_y_delta.py <protocolo_cuantitativo_PEC-1.1>"""
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from pec import prospectiva as P, secuencial as S  # noqa: E402

out = {"potencia_economica": [], "delta": [], "nota": __doc__.splitlines()[0]}
for anos in (3, 4, 5):
    n = round(365.25 * anos)
    plan = P.plan_de_miradas(min(max(n, 1096), 1826))
    for ir in (0.2, 0.35, 0.5, 0.75, 1.0, 1.27, 1.64, 2.0):
        pw = S.potencia(plan["t_k"], plan["c_k"], ir * math.sqrt(anos))
        out["potencia_economica"].append({"anos": anos, "ir_neto": ir, "potencia_prueba_z": round(pw, 3)})
for k in (10_000, 25_000, 50_000, 100_000):
    for f in (0, 250, 1000, 2600):
        for d in (0.25, 0.5):
            out["delta"].append({"K": k, "F": f, "pi": 0.025, "d": d, "delta": round((f / k + 0.025) / (1 - d), 4)})
print(json.dumps(out, ensure_ascii=False, indent=1))
