"""Verificación independiente (código nuevo, sin reutilizar p0_*.py) de los inicios de H y del margen frente a 156 semanas.
Solo lee estructural.json (semanas evaluables) y eventos.json (fallas de la primera pasada). Sin precios ni retornos."""
import datetime as dt
import json
import sys

E3 = sys.argv[1]
sem = json.load(open(f"{E3}/resultados/estructural/estructural.json"))["semanas"]
ev = json.load(open(f"{E3}/resultados/conciliacion_pasada1/eventos.json"))
d = dt.date.fromisoformat
fin = d("2026-05-18")


def lunes_siguiente(x):
    return x + dt.timedelta(days=(7 - x.weekday()) % 7 or 7)


def ventana(inicio):
    w = [s for s in sem if inicio <= d(s["lunes"]) <= fin]
    ev_ = sum(1 for s in w if s["evaluable"])
    return len(w), ev_, round(100 * (len(w) - ev_) / len(w), 1)


fallas = sorted((d(e["E"]), e["par"], e["categoria"]) for e in ev if e["categoria"] in ("T", "D", "C_no_explicada"))
print("fallas de la primera pasada:", [(str(a), b, c) for a, b, c in fallas])
i = d(json.load(open(f"{E3}/resultados/estructural/estructural.json"))["inicio_componente_i_13_semanas_evaluables"])
casos = {
    "v3 congelada, primera pasada (C sin resolver)": max(f[0] for f in fallas),
    "v3 congelada, C explicados por A3.5 (= regla de A)": max(f[0] for f in fallas if f[2] != "C_no_explicada"),
    "R1′ (sin apalancados; BKRW en alcance) (= regla de B)": max(f[0] for f in fallas if f[2] != "C_no_explicada" and not any(f[1][:-4].endswith(x) for x in ("UP", "DOWN", "BULL", "BEAR"))),
}
for nombre, ult in casos.items():
    ini = max(i, lunes_siguiente(ult))
    n, ne, pct = ventana(ini)
    print(f"{nombre}: última falla {ult} → inicio {ini} · semanas {n} · evaluables {ne} · no evaluables {pct} %")
# margen de A: la falla más tardía que A tolera (≥156 evaluables)
iniA = max(i, lunes_siguiente(d("2023-04-27")))
lunes_A = [d(s["lunes"]) for s in sem if iniA <= d(s["lunes"]) <= fin and s["evaluable"]]
ultimo = lunes_A[len(lunes_A) - 156]
print("A: semanas evaluables", len(lunes_A), "· último inicio con ≥ 156 evaluables:", ultimo,
      "· una falla en alcance con E ≥", ultimo, "mueve el inicio más allá y deja A INVÁLIDO")
