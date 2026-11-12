"""Criba de detectabilidad de las candidatas pendientes y tabla de δ (05_PLAN_CUANTITATIVO.md §5–§6). Solo aritmética
sobre los supuestos declarados en los documentos del proyecto; no usa ningún dato de precios.

Fuentes de los supuestos (PLAN_DE_EVIDENCIA_SUFFICIENTE.md §4.4 y §4.3; MATRIZ D-RS-6, D-EV-9; DICTAMEN §1):
- H-REV-SHOCK v0.2: desvío por operación s_op ≈ 12,6 %; N_min = 30 en la ventana E de 4,42 años (≈ 6,8 eventos por año)
  y un escenario optimista de 20 por año.
- H-EMA9-VWAP v0.2: s_op ≈ 1,7 %; N ≈ 300 en E (≈ 68 operaciones por año); costo ≈ 30 pb por operación.
- T: exceso fuera de muestra +7,05 %/año, TE ≈ 20,2 %/año (IR ≈ 0,35).
Uso: python3 -I criba_candidatas.py <carpeta protocolo_cuantitativo>"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from pec import potencia as P  # noqa: E402
from pec import secuencial as S  # noqa: E402

R5 = S.inflacion([0.2, 0.4, 0.6, 0.8, 1.0])["R"]
print(f"Inflación O'Brien–Fleming con 5 miradas equiespaciadas: R = {R5:.4f}\n")
print("== IR neto requerido para confirmar (α = 0,025 unilateral, potencia 80 %, 5 miradas OBF)")
for h in (1, 2, 3, 5, 10):
    print(f"  {h:>2} años: IR ≥ {P.ir_requerido(h) * math.sqrt(R5):.2f}")
print(f"  T (referencia): IR ≈ {0.0705 / 0.202:.2f} → {P.anos_necesarios(0.202, 0.0705) * R5:.0f} años\n")

print("== Ventaja neta mínima por operación para confirmar en H años: μ_op ≥ factor·√R·s_op/√(m·H)")
casos = [("H-REV-SHOCK v0.2 (escenario base)", 0.126, 30 / 4.42, 0.0),
         ("H-REV-SHOCK v0.2 (escenario optimista)", 0.126, 20.0, 0.0),
         ("H-EMA9-VWAP v0.2", 0.017, 300 / 4.42, 0.0030)]
for nombre, s_op, m, costo in casos:
    print(f"  {nombre}: s_op = {s_op:.1%}, {m:.1f} operaciones/año, costo {costo:.2%}/operación")
    for h in (3, 5, 10):
        neta = P.factor() * math.sqrt(R5) * s_op / math.sqrt(m * h)
        print(f"    H = {h:>2} años: neta ≥ {neta:.2%} por operación; bruta ≥ {neta + costo:.2%}; "
              f"señal/ruido por operación ≥ {neta / s_op:.2f}")

print("\n== Años de datos (una sola mirada) por δ y TE; con 5 miradas OBF multiplicar por R")
tes = (0.10, 0.15, 0.20, 0.30)
print("  δ \\ TE  " + "  ".join(f"{t:>6.0%}" for t in tes))
for d in (0.03, 0.05, 0.07, 0.10, 0.15, 0.20):
    print(f"  {d:>6.0%}  " + "  ".join(f"{P.anos_necesarios(t, d):>6.1f}" for t in tes))
