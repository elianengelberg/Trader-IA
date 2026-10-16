# Características operativas de la regla prerregistrada (SINTÉTICO)

**No es evidencia económica.** Cada mundo recorrió el pipeline real (formato oficial, manifiesto, calidad y evaluador). La conclusión oficial fue siempre EVIDENCIA INSUFICIENTE, por ser datos sintéticos. La tabla muestra la conclusión **en sombra**, es decir, la que daría la regla si los datos fueran históricos.

| Variante | Mundos | VENTAJA RESPALDADA | HIPÓTESIS NO RESPALDADA | EVIDENCIA INSUFICIENTE | Persistencia mediana (7 d) | CAGR test rev5 / umbral (medianas) |
|---|---|---|---|---|---|---|
| bajista_suave | 8 | 0 | 5 | 3 | +0.62 | 11.14% / 10.65% |
| bajista_suave NULO | 8 | 0 | 8 | 0 | -0.01 | 8.05% / 6.67% |
| base | 12 | 6 | 1 | 5 | +0.73 | 5.77% / 7.94% |
| base NULO | 12 | 0 | 12 | 0 | +0.00 | 5.37% / -1.25% |

P2 (carry de rev. 5), mundos normales, en sombra: {'EVIDENCIA INSUFICIENTE': 7, 'VENTAJA RESPALDADA': 12, 'HIPÓTESIS NO RESPALDADA': 1}

P2 (carry de rev. 5), mundos nulos, en sombra: {'VENTAJA RESPALDADA': 13, 'EVIDENCIA INSUFICIENTE': 6, 'HIPÓTESIS NO RESPALDADA': 1}

Huellas del código en estos resultados: ['2e35b68ff663', '4e31b92121b7']

## Comparación en test con costes base (medianas por grupo)

| Grupo | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación anual | Liquidaciones (suma) |
|---|---|---|---|---|---|---|---|---|
| bajista_suave | rev5 | 11.14% | 1.47% | 2876 | 70 | 100% | 2.2 | 0 |
| bajista_suave | umbral | 10.65% | 0.94% | 2939 | 331 | 80% | 10.2 | 0 |
| bajista_suave NULO | rev5 | 8.05% | 0.28% | 2041 | 78 | 100% | 2.4 | 0 |
| bajista_suave NULO | umbral | 6.67% | 0.83% | 2067 | 555 | 90% | 17.5 | 0 |
| base | rev5 | 5.77% | 5.65% | 1472 | 63 | 100% | 2.0 | 0 |
| base | umbral | 7.94% | 0.56% | 2162 | 282 | 75% | 8.9 | 0 |
| base NULO | rev5 | 5.37% | 0.43% | 1353 | 70 | 100% | 2.2 | 0 |
| base NULO | umbral | -1.25% | 3.89% | 781 | 969 | 69% | 34.1 | 0 |

## Sensibilidad en test: umbral − rev. 5 en PnL (mediana) y mundos con diferencia > 0

| Grupo | base | costes_x05 | costes_x2 | costes_x3 | retraso_1h | retraso_3h | pata_adversa | funding_x075 | nocional_min_perp_5 |
|---|---|---|---|---|---|---|---|---|---|
| bajista_suave | -13 (3/8) | +126 (5/8) | -267 (1/8) | -475 (1/8) | -9 (4/8) | -6 (4/8) | -427 (0/8) | -135 (3/8) | -15 (3/8) |
| bajista_suave NULO | -603 (0/8) | -392 (0/8) | -1032 (0/8) | -1516 (0/8) | -589 (0/8) | -608 (0/8) | -1296 (0/8) | -585 (0/8) | -603 (0/8) |
| base | +649 (11/12) | +759 (11/12) | +439 (8/12) | +233 (7/12) | +641 (11/12) | +646 (11/12) | +339 (8/12) | +253 (8/12) | +649 (11/12) |
| base NULO | -1257 (0/12) | -806 (0/12) | -2095 (0/12) | -2844 (0/12) | -1261 (0/12) | -1271 (0/12) | -2465 (0/12) | -1175 (0/12) | -1257 (0/12) |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test, mundos normales: {'DESCARTADA': 3, 'SIN VEREDICTO': 10, 'NO DESCARTADA': 7}

## Por mundo

| Mundo | P1 en sombra | P(dif > 0) | Diferencia de PnL en test | Estrés | Validación | Persistencia |
|---|---|---|---|---|---|---|
| base_101 | HIPÓTESIS NO RESPALDADA | 0.0225 | -211 | falla | ok | +0.73 |
| base_101_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -958 | falla | falla | +0.03 |
| base_102 | EVIDENCIA INSUFICIENTE | 0.9815 | 470 | ok | falla | +0.73 |
| base_102_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1343 | falla | falla | -0.05 |
| base_103 | VENTAJA RESPALDADA | 1.0 | 1585 | ok | ok | +0.77 |
| base_103_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1711 | falla | falla | -0.00 |
| base_104 | EVIDENCIA INSUFICIENTE | 0.641 | 109 | falla | ok | +0.78 |
| base_104_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1247 | falla | falla | -0.07 |
| base_105 | EVIDENCIA INSUFICIENTE | 0.6645 | 153 | falla | ok | +0.77 |
| base_105_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1572 | falla | falla | +0.01 |
| base_106 | VENTAJA RESPALDADA | 1.0 | 2188 | ok | ok | +0.68 |
| base_106_nulo | HIPÓTESIS NO RESPALDADA | 0.001 | -484 | falla | falla | +0.05 |
| base_107 | VENTAJA RESPALDADA | 0.98 | 735 | ok | ok | +0.61 |
| base_107_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1397 | falla | falla | +0.02 |
| base_108 | VENTAJA RESPALDADA | 0.992 | 790 | ok | ok | +0.63 |
| base_108_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -948 | falla | falla | -0.03 |
| base_109 | EVIDENCIA INSUFICIENTE | 0.731 | 262 | falla | falla | +0.62 |
| base_109_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1103 | falla | falla | -0.02 |
| base_110 | VENTAJA RESPALDADA | 0.9955 | 1367 | ok | ok | +0.74 |
| base_110_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1266 | falla | falla | +0.03 |
| base_111 | VENTAJA RESPALDADA | 0.958 | 562 | ok | ok | +0.72 |
| base_111_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1698 | falla | falla | -0.02 |
| base_112 | EVIDENCIA INSUFICIENTE | 1.0 | 1730 | ok | falla | +0.73 |
| base_112_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1048 | falla | falla | +0.02 |
| bajista_suave_201 | HIPÓTESIS NO RESPALDADA | 0.069 | -153 | falla | ok | +0.58 |
| bajista_suave_201_nulo | HIPÓTESIS NO RESPALDADA | 0.0075 | -356 | falla | falla | +0.06 |
| bajista_suave_202 | EVIDENCIA INSUFICIENTE | 0.76 | 116 | falla | falla | +0.71 |
| bajista_suave_202_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -468 | falla | falla | +0.06 |
| bajista_suave_203 | HIPÓTESIS NO RESPALDADA | 0.5105 | -2 | falla | ok | +0.60 |
| bajista_suave_203_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -999 | falla | falla | -0.02 |
| bajista_suave_204 | HIPÓTESIS NO RESPALDADA | 0.4245 | -24 | falla | falla | +0.69 |
| bajista_suave_204_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -1180 | falla | falla | -0.04 |
| bajista_suave_205 | EVIDENCIA INSUFICIENTE | 0.958 | 338 | falla | ok | +0.61 |
| bajista_suave_205_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -962 | falla | falla | +0.05 |
| bajista_suave_206 | HIPÓTESIS NO RESPALDADA | 0.102 | -176 | falla | falla | +0.65 |
| bajista_suave_206_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -739 | falla | falla | -0.06 |
| bajista_suave_207 | EVIDENCIA INSUFICIENTE | 0.9985 | 684 | falla | ok | +0.64 |
| bajista_suave_207_nulo | HIPÓTESIS NO RESPALDADA | 0.0355 | -320 | falla | falla | -0.07 |
| bajista_suave_208 | HIPÓTESIS NO RESPALDADA | 0.0635 | -242 | falla | falla | +0.59 |
| bajista_suave_208_nulo | HIPÓTESIS NO RESPALDADA | 0.0 | -372 | falla | falla | -0.00 |
