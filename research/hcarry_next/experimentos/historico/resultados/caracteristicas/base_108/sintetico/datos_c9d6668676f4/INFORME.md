# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `c9d6668676f46bbb…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": 789.9160378811957, "p_dif_mayor_que_cero": 0.992, "estres_ok": true, "validacion_mismo_signo": true, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.6312872924319732 · eventos negativos: 0.1015712682379349 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 10.61% | 4.35% | 3977 | 76 | 100% | 1.6 |
| desarrollo | umbral | 11.05% | 0.60% | 4312 | 279 | 89% | 5.9 |
| validacion | rev5 | 3.26% | 2.89% | 371 | 33 | 100% | 2.4 |
| validacion | umbral | 3.74% | 0.72% | 539 | 181 | 73% | 13.0 |
| test | rev5 | 2.85% | 6.22% | 739 | 60 | 100% | 2.0 |
| test | umbral | 6.05% | 0.85% | 1692 | 290 | 69% | 9.3 |

Bootstrap pareado en test (umbral − rev5): media anual 0.030563593487477073, intervalo 90 % [0.008272202997412081, 0.055300639203588436], P(> 0) = 0.992

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 2.98% | 6.67% | 914 |
| costes_x2 | 2.59% | 4.82% | 545 |
| costes_x3 | 2.33% | 3.59% | 306 |
| retraso_1h | 2.85% | 6.04% | 789 |
| retraso_3h | 2.85% | 6.05% | 790 |
| pata_adversa | 2.48% | 4.32% | 449 |
| funding_x075 | 2.08% | 3.73% | 399 |
| nocional_min_perp_5 | 2.85% | 6.05% | 790 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
