"""BKRWUSDT en la 2.ª pasada. Solo JSON. Uso (desde el scratchpad): python -B -I bkrw_pasada2.py"""
import json
e = json.load(open("reparacion_E3H1H2_2026-10-26/segunda_pasada/salida_pasada2/eventos.json"))
print("$ BKRW en eventos de la segunda pasada")
for x in e:
    if x["par"] == "BKRWUSDT": print({k: (v if k not in ("urls", "url_archivada", "titulos") else "...") for k, v in x.items()})
print("categorías en pasada2:", sorted({x.get("categoria") for x in e}, key=str))
