# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `b9cdf28e590f8988…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -948.3070624364718, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.03381215494537635 · eventos negativos: 0.14814814814814814 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 6.27% | 0.38% | 2286 | 80 | 100% | 1.8 |
| desarrollo | umbral | 1.75% | 1.50% | 1676 | 1079 | 78% | 26.0 |
| validacion | rev5 | 6.50% | 0.23% | 724 | 33 | 100% | 2.4 |
| validacion | umbral | 1.62% | 2.40% | 557 | 387 | 78% | 28.6 |
| test | rev5 | 6.74% | 0.44% | 1710 | 68 | 100% | 2.2 |
| test | umbral | 2.92% | 0.98% | 1392 | 701 | 79% | 23.2 |

Bootstrap pareado en test (umbral − rev5): media anual -0.036432700221354905, intervalo 90 % [-0.04542417291684207, -0.027355005176164137], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 6.91% | 4.42% | -624 |
| costes_x2 | 6.47% | -0.03% | -1581 |
| costes_x3 | 6.18% | -2.89% | -2160 |
| retraso_1h | 6.75% | 2.91% | -953 |
| retraso_3h | 6.74% | 2.90% | -953 |
| pata_adversa | 6.25% | -2.04% | -1989 |
| funding_x075 | 5.33% | 1.05% | -1041 |
| nocional_min_perp_5 | 6.74% | 2.92% | -948 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'NO DESCARTADA', 'criterios_activos': [], 'banda': 'no concluyente (6–7 %)'}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
