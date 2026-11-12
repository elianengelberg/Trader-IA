"""Fase 1, hallazgo F1-1: dependencia entre celdas de A-S1, demostrada con el código r1 (sin réplicas nuevas de tasas).
(a) C4 réplica r usa como rendimientos la serie de C2 réplica r + 1 (mismo n), reescalada;
(b) la semilla del bootstrap es la misma (20261103 + r) en los 6 procesos y en ℓ = 20 y ℓ = 40, así que los inicios de
    bloque son idénticos entre procesos con el mismo n.
Uso: python3 -B -I dependencia_entre_celdas.py <r1_extraido>"""
import importlib.util
import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
r1 = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("sintetico", r1 / "protocolo_cuantitativo" / "pec" / "sintetico.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
SEM, n = 20261103, 366
out = {}
for r in (0, 1, 7):
    c2_siguiente = s.proceso("C2", n, SEM + r + 1)          # celda C2, réplica r + 1 (desvío 1 %)
    rend_c4 = s.proceso("C2", n, SEM + r + 1, 1.0)          # lo que usa C4 en su réplica r (desvío 1)
    cocientes = {round(a / b, 9) for a, b in zip(rend_c4, c2_siguiente, strict=True) if b != 0}
    out[f"C4_r{r}_usa_C2_r{r + 1}"] = {"cocientes_distintos": len(cocientes), "cociente": sorted(cocientes)[:1]}
k = -(-n // 20)
rng = random.Random(SEM + 0)  # lo mismo que hace bootstrap_t con semilla = 20261103 + r
ini = [[rng.randrange(n) for _ in range(k)]]
out["inicios_bootstrap_r0_iguales_en_todos_los_procesos"] = "la semilla no depende del proceso: random.Random(20261103 + r)"
out["primeros_inicios_r0_n366"] = ini[0][:5]
print(json.dumps(out, ensure_ascii=False, indent=1))
