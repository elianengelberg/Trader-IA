# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `8581de52bc1565bc…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1571.7042463292328, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.014295607418209087 · eventos negativos: 0.17592592592592593 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 4.22% | 0.40% | 1487 | 52 | 100% | 1.2 |
| desarrollo | umbral | -0.64% | 3.22% | 1033 | 1257 | 64% | 31.4 |
| validacion | rev5 | 4.57% | 0.28% | 540 | 40 | 100% | 2.9 |
| validacion | umbral | -2.14% | 2.50% | 301 | 521 | 62% | 38.8 |
| test | rev5 | 4.93% | 0.46% | 1246 | 64 | 100% | 2.1 |
| test | umbral | -1.66% | 4.75% | 700 | 1109 | 66% | 39.0 |

Bootstrap pareado en test (umbral − rev5): media anual -0.06491683959412019, intervalo 90 % [-0.07671060113574103, -0.05324716264620662], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 5.07% | 0.76% | -1044 |
| costes_x2 | 4.66% | -6.34% | -2537 |
| costes_x3 | 4.39% | -10.80% | -3391 |
| retraso_1h | 4.93% | -1.62% | -1560 |
| retraso_3h | 4.93% | -1.71% | -1581 |
| pata_adversa | 4.60% | -7.80% | -2831 |
| funding_x075 | 3.59% | -2.19% | -1361 |
| nocional_min_perp_5 | 4.93% | -1.66% | -1572 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
