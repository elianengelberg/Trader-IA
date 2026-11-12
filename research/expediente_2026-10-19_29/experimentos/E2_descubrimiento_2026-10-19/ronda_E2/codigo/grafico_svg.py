"""Figura descriptiva de la ronda E2: lee los JSON congelados y escribe un SVG; usa solo la biblioteca estándar.

Uso: python -I grafico_svg.py <dir_resultados_real> <salida.svg>
No recalcula nada y no altera la clasificación.
"""
import json
import sys
from pathlib import Path

res = Path(sys.argv[1])
r = json.loads((res / "resultado_E2.json").read_text())
ic = json.loads((res / "descriptivo_ic_deltaR2.json").read_text())

filas = [(k.replace("E2-A ", "A · "), v["delta_R2_oos"], *v["ic90_bootstrap_bloques60"]) for k, v in ic.items()]
filas = [(n.replace("E2-C", "C · ATENCION (BTC h7)"), d, lo, hi) for n, d, lo, hi in filas]

W, izq, der, alto_fila, top = 940, 230, 150, 26, 60
x0, x1 = -0.36, 0.04          # escala ΔR² (recorta solo el eje; los valores se rotulan)
def X(v):
    v = max(x0, min(x1, v))
    return izq + (v - x0) / (x1 - x0) * (W - izq - der)

h1 = top + alto_fila * len(filas) + 50
B = r["E2-B"]
filasB = [("BTC", B["por_activo"]["BTC"]), ("ETH", B["por_activo"]["ETH"]), ("Conjunto", B["conjunto"])]
xb0, xb1 = -0.20, 0.15
def XB(v):
    return izq + (v - xb0) / (xb1 - xb0) * (W - izq - der)
top2 = h1 + 60
H = top2 + alto_fila * len(filasB) + 70

s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Helvetica,Arial,sans-serif" font-size="13">',
     f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
     f'<text x="20" y="28" font-size="16" font-weight="bold">E2-A y E2-C: ΔR² fuera de muestra (aumentado vs base) con IC90 descriptivo</text>',
     f'<text x="20" y="46" fill="#555">Punto = ΔR²_OOS; barra = IC90 bootstrap de bloques de 60 fechas (descriptivo, posterior, no prerregistrado). &gt; 0 = mejora.</text>']
for v in (-0.35, -0.30, -0.25, -0.20, -0.15, -0.10, -0.05, 0.0):
    s.append(f'<line x1="{X(v):.1f}" y1="{top - 6}" x2="{X(v):.1f}" y2="{top + alto_fila * len(filas)}" stroke="{"#000" if v == 0 else "#ddd"}"/>')
    s.append(f'<text x="{X(v):.1f}" y="{top + alto_fila * len(filas) + 16}" text-anchor="middle" fill="#555">{v:+.2f}</text>')
for i, (n, d, lo, hi) in enumerate(filas):
    y = top + alto_fila * i + alto_fila / 2
    col = "#1f6f3f" if d > 0 else "#a33"
    s.append(f'<text x="{izq - 10}" y="{y + 4:.1f}" text-anchor="end">{n}</text>')
    s.append(f'<line x1="{X(lo):.1f}" y1="{y:.1f}" x2="{X(hi):.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="2"/>')
    if lo < x0:
        s.append(f'<text x="{X(x0) + 2:.1f}" y="{y - 4:.1f}" font-size="10" fill="#555">◂ {lo:+.3f}</text>')
    s.append(f'<circle cx="{X(d):.1f}" cy="{y:.1f}" r="4" fill="{col}"/>')
    s.append(f'<text x="{W - der + 10}" y="{y + 4:.1f}" font-size="11" fill="#333">ΔR² {d:+.4f}</text>')

s.append(f'<text x="20" y="{h1 + 10}" font-size="16" font-weight="bold">E2-B: exceso de timing neto de costos (%/año) frente a la exposición estática, con IC90</text>')
s.append(f'<text x="20" y="{h1 + 28}" fill="#555">Bootstrap circular de bloques de 60 días (10 000 réplicas). Línea discontinua = +2 %/año (umbral de "en contra"). Rombo = costos ×2.</text>')
for v in (-0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.15):
    s.append(f'<line x1="{XB(v):.1f}" y1="{top2 - 6}" x2="{XB(v):.1f}" y2="{top2 + alto_fila * len(filasB)}" stroke="{"#000" if v == 0 else "#ddd"}"/>')
    s.append(f'<text x="{XB(v):.1f}" y="{top2 + alto_fila * len(filasB) + 16}" text-anchor="middle" fill="#555">{v * 100:+.0f}%</text>')
s.append(f'<line x1="{XB(0.02):.1f}" y1="{top2 - 6}" x2="{XB(0.02):.1f}" y2="{top2 + alto_fila * len(filasB)}" stroke="#555" stroke-dasharray="4,3"/>')
for i, (n, d) in enumerate(filasB):
    y = top2 + alto_fila * i + alto_fila / 2
    lo, hi = d["ic90"]
    e, e2 = d["exceso_anual"], d["exceso_anual_costes_x2"]
    col = "#1f6f3f" if e > 0 else "#a33"
    s.append(f'<text x="{izq - 10}" y="{y + 4:.1f}" text-anchor="end">{n}</text>')
    s.append(f'<line x1="{XB(lo):.1f}" y1="{y:.1f}" x2="{XB(hi):.1f}" y2="{y:.1f}" stroke="{col}" stroke-width="2"/>')
    s.append(f'<circle cx="{XB(e):.1f}" cy="{y:.1f}" r="4" fill="{col}"/>')
    s.append(f'<rect x="{XB(e2) - 3.5:.1f}" y="{y - 3.5:.1f}" width="7" height="7" transform="rotate(45 {XB(e2):.1f} {y:.1f})" fill="none" stroke="#333"/>')
    s.append(f'<text x="{W - der + 10}" y="{y + 4:.1f}" font-size="11" fill="#333">{e * 100:+.2f}% (×2: {e2 * 100:+.2f}%)</text>')
s.append(f'<text x="20" y="{H - 14}" font-size="11" fill="#777">Fuente: resultados/real/resultado_E2.json y descriptivo_ic_deltaR2.json (hashes en resultados/real/SHA256SUMS). Ninguna prueba pasa Holm (m = 3).</text>')
s.append("</svg>")
Path(sys.argv[2]).write_text("\n".join(s), encoding="utf-8")
print("ok", sys.argv[2])
