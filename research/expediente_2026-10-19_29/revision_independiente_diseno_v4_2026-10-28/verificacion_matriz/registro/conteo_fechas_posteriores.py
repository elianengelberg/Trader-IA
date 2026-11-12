"""Cuenta, sobre alcance_pasada_N5.json (original de la matriz), los eventos 2023-2024 con alguna fecha candidata POSTERIOR a E.
Solo JSON. Uso (desde el scratchpad): python -B -I conteo_fechas_posteriores.py"""
import json, datetime as dt
o = json.load(open("revision_independiente_diseno_v4_2026-10-28/metodologia/alcance_pasada_N5.json"))
d = dt.date.fromisoformat
filas = []
for f in o["filas"]:
    E = d(f["E"]); pos = [d(x) for x in f["difieren_de_E"] if d(x) > E]
    if E.year in (2023, 2024) and pos: filas.append((f["par"], f["E"], f["categoria_pasada1"], (max(pos) - E).days))
print("eventos 2023-2024 con alguna fecha candidata posterior a E:", len(filas))
for x in filas: print("  ", *x[:3], x[3], "d")
for u in (14, 28):
    print(f"con fecha posterior >= {u} días:", sum(1 for x in filas if x[3] >= u))
print("nombres con >= 28 días:", [x[0][:-4] for x in filas if x[3] >= 28])
print("con discrepancia (cualquier signo) y E en 2023-2024:", sum(1 for f in o["filas"] if f["difieren_de_E"] and d(f["E"]).year in (2023, 2024)))
