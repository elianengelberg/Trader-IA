# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `7ac686e1ac9caf18…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1698.367005924696, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.02289435681751107 · eventos negativos: 0.16358024691358025 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 4.82% | 0.35% | 1732 | 70 | 100% | 1.6 |
| desarrollo | umbral | 0.25% | 1.83% | 1246 | 1190 | 69% | 29.0 |
| validacion | rev5 | 5.73% | 0.40% | 663 | 44 | 100% | 3.1 |
| validacion | umbral | -0.48% | 1.24% | 444 | 481 | 67% | 35.6 |
| test | rev5 | 5.82% | 0.41% | 1491 | 79 | 100% | 2.6 |
| test | umbral | -1.25% | 4.13% | 842 | 1104 | 71% | 38.8 |

Bootstrap pareado en test (umbral − rev5): media anual -0.06911348048279728, intervalo 90 % [-0.08092245454268962, -0.057594924578281845], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 5.95% | 1.17% | -1169 |
| costes_x2 | 5.47% | -5.92% | -2648 |
| costes_x3 | 5.10% | -10.37% | -3483 |
| retraso_1h | 5.82% | -1.27% | -1705 |
| retraso_3h | 5.82% | -1.34% | -1719 |
| pata_adversa | 5.40% | -8.89% | -3256 |
| funding_x075 | 4.31% | -2.16% | -1530 |
| nocional_min_perp_5 | 5.82% | -1.25% | -1698 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
