# Ensayo SINTÉTICO del pipeline histórico — rev. 5 frente a UmbralFunding

> **SINTÉTICO.** Datos fabricados en formato oficial para ensayar el pipeline. **No es evidencia económica** y no puede citarse como resultado histórico.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `2e35b68ff663b936…` · datos: `054fb0388a0e64b9…` (fabricado en formato oficial para ensayar el pipeline)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: EVIDENCIA INSUFICIENTE**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: datos SINTÉTICOS: por definición no aportan evidencia económica (ensayo del pipeline)
- Detalles: `{"dif_pnl_test": -1710.702910395903, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": false}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: -0.0046634753655294655 · eventos negativos: 0.27441077441077444 → UmbralFunding no debería aportar (correlación < 0,2)

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 2.39% | 0.86% | 919 | 110 | 100% | 2.6 |
| desarrollo | umbral | -4.54% | 14.05% | 359 | 1719 | 46% | 45.4 |
| validacion | rev5 | 2.57% | 0.64% | 329 | 52 | 100% | 3.8 |
| validacion | umbral | -4.17% | 4.52% | 131 | 594 | 51% | 44.8 |
| test | rev5 | 3.23% | 0.70% | 835 | 56 | 100% | 1.9 |
| test | umbral | -4.15% | 9.55% | 302 | 1245 | 53% | 44.9 |

Bootstrap pareado en test (umbral − rev5): media anual -0.07418550804414883, intervalo 90 % [-0.08705350204942217, -0.06146015972766952], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 3.35% | -1.41% | -1123 |
| costes_x2 | 2.99% | -9.37% | -2762 |
| costes_x3 | 2.75% | -14.33% | -3680 |
| retraso_1h | 3.24% | -4.14% | -1711 |
| retraso_3h | 3.26% | -4.27% | -1745 |
| pata_adversa | 2.60% | -13.75% | -3533 |
| funding_x075 | 2.33% | -4.08% | -1477 |
| nocional_min_perp_5 | 3.23% | -4.15% | -1711 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'SIN VEREDICTO', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
