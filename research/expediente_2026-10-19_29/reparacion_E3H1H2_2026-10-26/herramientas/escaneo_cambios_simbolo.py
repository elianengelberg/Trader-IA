"""Escaneo de posibles cambios de símbolo sin anuncio archivado (Adenda 1, regla 3: solo se informan, no se mapean).
Solo usa episodios de actividad de `auditoria_por_simbolo.json` (derivados de `estado`); no lee precios.
Para cada listado nuevo Y que empieza en S ∈ [desde, hasta], lista los pares X cuyo episodio terminó en [S − 21, S − 1].
Uso: escaneo_cambios_simbolo.py <dir_E3> <desde> <hasta> <salida.txt>"""
import datetime as dt, json, sys
E3, desde, hasta, SAL = sys.argv[1], dt.date.fromisoformat(sys.argv[2]), dt.date.fromisoformat(sys.argv[3]), sys.argv[4]
aud = json.load(open(f"{E3}/resultados/calidad/auditoria_por_simbolo.json"))
ini, fin = [], []
for a in aud:
    for k, (e0, e1) in enumerate(a.get("episodios", [])):
        ini.append((dt.date.fromisoformat(e0), a["simbolo"], k)); fin.append((dt.date.fromisoformat(e1), a["simbolo"], k))
with open(SAL, "w") as out:
    n = 0
    for S_, y, k in sorted(ini):
        if not (desde <= S_ <= hasta):
            continue
        prev = [(L, x) for L, x, _ in fin if x != y and S_ - dt.timedelta(days=21) <= L <= S_ - dt.timedelta(days=1)]
        out.write(f"{S_} nuevo {y:<14} (episodio {k}) ← terminados en los 21 días previos: {', '.join(f'{x}@{L}' for L, x in sorted(prev)) or '—'}\n")
        n += 1
print(n)
