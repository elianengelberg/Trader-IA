# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `525db9bb2df79032…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1343.4494902283714, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.05077419202200132 · eventos negativos: 0.19163860830527496 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.15% | 0.41% | 2255 | 92 | 100% | 2.0 |
| desarrollo | umbral | 0.32% | 3.09% | 1498 | 1376 | 72% | 33.2 |
| validacion | rev5 | 7.24% | 0.35% | 817 | 35 | 100% | 2.5 |
| validacion | umbral | -0.14% | 1.74% | 542 | 532 | 73% | 39.3 |
| test | rev5 | 5.81% | 0.31% | 1460 | 49 | 100% | 1.6 |
| test | umbral | 0.27% | 2.60% | 1126 | 1037 | 73% | 35.3 |

Bootstrap pareado en test (umbral − rev5): media anual -0.05370578603580463, intervalo 90 % [-0.06615465069990344, -0.0414331091324817], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 5.95% | 2.51% | -847 |
| costes_x2 | 5.62% | -4.05% | -2277 |
| costes_x3 | 5.36% | -8.19% | -3102 |
| retraso_1h | 5.87% | 0.28% | -1357 |
| retraso_3h | 5.87% | 0.33% | -1347 |
| pata_adversa | 5.29% | -6.73% | -2776 |
| funding_x075 | 4.27% | -1.29% | -1322 |
| nocional_min_perp_5 | 5.83% | 0.27% | -1349 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': [], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
