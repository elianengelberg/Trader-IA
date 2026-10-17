# Validación HISTÓRICA — rev. 5 frente a UmbralFunding

Datos oficiales de data.binance.vision verificados por checksum.

- Prerregistro: `90642cd1c29c076243ca87e4ab3c014a7ea41fdf24d3249ff7cef56b144466bd` · código: `8a7cb0424b28fd96…` · datos: `8bdabde706bffadc…` (descarga directa)
- Calidad de datos apta: **sí** (ver `calidad.md`)

## Conclusión (criterios prerregistrados)

- **P1 · UmbralFunding frente a rev. 5: HIPÓTESIS NO RESPALDADA**
- **P2 · ventaja neta del carry de rev. 5: EVIDENCIA INSUFICIENTE**
- Motivo: criterios prerregistrados aplicados a datos históricos
- Detalles: `{"dif_pnl_test": -264.34413884471724, "p_dif_mayor_que_cero": 0.0, "estres_ok": false, "validacion_mismo_signo": false, "riesgo_ok": true}`

## Diagnóstico previo (solo desarrollo)

- Correlación de medias de 7 días consecutivos: 0.7192595076527756 · eventos negativos: 0.14568126520681265 → persistencia suficiente para que UmbralFunding pueda aportar

## Resultados por división (costes base)

| División | Política | CAGR neto | Caída máx. | Funding neto | Costes | Tiempo en mercado | Rotación |
|---|---|---|---|---|---|---|---|
| desarrollo | rev5 | 9.48% | 2.15% | 3280 | 113 | 100% | 2.5 |
| desarrollo | umbral | 7.95% | 1.77% | 2966 | 354 | 55% | 8.1 |
| validacion | rev5 | 4.04% | 1.12% | 477 | 39 | 100% | 2.8 |
| validacion | umbral | 2.80% | 1.40% | 384 | 84 | 60% | 6.1 |
| test | rev5 | 3.76% | 0.25% | 949 | 45 | 100% | 1.5 |
| test | umbral | 2.68% | 0.31% | 721 | 87 | 46% | 2.9 |

Bootstrap pareado en test (umbral − rev5): media anual -0.010530352813708881, intervalo 90 % [-0.014676782767909518, -0.006507079276056583], P(> 0) = 0.0

## Sensibilidad en test

| Escenario | rev5 CAGR | umbral CAGR | umbral − rev5 (PnL) |
|---|---|---|---|
| costes_x05 | 3.86% | 2.86% | -243 |
| costes_x2 | 3.55% | 2.30% | -302 |
| costes_x3 | 3.36% | 1.94% | -343 |
| retraso_1h | 3.77% | 2.68% | -264 |
| retraso_3h | 3.77% | 2.69% | -263 |
| pata_adversa | 3.34% | 2.38% | -231 |
| funding_x075 | 2.66% | 1.15% | -361 |
| nocional_min_perp_5 | 3.76% | 2.68% | -264 |

D1–D4 de rev. 5 (reconstrucción, regla R0) en test: {'resultado': 'DESCARTADA', 'criterios_activos': ['D1'], 'banda': None}

Evidencia prospectiva: **ninguna** (no se ha realizado ninguna prueba prospectiva).
