"""Fase 1: ¿los resultados de A-S1 dependen de la versión del intérprete? Recalcula una muestra estratificada de réplicas
(100 por celda, elegidas con random.Random(20261107)) con OTRO intérprete y las compara con los valores crudos de A-S1.
Python 3.12 cambió ``sum()`` de floats a suma compensada: si los resultados difieren, la reproducibilidad exacta queda
limitada al intérprete registrado (3.11.17).
Uso: python3.X -B -I otra_version_python.py <r1_extraido> <a_s1_extraido>"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def main(r1: Path, a: Path) -> int:
    ruta = r1 / "protocolo_cuantitativo" / "calibracion" / "calibracion_mec.py"
    spec = importlib.util.spec_from_file_location("calibracion_mec", ruta)
    cal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cal)
    par = json.loads(cal.PARAMETROS.read_bytes())
    rng = random.Random(20261107)
    total = iguales = decision_distinta = 0
    max_rel = 0.0
    ejemplos = []
    for pref, respaldo in (("primaria", False), ("respaldo", True)):
        for pr in par["procesos"]:
            for n in par["tamanos"]:
                crudo = json.loads((a / "salida" / "celdas" / f"{pref}_{pr}_n{n}.json").read_text())["replicas"]
                for r in sorted(rng.sample(range(par["replicas"]), 100)):
                    o = cal._replica(pr, n, r, par["semilla"], par["B"], respaldo)
                    p0, g0 = crudo[r]
                    total += 1
                    if [o["p"], o["degenerada"]] == [p0, g0]:
                        iguales += 1
                        continue
                    max_rel = max(max_rel, abs(o["p"] - p0) / p0)
                    flip = any((o["p"] <= float(al)) != (p0 <= float(al)) for al in par["bandas"])
                    decision_distinta += flip
                    if len(ejemplos) < 5:
                        ejemplos.append({"celda": f"{pref}_{pr}_n{n}", "r": r, "p_a_s1": p0, "p_ahora": o["p"]})
    print(json.dumps({"python": sys.version.split()[0], "replicas_comparadas": total, "identicas": iguales,
                      "distintas": total - iguales, "con_decision_distinta_al_2.5_o_5": decision_distinta,
                      "max_diferencia_relativa_de_p": max_rel, "ejemplos": ejemplos}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
