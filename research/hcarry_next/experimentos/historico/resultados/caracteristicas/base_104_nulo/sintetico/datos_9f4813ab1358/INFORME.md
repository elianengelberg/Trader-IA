# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `9f4813ab135809df…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1246.732928523943, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": false}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.0704191340378151 · eventos negativos: 0.21548821548821548 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 2.68% | 0.60% | 997 | 92 | 100% | 2.2 |
| desarrollo | umbral | -3.22% | 10.63% | 412 | 1427 | 49% | 36.9 |
| validacion | rev5 | 1.18% | 0.32% | 170 | 29 | 100% | 2.1 |
| validacion | umbral | -4.88% | 5.29% | 50 | 564 | 44% | 42.7 |
| test | rev5 | 2.41% | 0.53% | 630 | 57 | 100% | 1.9 |
| test | umbral | -2.96% | 7.90% | 302 | 947 | 46% | 33.7 |

Bootstrap pareado en test (umbral − rev5): media anual -0.053819465186498334, intervalo 90 % [-0.0656498646423624, -0.04209837705864081], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 2.53% | -0.89% | -808 |
| costes_x2 | 2.17% | -6.95% | -2059 |
| costes_x3 | 1.92% | -10.78% | -2790 |
| retraso_1h | 2.43% | -2.94% | -1246 |
| retraso_3h | 2.41% | -3.01% | -1259 |
| pata_adversa | 2.01% | -8.70% | -2386 |
| funding_x075 | 1.76% | -3.25% | -1155 |
| nocional_min_perp_5 | 2.41% | -2.96% | -1247 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
